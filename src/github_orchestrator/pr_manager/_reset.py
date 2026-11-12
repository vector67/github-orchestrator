import logging

from github_orchestrator.board_api.interface import (
    ResetRefusal,
    ResetRefusalCode,
    ResetToOrigin,
    Shelf,
    Shelves,
)
from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.conversation import ConversationManagerFactory
from github_orchestrator.domain import Pr, UtcClock
from github_orchestrator.pr_manager._config import ManagerConfig
from github_orchestrator.pr_manager._reset_shelf import keep_reset, kept_reset
from github_orchestrator.working_copies import WorkingCopies

log = logging.getLogger(__name__)


class QueuedReset:
    def __init__(self, config: ManagerConfig, shelves: Shelves, working_copies: WorkingCopies,
                 change_detection: ChangeDetection, clock: UtcClock,
                 conversation_managers: ConversationManagerFactory) -> None:
        self._config = config
        self._shelves = shelves
        self._working_copies = working_copies
        self._change_detection = change_detection
        self._clock = clock
        self._conversation_managers = conversation_managers

    def run_if_queued(self) -> None:
        pr = self._config.pr
        try:
            self._run_if_queued(pr, self._shelves.of(pr))
        except Exception:
            log.exception("%s: the queued reset to origin raised", pr)

    def _run_if_queued(self, pr: Pr, shelf: Shelf) -> None:
        queued = kept_reset(shelf)
        if queued is None or queued.queued_at is None:
            return
        facts = self._change_detection.facts(pr)
        if facts is None or facts.branch is None:
            self._did_not_run(pr, shelf, ResetRefusal(ResetRefusalCode.BRANCH_UNKNOWN))
            return
        checkout = self._working_copies.checkout(pr)
        if checkout.no_worktree() is not None:
            self._did_not_run(pr, shelf, ResetRefusal(ResetRefusalCode.WORKTREE_MISSING))
            return
        failed = checkout.fetch(facts.base_branch)
        if failed is not None:
            self._did_not_run(pr, shelf, ResetRefusal(ResetRefusalCode.FETCH_FAILED, failed))
            return
        seen = checkout.revisions.local_head()
        if kept_reset(shelf) != queued:
            log.info("%s: the queued reset to origin was cancelled while origin was fetched", pr)
            return
        holding = next((conversation.key
                        for conversation in self._conversation_managers.of(pr).all()
                        if conversation.fix.awaits_push), None)
        if holding is not None:
            self._did_not_run(pr, shelf, ResetRefusal(ResetRefusalCode.FIX_AWAITS_PUSH, holding))
            return
        if seen is None:
            self._did_not_run(pr, shelf, ResetRefusal(ResetRefusalCode.HEAD_UNREADABLE))
            return
        keep_reset(shelf, ResetToOrigin(
            ran_at=self._now(), refused=ResetRefusal(ResetRefusalCode.RESET_INTERRUPTED)))
        refused = checkout.reset_to_origin(facts.branch, seen)
        if refused is not None:
            self._did_not_run(pr, shelf, ResetRefusal(ResetRefusalCode(refused.code.value),
                                                      refused.detail))
            return
        keep_reset(shelf, ResetToOrigin(ran_at=self._now()))
        log.info("%s: the agent's run ended, so the worktree was reset to origin", pr)

    def _did_not_run(self, pr: Pr, shelf: Shelf, refused: ResetRefusal) -> None:
        log.warning("%s: the queued reset to origin did not run: %s %s", pr, refused.code,
                    refused.detail or "")
        keep_reset(shelf, ResetToOrigin(ran_at=self._now(), refused=refused))

    def _now(self) -> str:
        return self._clock.stamp()
