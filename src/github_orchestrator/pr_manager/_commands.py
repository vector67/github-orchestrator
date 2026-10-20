import logging

from github_orchestrator.agent_runs import PrWork, Run
from github_orchestrator.change_detection import ChangeDetection, ReviewRequested
from github_orchestrator.domain import Monotonic
from github_orchestrator.github import PullRequests
from github_orchestrator.pr_event_queue import Intake, Worklist
from github_orchestrator.pr_manager._command_file import Command, CommandFiles
from github_orchestrator.pr_manager._config import ManagerConfig
from github_orchestrator.pr_manager._refusals import Conditions, refusal
from github_orchestrator.settings import Dismissals, Holds

log = logging.getLogger(__name__)

NOTICE_SECONDS = 4.0


class ManagerCommands:
    def __init__(self, config: ManagerConfig, monotonic: Monotonic, *, holds: Holds, dismissals: Dismissals,
                 worklist: Worklist,
                 pull_requests: PullRequests, pr_work: PrWork,
                 change_detection: ChangeDetection, intake: Intake,
                 command_files: CommandFiles) -> None:
        self._config = config
        self._monotonic = monotonic
        self._holds = holds
        self._dismissals = dismissals
        self._worklist = worklist
        self._pull_requests = pull_requests
        self._pr_work = pr_work
        self._change_detection = change_detection
        self._intake = intake
        self._command_files = command_files
        self.active_run: Run | None = None
        self._dismissed = False
        self._notice: str | None = None
        self._notice_at = 0.0

    def obey(self, *, frozen: bool) -> None:
        for pending in self._command_files.pending(self._config.pr):
            self.carry_out(pending.command, frozen=frozen)
            self._command_files.delete(pending)

    def carry_out(self, command: Command, *, frozen: bool) -> None:
        pr = self._config.pr
        if self._dismissed:
            log.info("%s: %s dropped — the manager is leaving", pr, command)
            return
        log.info("%s: %s", pr, command)
        run = self.active_run
        refused = refusal(Conditions(frozen=frozen, running=run is not None and run.is_alive()),
                          command, agents_enabled=self._config.agents_enabled)
        if refused is not None:
            log.info("%s: %s refused — %s", pr, command, refused)
            self.notify(refused)
            return
        try:
            self._act(command)
        except Exception:
            log.exception("Error carrying out %s for %s", command, pr)

    @property
    def dismissed(self) -> bool:
        return self._dismissed

    def notify(self, text: str) -> None:
        self._notice = text
        self._notice_at = self._monotonic()

    def notice(self) -> str | None:
        if self._notice is None:
            return None
        if self._monotonic() - self._notice_at >= NOTICE_SECONDS:
            self._notice = None
            return None
        return self._notice

    def _act(self, command: Command) -> None:
        match command:
            case Command.HOLD:
                self._set_on_hold(True)
            case Command.RESUME:
                self._set_on_hold(False)
            case Command.CARRY_ON:
                self._carry_on()
            case Command.START_REVIEW:
                self._start_review()
            case Command.DISMISS_UNTIL_NEXT_EVENT:
                self._dismissals.dismiss_until_next_event(self._config.pr)
                self._leave("until the next event")
            case Command.DISMISS_UNTIL_READY_FOR_REVIEW:
                self._dismissals.dismiss_until_ready_for_review(self._config.pr)
                self._leave("until ready for review")
            case Command.DISMISS_FOREVER:
                self._dismissals.dismiss_forever(self._config.pr)
                self._leave("forever")
            case Command.CLOSE:
                self._close()
            case Command.MARK_READY:
                self._mark_ready()

    def _set_on_hold(self, on_hold: bool) -> None:
        pr = self._config.pr
        self._holds.set_on_hold(pr, on_hold)
        log.info("%s: hold %s", pr, "ON" if on_hold else "OFF")

    def _start_review(self) -> None:
        pr = self._config.pr
        facts = self._change_detection.facts(pr)
        log.info("start review %s: queuing a review request", pr)
        self._intake.add(pr, ReviewRequested(title=facts.title if facts else None,
                                             url=facts.url if facts else None))

    def _carry_on(self) -> None:
        config = self._config
        pr = config.pr
        log.info("carry on %s: carrying on the last agent run", pr)
        started = self._pr_work.carry_on(config.worktree, pr)
        if isinstance(started, str):
            self.notify(started)
            return
        self.active_run = started

    def _leave(self, how_long: str) -> None:
        pr = self._config.pr
        if self.active_run is not None:
            self.active_run.terminate()
        self._worklist.drop_in_flight(pr)
        log.info("Dismissed %s %s — exiting; the watcher closes its window", pr, how_long)
        self._dismissed = True

    def _close(self) -> None:
        pr = self._config.pr
        refused = self._pull_requests.close(pr)
        if refused is not None:
            log.warning("close %s: GitHub refused — %s", pr, refused)
            self.notify(refused)
            return
        log.info("Closed %s on GitHub; the watcher tears it down on its next poll", pr)

    def _mark_ready(self) -> None:
        pr = self._config.pr
        refused = self._pull_requests.mark_ready(pr)
        if refused is not None:
            log.warning("mark ready %s: GitHub refused — %s", pr, refused)
            self.notify(refused)
            return
        log.info("Marked %s ready for review on GitHub", pr)
