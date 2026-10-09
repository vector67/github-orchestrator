import logging
import signal
from pathlib import Path

from github_orchestrator.agent_runs import FixComment, LastRun, PrWork, Run
from github_orchestrator.change_detection import (
    BecameMergeable,
    BecameUnmergeable,
    ChangeDetection,
    CiFailed,
    CiSucceeded,
    Facts,
    HeadChanged,
    PrClosed,
    PushedSinceReview,
    ReviewDecisionChanged,
    ReviewRequested,
)
from github_orchestrator.conversation import ConversationManager, ThreadActivity
from github_orchestrator.domain import LocalClock, Pr
from github_orchestrator.notifications import PrStatus, Runs
from github_orchestrator.pr_event_queue import Intake, Launching, Response
from github_orchestrator.pr_manager._config import ManagerConfig
from github_orchestrator.pr_manager._next_move import reviewed_before
from github_orchestrator.pr_processes import AgentChanges
from github_orchestrator.working_copies import WorkingCopies

log = logging.getLogger(__name__)


def exit_word(exit_code: int | None) -> str:
    if exit_code is None:
        return "exit unknown"
    if exit_code == 0:
        return "ok"
    if exit_code > 0:
        return f"exit {exit_code}"
    try:
        return f"killed ({signal.Signals(-exit_code).name})"
    except ValueError:
        return f"killed (signal {-exit_code})"

CI_FIX_RETRIES = 3

Noted = (CiSucceeded | CiFailed | BecameUnmergeable | BecameMergeable
                | ReviewDecisionChanged | PushedSinceReview)


def _review_title(pr: Pr, review: ReviewRequested) -> str:
    return review.title or f"PR {pr.in_repo}"


def _newest_summary(conversations: ConversationManager, account: str) -> FixComment | None:
    summaries = [conversation for conversation in conversations.all()
                 if conversation.author == account and conversation.review_state is not None
                 and conversation.body.strip()]
    if not summaries:
        return None
    newest = max(summaries, key=lambda summary: summary.comment_created_at or "")
    return FixComment(newest.author, newest.body, newest.comment_created_at)


def _replied(conversations: ConversationManager,
             ) -> tuple[tuple[str | None, int | None, tuple[FixComment, ...]], ...]:
    answered = [conversations.get(key) for key in conversations.counts().answered]
    return tuple((thread.path, thread.line,
                  tuple(FixComment(comment.author, comment.body, comment.created_at)
                        for comment in thread.comments))
                 for thread in answered if thread is not None)


def _status_note(event: Noted) -> str | None:
    match event:
        case CiSucceeded():
            return f"CI passed: {', '.join(event.checks)} — all checks success."
        case CiFailed():
            return f"CI check '{event.check}' failed. Summary: {event.summary or ''}"
        case BecameUnmergeable():
            return f"PR became unmergeable: {event.reason.value}."
        case BecameMergeable():
            return f"PR became mergeable: {event.reason.value}."
        case PushedSinceReview():
            return event.pushes + "."
    return None


def _launch_note(pr: Pr, launch: Launching) -> str:
    match launch:
        case CiFailed():
            return f"CI check '{launch.check}' failed. See diagnosis output below."
        case BecameUnmergeable():
            return (f"PR became unmergeable ({launch.reason.value}). "
                    "See rebase output below.")
        case ReviewRequested():
            return (f"Review requested: \"{_review_title(pr, launch)}\". "
                    "See review findings below.")


def _disabled_note(kind: str) -> str:
    return f"Agents are disabled (agents_enabled=false) — skipped {kind}; no agent run."


class EventCarryOut:
    def __init__(self, config: ManagerConfig, clock: LocalClock, pr_status: PrStatus,
                 runs: Runs, pr_work: PrWork, change_detection: ChangeDetection,
                 agent_changes: AgentChanges, intake: Intake,
                 working_copies: WorkingCopies) -> None:
        self._pr = config.pr
        self._worktree = config.worktree
        self._account = config.account
        self._working_copies = working_copies
        self._clock = clock
        self._pr_status = pr_status
        self._runs = runs
        self._pr_work = pr_work
        self._change_detection = change_detection
        self._agent_changes = agent_changes
        self._intake = intake
        self._fixing: tuple[Run, CiFailed] | None = None

    def carry_out(self, response: Response, *, is_author: bool, active_run: Run | None,
                  conversations: ConversationManager) -> Run | str | None:
        pr, event = self._pr, response.event
        if response.launch is not None:
            if isinstance(response.launch, CiFailed) and not self._retrying(response.launch):
                return None
            self._note(_launch_note(pr, response.launch))
            if response.skipped:
                self._skipped(event.kind)
                return None
            started = self._launch(response.launch, push=not response.more_failures_wait,
                                   conversations=conversations)
            if isinstance(response.launch, CiFailed) and not isinstance(started, str):
                self._fixing = (started, response.launch)
            return started
        match event:
            case PrClosed():
                if active_run is not None:
                    active_run.terminate()
                self._pr_status.changed(pr, event)
            case ThreadActivity():
                self._absorb(event, is_author, conversations)
            case HeadChanged():
                log.debug("%s: head moved %s -> %s (force_push=%s, away_seconds=%s)",
                          pr, event.previous, event.head, event.force_push,
                          event.away_seconds)
            case (CiSucceeded() | CiFailed() | BecameUnmergeable() | BecameMergeable()
                  | ReviewDecisionChanged() | PushedSinceReview()):
                self._pr_status.changed(pr, event)
                noted = _status_note(event)
                if noted is not None:
                    self._note(noted)
        return None

    def run_ended(self, run: Run, finished: LastRun) -> None:
        fixing, self._fixing = self._fixing, None
        if finished.exit_code == 0:
            return
        self._runs.run_failed(self._pr, finished.event_type, finished.exit_code)
        if fixing is not None and fixing[0] is run:
            self._intake.add(self._pr, fixing[1].retried(exit_word(finished.exit_code)))

    def _retrying(self, failed: CiFailed) -> bool:
        if failed.retry_reason is None:
            return True
        said = f"CI fix for {failed.check} failed ({failed.retry_reason})"
        going_on = failed.attempt <= CI_FIX_RETRIES
        if going_on:
            note = f"{said}; retry {failed.attempt} of {CI_FIX_RETRIES}."
        else:
            note = f"{said} after {CI_FIX_RETRIES} retries; giving up."
        log.warning("loop %s: %s", self._pr, note)
        self._note(note)
        return going_on

    def _note(self, text: str) -> None:
        self._agent_changes.note(Path(self._worktree), text, self._clock())

    def _skipped(self, kind: str) -> None:
        self._runs.agent_skipped(self._pr, kind)
        self._note(_disabled_note(kind))

    def _launch(self, launch: Launching, *, push: bool,
                conversations: ConversationManager) -> Run | str:
        pr, worktree, kind = self._pr, self._worktree, launch.kind
        match launch:
            case CiFailed():
                return self._pr_work.fix_check(worktree, pr, kind, check=launch.check,
                                               summary=launch.summary, push=push)
            case BecameUnmergeable():
                return self._pr_work.rebase(worktree, pr, kind, reason=launch.reason.value)
            case ReviewRequested():
                facts = self._change_detection.facts(pr)
                if facts is not None and reviewed_before(facts):
                    return self._rereview(launch, facts, conversations)
                return self._pr_work.review(
                    worktree, pr, kind, title=_review_title(pr, launch), url=launch.url or "",
                    branch=(facts.branch if facts else None) or "",
                    additions=facts.additions if facts else 0,
                    deletions=facts.deletions if facts else 0)

    def _rereview(self, review: ReviewRequested, facts: Facts,
                  conversations: ConversationManager) -> Run | str:
        since = facts.since_review.sha if facts.since_review else None
        return self._pr_work.rereview(
            self._worktree, self._pr, review.kind, title=_review_title(self._pr, review),
            url=review.url or "", branch=facts.branch or "",
            verdict=facts.my_review.value if facts.my_review else "",
            said=_newest_summary(conversations, self._account), since=since,
            commits=self._working_copies.commits_since(self._worktree, since),
            replied=_replied(conversations))

    def _absorb(self, activity: ThreadActivity, is_author: bool,
                conversations: ConversationManager) -> None:
        absorbed = conversations.absorb(activity)
        if absorbed.drained:
            self._skipped(activity.kind)
            return
        if is_author and absorbed.threads:
            self._note(f"Thread activity ({absorbed.threads}): materialised "
                       f"{len(absorbed.created)} thread(s) — they are on the review board.")
        log.info("%s: materialised %d thread(s), refreshed %d",
                 self._pr, len(absorbed.created), len(absorbed.refreshed))
