import logging

from github_orchestrator.agent_runs import History, LastRun, Run
from github_orchestrator.change_detection import ChangeDetection, CiFailed
from github_orchestrator.conversation import (
    ConversationManager,
    ConversationManagerFactory,
)
from github_orchestrator.domain import LocalClock
from github_orchestrator.notifications import ThreadNews
from github_orchestrator.pr_event_queue import Taken, Worklist
from github_orchestrator.pr_manager._carry_out import EventCarryOut
from github_orchestrator.pr_manager._commands import ManagerCommands
from github_orchestrator.pr_manager._config import ManagerConfig
from github_orchestrator.pr_manager._dashboard_source import DashboardSource
from github_orchestrator.pr_manager.interface import Front
from github_orchestrator.working_copies import WorkingCopies, WrongBranch

log = logging.getLogger(__name__)


def agent_status(working_on: str | None) -> str:
    return "idle" if working_on is None else f"working ({working_on})"


class ManagerLoop:
    def __init__(self, config: ManagerConfig, front: Front, commands: ManagerCommands,
                 clock: LocalClock, *,
                 thread_news: ThreadNews, events: EventCarryOut,
                 worklist: Worklist, working_copies: WorkingCopies, history: History,
                 conversation_managers: ConversationManagerFactory,
                 change_detection: ChangeDetection, dashboards: DashboardSource) -> None:
        self._config = config
        self._front = front
        self._commands = commands
        self._clock = clock
        self._thread_news = thread_news
        self._events = events
        self._worklist = worklist
        self._working_copies = working_copies
        self._history = history
        self._conversation_managers = conversation_managers
        self._change_detection = change_detection
        self._dashboards = dashboards
        self._interrupted = False
        self._should_exit = False
        self._frozen_on: str | None = None
        self._conversation_manager: ConversationManager | None = None
        self._fix_taken: tuple[Run, Taken] | None = None

    def _is_author(self) -> bool | None:
        facts = self._change_detection.facts(self._config.pr)
        return None if facts is None else facts.is_author

    def run(self) -> None:
        config = self._config
        pr = config.pr
        is_author = self._is_author()
        log.info("Agent manager started for %s in %s (role: %s)", pr, config.worktree,
                 "unknown" if is_author is None else "author" if is_author else "reviewer")
        self._worklist.recover(pr)
        interrupted = self._history.interrupted(pr)
        self._interrupted = interrupted is not None and interrupted != CiFailed.kind
        with self._front.session():
            try:
                while True:
                    try:
                        self._tick()
                    except Exception:
                        log.exception("Error in dashboard loop for %s", pr)
                    if self._should_exit:
                        log.info("Agent manager for %s exiting after pr-closed", pr)
                        break
                    self._front.wait(config.refresh_interval)
                    self._commands.obey()
                    if self._commands.dismissed:
                        log.info("Agent manager for %s exiting after its dismissal", pr)
                        break
            finally:
                active_run = self._commands.active_run
                if active_run is not None:
                    try:
                        active_run.interrupt()
                    except Exception:
                        log.exception("loop %s: interrupt during shutdown raised", pr)

    def _process_next_event(self, busy: bool = False) -> bool:
        config = self._config
        pr = config.pr
        is_author = self._is_author()
        if is_author is None:
            log.debug("loop %s: whose PR this is is not known yet — leaving the queue", pr)
            return False
        taken = self._worklist.next(pr, is_author=is_author,
                                 agents_enabled=config.agents_enabled, busy=busy)
        if taken is None:
            return False
        response = taken.response
        kind = response.event.kind
        try:
            run = self._events.carry_out(response, is_author=is_author,
                                         active_run=self._commands.active_run,
                                         conversations=self._conversations())
        except Exception:
            log.exception("Handler failed for %s event %s", pr, kind)
            taken.failed()
            return True
        if isinstance(run, str):
            log.error("loop %s: %s for %s", pr, run, kind)
            self._commands.notify(run)
            taken.failed()
            return True
        if run is not None:
            self._commands.active_run = run
        if run is not None and isinstance(response.launch, CiFailed):
            self._fix_taken = (run, taken)
        else:
            self._finish(taken, kind)
        if response.closes:
            self._should_exit = True
        return True

    def _freeze_on_wrong_branch(self, expected_branch: str | None) -> WrongBranch | None:
        config = self._config
        pr, worktree = config.pr, config.worktree
        now = self._clock().timestamp()
        run = self._commands.active_run
        verdict = self._working_copies.report_branch(
            pr, worktree, expected_branch, now=now,
            run_output_at=None if run is None else now - run.silent_for(),
        )
        if verdict is None:
            self._frozen_on = None
            return None

        if self._frozen_on != verdict.here:
            log.error(
                "%s: worktree %s has branch %s checked out, expected %s — "
                "freezing event dispatch",
                pr, worktree, verdict.here, verdict.expected,
            )
        self._frozen_on = verdict.here
        return verdict

    def _pump_active_run(self) -> None:
        pr = self._config.pr
        run = self._commands.active_run
        if run is None:
            return
        try:
            alive = run.pump()
        except Exception:
            log.exception(
                "loop %s: pump raised; abandoning run (event=%s)",
                pr, run.event_type,
            )
            try:
                run.terminate()
            except Exception:
                log.exception("loop %s: terminate after pump failure also raised", pr)
            self._run_ended(run, run.finished())
            return
        if not alive:
            log.info(
                "loop %s: agent run finished (event=%s, elapsed=%.1fs)",
                pr, run.event_type, run.elapsed(),
            )
            self._run_ended(run, run.finished())

    def _finish(self, taken: Taken, kind: str) -> None:
        try:
            taken.done()
        except OSError:
            log.exception(
                "loop %s: finishing %s raised; queue file may linger",
                self._config.pr, kind,
            )

    def _run_ended(self, run: Run, finished: LastRun) -> None:
        self._commands.active_run = None
        self._events.run_ended(run, finished)
        fix_taken, self._fix_taken = self._fix_taken, None
        if fix_taken is not None and fix_taken[0] is run:
            self._finish(fix_taken[1], CiFailed.kind)

    def _conversations(self) -> ConversationManager:
        if self._conversation_manager is None:
            self._conversation_manager = self._conversation_managers.of(self._config.pr)
        return self._conversation_manager

    def _tick(self) -> None:
        config = self._config
        pr = config.pr
        state = self._change_detection.facts(pr)

        self._pump_active_run()

        wrong = self._freeze_on_wrong_branch(state.branch if state else None)
        waiting = self._worklist.waiting(pr)
        drawn = self._dashboards.drawn(config, self._conversations(), wrong=wrong,
                                       run=self._commands.active_run,
                                       notice=self._commands.notice())
        self._commands.publish(drawn)
        if wrong is not None:
            return

        self._front.serve_board()
        dashboard = drawn.dashboard

        if self._interrupted:
            self._interrupted = False
            log.info("loop %s: the agent was interrupted by the last manager's end", pr)
            self._commands.carry_on()

        conversations = self._conversations()
        on_hold = dashboard.on_hold
        agent = agent_status(dashboard.working_on)

        conversations.tick(self._thread_news, on_hold=on_hold)

        if waiting.closing:
            log.debug(
                "loop %s: pr-closed queued — running cleanup (on_hold=%s, agent=%s)",
                pr, on_hold, agent,
            )
            self._process_next_event()
        elif on_hold:
            log.debug("loop %s: ON HOLD — skipping queue", pr)
        elif self._commands.active_run is None:
            log.debug("loop %s: agent idle, checking queue (%d pending)", pr,
                      dashboard.queued_events)
            self._process_next_event()
        else:
            log.debug(
                "loop %s: agent=%s, dispatching slot-free events only",
                pr, agent,
            )
            self._process_next_event(busy=True)
