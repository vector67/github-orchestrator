import logging

from github_orchestrator.domain import Pr
from github_orchestrator.pr_processes import PrProcesses
from github_orchestrator.settings import Boards, Holds
from github_orchestrator.working_copies import WorkingCopies

log = logging.getLogger(__name__)


class WatchedHoldings:
    def __init__(self, *, pr_processes: PrProcesses, holds: Holds, boards: Boards,
                 working_copies: WorkingCopies) -> None:
        self._pr_processes = pr_processes
        self._holds = holds
        self._boards = boards
        self._working_copies = working_copies

    def manager(self, pr: Pr) -> str:
        return self._pr_processes.manager(pr).value

    def board_port(self, pr: Pr) -> int | None:
        return self._boards.board_port(pr) if self._boards.board_wanted(pr) else None

    def hold(self, pr: Pr) -> None:
        self._holds.set_on_hold(pr, True)
        log.info("hub: put %s on hold", pr)

    def resume(self, pr: Pr) -> None:
        self._holds.set_on_hold(pr, False)
        log.info("hub: resumed %s", pr)

    def release(self, pr: Pr) -> bool:
        released = self._working_copies.request_release(pr)
        log.info("hub: release of %s %s", pr,
                 "requested; the next cycle keeps the old worktree aside and cuts a fresh one"
                 if released else "refused — its manager is not frozen on the wrong branch")
        return released
