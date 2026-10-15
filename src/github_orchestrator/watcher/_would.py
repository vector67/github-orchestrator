from collections.abc import Callable, Mapping
from datetime import datetime

from github_orchestrator.domain import HubState, Pr
from github_orchestrator.pr_event_queue import Worklist
from github_orchestrator.pr_processes import ManagerPane
from github_orchestrator.pr_summaries import PrSummaries
from github_orchestrator.settings import Dismissals
from github_orchestrator.watcher._config import WatcherConfig
from github_orchestrator.watcher._poll import Fetched
from github_orchestrator.watcher._teardown import Reason


class WouldPlace:
    def __init__(self, config: WatcherConfig, *, dismissals: Dismissals, worklist: Worklist,
                 enqueued: Callable[[Pr], int], say: Callable[[str], None]) -> None:
        self._repos = config.repos
        self._dismissals = dismissals
        self._worklist = worklist
        self._enqueued = enqueued
        self._say = say

    def ensure(self, pr: Pr, *, fetch: bool = False) -> None:
        waiting = self._worklist.waiting(pr).count + self._enqueued(pr)
        if self._dismissals.is_hidden(pr, events_waiting=bool(waiting)):
            self._say(f"would leave PR {pr.number} alone (dismissed until the next event)")
            return
        clone = self._repos[pr.repo]
        self._say(f"would open or revive PR {pr.number}'s window — a worktree for its head "
                  f"branch beside {clone.path}, running its agent manager")
        if clone.new_worktree_command:
            self._say(f"would run new_worktree_command with sh -c in a newly cut worktree: "
                      f"{clone.new_worktree_command}")

    def revive_pending(self) -> None:
        pass


class WouldTearDown:
    def __init__(self, say: Callable[[str], None]) -> None:
        self._say = say

    def reap(self, pr: Pr, reason: Reason) -> bool:
        match reason:
            case Reason.CLOSED:
                self._say(f"would reap {pr}")
            case Reason.DISMISSED:
                self._say(f"would tear down {pr} (dismissed forever)")
        return True


class WouldSave:
    def began(self, state: HubState) -> None:
        pass

    def threads_seen(self, pr: Pr, fetched: Fetched) -> None:
        pass

    def polled(self, managers: Mapping[Pr, ManagerPane]) -> None:
        pass

    def failed(self, exc: BaseException) -> None:
        pass


class WouldKeepServer:
    def __init__(self, say: Callable[[str], None]) -> None:
        self._say = say
        self._said = False

    def keep_running(self) -> None:
        if not self._said:
            self._say("would start the server if none is running")
            self._said = True


class WouldSummarise:
    def __init__(self, summaries: PrSummaries, say: Callable[[str], None]) -> None:
        self._summaries = summaries
        self._say = say

    def poll(self) -> None:
        due = self._summaries.due(set())
        if due:
            self._say(f"would summarise {due[0]}")

    def start(self, pr: Pr, *, use_github_api: bool) -> str | None:
        return "a dry run summarises nothing"

    def progress(self, pr: Pr) -> None:
        return None


class WouldDeliver:
    def deliver(self, woke_at: datetime, polled_at: datetime | None) -> None:
        pass
