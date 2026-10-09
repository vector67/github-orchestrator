from collections.abc import Callable
from dataclasses import replace

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
from github_orchestrator.pr_manager._status import StatusFiles
from github_orchestrator.pr_processes import PrProcesses
from github_orchestrator.settings import Dismissals, Holds
from github_orchestrator.working_copies import WorkingCopies, WrongBranch

ConfigOf = Callable[[Pr, str], ManagerConfig]

Flags = tuple[str | None, bool, str | None, bool, int]

_STAMP = "%Y-%m-%dT%H:%M:%S.%fZ"


class DashboardSource:
    def __init__(self, config_of: ConfigOf,
                 clock: UtcClock, *, change_detection: ChangeDetection,
                 history: History, worklist: Worklist, holds: Holds,
                 dismissals: Dismissals, working_copies: WorkingCopies,
                 conversation_managers: ConversationManagerFactory, pr_processes: PrProcesses,
                 status_files: StatusFiles) -> None:
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
        self._status_files = status_files
        self._flags_seen: dict[Pr, tuple[Flags, str]] = {}

    def dashboard(self, pr: Pr) -> Dashboard:
        wrong = self._working_copies.wrong_branch(pr, now=self._clock().timestamp())
        worktree = wrong.worktree if wrong is not None else self._pr_processes.manager_path(pr) or ""
        drawn = self.drawn(self._config_of(pr, worktree), self._conversation_managers.of(pr),
                           wrong=wrong, run=None, notice=None)
        return self._status_files.laid_over(
            replace(drawn, unpushed_commits=self._unpushed(worktree, pr)))

    def drawn(self, config: ManagerConfig, threads: ConversationManager, *,
              wrong: WrongBranch | None, run: Run | None, notice: str | None) -> Dashboard:
        pr = config.pr
        facts = self._change_detection.facts(pr)
        queued = self._worklist.waiting(pr).count
        return self._stamped(dashboard_of(
            config, facts, run=run, last_run=self._history.last_run(pr), queued_events=queued,
            on_hold=self._holds.on_hold(pr), threads=threads, wrong=wrong, notice=notice,
            hidden=self._dismissals.is_hidden(pr, events_waiting=queued > 0),
        ))

    def _unpushed(self, worktree: str, pr: Pr) -> int | None:
        if not worktree:
            return None
        facts = self._change_detection.facts(pr)
        commits = self._working_copies.commits_since(worktree, None if facts is None else facts.head_sha)
        return None if commits is None else len(commits)

    def _stamped(self, dashboard: Dashboard) -> Dashboard:
        flags = (dashboard.frozen_on, dashboard.on_hold, dashboard.working_on,
                 dashboard.hidden, len(dashboard.threads_live))
        seen = self._flags_seen.get(dashboard.pr)
        if seen is None or seen[0] != flags:
            seen = (flags, self._clock().strftime(_STAMP))
            self._flags_seen[dashboard.pr] = seen
        return replace(dashboard, flags_changed_at=seen[1])
