import logging

from github_orchestrator.board_api.interface import ResetToOrigin, Shelves
from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.domain import UtcClock
from github_orchestrator.pr_manager._config import ManagerConfig
from github_orchestrator.working_copies import WorkingCopies

log = logging.getLogger(__name__)

_AT = "%Y-%m-%dT%H:%M:%SZ"


class QueuedReset:
    def __init__(self, config: ManagerConfig, shelves: Shelves, working_copies: WorkingCopies,
                 change_detection: ChangeDetection, clock: UtcClock) -> None:
        self._config = config
        self._shelves = shelves
        self._working_copies = working_copies
        self._change_detection = change_detection
        self._clock = clock

    def run_if_queued(self) -> None:
        pr = self._config.pr
        shelf = self._shelves.of(pr)
        kept = ResetToOrigin.kept(shelf)
        if kept is None or kept.queued_at is None:
            return
        facts = self._change_detection.facts(pr)
        refused = self._working_copies.checkout(pr).fetch(
            None if facts is None else facts.base_branch, reset=True)
        if refused is None:
            log.info("%s: the agent's run ended, so the worktree was reset to origin", pr)
        else:
            log.warning("%s: the queued reset to origin did not run: %s", pr, refused)
        ResetToOrigin(ran_at=self._clock().strftime(_AT), refused=refused).keep(shelf)
