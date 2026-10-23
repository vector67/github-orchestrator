import logging

from github_orchestrator.board_api.interface import ResetToOrigin, Shelf, Shelves
from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.domain import Pr, UtcClock
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
        try:
            self._run_if_queued(pr, self._shelves.of(pr))
        except Exception:
            log.exception("%s: the queued reset to origin raised", pr)

    def _run_if_queued(self, pr: Pr, shelf: Shelf) -> None:
        queued = ResetToOrigin.kept(shelf)
        if queued is None or queued.queued_at is None:
            return
        facts = self._change_detection.facts(pr)
        if facts is None or facts.branch is None:
            self._did_not_run(pr, shelf, "GitHub has not named the pull request's branch, "
                                         "so the worktree was left as it is")
            return
        checkout = self._working_copies.checkout(pr)
        failed = checkout.fetch(facts.base_branch)
        if failed is not None:
            self._did_not_run(pr, shelf, failed)
            return
        if ResetToOrigin.kept(shelf) != queued:
            log.info("%s: the queued reset to origin was cancelled while origin was fetched", pr)
            return
        ResetToOrigin(ran_at=self._now()).keep(shelf)
        refused = checkout.reset_to_origin(facts.branch, facts.base_branch)
        if refused is not None:
            self._did_not_run(pr, shelf, refused)
            return
        log.info("%s: the agent's run ended, so the worktree was reset to origin", pr)

    def _did_not_run(self, pr: Pr, shelf: Shelf, refused: str) -> None:
        log.warning("%s: the queued reset to origin did not run: %s", pr, refused)
        ResetToOrigin(ran_at=self._now(), refused=refused).keep(shelf)

    def _now(self) -> str:
        return self._clock().strftime(_AT)
