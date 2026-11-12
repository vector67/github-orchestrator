from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from github_orchestrator.board_api.interface import (
    NO_MENTIONS_LISTED,
    NOTHING_HELD,
    BranchNotRenamed,
    CloneSpot,
    Dashboard,
    FieldRefusal,
    FolderInUse,
    Held,
    ManagerRefusal,
    ManagerStanding,
    MentionDeferral,
    MentionsListing,
    RepoChoice,
    SetupOptions,
    SetupProgress,
    SetupRead,
    SetupWrite,
)
from github_orchestrator.domain import (
    CiCheck,
    DismissUntil,
    HubState,
    Pr,
    Repo,
    ReviewerPick,
)

IDLE = Dashboard(
    pr=Pr(Repo("o", "n"), 1), worktree="/wt", polled=True,
    title="Remove the changes field", url="https://github.com/o/n/pull/1",
    branch="PROJ-34-remove-changes", base_branch="main", ticket="PROJ-34", author="octocat", is_author=True,
    detailed_reviewer="carol", is_detailed_reviewer=False, ci="passing",
    review_decision=None, my_review=None, last_event_at="2026-06-10T10:30:00Z",
    review_ready_at="2026-06-09T08:00:00Z", since_commits=None,
    since_force_push=False, since_reviews=0, since_comments=0, since_resolved=0,
    checks=(CiCheck("tests", passed=True, failed=False, done=True, url="https://ci/tests",
                    summary="tests passed"),), changed_files=7, approved_by=(),
    changes_requested_by=(), pending_reviewers=("carol",), unresolved_threads=0,
    polled_at="2026-06-10T10:30:00Z", ended=False, draft=False, merge_state="clean",
    viewer_requested=False, mentioned=False, mentions=(), my_review_at=None,
    my_review_sha=None, force_pushed_at=None,
    agents_enabled=True,
    agent_name="Agent",
    working_on=None,
    elapsed_seconds=None, silent_seconds=None, last_run_event=None,
    last_run_exit_code=None, last_run_ended_at=None, queue=(), on_hold=False,
    assign_when_ready=None, unpushed_commits=(), diverged=False, reset_to_origin=None, base=None, threads_live=frozenset(),
    frozen_on=None, expected_branch=None,
    seconds_left=None, run_working=False, release_requested=False,
    hidden=False, importance=None, nudge_due=False, flags_changed_at=None, thread_rows=(), unreadable_threads=(), threads_listed_at=None,
    undismiss_command="github-orchestrator undismiss --repo o/n 1",
    notice=None, standing=ManagerStanding.ANSWERING)


@dataclass
class FakeManagerPanel:
    now: Dashboard = IDLE
    changes_text: str | None = None
    output: list[tuple[str, bool]] = field(default_factory=list)
    carried_on: int = 0
    reviews_started: int = 0
    dismissed: DismissUntil | None = None
    closed: int = 0
    reopened: int = 0
    marked_ready: int = 0
    converted_to_draft: int = 0
    assigned: list[tuple[tuple[str, ...], str | None]] = field(default_factory=list)
    taken_over: int = 0
    handed_back: int = 0
    git_answer: tuple[int, list[str], float] = (0, [], 0.1)
    ran: list[str] = field(default_factory=list)
    opened: list[str] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)
    git_refusal: ManagerRefusal | None = None
    terminal_refusal: ManagerRefusal | str | None = None
    refusal: ManagerRefusal | None = None

    def dashboard(self) -> Dashboard:
        return self.now

    def changes(self) -> str | None:
        return self.changes_text

    def agent_output(self, lines: int) -> list[tuple[str, bool]]:
        return self.output[-lines:]

    def set_on_hold(self, on_hold: bool) -> ManagerRefusal | None:
        if self.refusal is None:
            self.now = replace(self.now, on_hold=on_hold)
        return self.refusal

    def carry_on(self) -> ManagerRefusal | None:
        if self.refusal is None:
            self.carried_on += 1
        return self.refusal

    def start_review(self) -> ManagerRefusal | None:
        if self.refusal is None:
            self.reviews_started += 1
        return self.refusal

    def dismiss(self, until: DismissUntil) -> ManagerRefusal | None:
        if self.refusal is None:
            self.dismissed = until
        return self.refusal

    def close(self) -> ManagerRefusal | None:
        if self.refusal is None:
            self.closed += 1
        return self.refusal

    def reopen(self) -> ManagerRefusal | None:
        if self.refusal is None:
            self.reopened += 1
        return self.refusal

    def mark_ready(self) -> ManagerRefusal | None:
        if self.refusal is None:
            self.marked_ready += 1
        return self.refusal

    def convert_to_draft(self) -> ManagerRefusal | None:
        if self.refusal is None:
            self.converted_to_draft += 1
        return self.refusal

    def assign_reviewers(self, reviewers: Sequence[str], detailed: str | None) -> ManagerRefusal | None:
        if self.refusal is None:
            self.assigned.append((tuple(reviewers), detailed))
        return self.refusal

    def assign_when_ready(self, reviewers: Sequence[str], detailed: str | None) -> ManagerRefusal | None:
        if self.refusal is None:
            self.now = replace(self.now,
                               assign_when_ready=ReviewerPick(tuple(reviewers), detailed))
        return self.refusal

    def take_over(self) -> ManagerRefusal | None:
        if self.refusal is None:
            self.taken_over += 1
        return self.refusal

    def hand_back(self) -> ManagerRefusal | None:
        if self.refusal is None:
            self.handed_back += 1
        return self.refusal

    def run_git(self, keys: str) -> tuple[int, list[str], float] | ManagerRefusal:
        if self.git_refusal is not None:
            return self.git_refusal
        self.ran.append(keys)
        return self.git_answer

    def open_terminal(self, keys: str) -> ManagerRefusal | str | None:
        if self.terminal_refusal is None:
            self.opened.append(keys)
        return self.terminal_refusal

    def ask(self, prompt: str) -> ManagerRefusal | str | None:
        if self.terminal_refusal is None:
            self.asked.append(prompt)
        return self.terminal_refusal


@dataclass
class FakeDashboards:
    prs: dict[Pr, Dashboard] = field(default_factory=dict)

    def dashboard(self, pr: Pr) -> Dashboard:
        return self.prs.get(pr) or replace(IDLE, pr=pr)


@dataclass
class FakeTold:
    now: Held = NOTHING_HELD
    hub_state: HubState | None = HubState.WATCHING

    def held(self) -> Held:
        return self.now

    def state(self) -> HubState | None:
        return self.hub_state


@dataclass
class FakeMentionsList:
    now: MentionsListing = NO_MENTIONS_LISTED
    dismissed: list[tuple[Pr, int | None]] = field(default_factory=list)
    deferred: list[tuple[Pr, int | None, MentionDeferral]] = field(default_factory=list)
    undeferred: list[tuple[Pr, int | None]] = field(default_factory=list)
    opened_for: list[tuple[Pr, int | None]] = field(default_factory=list)
    on_the_wall: list[Pr] = field(default_factory=list)

    def listed(self) -> MentionsListing:
        return self.now

    def dismiss(self, pr: Pr, comment_id: int | None) -> None:
        self.dismissed.append((pr, comment_id))

    def open(self, pr: Pr, comment_id: int | None) -> None:
        self.opened_for.append((pr, comment_id))

    def add_to_wall(self, pr: Pr) -> None:
        self.on_the_wall.append(pr)

    def defer(self, pr: Pr, comment_id: int | None, deferral: MentionDeferral) -> None:
        self.deferred.append((pr, comment_id, deferral))

    def stop_deferring(self, pr: Pr, comment_id: int | None) -> None:
        self.undeferred.append((pr, comment_id))


@dataclass
class FakeHoldings:
    frozen: set[Pr] = field(default_factory=set)
    on_hold: set[Pr] = field(default_factory=set)
    released: set[Pr] = field(default_factory=set)

    def hold(self, pr: Pr) -> None:
        self.on_hold.add(pr)

    def resume(self, pr: Pr) -> None:
        self.on_hold.discard(pr)

    def release(self, pr: Pr) -> bool:
        if pr not in self.frozen:
            return False
        self.released.add(pr)
        return True


WATCHED = SetupRead(state=HubState.WATCHING, config_path="/nonexistent/config.toml",
                    problem=None, active_account="octocat", account="octocat", repos=(),
                    options=SetupOptions("opus", True, 4), hub_port=8720, agent_name="Agent",
                    requirements=())


@dataclass
class FakeSetupDesk:
    answer: SetupRead = WATCHED

    def read(self) -> SetupRead:
        return self.answer

    def scopes(self, login: str) -> tuple[str, ...] | str:
        return ("repo",)

    def repos(self, login: str) -> list[RepoChoice] | str:
        return []

    def repo(self, login: str, repo: Repo) -> RepoChoice | str:
        return f"{login} cannot see {repo}"

    def clone(self, repo: Repo) -> CloneSpot:
        return CloneSpot(repo, f"~/repositories/{repo.name}", False, False)

    def write(self, asked: SetupWrite) -> SetupProgress | list[FieldRefusal]:
        return [FieldRefusal("config", "the fake setup desk writes nothing")]

    def progress(self, operation: str) -> SetupProgress | None:
        return None

    def move_aside(self) -> str | None:
        return None


@dataclass
class FakeEmojis:
    listed: dict[str, str] = field(default_factory=dict)

    def named(self) -> dict[str, str]:
        return self.listed


@dataclass
class FakeMentionable:
    listed: dict[Repo, list[str]] = field(default_factory=dict)
    asked: dict[Repo, dict[str, int]] = field(default_factory=dict)

    def of(self, repo: Repo) -> list[str]:
        return self.listed.get(repo, [])

    def asked_to_review(self, repo: Repo) -> dict[str, int]:
        return self.asked.get(repo, {})


@dataclass
class FakeHarvestSetup:
    answer: Path | str = Path("/nonexistent/harvest-extension")
    prepared: int = 0

    def prepare(self) -> Path | str:
        self.prepared += 1
        return self.answer


class FakeNamesMigration:
    def __init__(self, in_the_way: list[FolderInUse] | None = None,
                 not_renamed: list[BranchNotRenamed] | None = None) -> None:
        self.held = list(in_the_way or [])
        self.stuck = list(not_renamed or [])
        self.closed = 0

    def migrated(self) -> bool:
        return not self.held and not self.stuck

    def in_the_way(self) -> list[FolderInUse]:
        return list(self.held)

    def not_renamed(self) -> list[BranchNotRenamed]:
        return list(self.stuck)

    def close_sessions_and_migrate(self) -> list[FolderInUse]:
        self.closed += 1
        self.held = []
        return []


@dataclass
class FakeTour:
    is_due: bool = False

    def due(self) -> bool:
        return self.is_due

    def arm(self) -> None:
        self.is_due = True

    def seen(self) -> None:
        self.is_due = False
