import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from github_orchestrator.desktop import Badge
from github_orchestrator.domain import LocalClock, Pr
from github_orchestrator.notifications._facts import (
    AgentSkipped,
    Arrival,
    CommentArrived,
    FixReady,
    Gathered,
    Posted,
)


class Outbox(Protocol):
    def post(self, posted: Posted) -> None: ...

    def gather(self, item: Gathered) -> None: ...


class Sent(Protocol):
    def first(self, key: str) -> bool: ...


def _streak(fix: str | None, failed: str, error: str, log_file: Path) -> str:
    told = f"{fix} " if fix else ""
    return f"{told}{failed}: {error}. Details in {log_file}"


class News:
    def __init__(self, outbox: Outbox, sent: Sent, clock: LocalClock) -> None:
        self._outbox = outbox
        self._sent = sent
        self._clock = clock

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
        if not self._first_today(pr, "fix failed"):
            return
        self._post(pr, Badge.FAILED, f"Fix failed on {pr.short}", f"{gist or author}: {reason}")

    def agent_asked(self, pr: Pr, key: str, *, question: str) -> None:
        asked = hashlib.sha1(question.encode()).hexdigest()
        if not self._sent.first(f"agent asked {pr} {key} {asked}"):
            return
        self._post(pr, Badge.NEEDS_YOU, f"Agent question on {pr.short}", question)

    def run_failed(self, pr: Pr, kind: str, exit_code: int | None) -> None:
        if not self._first_today(pr, "run failed"):
            return
        self._post(pr, Badge.FAILED, f"Run failed on {pr.short}", f"{kind} exited {exit_code}")

    def _first_today(self, pr: Pr, kind: str) -> bool:
        return self._sent.first(f"{kind} {pr} {self._clock():%Y-%m-%d}")

    def agent_skipped(self, pr: Pr, kind: str) -> None:
        self._outbox.gather(AgentSkipped(pr, kind))

    def blocked(self, pr: Pr) -> None:
        self._post(pr, Badge.FAILED, f"{pr.short} blocked",
                   "Cannot create worktree because branch already checked out!")

    def fetch_failed(self, pr: Pr, branch: str) -> None:
        self._post(pr, Badge.FAILED, f"{pr.short} fetch failed",
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
        self._post(pr, Badge.FAILED, f"{pr.short} left on the wrong branch",
                   "Stopped its agent manager and left its worktree as it was; "
                   "building a fresh worktree")

    def shared(self, pr: Pr, worktree: Path, other: Pr) -> None:
        self._post(pr, Badge.FAILED, f"{pr.short} shares a worktree",
                   f"{worktree.name} already belongs to {other.short}, so no agent "
                   "manager starts in it")

    def still_shared(self, pr: Pr, worktree: Path, other: Pr, minutes: int) -> None:
        self._post(pr, Badge.FAILED, f"{pr.short} worktree still shared",
                   f"{worktree.name} still belongs to {other.short} after {minutes} min. "
                   "Opening it anyway")

    def failed(self, consecutive: int, error: str, fix: str | None, log_file: Path) -> None:
        self._post(None, Badge.FAILED, "Watcher not polling",
                   _streak(fix, f"{consecutive} cycles in a row failed", error, log_file))

    def mentions_failed(self, consecutive: int, error: str, log_file: Path) -> None:
        self._post(None, Badge.FAILED, "Mentions search failed",
                   _streak(None, f"{consecutive} searches in a row failed", error, log_file))
