import logging
from collections.abc import Callable
from typing import Any

from github_orchestrator.agent_runs import PrWork, Run
from github_orchestrator.board_api.interface import Notice, NoticeCode
from github_orchestrator.change_detection import ChangeDetection, Facts, ReviewRequested
from github_orchestrator.domain import Monotonic, ReviewerPick
from github_orchestrator.github import PullRequests
from github_orchestrator.pr_event_queue import Intake, Worklist
from github_orchestrator.pr_manager._command_file import Command, CommandFiles
from github_orchestrator.pr_manager._config import ManagerConfig
from github_orchestrator.pr_manager._refusals import Conditions, refusal
from github_orchestrator.settings import Dismissals, Holds, ReviewerPicks

log = logging.getLogger(__name__)

NOTICE_SECONDS = 4.0
CLOSE_UNDO_SECONDS = 10.0


class ManagerCommands:
    def __init__(self, config: ManagerConfig, monotonic: Monotonic, *, holds: Holds, dismissals: Dismissals,
                 worklist: Worklist,
                 pull_requests: PullRequests, pr_work: PrWork,
                 change_detection: ChangeDetection, intake: Intake,
                 command_files: CommandFiles, picks: ReviewerPicks) -> None:
        self._config = config
        self._picks = picks
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
        self._notice: Notice | None = None
        self._notice_at = 0.0
        self._closed_at: float | None = None

    def obey(self, *, frozen: bool, agents_held: Callable[[], bool]) -> None:
        for pending in self._command_files.pending(self._config.pr):
            self.carry_out(pending.command, frozen=frozen, agents_held=agents_held(),
                           fields=pending.fields)
            self._command_files.delete(pending)

    def carry_out(self, command: Command, *, frozen: bool, agents_held: bool,
                  fields: dict[str, Any] | None = None) -> None:
        pr = self._config.pr
        if self._dismissed:
            log.info("%s: %s dropped — the manager is leaving", pr, command)
            return
        log.info("%s: %s", pr, command)
        run = self.active_run
        refused = refusal(Conditions(frozen=frozen, running=run is not None and run.is_alive(),
                                     answering=True, agents_held=agents_held),
                          command, agents_enabled=self._config.agents_enabled)
        if refused is not None:
            log.info("%s: %s refused — %s", pr, command, refused)
            self.notify(Notice(NoticeCode(refused.value)))
            return
        try:
            self._act(command, fields or {})
        except Exception:
            log.exception("Error carrying out %s for %s", command, pr)

    @property
    def dismissed(self) -> bool:
        return self._dismissed

    def notify(self, notice: Notice) -> None:
        self._notice = notice
        self._notice_at = self._monotonic()

    def notice(self) -> Notice | None:
        if self._notice is None:
            return None
        if self._monotonic() - self._notice_at >= NOTICE_SECONDS:
            self._notice = None
            return None
        return self._notice

    def _act(self, command: Command, fields: dict[str, Any]) -> None:
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
            case Command.REOPEN:
                self._reopen()
            case Command.MARK_READY:
                self._mark_ready()
            case Command.CONVERT_TO_DRAFT:
                self._convert_to_draft()
            case Command.ASSIGN_REVIEWERS:
                self._assign_reviewers(fields["reviewers"], fields["detailed"])
            case Command.ASSIGN_WHEN_READY:
                self._assign_when_ready(ReviewerPick(tuple(fields["reviewers"]),
                                                     fields["detailed"]))
            case Command.TAKE_OVER:
                self._change_detection.take_over(self._config.pr)
                log.info("%s: taken over — treated as yours from now on", self._config.pr)
            case Command.HAND_BACK:
                self._change_detection.end_take_over(self._config.pr)
                log.info("%s: handed back — its author's again", self._config.pr)

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
        facts = self._change_detection.facts(pr)
        started = self._pr_work.carry_on(config.worktree, pr,
                                         yours=facts is not None and facts.is_author is True)
        if isinstance(started, str):
            self.notify(Notice(NoticeCode.AGENT_WONT_START, started))
            return
        self.active_run = started

    def _leave(self, how_long: str) -> None:
        pr = self._config.pr
        if self.active_run is not None:
            self.active_run.terminate()
        self._worklist.drop_in_flight(pr)
        log.info("Dismissed %s %s — exiting; the watcher closes its record", pr, how_long)
        self._dismissed = True

    def _close(self) -> None:
        pr = self._config.pr
        refused = self._pull_requests.close(pr)
        if refused is not None:
            log.warning("close %s: GitHub refused — %s", pr, refused)
            self.notify(Notice(NoticeCode.CLOSE_REFUSED, refused))
            return
        self._closed_at = self._monotonic()
        log.info("Closed %s on GitHub; the watcher tears it down on its next poll", pr)

    def keeps_the_close(self) -> bool:
        return (self._closed_at is not None
                and self._monotonic() - self._closed_at < CLOSE_UNDO_SECONDS)

    def _reopen(self) -> None:
        pr = self._config.pr
        refused = self._pull_requests.reopen(pr)
        if refused is not None:
            log.warning("reopen %s: GitHub refused — %s", pr, refused)
            self.notify(Notice(NoticeCode.REOPEN_REFUSED, refused))
            return
        self._closed_at = None
        if self._change_detection.closing(pr):
            self._worklist.withdraw_close(pr)
            self._change_detection.reopen(pr)
            log.info("Reopened %s on GitHub and withdrew the teardown the watcher queued", pr)
            return
        log.info("Reopened %s on GitHub", pr)

    def _convert_to_draft(self) -> None:
        pr = self._config.pr
        refused = self._pull_requests.set_draft(pr, True)
        if refused is not None:
            log.warning("convert to draft %s: GitHub refused — %s", pr, refused)
            self.notify(Notice(NoticeCode.CONVERT_TO_DRAFT_REFUSED, refused))
            return
        log.info("Converted %s to a draft on GitHub", pr)

    def _mark_ready(self) -> None:
        pr = self._config.pr
        facts = self._change_detection.facts(pr)
        if facts is None or not (facts.is_author and facts.draft):
            log.info("mark ready %s: refused — not your draft", pr)
            self.notify(Notice(NoticeCode.NOT_YOUR_DRAFT))
            return
        refused = self._pull_requests.set_draft(pr, False)
        if refused is not None:
            log.warning("mark ready %s: GitHub refused — %s", pr, refused)
            self.notify(Notice(NoticeCode.MARK_READY_REFUSED, refused))
            return
        log.info("Marked %s ready for review on GitHub", pr)

    def assign_once_ready(self, facts: Facts | None) -> None:
        pr = self._config.pr
        if facts is None or facts.draft:
            return
        pick = self._picks.saved(pr)
        if pick is None:
            return
        log.info("%s: no longer a draft — asking the reviewers picked for when it is ready", pr)
        self._assign_reviewers(list(pick.reviewers), pick.detailed)
        self._picks.forget(pr)

    def _assign_when_ready(self, pick: ReviewerPick) -> None:
        pr = self._config.pr
        if not self._yours_to_assign():
            return
        self._picks.save(pr, pick)
        log.info("%s: %s to be asked to review once it is ready", pr, ", ".join(pick.reviewers))

    def _yours_to_assign(self) -> bool:
        pr = self._config.pr
        facts = self._change_detection.facts(pr)
        if facts is None or not facts.is_author:
            log.info("assign reviewers %s: refused — not yours", pr)
            self.notify(Notice(NoticeCode.NOT_YOURS_TO_ASSIGN))
            return False
        return True

    def _assign_reviewers(self, reviewers: list[str], detailed: str | None) -> None:
        pr = self._config.pr
        if not self._yours_to_assign():
            return
        refused = self._pull_requests.assign_reviewers(pr, reviewers, detailed)
        if refused is not None:
            log.warning("assign reviewers %s: GitHub refused — %s", pr, refused)
            self.notify(Notice(NoticeCode.ASSIGN_REVIEWERS_REFUSED, refused))
            return
        log.info("Asked %s to review %s on GitHub", ", ".join(reviewers), pr)
