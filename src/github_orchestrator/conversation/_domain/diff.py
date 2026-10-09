import hashlib
from typing import Any

from github_orchestrator.conversation._domain.conversation import Comment
from github_orchestrator.conversation._domain.thread import (
    ActiveThread,
    FetchedThread,
)

KIND_REVIEW = "review"
KIND_ISSUE = "issue"
KIND_REVIEW_SUMMARY = "review-summary"
KIND_DRAFT = "draft"

BOT_MARKER = "\U0001F916"


def within_cutoff(comment: Comment, cutoff_iso: str | None) -> bool:
    return cutoff_iso is None or (comment.created_at or "") <= cutoff_iso


def fingerprint(comment: Comment) -> str:
    body = comment.body.encode("utf-8", "surrogatepass")
    return hashlib.sha256(body).hexdigest()[:16]


def _seen(entry: dict[str, Any] | list[Any] | None) -> dict[int | None, str | None]:
    """Comment id to its stored body fingerprint, None where a bare id was stored."""
    stored = entry.get("comments") if isinstance(entry, dict) else entry
    seen: dict[int | None, str | None] = {}
    for item in stored or []:
        if isinstance(item, (list, tuple)):
            seen[item[0]] = item[1] if len(item) > 1 else None
        else:
            seen[item] = None
    return seen


def _was_resolved(entry: dict[str, Any] | list[Any] | None) -> bool | None:
    """What GitHub last said, or None in an entry written before the flag."""
    if not isinstance(entry, dict):
        return None
    was = entry.get("is_resolved")
    return None if was is None else bool(was)


def _is_ours(comment: Comment, bot_login: str) -> bool:
    return (
        comment.author == bot_login
        and comment.body.lstrip().startswith(BOT_MARKER)
    )


def _resolution_moved(entry: dict[str, Any] | list[Any] | None,
                      thread: FetchedThread) -> bool:
    was = _was_resolved(entry)
    return was is not None and was != bool(thread.is_resolved)


def _drifted(seen: dict[int | None, str | None],
             comments: tuple[Comment, ...]) -> bool:
    now = {c.id: fingerprint(c) for c in comments}
    if set(now) != set(seen):
        return True
    return any(fp is not None and now[cid] != fp for cid, fp in seen.items())


def open_review_threads(threads: list[FetchedThread], *, bot_login: str,
                        cutoff_iso: str | None) -> list[FetchedThread]:
    return [thread for thread in threads
            if thread.kind == KIND_REVIEW and not thread.is_resolved
            and any(not _is_ours(comment, bot_login) and within_cutoff(comment, cutoff_iso)
                    for comment in thread.comments)]


def diff_threads(
    old_snapshot: dict[str, Any] | None,
    threads: list[FetchedThread],
    posted_reply_ids: frozenset[int] = frozenset(),
    cutoff_iso: str | None = None,
    posted_comment_keys: frozenset[str] = frozenset(),
    *,
    bot_login: str,
) -> dict[str, Any]:
    old = old_snapshot or {}

    active = []
    stale = []
    for thread in threads:
        if thread.key in posted_comment_keys:
            continue
        entry = old.get(thread.key)
        seen = _seen(entry)
        ours = posted_reply_ids if thread.kind == KIND_REVIEW else frozenset()
        comments = thread.comments
        root_id = comments[0].id if comments else None
        fresh = tuple(
            c for c in comments
            if c.id not in ours
            and not _is_ours(c, bot_login)
            and within_cutoff(c, cutoff_iso)
            and (c.id not in seen
                 or (c.id == root_id
                     and seen[c.id] is not None
                     and seen[c.id] != fingerprint(c)))
        )
        if fresh:
            active.append(ActiveThread(thread=thread, new_comments=fresh))
        elif thread.key in old and (_drifted(seen, comments)
                                       or _resolution_moved(entry, thread)):
            stale.append(thread)

    return {
        "active": active,
        "stale": stale,
    }
