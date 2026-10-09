from collections.abc import Callable, Sequence
from datetime import datetime

from github_orchestrator.domain import Pr
from github_orchestrator.pr_event_queue import Worklist
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
    def threads_seen(self, pr: Pr, fetched: Fetched) -> None:
        pass

    def polled(self) -> None:
        pass

    def failed(self, exc: BaseException) -> None:
        pass


class WouldServeHub:
    def __init__(self, say: Callable[[str], None]) -> None:
        self._say = say

    def start(self, port: int, holdings: object, state: object) -> str:
        self._say(f"would serve the hub on port {port}")
        return f"port {port}, not served on a dry run"

    def show(self, prs: Sequence[Pr]) -> None:
        pass

    def stop(self) -> bool:
        return False


class WouldDeliver:
    def deliver(self, woke_at: datetime, polled_at: datetime | None) -> None:
        pass
