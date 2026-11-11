import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from starlette.types import ASGIApp

from github_orchestrator.domain import (
    CiCheck,
    DismissUntil,
    HubState,
    Mention,
    Pr,
    Repo,
    ReviewerPick,
    ThreadRow,
)


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


class ManagerRefusal(StrEnum):
    MANAGER_DOWN = "manager-down"
    NO_WORKTREE = "no-worktree"
    WORKTREE_FROZEN = "worktree-frozen"
    AGENTS_DISABLED = "agents-disabled"
    AGENT_RUNNING = "agent-running"


class NoticeCode(StrEnum):
    WORKTREE_FROZEN = "worktree-frozen"
    AGENTS_DISABLED = "agents-disabled"
    AGENT_RUNNING = "agent-running"
    AGENT_WONT_START = "agent-wont-start"
    NOT_YOUR_DRAFT = "not-your-draft"
    NOT_YOURS_TO_ASSIGN = "not-yours-to-assign"
    CLOSE_REFUSED = "close-refused"
    MARK_READY_REFUSED = "mark-ready-refused"
    ASSIGN_REVIEWERS_REFUSED = "assign-reviewers-refused"


@dataclass(frozen=True)
class Notice:
    code: NoticeCode
    detail: str | None = None


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


RESET_TO_ORIGIN = "reset"
_RESET_STATE = "state"


class ResetRefusalCode(StrEnum):
    BRANCH_UNKNOWN = "branch-unknown"
    FETCH_FAILED = "fetch-failed"
    FIX_AWAITS_PUSH = "fix-awaits-push"
    RESET_INTERRUPTED = "reset-interrupted"
    WORKTREE_MISSING = "worktree-missing"
    NO_ORIGIN_BRANCH = "no-origin-branch"
    ON_ANOTHER_BRANCH = "on-another-branch"
    UNCOMMITTED_CHANGES = "uncommitted-changes"
    HEAD_UNREADABLE = "head-unreadable"
    WORKTREE_MOVED = "worktree-moved"
    NOT_DIVERGED = "not-diverged"
    ORIGIN_ADDS_UNKNOWN = "origin-adds-unknown"
    UNTRACKED_IN_THE_WAY = "untracked-in-the-way"
    RESET_REFUSED = "reset-refused"


@dataclass(frozen=True)
class ResetRefusal:
    code: ResetRefusalCode
    detail: str | None = None


def _text(field: object) -> bool:
    return field is None or (isinstance(field, str) and bool(field))


def _refusal_of(field: object) -> ResetRefusal:
    if not isinstance(field, dict):
        raise ValueError(field)
    code, detail = field.get("code"), field.get("detail")
    if not isinstance(code, str) or not _text(detail):
        raise ValueError(field)
    return ResetRefusal(ResetRefusalCode(code), detail)


@dataclass(frozen=True)
class ResetToOrigin:
    queued_at: str | None = None
    ran_at: str | None = None
    refused: ResetRefusal | None = None

    def keep(self, shelf: "Shelf") -> None:
        shelf.save(RESET_TO_ORIGIN, _RESET_STATE, json.dumps(asdict(self)).encode())

    @staticmethod
    def kept(shelf: "Shelf") -> "ResetToOrigin | None":
        document = shelf.list(RESET_TO_ORIGIN).get(_RESET_STATE)
        if document is None:
            return None
        try:
            fields = json.loads(document)
            queued_at, ran_at = fields.get("queued_at"), fields.get("ran_at")
            refused = fields.get("refused")
            if not (_text(queued_at) and _text(ran_at)):
                return None
            return ResetToOrigin(queued_at, ran_at,
                                 None if refused is None else _refusal_of(refused))
        except (ValueError, TypeError, AttributeError, RecursionError):
            return None

    @staticmethod
    def forget(shelf: "Shelf") -> None:
        shelf.delete(RESET_TO_ORIGIN, _RESET_STATE)


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
    my_review_sha: str | None
    force_pushed_at: str | None
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
    assign_when_ready: ReviewerPick | None
    unpushed_commits: tuple[UnpushedCommit, ...] | None
    diverged: bool
    reset_to_origin: ResetToOrigin | None
    base: BaseStanding | None
    threads_live: frozenset[str]
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
    notice: Notice | None
    standing: ManagerStanding


class ManagerPanel(Protocol):
    def dashboard(self) -> Dashboard: ...

    def set_on_hold(self, on_hold: bool) -> ManagerRefusal | None: ...

    def carry_on(self) -> ManagerRefusal | None: ...

    def start_review(self) -> ManagerRefusal | None: ...

    def dismiss(self, until: DismissUntil) -> ManagerRefusal | None: ...

    def close(self) -> ManagerRefusal | None: ...

    def mark_ready(self) -> ManagerRefusal | None: ...

    def assign_reviewers(self, reviewers: Sequence[str],
                         detailed: str | None) -> ManagerRefusal | None: ...

    def assign_when_ready(self, reviewers: Sequence[str],
                          detailed: str | None) -> ManagerRefusal | None: ...

    def take_over(self) -> ManagerRefusal | None: ...


class ManagerWorktree(Protocol):
    def changes(self) -> str | None: ...

    def agent_output(self, lines: int) -> list[tuple[str, bool]]: ...

    def run_git(self, keys: str) -> tuple[int, list[str], float] | ManagerRefusal: ...

    def open_terminal(self, keys: str) -> ManagerRefusal | str | None: ...

    def ask(self, prompt: str) -> ManagerRefusal | str | None: ...


class ManagerPanels(Protocol):
    def of(self, pr: Pr) -> ManagerPanel: ...

    def worktree(self, pr: Pr) -> ManagerWorktree: ...


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


class PrMilestone(StrEnum):
    NEEDS_YOU = "needs-you"
    APPROVED = "approved"
    NEW_COMMIT = "new-commit"
    MERGED = "merged"
    CLOSED = "closed"
    ANY_ACTIVITY = "any-activity"


@dataclass(frozen=True)
class DeferredUntilPr:
    pr: Pr
    state: PrMilestone


@dataclass(frozen=True)
class MentionDeferral:
    deferred_at: str
    until_at: str | None
    until_pr: DeferredUntilPr | None
    head_sha: str | None = None


@dataclass(frozen=True)
class ListedMention:
    pr: Pr
    thread: str | None
    comment_id: int | None
    kind: str
    author: str
    at: str | None
    body: str
    url: str
    on_board: bool
    building: bool
    deferred: MentionDeferral | None = None


@dataclass(frozen=True)
class MentionsListing:
    searched_at: str | None
    mentions: tuple[ListedMention, ...]


NO_MENTIONS_LISTED = MentionsListing(searched_at=None, mentions=())


class MentionsList(Protocol):
    def listed(self) -> MentionsListing: ...

    def dismiss(self, pr: Pr, comment_id: int | None) -> None: ...

    def defer(self, pr: Pr, comment_id: int | None, deferral: MentionDeferral) -> None: ...

    def stop_deferring(self, pr: Pr, comment_id: int | None) -> None: ...


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


class Shelf(Protocol):
    def save(self, kind: str, key: str, document: bytes) -> None: ...

    def list(self, kind: str) -> Mapping[str, bytes | None]: ...

    def delete(self, kind: str, key: str) -> None: ...


class Shelves(Protocol):
    def of(self, pr: Pr) -> Shelf: ...


class KeptReviews(Protocol):
    def keep(self, pr: Pr, sha: str, base_branch: str | None) -> None: ...


@dataclass(frozen=True)
class FolderInUse:
    pr: Pr
    thread: str
    folder: str


class NamesMigration(Protocol):
    def migrated(self) -> bool: ...

    def in_the_way(self) -> list[FolderInUse]: ...

    def close_sessions_and_migrate(self) -> list[FolderInUse]: ...


class TourMarker(Protocol):
    def due(self) -> bool: ...

    def arm(self) -> None: ...

    def seen(self) -> None: ...


class Emojis(Protocol):
    def named(self) -> dict[str, str]: ...


class Mentionable(Protocol):
    def of(self, repo: Repo) -> list[str]: ...

    def asked_to_review(self, repo: Repo) -> dict[str, int]: ...


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
