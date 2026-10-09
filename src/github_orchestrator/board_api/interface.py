from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from github_orchestrator.domain import HubState, Mention, Pr, Repo, ThreadRow


class WallGroup(StrEnum):
    """Who holds the ball on a pull request, the wall's groups in the order
    the wall shows them: it needs you, it is your draft, an agent is working
    on it, it waits on someone else (a reviewer, the author, CI or the first
    poll), it is on hold, or it mentioned you and every mention is answered."""

    NEEDS_YOU = "needs-you"
    DRAFT = "draft"
    AGENT_WORKING = "agent-working"
    WAITING_ON_OTHERS = "waiting-on-others"
    ON_HOLD = "on-hold"
    MENTIONED = "mentioned"


@dataclass(frozen=True)
class Dashboard:
    pr: Pr
    worktree: str
    polled: bool
    title: str | None
    url: str | None
    branch: str | None
    ticket: str | None
    author: str | None
    is_author: bool | None
    detailed_reviewer: str | None
    is_detailed_reviewer: bool
    ci: str
    mergeable: bool
    needs_rebase: bool
    review_decision: str | None
    my_review: str | None
    last_event_at: str | None
    review_ready_at: str | None
    since_commits: int | None
    since_force_push: bool
    since_reviews: int
    since_comments: int
    since_resolved: int
    failed_checks: tuple[str, ...]
    checks_done: int
    checks_total: int
    changed_files: int | None
    approved_by: tuple[str, ...]
    changes_requested_by: tuple[str, ...]
    pending_reviewers: tuple[str, ...]
    unresolved_threads: int | None
    polled_at: str | None
    ended: bool
    draft: bool
    merge_state: str | None
    viewer_requested: bool
    mentioned: bool
    mentions: tuple[Mention, ...]
    my_review_at: str | None
    agents_enabled: bool
    agent_name: str
    working_on: str | None
    elapsed_seconds: float | None
    silent_seconds: float | None
    last_run_event: str | None
    last_run_exit_code: int | None
    last_run_ended_at: str | None
    queued_events: int
    on_hold: bool
    unpushed_commits: int | None
    threads_queued: int
    threads_live: frozenset[str]
    threads_proposed: int
    threads_drafts: int
    frozen_on: str | None
    expected_branch: str | None
    seconds_left: float | None
    run_working: bool
    release_requested: bool
    hidden: bool
    flags_changed_at: str | None
    thread_rows: tuple[ThreadRow, ...]
    unreadable_threads: tuple[str, ...]
    threads_listed_at: str | None
    undismiss_command: str
    notice: str | None


class ManagerPanel(Protocol):
    def dashboard(self) -> Dashboard | None: ...

    def changes(self) -> str | None: ...

    def agent_output(self, lines: int) -> list[tuple[str, bool]]: ...

    def set_on_hold(self, on_hold: bool) -> None: ...

    def carry_on(self) -> None: ...

    def start_review(self) -> None: ...

    def dismiss(self, forever: bool) -> None: ...

    def close(self) -> None: ...

    def run_git(self, keys: str) -> tuple[int, list[str], float]: ...

    def open_terminal(self, keys: str) -> str | None: ...


class Dashboards(Protocol):
    def dashboard(self, pr: Pr) -> Dashboard: ...


class ManagerStanding(StrEnum):
    STARTING = "starting"
    ANSWERING = "answering"
    GONE = "gone"


class ManagerStatuses(Protocol):
    def standing(self, pr: Pr) -> ManagerStanding: ...


class Holdings(Protocol):
    def manager(self, pr: Pr) -> str: ...

    def board_port(self, pr: Pr) -> int | None: ...

    def hold(self, pr: Pr) -> None: ...

    def resume(self, pr: Pr) -> None: ...

    def release(self, pr: Pr) -> bool: ...


class FinishedRun(Protocol):
    @property
    def pr(self) -> Pr | None: ...

    @property
    def event(self) -> str: ...

    @property
    def elapsed_seconds(self) -> float: ...

    @property
    def cost_usd(self) -> float | None: ...

    @property
    def ended_at(self) -> datetime: ...

    @property
    def exit_code(self) -> int | None: ...

    @property
    def failed(self) -> bool: ...


class RunDay(Protocol):
    @property
    def finished(self) -> Sequence[FinishedRun]: ...

    @property
    def cost_usd(self) -> float | None: ...

    @property
    def unpriced(self) -> int: ...


class RunLedger(Protocol):
    def finished_since(self, when: datetime) -> Sequence[FinishedRun]: ...

    def finished_today(self, now: datetime) -> RunDay: ...


class Pulse(Protocol):
    @property
    def since_last_poll(self) -> timedelta | None: ...

    @property
    def last_error(self) -> str | None: ...

    @property
    def fix(self) -> str | None: ...

    @property
    def overdue(self) -> bool: ...

    @property
    def next_poll_in(self) -> timedelta | None: ...


class WatcherPulse(Protocol):
    def health(self) -> Pulse: ...


class ReleaseSeen(Protocol):
    @property
    def version(self) -> str: ...

    @property
    def checked_at(self) -> datetime | None: ...

    def newer_than(self, running: str | None) -> bool: ...


class ReleaseRecord(Protocol):
    def recorded(self) -> ReleaseSeen | None: ...


class TourMarker(Protocol):
    def due(self) -> bool: ...

    def arm(self) -> None: ...

    def seen(self) -> None: ...


class Hub(Protocol):
    def start(self, port: int, holdings: Holdings, state: HubState) -> str: ...

    def show(self, prs: Sequence[Pr]) -> None: ...

    def stop(self) -> bool: ...


class BoardApi(Protocol):
    def start(self, pr: Pr, *, port: int, manager: ManagerPanel) -> str: ...

    def stop(self) -> bool: ...

    def is_running(self) -> bool: ...


@dataclass(frozen=True)
class SetupRepo:
    repo: str
    local_path: str
    new_worktree_command: str


@dataclass(frozen=True)
class SetupOptions:
    agent_model: str
    agents_enabled: bool
    max_thread_runs: int


@dataclass(frozen=True)
class Requirement:
    program: str
    fix: str | None


@dataclass(frozen=True)
class SetupRead:
    state: HubState
    config_path: str
    problem: str | None
    active_account: str | None
    account: str | None
    repos: tuple[SetupRepo, ...]
    options: SetupOptions
    hub_port: int
    agent_name: str
    requirements: tuple[Requirement, ...]


@dataclass(frozen=True)
class RepoChoice:
    repo: Repo
    can_push: bool
    has_my_prs: bool
    default_branch: str


@dataclass(frozen=True)
class CloneSpot:
    repo: Repo
    path: str
    exists: bool
    is_clone: bool


class CloneState(StrEnum):
    WAITING = "waiting"
    CLONING = "cloning"
    CLONED = "cloned"
    FOUND = "found"
    FAILED = "failed"


@dataclass(frozen=True)
class CloneProgress:
    repo: Repo
    path: str
    state: CloneState
    error: str | None = None


class WriteState(StrEnum):
    CLONING = "cloning"
    FAILED = "failed"
    RESTARTING = "restarting"


@dataclass(frozen=True)
class SetupProgress:
    id: str
    state: WriteState
    clones: tuple[CloneProgress, ...]
    error: str | None = None
    archived: tuple[str, ...] = ()
    kept_worktrees: tuple[str, ...] = ()


@dataclass(frozen=True)
class SetupWrite:
    account: str
    repos: tuple[SetupRepo, ...]
    options: SetupOptions
    hub_port: int | None


@dataclass(frozen=True)
class FieldRefusal:
    field: str
    detail: str


class SetupDesk(Protocol):
    def read(self) -> SetupRead: ...

    def scopes(self, login: str) -> tuple[str, ...] | str: ...

    def repos(self, login: str) -> list[RepoChoice] | str: ...

    def repo(self, login: str, repo: Repo) -> RepoChoice | str: ...

    def clone(self, repo: Repo) -> CloneSpot: ...

    def write(self, asked: SetupWrite) -> SetupProgress | list[FieldRefusal]: ...

    def progress(self, operation: str) -> SetupProgress | None: ...

    def move_aside(self) -> str | None: ...
