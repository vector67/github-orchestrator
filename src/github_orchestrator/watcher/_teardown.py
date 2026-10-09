import enum
import logging
from typing import Protocol

from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.domain import Pr
from github_orchestrator.pr_event_queue import Worklist
from github_orchestrator.pr_processes import ManagerPane, PrProcesses
from github_orchestrator.settings import Boards, Dismissals, Holds
from github_orchestrator.thread_records import ThreadRecords
from github_orchestrator.watcher._config import WatcherConfig
from github_orchestrator.working_copies import WorkingCopies

log = logging.getLogger(__name__)


class Reason(enum.Enum):
    CLOSED = "closed"
    DISMISSED = "dismissed"


class Teardown(Protocol):
    def reap(self, pr: Pr, reason: Reason) -> bool: ...


class PrTeardown:
    def __init__(self, config: WatcherConfig, *, worklist: Worklist, pr_processes: PrProcesses,
                 working_copies: WorkingCopies, thread_records: ThreadRecords,
                 change_detection: ChangeDetection, holds: Holds,
                 dismissals: Dismissals, boards: Boards) -> None:
        self._repos = config.repos
        self._worklist = worklist
        self._pr_processes = pr_processes
        self._working_copies = working_copies
        self._thread_records = thread_records
        self._change_detection = change_detection
        self._holds = holds
        self._dismissals = dismissals
        self._boards = boards

    def reap(self, pr: Pr, reason: Reason) -> bool:
        if self._manager_still_running(pr, reason):
            log.debug("reap %s (%s): agent alive and not done yet; deferring", pr, reason.value)
            return False

        ok = True
        if not self._working_copies.forget_pr(self._repos[pr.repo].path, pr, self._branch(pr)):
            ok = False
        elif not self._thread_records.forget(pr):
            ok = False
        if reason is Reason.CLOSED and not self._pr_processes.close(pr):
            ok = False
        if not self._worklist.forget(pr):
            ok = False
        forgotten = [self._holds.forget(pr), self._boards.forget(pr)]
        if reason is Reason.CLOSED:
            forgotten.append(self._dismissals.forget(pr))
        if not all(forgotten):
            ok = False

        if not ok:
            log.warning("reap %s (%s): teardown incomplete; keeping state for retry",
                        pr, reason.value)
            return False

        done = (self._pr_processes.close(pr) if reason is Reason.DISMISSED
                else self._change_detection.forget(pr))
        if done:
            log.info("reap %s (%s): teardown complete", pr, reason.value)
        return done

    def _manager_still_running(self, pr: Pr, reason: Reason) -> bool:
        if reason is Reason.CLOSED and self._worklist.is_torn_down(pr):
            return False
        return self._pr_processes.manager(pr) is ManagerPane.RUNNING

    def _branch(self, pr: Pr) -> str | None:
        facts = self._change_detection.facts(pr)
        return (facts.branch if facts else None) or None
