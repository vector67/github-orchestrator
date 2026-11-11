import fcntl
import json
import logging
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from github_orchestrator.board_api.interface import (
    NO_MENTIONS_LISTED,
    DeferredUntilPr,
    ListedMention,
    MentionDeferral,
    MentionsListing,
    OpenedForMention,
    PrEnded,
    PrMilestone,
)
from github_orchestrator.domain import Mention, Pr, Repo, UtcClock
from github_orchestrator.mentions._deferrals import lapsed

log = logging.getLogger(__name__)


def listed(pr: Pr, mention: Mention, *, url: str, on_board: bool,
           building: bool, ended: PrEnded | None) -> ListedMention:
    return ListedMention(pr=pr, thread=mention.thread, comment_id=mention.comment_id,
                         kind=mention.kind, author=mention.author, at=mention.at,
                         body=mention.body, url=url, on_board=on_board, building=building,
                         ended=ended)


def started_before(path: Path) -> dict[str, str] | None:
    try:
        started: dict[str, str] = json.loads(path.read_text())["started"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return started if isinstance(started, dict) else None


def building_since(path: Path) -> dict[str, str]:
    try:
        building: dict[str, str] = json.loads(path.read_text())["building_since"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    return building if isinstance(building, dict) else {}


def dismissal(pr: Pr, comment_id: int | None) -> str:
    return f"{pr}:{'pr-body' if comment_id is None else comment_id}"


def _dismissals_at(path: Path) -> Path:
    return path.with_name(f"{path.stem}-dismissed{path.suffix}")


def dismissed(path: Path) -> frozenset[str]:
    at = _dismissals_at(path)
    try:
        keys = json.loads(at.read_text())
    except FileNotFoundError:
        return frozenset()
    except (OSError, ValueError) as damaged:
        log.warning("%s will not read, so no mention is dismissed: %s", at, damaged)
        return frozenset()
    if not isinstance(keys, list):
        log.warning("%s is not a list, so no mention is dismissed", at)
        return frozenset()
    return frozenset(key for key in keys if isinstance(key, str))


def _deferrals_at(path: Path) -> Path:
    return path.with_name(f"{path.stem}-deferred{path.suffix}")


def deferrals(path: Path) -> dict[str, MentionDeferral]:
    at = _deferrals_at(path)
    try:
        stored = json.loads(at.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as damaged:
        log.warning("%s will not read, so no mention is deferred: %s", at, damaged)
        return {}
    if not isinstance(stored, dict):
        log.warning("%s is not a mapping, so no mention is deferred", at)
        return {}
    kept = {}
    for key, entry in stored.items():
        try:
            kept[key] = _deferral(entry)
        except (KeyError, TypeError, ValueError) as damaged:
            log.warning("the deferral of %s in %s is damaged, so it is dropped: %r",
                        key, at, damaged)
    return kept


def change_deferrals(path: Path,
                     change: Callable[[dict[str, MentionDeferral]], None]) -> None:
    at = _deferrals_at(path)
    at.parent.mkdir(parents=True, exist_ok=True)
    with at.with_name(f"{at.name}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        held = deferrals(path)
        change(held)
        writing = at.with_name(f"{at.name}.writing")
        writing.write_text(json.dumps({key: _stored_deferral(deferral)
                                       for key, deferral in sorted(held.items())}))
        os.replace(writing, at)


def _stored_deferral(deferral: MentionDeferral) -> dict[str, Any]:
    awaited = deferral.until_pr
    return {"deferred_at": deferral.deferred_at, "until_at": deferral.until_at,
            "until_pr": None if awaited is None else {
                "repo": str(awaited.pr.repo), "number": awaited.pr.number,
                "state": awaited.state.value},
            "head_sha": deferral.head_sha}


def _deferral(entry: Mapping[str, Any]) -> MentionDeferral:
    awaited = entry["until_pr"]
    if awaited is not None and type(awaited["number"]) is not int:
        raise TypeError(f"the PR number {awaited['number']!r} is not a number")
    return MentionDeferral(
        deferred_at=str(entry["deferred_at"]), until_at=entry["until_at"],
        until_pr=None if awaited is None else DeferredUntilPr(
            pr=Pr(Repo.parse(awaited["repo"]), awaited["number"]),
            state=PrMilestone(awaited["state"])),
        head_sha=entry.get("head_sha"))


@dataclass(frozen=True)
class _Opening:
    pr: Pr
    comment_id: int | None
    on_wall: bool


def _openings_at(path: Path) -> Path:
    return path.with_name(f"{path.stem}-opened{path.suffix}")


def _openings(path: Path) -> dict[Pr, _Opening]:
    at = _openings_at(path)
    try:
        stored = json.loads(at.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as damaged:
        log.warning("%s will not read, so no pull request is open for a mention: %s", at, damaged)
        return {}
    try:
        openings = [_opening(entry) for entry in stored]
    except (KeyError, TypeError, ValueError) as damaged:
        log.warning("%s is damaged, so no pull request is open for a mention: %r", at, damaged)
        return {}
    return {opening.pr: opening for opening in openings}


def _opening(entry: Mapping[str, Any]) -> _Opening:
    if type(entry["number"]) is not int or type(entry["on_wall"]) is not bool:
        raise TypeError(f"the opening {entry!r} is not a number and a flag")
    return _Opening(pr=Pr(Repo.parse(entry["repo"]), entry["number"]),
                    comment_id=entry["comment_id"], on_wall=entry["on_wall"])


def _change_openings(path: Path, change: Callable[[dict[Pr, _Opening]], None]) -> None:
    at = _openings_at(path)
    at.parent.mkdir(parents=True, exist_ok=True)
    with at.with_name(f"{at.name}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        held = _openings(path)
        change(held)
        writing = at.with_name(f"{at.name}.writing")
        writing.write_text(json.dumps([
            {"repo": str(opening.pr.repo), "number": opening.pr.number,
             "comment_id": opening.comment_id, "on_wall": opening.on_wall}
            for opening in held.values()]))
        os.replace(writing, at)


def _opened(openings: Mapping[Pr, _Opening],
            mentions: Sequence[ListedMention]) -> tuple[OpenedForMention, ...]:
    return tuple(
        OpenedForMention(pr=opening.pr, comment_id=opening.comment_id,
                         outside_wall=not opening.on_wall and any(
                             mention.ended is not None for mention in mentions
                             if mention.pr == opening.pr))
        for opening in openings.values()
        if opening.on_wall or any(mention.pr == opening.pr for mention in mentions))


def write_listing(path: Path, searched_at: datetime, started: Mapping[str, str],
                  mentions: Sequence[ListedMention], building: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writing = path.with_name(f"{path.name}.writing")
    writing.write_text(json.dumps({"searched_at": searched_at.isoformat(),
                                   "started": dict(started),
                                   "building_since": dict(building),
                                   "mentions": [_entry(mention) for mention in mentions]}))
    os.replace(writing, path)


class ListingFile:
    def __init__(self, path: Path, clock: UtcClock) -> None:
        self._path = path
        self._clock = clock

    def defer(self, pr: Pr, comment_id: int | None, deferral: MentionDeferral) -> None:
        change_deferrals(self._path, lambda held: held.update(
            {dismissal(pr, comment_id): deferral}))

    def stop_deferring(self, pr: Pr, comment_id: int | None) -> None:
        def stop(held: dict[str, MentionDeferral]) -> None:
            held.pop(dismissal(pr, comment_id), None)

        change_deferrals(self._path, stop)

    def dismiss(self, pr: Pr, comment_id: int | None) -> None:
        at = _dismissals_at(self._path)
        at.parent.mkdir(parents=True, exist_ok=True)
        with at.with_name(f"{at.name}.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            writing = at.with_name(f"{at.name}.writing")
            writing.write_text(json.dumps(sorted(dismissed(self._path)
                                                 | {dismissal(pr, comment_id)})))
            os.replace(writing, at)

    def open(self, pr: Pr, comment_id: int | None) -> None:
        def opening(held: dict[Pr, _Opening]) -> None:
            before = held.get(pr)
            held[pr] = _Opening(pr=pr, comment_id=comment_id,
                                on_wall=before is not None and before.on_wall)

        _change_openings(self._path, opening)

    def add_to_wall(self, pr: Pr) -> None:
        def walled(held: dict[Pr, _Opening]) -> None:
            if pr in held:
                held[pr] = replace(held[pr], on_wall=True)

        _change_openings(self._path, walled)

    def listed(self) -> MentionsListing:
        try:
            document = json.loads(self._path.read_text())
        except FileNotFoundError:
            return NO_MENTIONS_LISTED
        except (OSError, ValueError) as damaged:
            log.warning("%s will not read, so no mentions are listed: %s", self._path, damaged)
            return NO_MENTIONS_LISTED
        gone = dismissed(self._path)
        held = deferrals(self._path)
        now = self._clock()
        try:
            mentions = tuple(
                replace(mention, deferred=_holding(held.get(
                    dismissal(mention.pr, mention.comment_id)), now))
                for mention in map(_listed_mention, document["mentions"])
                if dismissal(mention.pr, mention.comment_id) not in gone)
            return MentionsListing(searched_at=document["searched_at"], mentions=mentions,
                                   opened=_opened(_openings(self._path), mentions))
        except (KeyError, TypeError, ValueError) as damaged:
            log.warning("%s is damaged, so no mentions are listed: %r", self._path, damaged)
            return NO_MENTIONS_LISTED


def _holding(deferral: MentionDeferral | None, now: datetime) -> MentionDeferral | None:
    return None if deferral is None or lapsed(deferral, now) else deferral


def _entry(mention: ListedMention) -> dict[str, Any]:
    return {"repo": str(mention.pr.repo), "number": mention.pr.number,
            "thread": mention.thread, "comment_id": mention.comment_id, "kind": mention.kind,
            "author": mention.author, "at": mention.at, "body": mention.body,
            "url": mention.url, "on_board": mention.on_board, "building": mention.building,
            "ended": mention.ended}


def _listed_mention(entry: Mapping[str, Any]) -> ListedMention:
    if type(entry["number"]) is not int:
        raise TypeError(f"the PR number {entry['number']!r} is not a number")
    ended = entry.get("ended")
    return ListedMention(pr=Pr(Repo.parse(entry["repo"]), entry["number"]),
                         thread=entry["thread"], comment_id=entry["comment_id"],
                         kind=entry["kind"], author=entry["author"], at=entry["at"],
                         body=entry["body"], url=entry["url"], on_board=entry["on_board"],
                         building=entry["building"],
                         ended=None if ended is None else PrEnded(ended))
