from collections.abc import Callable
from dataclasses import asdict
from datetime import timedelta
from typing import Any

from github_orchestrator.desktop import Badge
from github_orchestrator.domain import Pr, Repo
from github_orchestrator.notifications._facts import (
    AgentSkipped,
    Arrival,
    CommentArrived,
    FixReady,
    Gathered,
)
from github_orchestrator.notifications.interface import FixProgress

WINDOW = timedelta(minutes=3)
SUMMARY_WAIT = timedelta(seconds=60)
SUMMARY_CHARS = 110
SUMMARY_ASKED_CHARS = 100
GIST_CHARS = 60

_FIX_READY = "fix-ready"
_AGENT_SKIPPED = "agent-skipped"
_COMMENT = "comment"

_PROGRESS = {FixProgress.NONE: "No fix", FixProgress.QUEUED: "Fix queued",
             FixProgress.STARTED: "Fix started"}


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def clipped(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def group_of(item: Gathered) -> str:
    if isinstance(item, FixReady):
        return f"fixes-ready--{item.pr.repo.owner}--{item.pr.repo.name}--{item.pr.number}"
    if isinstance(item, CommentArrived):
        return f"comments--{item.pr.repo.owner}--{item.pr.repo.name}--{item.pr.number}"
    return "agents-disabled"


def encoded(item: Gathered) -> dict[str, Any]:
    if isinstance(item, FixReady):
        kind = _FIX_READY
    elif isinstance(item, CommentArrived):
        kind = _COMMENT
    else:
        kind = _AGENT_SKIPPED
    fields = asdict(item)
    del fields["pr"]
    if isinstance(item, CommentArrived):
        del fields["arrival"]
        fields["action"] = item.arrival.value
    return {"kind": kind, **naming(item.pr), **fields}


def naming(pr: Pr | None) -> dict[str, Any]:
    return {} if pr is None else {"repo": str(pr.repo), "pr": pr.number}


def _pr_of(document: dict[str, Any]) -> Pr:
    return Pr(Repo.parse(document["repo"]), document["pr"])


def named(document: dict[str, Any]) -> Pr | None:
    return _pr_of(document) if "pr" in document else None


def decoded(document: dict[str, Any]) -> Gathered:
    where = _pr_of(document)
    if document["kind"] == _FIX_READY:
        return FixReady(pr=where, key=document["key"],
                        gist=document["gist"],
                        comments=tuple((author, body) for author, body in document["comments"]),
                        fix_summary=document["fix_summary"])
    if document["kind"] == _COMMENT:
        return CommentArrived(pr=where, key=document["key"],
                              comment_id=document["comment_id"], author=document["author"],
                              body=document["body"], created_at=document["created_at"],
                              arrival=Arrival(document["action"]),
                              review_comment=document["review_comment"])
    return AgentSkipped(pr=where, event_type=document["event_type"])


def fixes(items: list[Gathered]) -> list[FixReady]:
    return [item for item in items if isinstance(item, FixReady)]


def comments(items: list[Gathered]) -> list[CommentArrived]:
    return sorted((item for item in items if isinstance(item, CommentArrived)),
                  key=lambda item: item.created_at)


def _fallback_summary(ready: list[FixReady]) -> str:
    return "; ".join(item.gist or (item.comments[0][0] if item.comments else "") for item in ready)


def rendered(items: list[Gathered], summary: str | None, gists: tuple[str, ...],
             fix_of: Callable[[CommentArrived], FixProgress]
             ) -> tuple[Pr | None, Badge, str, str]:
    ready = fixes(items)
    if ready:
        first = ready[0]
        return (first.pr, Badge.READY,
                f"{_plural(len(ready), 'fix', 'fixes')} ready on {first.pr.short}",
                clipped(summary or _fallback_summary(ready), SUMMARY_CHARS))
    arrived = comments(items)
    if arrived:
        return (arrived[0].pr, *_comment_banner(arrived, gists, fix_of))
    skipped: dict[Pr, list[str]] = {}
    for item in items:
        if isinstance(item, AgentSkipped):
            skipped.setdefault(item.pr, []).append(item.event_type)
    prs = ", ".join(pr.in_repo for pr in skipped)
    body = "; ".join(f"{pr.short}: {', '.join(types)}"
                     for pr, types in skipped.items())
    only = next(iter(skipped)) if len(skipped) == 1 else None
    return only, Badge.INFO, f"Agents disabled — skipped events on {prs}", body


def _comment_banner(comments: list[CommentArrived], gists: tuple[str, ...],
                    fix_of: Callable[[CommentArrived], FixProgress]) -> tuple[Badge, str, str]:
    fixes = [fix_of(comment) for comment in comments]
    lines = []
    for at, (comment, fix) in enumerate(zip(comments, fixes, strict=True)):
        who = f"{comment.author} (review comment)" if comment.review_comment else comment.author
        gist = clipped((gists[at] if at < len(gists) else "") or comment.body, GIST_CHARS)
        lines.append(f'{comment.arrival.value} | {_PROGRESS[fix]} | {who}: "{gist}"')
    started, queued = fixes.count(FixProgress.STARTED), fixes.count(FixProgress.QUEUED)
    counts = []
    if started:
        counts.append(f"{_plural(started, 'fix', 'fixes')} started")
    if queued:
        counts.append(f"{queued} queued" if started else f"{_plural(queued, 'fix', 'fixes')} queued")
    first = comments[0]
    title = f"{_plural(len(comments), 'comment', 'comments')} on {first.pr.short}"
    if counts:
        title = f"{title} · {', '.join(counts)}"
    return Badge.COMMENTS, title, "\n".join(lines)
