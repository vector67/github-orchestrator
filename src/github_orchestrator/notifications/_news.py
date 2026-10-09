from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from github_orchestrator.change_detection import (
    BecameMergeable,
    BecameUnmergeable,
    CiSucceeded,
    PrClosed,
    PushedSinceReview,
    ReviewDecisionChanged,
)
from github_orchestrator.desktop import Badge
from github_orchestrator.domain import Pr
from github_orchestrator.notifications._facts import (
    AgentSkipped,
    Arrival,
    CommentArrived,
    FixReady,
    Gathered,
    Posted,
)
from github_orchestrator.notifications.interface import StatusChange


class Outbox(Protocol):
    def post(self, posted: Posted) -> None: ...

    def gather(self, item: Gathered) -> None: ...


def _word(value: object) -> object:
    return getattr(value, "value", value)


def _cycles(consecutive: int | None) -> str:
    if consecutive is None:
        return "watcher cycle failed"
    return f"{consecutive} consecutive failed {'cycle' if consecutive == 1 else 'cycles'}"


class News:
    def __init__(self, outbox: Outbox) -> None:
        self._outbox = outbox

    def _post(self, pr: Pr | None, badge: Badge, title: str, body: str) -> None:
        self._outbox.post(Posted(pr, badge, title, body))

    def fix_ready(self, pr: Pr, key: str, *, gist: str,
                  comments: Sequence[tuple[str, str]], fix_summary: str | None) -> None:
        self._outbox.gather(FixReady(
            pr=pr, key=key, gist=gist,
            comments=tuple((author or "ghost", body) for author, body in comments),
            fix_summary=fix_summary or ""))

    def comment_arrived(self, pr: Pr, key: str, *, comment_id: int | None, author: str,
                        body: str, created_at: str, opens_thread: bool, reopens: bool,
                        review_comment: bool) -> None:
        arrival = (Arrival.REOPENED if reopens
                   else Arrival.NEW_THREAD if opens_thread else Arrival.REPLY)
        self._outbox.gather(CommentArrived(
            pr=pr, key=key, comment_id=comment_id, author=author, body=body,
            created_at=created_at, arrival=arrival, review_comment=review_comment))

    def needs_your_call(self, pr: Pr, *, author: str, classification: str | None,
                        reason: str | None) -> None:
        self._post(pr, Badge.NEEDS_YOU, f"Comment needs your call on {pr.short}",
                   f"{author}\n{classification}: {reason}")

    def fix_failed(self, pr: Pr, *, gist: str, author: str, reason: str | None) -> None:
        self._post(pr, Badge.FAILED, f"Fix failed on {pr.short}", f"{gist or author}: {reason}")

    def run_failed(self, pr: Pr, kind: str, exit_code: int | None) -> None:
        self._post(pr, Badge.FAILED, f"Run failed on {pr.short}", f"{kind} exited {exit_code}")

    def agent_skipped(self, pr: Pr, kind: str) -> None:
        self._outbox.gather(AgentSkipped(pr, kind))

    def blocked(self, pr: Pr) -> None:
        self._post(pr, Badge.FAILED, f"PR {pr.in_repo} blocked",
                   "Cannot create worktree because branch already checked out!")

    def fetch_failed(self, pr: Pr, branch: str) -> None:
        self._post(pr, Badge.FAILED, f"PR {pr.in_repo} fetch failed",
                   f"Could not fetch {branch}; the previous head's objects may be gone")

    def init_timed_out(self, worktree: Path, seconds: int) -> None:
        self._post(None, Badge.FAILED, "Worktree init timed out",
                   f"new_worktree_command gave up after {seconds}s in {worktree.name}; "
                   "the worktree is usable but uninitialised")

    def init_failed(self, worktree: Path, exit_code: int) -> None:
        self._post(None, Badge.FAILED, "Worktree init failed",
                   f"new_worktree_command exited {exit_code} in {worktree.name}; "
                   "the worktree is usable but uninitialised")

    def wrong_branch(self, pr: Pr, kept_as: str) -> None:
        self._post(pr, Badge.FAILED, f"PR {pr.in_repo} left on the wrong branch",
                   f"Window kept as {kept_as}; building a fresh worktree")

    def shared(self, pr: Pr, worktree: Path, other: Pr) -> None:
        self._post(pr, Badge.FAILED, f"PR {pr.in_repo} shares a worktree",
                   f"{worktree.name} is already PR {other.in_repo}'s — not opening a "
                   f"window; press w on PR {other.in_repo}'s screen to release it")

    def still_shared(self, pr: Pr, worktree: Path, other: Pr, minutes: int) -> None:
        self._post(pr, Badge.FAILED, f"PR {pr.in_repo} worktree still shared",
                   f"{worktree.name} is still PR {other.in_repo}'s after {minutes} min — "
                   "opening it anyway")

    def changed(self, pr: Pr, change: StatusChange) -> None:
        match change:
            case CiSucceeded():
                self._post(pr, Badge.INFO, f"CI passed — PR {pr.in_repo}",
                           f"Checks passed: {', '.join(change.checks)} (success)")
            case BecameUnmergeable():
                self._post(pr, Badge.FAILED, f"PR {pr.in_repo} unmergeable",
                           f"Reason: {change.reason.value}")
            case BecameMergeable():
                self._post(pr, Badge.INFO, f"PR {pr.in_repo} is now mergeable",
                           f"Reason: {change.reason.value}")
            case ReviewDecisionChanged():
                self._post(pr, Badge.INFO, f"Review decision changed — PR {pr.in_repo}",
                           f"{change.reviewer} changed review from {_word(change.before)} "
                           f"to {_word(change.after)}")
            case PushedSinceReview():
                self._post(pr, Badge.INFO, f"PR {pr.in_repo} updated", change.pushes)
            case PrClosed():
                self._closed(pr, change)

    def _closed(self, pr: Pr, event: PrClosed) -> None:
        if event.no_longer_relevant:
            self._post(None, Badge.INFO, f"PR {pr.in_repo} no longer relevant",
                       "Removed from your watch list (not authored, not reviewed, "
                       "not requested).")
            return
        status = "merged" if event.merged else "closed without merging"
        self._post(None, Badge.INFO, f"PR {pr.in_repo} closed", f"PR was {status}.")

    def failed(self, consecutive: int | None, error: str, log_file: Path) -> None:
        self._post(None, Badge.FAILED, "Watcher not polling",
                   f"{_cycles(consecutive)}: {error}. Details in {log_file}")
