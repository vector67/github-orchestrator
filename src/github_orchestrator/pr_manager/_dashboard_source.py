from collections.abc import Callable
from dataclasses import dataclass, replace

from github_orchestrator.agent_runs import History, Run
from github_orchestrator.board_api import Dashboard
from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.conversation import (
    ConversationManager,
    ConversationManagerFactory,
)
from github_orchestrator.domain import Pr, UtcClock
from github_orchestrator.pr_event_queue import Worklist
from github_orchestrator.pr_manager._config import ManagerConfig
from github_orchestrator.pr_manager._snapshot import dashboard_of
from github_orchestrator.pr_processes import PrProcesses
from github_orchestrator.settings import Dismissals, Holds
from github_orchestrator.working_copies import WorkingCopies, WrongBranch


@dataclass(frozen=True)
class Drawn:
    dashboard: Dashboard
    unpushed: Callable[[], int | None]

    def counted(self) -> Dashboard:
        return replace(self.dashboard, unpushed_commits=self.unpushed())


ConfigOf = Callable[[Pr, str], ManagerConfig]

Flags = tuple[str | None, bool, str | None, bool, int]

_STAMP = "%Y-%m-%dT%H:%M:%S.%fZ"


class DashboardSource:
    def __init__(self, config_of: ConfigOf,
                 clock: UtcClock, *, change_detection: ChangeDetection,
                 history: History, worklist: Worklist, holds: Holds,
                 dismissals: Dismissals, working_copies: WorkingCopies,
                 conversation_managers: ConversationManagerFactory, pr_processes: PrProcesses) -> None:
        self._config_of = config_of
        self._clock = clock
        self._change_detection = change_detection
        self._history = history
        self._worklist = worklist
        self._holds = holds
        self._dismissals = dismissals
        self._working_copies = working_copies
        self._conversation_managers = conversation_managers
        self._pr_processes = pr_processes
        self._flags_seen: dict[Pr, tuple[Flags, str]] = {}

    def dashboard(self, pr: Pr) -> Dashboard:
        wrong = self._working_copies.wrong_branch(pr, now=self._clock().timestamp())
        worktree = wrong.worktree if wrong is not None else self._pr_processes.manager_path(pr) or ""
        return self.drawn(self._config_of(pr, worktree), self._conversation_managers.of(pr),
                          wrong=wrong, run=None, notice=None).counted()

    def drawn(self, config: ManagerConfig, threads: ConversationManager, *,
              wrong: WrongBranch | None, run: Run | None, notice: str | None) -> Drawn:
        pr, worktree = config.pr, config.worktree
        facts = self._change_detection.facts(pr)
        queued = self._worklist.waiting(pr).count
        head_sha = None if facts is None else facts.head_sha

        def unpushed() -> int | None:
            if not worktree:
                return None
            commits = self._working_copies.commits_since(worktree, head_sha)
            return None if commits is None else len(commits)

        return Drawn(self._stamped(dashboard_of(
            config, facts, run=run, last_run=self._history.last_run(pr), queued_events=queued,
            on_hold=self._holds.on_hold(pr), threads=threads, wrong=wrong, notice=notice,
            hidden=self._dismissals.is_hidden(pr, events_waiting=queued > 0),
        )), unpushed)

    def _stamped(self, dashboard: Dashboard) -> Dashboard:
        flags = (dashboard.frozen_on, dashboard.on_hold, dashboard.working_on,
                 dashboard.hidden, dashboard.threads_live)
        seen = self._flags_seen.get(dashboard.pr)
        if seen is None or seen[0] != flags:
            seen = (flags, self._clock().strftime(_STAMP))
            self._flags_seen[dashboard.pr] = seen
        return replace(dashboard, flags_changed_at=seen[1])
