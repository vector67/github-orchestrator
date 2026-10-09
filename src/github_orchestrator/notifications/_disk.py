import hashlib
import itertools
import json
import logging
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from github_orchestrator.agent_runs import Summaries
from github_orchestrator.desktop import Badge, Desktop
from github_orchestrator.domain import LocalClock, Pr
from github_orchestrator.notifications._batches import (
    GIST_CHARS,
    SUMMARY_ASKED_CHARS,
    SUMMARY_WAIT,
    WINDOW,
    comments,
    decoded,
    encoded,
    fixes,
    group_of,
    named,
    naming,
    rendered,
)
from github_orchestrator.notifications._facts import (
    CommentArrived,
    FixReady,
    Gathered,
    Posted,
)
from github_orchestrator.notifications.interface import (
    BoardPages,
    FixProgress,
    Settling,
    Standing,
)

log = logging.getLogger(__name__)

LATE = timedelta(minutes=30)

_counter = itertools.count()


def _write(directory: Path, document: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{time.time_ns()}-{os.getpid()}-{next(_counter)}.json"
    with tempfile.NamedTemporaryFile("w", dir=directory, suffix=".tmp", delete=False) as tmp:
        json.dump(document, tmp)
        tmp.flush()
        os.fsync(tmp.fileno())
    Path(tmp.name).replace(directory / name)


class DiskOutbox:
    def __init__(self, root: Path, clock: LocalClock) -> None:
        self._root = root
        self._clock = clock

    def post(self, posted: Posted) -> None:
        _write(self._root, {**naming(posted.pr), "badge": posted.badge.value,
                            "title": posted.title, "body": posted.body,
                            "posted_at": self._clock().isoformat()})

    def gather(self, item: Gathered) -> None:
        _write(self._root / "batches" / group_of(item),
               {**encoded(item), "posted_at": self._clock().isoformat()})


@dataclass
class _Asking:
    paths: list[Path]
    asked_at: datetime
    summary: str | None = None
    gists: tuple[str, ...] | None = None

    @property
    def answered(self) -> bool:
        return self.summary is not None or self.gists is not None


class DiskCourier:
    def __init__(self, root: Path, desktop: Desktop, clock: LocalClock,
                 summaries: Summaries, standing: Standing, settling: Settling,
                 pages: BoardPages) -> None:
        self._root = root
        self._desktop = desktop
        self._clock = clock
        self._summaries = summaries
        self._standing = standing
        self._settling_on = settling
        self._pages = pages
        self._asking: dict[str, _Asking] = {}
        self._lock = threading.Lock()

    def deliver(self, woke_at: datetime, polled_at: datetime | None) -> None:
        if not self._root.exists():
            return
        now = self._clock()
        for path in sorted(self._root.glob("*.json")):
            document = json.loads(path.read_text())
            posted = datetime.fromisoformat(document["posted_at"])
            if self._shown(named(document), Badge(document["badge"]),
                           self._titled(document["title"], posted, now),
                           document["body"], path.stem):
                path.unlink()
        batches = self._root / "batches"
        if batches.exists():
            for group in sorted(batches.iterdir()):
                try:
                    self._deliver_batch(group, now, woke_at, polled_at)
                except Exception:
                    log.exception("could not deliver the %s batch; kept to try again",
                                  group.name)

    def _deliver_batch(self, group: Path, now: datetime, woke_at: datetime,
                       polled_at: datetime | None) -> None:
        asking = self._asking.get(group.name)
        if asking is None:
            paths = sorted(group.glob("*.json"))
            if not paths:
                return
            opened = min(self._posted_at(path) for path in paths)
            due = opened + WINDOW
            if now < due:
                return
            if due <= woke_at and (polled_at is None or polled_at < woke_at):
                return
            if now - due < SUMMARY_WAIT and self._settling(paths):
                return
            paths = self._news(paths)
            if not paths:
                return
            asking = _Asking(paths, now)
            if self._ask([decoded(json.loads(path.read_text())) for path in paths], asking):
                self._asking[group.name] = asking
        items = [decoded(json.loads(path.read_text())) for path in asking.paths]
        with self._lock:
            summary, gists, answered = asking.summary, asking.gists, asking.answered
        if group.name in self._asking and not answered and now - asking.asked_at < SUMMARY_WAIT:
            return
        opened = min(self._posted_at(path) for path in asking.paths)
        pr, badge, title, body = rendered(items, summary, gists or (), self._fix_of)
        key = hashlib.sha1("".join(path.stem for path in asking.paths).encode()).hexdigest()
        if not self._shown(pr, badge, self._titled(title, opened, now), body,
                           f"{group.name}-{key}"):
            return
        self._asking.pop(group.name, None)
        for path in asking.paths:
            path.unlink()

    def _settling(self, paths: list[Path]) -> bool:
        items = [decoded(json.loads(path.read_text())) for path in paths]
        return any(self._settling_on.settling(item.pr)
                   for item in items if isinstance(item, CommentArrived))

    def _fix_of(self, item: CommentArrived) -> FixProgress:
        return self._standing.fix_progress(item.pr, item.key)

    def _still_news(self, item: Gathered) -> bool:
        if isinstance(item, FixReady):
            return self._standing.fix_still_news(item.pr, item.key)
        if isinstance(item, CommentArrived):
            return self._standing.comment_still_news(item.pr, item.key, item.created_at)
        return True

    def _news(self, paths: list[Path]) -> list[Path]:
        fresh = []
        for path in paths:
            if self._still_news(decoded(json.loads(path.read_text()))):
                fresh.append(path)
            else:
                path.unlink()
        return fresh

    def _ask(self, items: list[Gathered], asking: _Asking) -> bool:
        ready = fixes(items)
        if ready:
            self._summaries.summarize_fixes(
                [(item.comments, item.fix_summary) for item in ready],
                lambda summary: self._summarized(asking, summary), chars=SUMMARY_ASKED_CHARS)
            return True
        arrived = comments(items)
        if arrived:
            self._summaries.summarize_comments(
                [comment.body for comment in arrived],
                lambda gists: self._gisted(asking, gists), chars=GIST_CHARS)
            return True
        return False

    def _summarized(self, asking: _Asking, summary: str) -> None:
        with self._lock:
            asking.summary = summary

    def _gisted(self, asking: _Asking, gists: tuple[str, ...]) -> None:
        with self._lock:
            asking.gists = gists

    def _shown(self, pr: Pr | None, badge: Badge, title: str, body: str, key: str) -> bool:
        link = None if pr is None else self._pages.board_of(pr)
        reason = self._desktop.announce(badge, title, body, key, link)
        if reason is not None:
            log.warning("notification %s kept to try again: %s", key, reason)
        return reason is None

    @staticmethod
    def _posted_at(path: Path) -> datetime:
        return datetime.fromisoformat(json.loads(path.read_text())["posted_at"])

    @staticmethod
    def _titled(title: str, posted: datetime, now: datetime) -> str:
        if now - posted <= LATE:
            return title
        return f"{title} (from {posted.astimezone(now.tzinfo):%H:%M})"
