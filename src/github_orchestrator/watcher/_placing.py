import logging
from typing import Protocol

from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.domain import Pr, UtcClock
from github_orchestrator.pr_event_queue import Queues, Worklist
from github_orchestrator.pr_processes import ManagerPane, PrProcesses
from github_orchestrator.settings import Boards, Dismissals
from github_orchestrator.watcher._config import WatcherConfig
from github_orchestrator.working_copies import WorkingCopies

log = logging.getLogger(__name__)


class Placement(Protocol):
    def ensure(self, pr: Pr, *, fetch: bool = False) -> None: ...

    def revive_pending(self) -> None: ...


class WindowPlacement:
    def __init__(self, config: WatcherConfig, clock: UtcClock, *,
                 worklist: Worklist, queues: Queues, pr_processes: PrProcesses,
                 working_copies: WorkingCopies, change_detection: ChangeDetection,
                 dismissals: Dismissals, boards: Boards) -> None:
        self._repos = config.repos
        self._clock = clock
        self._worklist = worklist
        self._queues = queues
        self._pr_processes = pr_processes
        self._working_copies = working_copies
        self._change_detection = change_detection
        self._dismissals = dismissals
        self._boards = boards

    def ensure(self, pr: Pr, *, fetch: bool = False) -> None:
        if self._dismissals.is_hidden(pr, events_waiting=bool(self._worklist.waiting(pr).count)):
            if (not self._dismissals.is_dismissed_forever(pr)
                    and self._pr_processes.manager(pr) is ManagerPane.EXITED):
                log.info("ensure_pr_window %s: dismissed and its manager has exited; "
                         "closing its window", pr)
                self._pr_processes.close(pr)
            else:
                log.debug("ensure_pr_window %s: dismissed; skipping", pr)
            return
        facts = self._change_detection.facts(pr)
        if facts is None or facts.is_author is None:
            log.info("ensure_pr_window %s: whose PR this is is not known yet; "
                     "leaving its window for the next cycle", pr)
            return
        is_author = facts.is_author

        log.debug("ensure_pr_window %s (is_author=%s)", pr, is_author)
        branch = facts.branch or None
        manager = self._pr_processes.manager(pr)
        if manager is not ManagerPane.NO_WINDOW:
            if self._handled_mismatch(pr, manager is ManagerPane.RUNNING, branch):
                return
            if fetch and branch:
                self._working_copies.fetch_pr_branch(self._repos[pr.repo].path, pr, branch,
                                                     facts.base_branch)
            self._pr_processes.revive(pr)
            return

        worktree = self._working_copies.pr_worktree(self._repos[pr.repo].path, pr, branch,
                                                    facts.base_branch, fetch=fetch)
        if worktree is None:
            return
        sharing = self._working_copies.verdict(pr, worktree, now=self._clock().timestamp(),
                                               window_open=False,
                                               others=self._other_windows(pr))
        if sharing is not None and not sharing.hands_off:
            return
        self._boards.board_port(pr)
        self._pr_processes.open(pr, worktree)

    def revive_pending(self) -> None:
        worklist = self._worklist
        for queue in self._queues.queues():
            pr = queue.pr
            if pr.repo not in self._repos:
                continue
            manager = self._pr_processes.manager(pr)
            manager_alive = manager in (ManagerPane.RUNNING, ManagerPane.UNREADABLE)

            if not manager_alive:
                worklist.recover(pr)

            if not worklist.waiting(pr).count:
                continue

            if manager is ManagerPane.NO_WINDOW:
                log.warning(
                    "Pending events for %s but no window registered; skipping",
                    pr,
                )
                continue

            if manager_alive:
                continue

            log.info(
                "Reviving dead agent manager for %s (pane=%s, has pending events)",
                pr,
                manager.value,
            )
            self.ensure(pr)

    def _handled_mismatch(self, pr: Pr, manager_running: bool,
                          branch: str | None) -> bool:
        pane = self._pr_processes.manager_path(pr) if manager_running and branch else None
        verdict = self._working_copies.verdict(pr, pane, now=self._clock().timestamp(), window_open=True,
                                               manager_running=manager_running,
                                               expected=branch)
        if verdict is None:
            return False
        if not verdict.hands_off:
            log.info(
                "ensure_pr_window %s: %s — leaving it alone (%.0fs of grace left, "
                "run_working=%s)",
                pr, verdict.trouble, verdict.seconds_left, verdict.run_working,
            )
            return True
        log.error("ensure_pr_window %s: %s — detaching its window", pr, verdict.trouble)
        defunct_name = self._pr_processes.detach(pr)
        if defunct_name is None:
            return True
        self._working_copies.handed_off(pr, defunct_name)
        return True

    def _other_windows(self, pr: Pr) -> dict[Pr, str]:
        windows = {}
        for other in self._change_detection.tracked():
            if other == pr:
                continue
            path = self._pr_processes.manager_path(other)
            if path is not None:
                windows[other] = path
        return windows
