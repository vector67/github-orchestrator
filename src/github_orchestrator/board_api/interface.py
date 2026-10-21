from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from starlette.types import ASGIApp

from github_orchestrator.domain import CiCheck, HubState, Mention, Pr, Repo, ThreadRow


class WallGroup(StrEnum):
    """Who moves next on a pull request, the wall's groups in the order the
    wall shows them: you (your drafts too when they hold something to decide),
    an agent, someone else (a reviewer, the author, CI or the first poll), or
    nobody while it is parked (on hold, or a draft with nothing to do)."""

    NEEDS_YOU = "needs-you"
    AGENT_WORKING = "agent-working"
    WAITING_ON_OTHERS = "waiting-on-others"
    PARKED = "parked"


class ManagerStanding(StrEnum):
    STARTING = "starting"
    ANSWERING = "answering"
    GONE = "gone"


class DismissUntil(StrEnum):
    NEXT_EVENT = "next-event"
    READY_FOR_REVIEW = "ready-for-review"
    FOREVER = "forever"


@dataclass(frozen=True)
class BaseStanding:
    behind_by: int
    conflicts: tuple[str, ...]
    fetched_at: float | None


@dataclass(frozen=True)
class QueuedEvent:
    event: str | None
    queued_at: str


@dataclass(frozen=True)
class UnpushedCommit:
    sha: str
    subject: str


@dataclass(frozen=True)
class Dashboard:
    pr: Pr
    worktree: str
    polled: bool
    title: str | None
    url: str | None
    branch: str | None
    base_branch: str | None
    ticket: str | None
    author: str | None
    is_author: bool | None
    detailed_reviewer: str | None
    is_detailed_reviewer: bool
    ci: str
    mergeable: bool | None
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
    checks: tuple[CiCheck, ...]
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
    queue: tuple[QueuedEvent, ...]
    on_hold: bool
    unpushed_commits: tuple[UnpushedCommit, ...] | None
    base: BaseStanding | None
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
    standing: ManagerStanding


class ManagerPanel(Protocol):
    def dashboard(self) -> Dashboard: ...

    def changes(self) -> str | None: ...

    def agent_output(self, lines: int) -> list[tuple[str, bool]]: ...

    def set_on_hold(self, on_hold: bool) -> str | None: ...

    def carry_on(self) -> str | None: ...

    def start_review(self) -> str | None: ...

    def dismiss(self, until: DismissUntil) -> str | None: ...

    def close(self) -> str | None: ...

    def mark_ready(self) -> str | None: ...

    def run_git(self, keys: str) -> tuple[int, list[str], float]: ...

    def open_terminal(self, keys: str) -> str | None: ...

    def ask(self, prompt: str) -> str | None: ...


class ManagerPanels(Protocol):
    def of(self, pr: Pr) -> ManagerPanel: ...


class Dashboards(Protocol):
    def dashboard(self, pr: Pr) -> Dashboard: ...


@dataclass(frozen=True)
class Held:
    told: bool
    managers: Mapping[Pr, str]


NOTHING_HELD = Held(told=False, managers={})


class Told(Protocol):
    def held(self) -> Held: ...

    def state(self) -> HubState | None: ...


class Holdings(Protocol):
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
    def polled_at(self) -> datetime | None: ...

    @property
    def last_error(self) -> str | None: ...

    @property
    def fix(self) -> str | None: ...

    @property
    def overdue(self) -> bool: ...

    @property
    def next_poll_at(self) -> datetime | None: ...


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


class Emojis(Protocol):
    def named(self) -> dict[str, str]: ...


class HarvestSetup(Protocol):
    def prepare(self) -> Path | str: ...


class ServerApp(Protocol):
    def app(self, port: int, pid: int) -> ASGIApp: ...


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
