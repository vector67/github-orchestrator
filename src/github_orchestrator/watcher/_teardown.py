import enum
import logging
from datetime import datetime
from typing import Protocol

from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.domain import Pr
from github_orchestrator.pr_event_queue import Worklist
from github_orchestrator.pr_processes import ManagerPane, PrProcesses
from github_orchestrator.pr_summaries import PrSummaries
from github_orchestrator.settings import Dismissals, Holds, ReviewerPicks
from github_orchestrator.thread_records import ThreadRecords
from github_orchestrator.watcher._config import WatcherConfig
from github_orchestrator.working_copies import CleanUp, WorkingCopies

log = logging.getLogger(__name__)


class Reason(enum.Enum):
    CLOSED = "closed"
    DISMISSED = "dismissed"


class Teardown(Protocol):
    def reap(self, pr: Pr, reason: Reason) -> bool: ...

    def waiting_for_you(self, now: datetime) -> list[Pr]: ...


def _shown(clean_up: CleanUp | None, now: datetime) -> bool:
    return clean_up is not None and (clean_up.dismissed_until is None
                                     or clean_up.dismissed_until <= now)


class ManagerLeftovers(Protocol):
    def forget(self, pr: Pr) -> bool: ...


class PrTeardown:
    def __init__(self, config: WatcherConfig, *, worklist: Worklist, pr_processes: PrProcesses,
                 working_copies: WorkingCopies, thread_records: ThreadRecords,
                 change_detection: ChangeDetection, holds: Holds,
                 dismissals: Dismissals, manager_leftovers: ManagerLeftovers,
                 summaries: PrSummaries, picks: ReviewerPicks) -> None:
        self._repos = config.repos
        self._worklist = worklist
        self._pr_processes = pr_processes
        self._working_copies = working_copies
        self._thread_records = thread_records
        self._change_detection = change_detection
        self._holds = holds
        self._dismissals = dismissals
        self._manager_leftovers = manager_leftovers
        self._summaries = summaries
        self._picks = picks

    def reap(self, pr: Pr, reason: Reason) -> bool:
        if self._manager_still_running(pr, reason):
            log.debug("reap %s (%s): agent alive and not done yet; deferring", pr, reason.value)
            return False
        repo_dir = self._repos[pr.repo].path
        if self._working_copies.asks_before_removing(repo_dir, pr, self._branch(pr)):
            log.info("reap %s (%s): its worktree holds files no agent wrote; asking before "
                     "removing it", pr, reason.value)
            return False

        ok = True
        if not self._working_copies.forget_pr(repo_dir, pr, self._branch(pr)):
            ok = False
        elif not self._thread_records.forget(pr):
            ok = False
        if reason is Reason.CLOSED and not self._pr_processes.close(pr):
            ok = False
        if not self._worklist.forget(pr):
            ok = False
        forgotten = [self._holds.forget(pr), self._manager_leftovers.forget(pr),
                     self._summaries.unwant(pr)]
        if reason is Reason.CLOSED:
            forgotten += [self._dismissals.forget(pr), self._picks.forget(pr)]
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

    def waiting_for_you(self, now: datetime) -> list[Pr]:
        return [pr for pr in self._working_copies.asked_to_clean_up()
                if pr.repo in self._repos and _shown(self._working_copies.clean_up(pr), now)]

    def _manager_still_running(self, pr: Pr, reason: Reason) -> bool:
        if reason is Reason.CLOSED and self._worklist.is_torn_down(pr):
            return False
        return self._pr_processes.manager(pr) is ManagerPane.RUNNING

    def _branch(self, pr: Pr) -> str | None:
        facts = self._change_detection.facts(pr)
        return (facts.branch if facts else None) or None
