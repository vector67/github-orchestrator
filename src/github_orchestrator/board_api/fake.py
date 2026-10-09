from dataclasses import dataclass, field, replace

from github_orchestrator.board_api.interface import (
    NOTHING_HELD,
    CloneSpot,
    Dashboard,
    FieldRefusal,
    Held,
    ManagerStanding,
    RepoChoice,
    SetupOptions,
    SetupProgress,
    SetupRead,
    SetupWrite,
)
from github_orchestrator.domain import HubState, Pr, Repo

IDLE = Dashboard(
    pr=Pr(Repo("o", "n"), 1), worktree="/wt", polled=True,
    title="Remove the changes field", url="https://github.com/o/n/pull/1",
    branch="PROJ-34-remove-changes", ticket="PROJ-34", author="octocat", is_author=True,
    detailed_reviewer="carol", is_detailed_reviewer=False, ci="passing", mergeable=True,
    needs_rebase=False,    review_decision=None, my_review=None, last_event_at="2026-06-10T10:30:00Z",
    review_ready_at="2026-06-09T08:00:00Z", since_commits=None,
    since_force_push=False, since_reviews=0, since_comments=0, since_resolved=0,
    failed_checks=(), checks_done=4, checks_total=4, changed_files=7, approved_by=(),
    changes_requested_by=(), pending_reviewers=("carol",), unresolved_threads=0,
    polled_at="2026-06-10T10:30:00Z", ended=False, draft=False, merge_state="clean",
    viewer_requested=False, mentioned=False, mentions=(), my_review_at=None,
    agents_enabled=True,
    agent_name="Agent",
    working_on=None,
    elapsed_seconds=None, silent_seconds=None, last_run_event=None,
    last_run_exit_code=None, last_run_ended_at=None, queued_events=0, on_hold=False,
    unpushed_commits=0, threads_queued=0, threads_live=frozenset(), threads_proposed=0,
    threads_drafts=0, frozen_on=None, expected_branch=None,
    seconds_left=None, run_working=False, release_requested=False,
    hidden=False, flags_changed_at=None, thread_rows=(), unreadable_threads=(), threads_listed_at=None,
    undismiss_command="github-orchestrator undismiss --repo o/n 1",
    notice=None, standing=ManagerStanding.ANSWERING)


@dataclass
class FakeManagerPanel:
    now: Dashboard = IDLE
    changes_text: str | None = None
    output: list[tuple[str, bool]] = field(default_factory=list)
    carried_on: int = 0
    reviews_started: int = 0
    dismissed: str | None = None
    closed: int = 0
    git_answer: tuple[int, list[str], float] = (0, [], 0.1)
    ran: list[str] = field(default_factory=list)
    opened: list[str] = field(default_factory=list)
    terminal_refusal: str | None = None
    refusal: str | None = None

    def dashboard(self) -> Dashboard:
        return self.now

    def changes(self) -> str | None:
        return self.changes_text

    def agent_output(self, lines: int) -> list[tuple[str, bool]]:
        return self.output[-lines:]

    def set_on_hold(self, on_hold: bool) -> str | None:
        if self.refusal is None:
            self.now = replace(self.now, on_hold=on_hold)
        return self.refusal

    def carry_on(self) -> str | None:
        if self.refusal is None:
            self.carried_on += 1
        return self.refusal

    def start_review(self) -> str | None:
        if self.refusal is None:
            self.reviews_started += 1
        return self.refusal

    def dismiss(self, forever: bool) -> str | None:
        if self.refusal is None:
            self.dismissed = "forever" if forever else "until the next event"
        return self.refusal

    def close(self) -> str | None:
        if self.refusal is None:
            self.closed += 1
        return self.refusal

    def run_git(self, keys: str) -> tuple[int, list[str], float]:
        self.ran.append(keys)
        return self.git_answer

    def open_terminal(self, keys: str) -> str | None:
        if self.terminal_refusal is None:
            self.opened.append(keys)
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
class FakeTour:
    is_due: bool = False

    def due(self) -> bool:
        return self.is_due

    def arm(self) -> None:
        self.is_due = True

    def seen(self) -> None:
        self.is_due = False
