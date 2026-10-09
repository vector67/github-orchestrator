import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from github_orchestrator.conversation._adapters.github_threads import fetch_threads
from github_orchestrator.conversation._domain.diff import (
    KIND_REVIEW,
    diff_threads,
    fingerprint,
    open_review_threads,
    within_cutoff,
)
from github_orchestrator.conversation._domain.thread import (
    ActiveThread,
    FetchedThread,
)
from github_orchestrator.domain import Pr
from github_orchestrator.github import Threads

log = logging.getLogger(__name__)

_COMMENT_CUTOFF_SECONDS = 5


def comment_cutoff(now: datetime) -> str:
    cutoff = now - timedelta(seconds=_COMMENT_CUTOFF_SECONDS)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")


def thread_snapshot(
        threads: list[FetchedThread],
        cutoff_iso: str | None = None) -> dict[str, dict[str, Any]]:
    return {
        t.key: {
            "comments": [[c.id, fingerprint(c)] for c in t.comments
                         if within_cutoff(c, cutoff_iso)],
            "is_resolved": bool(t.is_resolved),
        }
        for t in threads
    }


@dataclass(frozen=True)
class ThreadPoll:
    active: list[ActiveThread]
    stale: list[FetchedThread]
    open_review_threads: list[FetchedThread]
    snapshot: dict[str, dict[str, Any]] | None
    unresolved_count: int | None
    fetched: list[FetchedThread] | None


def poll_threads(
    github: Threads,
    pr: Pr,
    *,
    bot_login: str,
    old_snapshot: dict[str, Any] | None,
    cutoff_iso: str | None,
    posted_reply_ids: frozenset[int] = frozenset(),
    posted_comment_keys: frozenset[str] = frozenset(),
) -> ThreadPoll:
    try:
        threads = fetch_threads(github, pr)
    except Exception:
        log.exception("Thread fetch failed for %s; skipping comment processing",
                      pr)
        return ThreadPoll(active=[], stale=[], open_review_threads=[],
                          snapshot=old_snapshot, unresolved_count=None, fetched=None)

    changes = diff_threads(
        old_snapshot, threads,
        posted_reply_ids=posted_reply_ids,
        cutoff_iso=cutoff_iso,
        posted_comment_keys=posted_comment_keys,
        bot_login=bot_login,
    )
    return ThreadPoll(
        active=changes["active"],
        stale=changes["stale"],
        open_review_threads=open_review_threads(threads, bot_login=bot_login,
                                                cutoff_iso=cutoff_iso),
        snapshot=thread_snapshot(threads, cutoff_iso=cutoff_iso),
        unresolved_count=sum(1 for t in threads
                             if t.kind == KIND_REVIEW and not t.is_resolved),
        fetched=threads,
    )
