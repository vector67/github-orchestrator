from collections.abc import Callable, Mapping, Sequence, Set
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from github_orchestrator.domain import Pr, Repo


@dataclass(frozen=True)
class LastRun:
    event_type: str
    exit_code: int | None
    ended_at: str


@dataclass(frozen=True)
class FinishedRun:
    pr: Pr | None
    event: str
    elapsed_seconds: float
    cost_usd: float | None
    ended_at: datetime
    exit_code: int | None
    failed: bool


@dataclass(frozen=True)
class RunDay:
    finished: tuple[FinishedRun, ...]

    @property
    def cost_usd(self) -> float | None:
        costs = [run.cost_usd for run in self.finished if run.cost_usd is not None]
        return sum(costs) if costs else None

    @property
    def unpriced(self) -> int:
        return sum(1 for run in self.finished if run.cost_usd is None)


@dataclass(frozen=True)
class FixComment:
    author: str
    body: str
    created_at: str | None = None
    author_name: str | None = None
    by_pr_author: bool = False


@dataclass(frozen=True)
class PointedAt:
    file: str
    line: int | None
    text: str


@dataclass(frozen=True)
class ThreadFix:
    pr: Pr
    key: str
    worktree: str
    author: str
    path: str | None
    line: int | None
    body: str
    comments: tuple[FixComment, ...] = ()
    confidence_levels: tuple[str, ...] = ()
    before_reply: str = ""
    withdraws_proposal: bool = False
    conflict: str | None = None
    classification: str | None = None
    skipped_because: str | None = None
    reply: str | None = None
    ticket_project: str | None = None
    ticket_title: str | None = None
    ticket_body: str | None = None
    tracker: str | None = None
    tracker_project: str | None = None
    branch_ticket: str | None = None
    note: str = ""
    pointed: tuple[PointedAt, ...] = ()
    replies: tuple[FixComment, ...] = ()


Replied = Sequence[tuple[str | None, int | None, Sequence[FixComment]]]


class Run(Protocol):
    @property
    def event_type(self) -> str: ...

    @property
    def last_action(self) -> str | None: ...

    def is_alive(self) -> bool: ...

    def pump(self) -> bool: ...

    def interrupt(self) -> None: ...

    def terminate(self) -> None: ...

    def elapsed(self) -> float: ...

    def silent_for(self) -> float: ...

    def finished(self) -> LastRun: ...


class PrWork(Protocol):
    def review(self, worktree: str, pr: Pr, event_type: str, *, title: str, url: str,
               branch: str, additions: int, deletions: int) -> Run | str: ...

    def rereview(self, worktree: str, pr: Pr, event_type: str, *, title: str, url: str,
                 branch: str, verdict: str, said: FixComment | None, since: str | None,
                 commits: Sequence[str] | None, replied: Replied) -> Run | str: ...

    def fix_check(self, worktree: str, pr: Pr, event_type: str, *, check: str,
                  summary: str | None, push: bool) -> Run | str: ...

    def rebase(self, worktree: str, pr: Pr, event_type: str, *, reason: str) -> Run | str: ...

    def carry_on(self, worktree: str, pr: Pr) -> Run | str: ...

    def rebase_in_session(self, pr: Pr, worktree: str) -> str | None: ...


class Summaries(Protocol):
    def summarize_comment(self, key: str, path: str | None, line: int | None, body: str,
                          done: Callable[[str], None], *, chars: int) -> None: ...

    def summarize_thread(self, key: str, path: str | None, line: int | None,
                         comments: Sequence[tuple[str, str]], done: Callable[[str], None],
                         *, chars: int) -> None: ...

    def summarize_comments(self, bodies: Sequence[str],
                           done: Callable[[tuple[str, ...]], None], *, chars: int) -> None: ...

    def summarize_fixes(self, fixes: Sequence[tuple[Sequence[tuple[str, str]], str | None]],
                        done: Callable[[str], None], *, chars: int) -> None: ...

    def judge_thread(self, key: str, comments: Sequence[tuple[str, str, str]], *,
                     viewer: str, pr_author: str, spoke_last: str, viewer_commented: bool,
                     mentions_viewer: bool, kind: str, answers: Mapping[str, str],
                     done: Callable[[str], None]) -> None: ...


class ThreadWork(Protocol):
    def fix(self, fix: ThreadFix) -> Run | str: ...

    def rebase_fix(self, fix: ThreadFix, onto: str | None) -> Run | str: ...

    def rework(self, fix: ThreadFix) -> Run | str: ...

    def file_ticket(self, fix: ThreadFix) -> Run | str: ...

    def open_session(self, fix: ThreadFix, steer: str | None) -> str | None: ...


class History(Protocol):
    def last_run(self, pr: Pr) -> LastRun | None: ...

    def transcript_tail(self, pr: Pr, limit: int) -> list[tuple[str, bool]]: ...

    def finished_since(self, when: datetime) -> list[FinishedRun]: ...

    def finished_today(self, now: datetime) -> RunDay: ...

    def live(self, pr: Pr) -> bool: ...

    def interrupted(self, pr: Pr) -> str | None: ...

    def archive_other_repos(self, keep: Set[Repo], into: Path) -> list[Path]: ...
