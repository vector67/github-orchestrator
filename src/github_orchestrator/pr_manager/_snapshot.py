from github_orchestrator.agent_runs import LastRun, Run
from github_orchestrator.board_api import Dashboard
from github_orchestrator.board_api.interface import ManagerStanding
from github_orchestrator.change_detection import (
    CiStatus,
    Facts,
    ReviewerStatus,
    SinceReview,
)
from github_orchestrator.conversation import ConversationManager
from github_orchestrator.pr_manager._config import ManagerConfig
from github_orchestrator.working_copies import WrongBranch


def _my_review(state: Facts) -> str | None:
    review = state.my_review
    if review is None or review is ReviewerStatus.PENDING:
        return None
    return str(review.value)


def _ci(facts: Facts | None) -> CiStatus:
    if facts is None or facts.ci_status is None:
        return CiStatus.PENDING
    return facts.ci_status


def _since_review(state: Facts | None) -> SinceReview | None:
    if state is None or state.is_author is True:
        return None
    return state.since_review


def dashboard_of(config: ManagerConfig, facts: Facts | None, *, run: Run | None,
                 last_run: LastRun | None, queued_events: int, on_hold: bool,
                 threads: ConversationManager, wrong: WrongBranch | None,
                 notice: str | None, hidden: bool) -> Dashboard:
    counts = threads.counts()
    since = _since_review(facts)
    return Dashboard(
        pr=config.pr,
        worktree=config.worktree,
        polled=facts is not None,
        title=None if facts is None else facts.title,
        url=(facts.url if facts else None) or None,
        branch=None if facts is None else facts.branch,
        ticket=None if facts is None else facts.ticket,
        author=None if facts is None or facts.author == "unknown" else facts.author,
        is_author=None if facts is None else facts.is_author,
        detailed_reviewer=None if facts is None else facts.detailed_reviewer,
        is_detailed_reviewer=facts is not None and facts.is_detailed_reviewer,
        ci=_ci(facts).value,
        mergeable=facts is not None and bool(facts.mergeable),
        needs_rebase=facts is not None and facts.needs_rebase,
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
        failed_checks=() if facts is None else facts.failed_checks,
        checks_done=0 if facts is None else facts.checks_done,
        checks_total=0 if facts is None else facts.checks_total,
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
        agents_enabled=config.agents_enabled,
        agent_name=config.agent_name,
        working_on=None if run is None else run.event_type,
        elapsed_seconds=None if run is None else run.elapsed(),
        silent_seconds=None if run is None else run.silent_for(),
        last_run_event=None if last_run is None else last_run.event_type,
        last_run_exit_code=None if last_run is None else last_run.exit_code,
        last_run_ended_at=None if last_run is None else last_run.ended_at,
        queued_events=queued_events,
        on_hold=on_hold,
        unpushed_commits=None,
        threads_queued=counts.queued,
        threads_live=counts.live,
        threads_proposed=counts.proposed,
        threads_drafts=counts.drafts,
        frozen_on=None if wrong is None else wrong.here,
        expected_branch=None if wrong is None else wrong.expected,
        seconds_left=None if wrong is None else wrong.seconds_left,
        run_working=wrong is not None and wrong.run_working,
        release_requested=wrong is not None and wrong.release_requested,
        hidden=hidden,
        flags_changed_at=None,
        thread_rows=counts.rows,
        unreadable_threads=counts.unreadable,
        threads_listed_at=counts.listed_at,
        undismiss_command=config.undismiss_command,
        notice=notice,
        standing=ManagerStanding.STARTING,
    )
