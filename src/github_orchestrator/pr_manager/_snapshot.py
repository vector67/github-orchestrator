from dataclasses import replace

from github_orchestrator.agent_runs import LastRun, Run
from github_orchestrator.board_api import Dashboard
from github_orchestrator.board_api.interface import (
    HeldAgentSettings,
    ManagerStanding,
    Notice,
    QueuedEvent,
)
from github_orchestrator.change_detection import (
    CiStatus,
    Facts,
    ReviewerStatus,
)
from github_orchestrator.conversation import ConversationManager
from github_orchestrator.domain import ReviewerPick
from github_orchestrator.pr_manager._config import ManagerConfig
from github_orchestrator.working_copies import WrongBranch

_VERDICTS = frozenset({ReviewerStatus.APPROVED, ReviewerStatus.CHANGES_REQUESTED})


def _as_sent(facts: Facts, threads: ConversationManager) -> Facts:
    sent = None if facts.polled_at is None else threads.sent_since(facts.polled_at)
    if sent is None:
        return facts
    given, settled_at = sent
    if given is ReviewerStatus.COMMENTED and facts.my_review in _VERDICTS:
        return replace(facts, viewer_requested=False)
    return replace(facts, my_review=given, my_review_at=settled_at, viewer_requested=False)


def _my_review(state: Facts) -> str | None:
    review = state.my_review
    if review is None or review is ReviewerStatus.PENDING:
        return None
    return str(review.value)


def _ci(facts: Facts | None) -> CiStatus:
    if facts is None or facts.ci_status is None:
        return CiStatus.PENDING
    return facts.ci_status


def dashboard_of(config: ManagerConfig, facts: Facts | None, *, run: Run | None,
                 last_run: LastRun | None, queue: tuple[QueuedEvent, ...], on_hold: bool,
                 threads: ConversationManager, wrong: WrongBranch | None,
                 notice: Notice | None, hidden: bool,
                 assign_when_ready: ReviewerPick | None,
                 agent_settings: HeldAgentSettings | None) -> Dashboard:
    counts = threads.counts()
    facts = None if facts is None else _as_sent(facts, threads)
    since = None if facts is None or facts.is_author is True else facts.since_review
    return Dashboard(
        pr=config.pr,
        worktree=config.worktree,
        polled=facts is not None,
        title=None if facts is None else facts.title,
        url=(facts.url if facts else None) or None,
        branch=None if facts is None else facts.branch,
        base_branch=None if facts is None else facts.base_branch,
        ticket=None if facts is None else facts.ticket,
        author=None if facts is None or facts.author == "unknown" else facts.author,
        is_author=None if facts is None else facts.is_author,
        detailed_reviewer=None if facts is None else facts.detailed_reviewer,
        is_detailed_reviewer=facts is not None and facts.is_detailed_reviewer,
        ci=_ci(facts).value,
        review_decision=None if facts is None or facts.review_decision is None
        else facts.review_decision.value,
        my_review=None if facts is None else _my_review(facts),
        last_event_at=None if facts is None else facts.last_event_at,
        review_ready_at=None if facts is None else facts.review_ready_at,
        since_commits=None if since is None else since.commits,
        since_force_push=since is not None and since.force_push,
        since_reviews=0 if since is None else since.reviews,
        since_comments=0 if since is None else since.comments,
        since_resolved=0 if since is None else since.resolved,
        checks=() if facts is None else facts.checks,
        changed_files=None if facts is None else facts.changed_files,
        approved_by=() if facts is None else facts.approved_by,
        changes_requested_by=() if facts is None else facts.changes_requested_by,
        pending_reviewers=() if facts is None else facts.pending_reviewers,
        unresolved_threads=None if facts is None else facts.unresolved_threads,
        polled_at=None if facts is None else facts.polled_at,
        ended=facts is not None and facts.ended,
        draft=facts is not None and facts.draft,
        merge_state=None if facts is None or facts.merge_state is None
        else facts.merge_state.value,
        viewer_requested=facts is not None and facts.viewer_requested,
        mentioned=facts is not None and facts.mentioned,
        mentions=() if facts is None else facts.mentions,
        my_review_at=None if facts is None else facts.my_review_at,
        my_review_sha=None if facts is None else facts.my_review_sha,
        force_pushed_at=None if facts is None else facts.force_pushed_at,
        agents_enabled=config.agents_enabled,
        agent_name=config.agent_name,
        working_on=None if run is None else run.event_type,
        elapsed_seconds=None if run is None else run.elapsed(),
        silent_seconds=None if run is None else run.silent_for(),
        last_run_event=None if last_run is None else last_run.event_type,
        last_run_exit_code=None if last_run is None else last_run.exit_code,
        last_run_ended_at=None if last_run is None else last_run.ended_at,
        queue=queue,
        on_hold=on_hold,
        assign_when_ready=assign_when_ready,
        unpushed_commits=None,
        diverged=False,
        reset_to_origin=None,
        base=None,
        threads_live=counts.live,
        frozen_on=None if wrong is None else wrong.here,
        expected_branch=None if wrong is None else wrong.expected,
        seconds_left=None if wrong is None else wrong.seconds_left,
        run_working=wrong is not None and wrong.run_working,
        release_requested=wrong is not None and wrong.release_requested,
        agent_settings=agent_settings,
        hidden=hidden,
        importance=None,
        nudge_due=False,
        flags_changed_at=None,
        thread_rows=counts.rows,
        unreadable_threads=counts.unreadable,
        threads_listed_at=counts.listed_at,
        undismiss_command=config.undismiss_command,
        notice=notice,
        standing=ManagerStanding.STARTING,
    )
