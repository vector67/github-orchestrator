import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from github_orchestrator.change_detection._review_activity import (
    compute_review_activity,
)
from github_orchestrator.change_detection._stored import (
    Words,
    mentions_of,
    stored_mentions,
    words_of,
)
from github_orchestrator.change_detection._unmergeable import (
    REBASE_STATES,
    UNMERGEABLE,
)
from github_orchestrator.change_detection.interface import (
    BecameMergeable,
    CiFailed,
    CiStatus,
    CiSucceeded,
    HeadChanged,
    Mergeability,
    MergeableReason,
    Poll,
    PrClosed,
    PrEvent,
    PushedSinceReview,
    ReviewDecision,
    ReviewDecisionChanged,
    ReviewerStatus,
    ReviewRequested,
)
from github_orchestrator.domain import Pr
from github_orchestrator.github import PullRequestState, ReviewState

_STATUS_OF = {
    ReviewState.APPROVED: ReviewerStatus.APPROVED,
    ReviewState.CHANGES_REQUESTED: ReviewerStatus.CHANGES_REQUESTED,
    ReviewState.COMMENTED: ReviewerStatus.COMMENTED,
    ReviewState.DISMISSED: ReviewerStatus.DISMISSED,
    ReviewState.PENDING: ReviewerStatus.PENDING,
}

_VERDICTS = frozenset({ReviewerStatus.APPROVED, ReviewerStatus.CHANGES_REQUESTED})


@dataclass(frozen=True)
class Step:
    snapshot: dict[str, Any]
    events: list[PrEvent]


def _ci_status(poll: Poll) -> CiStatus:
    checks = poll.state.checks
    done = [c for c in checks if c.done]
    if any(c.failed for c in done):
        return CiStatus.FAILING
    if done and len(done) == len(checks) and all(c.passed for c in done):
        return CiStatus.PASSING
    return CiStatus.PENDING


def _mergeability(state: PullRequestState) -> Mergeability:
    if state.conflicts:
        return Mergeability.CONFLICTS
    if state.checks_failing:
        return Mergeability.CHECKS_FAILING
    if state.behind_base:
        return Mergeability.BEHIND
    if state.blocked:
        return Mergeability.BLOCKED
    if state.merges_cleanly:
        return Mergeability.CLEAN
    if not state.mergeability_known:
        return Mergeability.UNKNOWN
    return Mergeability.OTHER


def _review_decision(state: PullRequestState) -> ReviewDecision | None:
    if state.approved:
        return ReviewDecision.APPROVED
    if state.changes_requested:
        return ReviewDecision.CHANGES_REQUESTED
    if state.review_required:
        return ReviewDecision.REVIEW_REQUIRED
    return None


def snapshot_of(pr: Pr, poll: Poll, old: dict[str, Any] | None, *,
                account: str) -> dict[str, Any]:
    state = poll.state

    latest_reviewer = None
    reviewer_status: dict[str, ReviewerStatus] = {}
    my_review_at = None
    for review in state.reviews:
        login = review.author
        if not (login and review.state):
            continue
        status = _STATUS_OF[review.state]
        if status is ReviewerStatus.COMMENTED and reviewer_status.get(login) in _VERDICTS:
            continue
        reviewer_status[login] = status
        if login == account:
            my_review_at = review.submitted_at
    actionable = [r for r in state.reviews
                  if r.state is None or _STATUS_OF[r.state] is not ReviewerStatus.COMMENTED]
    if actionable:
        latest_reviewer = actionable[-1].author

    detailed_reviewer_match = re.search(
        r"^\s*[Dd]etailed [Rr]eviewer:\s*@(\S+)", state.body, re.MULTILINE,
    )
    detailed_reviewer = detailed_reviewer_match.group(1) if detailed_reviewer_match else None
    is_detailed_reviewer = detailed_reviewer == account

    is_author_pr = state.author == account

    activity = compute_review_activity(
        account=account,
        is_author=is_author_pr,
        state=state,
        my_last_comment_at=poll.my_last_comment_at,
        comments_by_others=poll.comments_by_others,
        unresolved_thread_count=poll.unresolved_thread_count,
        old_state=old,
    )

    decision = _review_decision(state)
    mentions = mentions_of(old or {}) if poll.mentions is None else poll.mentions
    return {
        "repo": str(pr.repo),
        "pr": pr.number,
        "title": state.title,
        "url": state.url,
        "branch": state.branch,
        "base_branch": state.base_branch,
        "pr_author": state.author,
        "changed_files": state.changed_files,
        "additions": state.additions,
        "deletions": state.deletions,
        "head_sha": state.head_sha,
        "mergeable": state.mergeable,
        "mergeable_state": _mergeability(state).value,
        "draft": state.draft,
        "last_poll_timestamp": poll.polled_at,
        "ci_status": _ci_status(poll).value,
        "review_ready_at": state.ready_for_review_at,
        "checks": [
            {
                "name": c.name,
                "passed": c.passed,
                "failed": c.failed,
                "done": c.done,
                "html_url": c.html_url,
                "summary": c.summary,
            }
            for c in state.checks
        ],
        "review_decision": None if decision is None else decision.value,
        "latest_reviewer": latest_reviewer,
        "reviewer_status": {login: status.value for login, status in reviewer_status.items()},
        "pending_reviewers": list(state.pending_reviewers),
        "review_requested": poll.review_requested,
        "unresolved_thread_count": poll.unresolved_thread_count,
        "is_author": is_author_pr,
        **activity,
        "detailed_reviewer": detailed_reviewer,
        "is_detailed_reviewer": is_detailed_reviewer,
        "my_review_at": my_review_at,
        "mentions": stored_mentions(mentions),
        "mentioned": poll.mentioned or bool(mentions) or bool((old or {}).get("mentioned")),
    }


def _seconds_away(old: dict[str, Any], new: dict[str, Any],
                  poll_interval: int) -> int | None:
    before = old.get("last_poll_timestamp")
    after = new.get("last_poll_timestamp")
    if not before or not after:
        return None
    try:
        gap = datetime.fromisoformat(after) - datetime.fromisoformat(before)
    except (TypeError, ValueError):
        return None
    seconds = int(gap.total_seconds())
    return seconds if seconds > 2 * poll_interval else None


def _mergeable_reason(old: Words, new: Words) -> MergeableReason:
    if old.mergeability is Mergeability.CONFLICTS:
        return MergeableReason.CONFLICTS_RESOLVED
    if (old.decision is not ReviewDecision.APPROVED
            and new.decision is ReviewDecision.APPROVED):
        return MergeableReason.APPROVED
    if old.ci is not CiStatus.PASSING and new.ci is CiStatus.PASSING:
        return MergeableReason.CI_PASSED
    if old.mergeability in (Mergeability.UNKNOWN, None):
        return MergeableReason.STATUS_RESOLVED
    return MergeableReason.UNKNOWN


def diff_state(old: dict[str, Any],
               new: dict[str, Any], *, poll_interval: int) -> list[PrEvent]:
    events: list[PrEvent] = []
    was, now = words_of(old), words_of(new)

    if was.ci is not CiStatus.PASSING and now.ci is CiStatus.PASSING:
        events.append(CiSucceeded(tuple(check["name"] for check in new.get("checks", []))))

    left_good_state = (
        was.mergeability not in UNMERGEABLE and now.mergeability in UNMERGEABLE
    )
    entered_rebase_actionable = (
        now.mergeability in REBASE_STATES
        and was.mergeability not in REBASE_STATES
    )
    if left_good_state or entered_rebase_actionable:
        events.append(UNMERGEABLE[now.mergeability])

    if was.mergeability is not Mergeability.CLEAN and now.mergeability is Mergeability.CLEAN:
        events.append(BecameMergeable(_mergeable_reason(was, now)))

    if was.decision is not now.decision:
        events.append(ReviewDecisionChanged(
            before=was.decision,
            after=now.decision,
            reviewer=new.get("latest_reviewer", ""),
        ))

    if (
        new.get("review_anchor_sha")
        and new.get("head_sha")
        and old.get("head_sha") != new.get("head_sha")
        and (new.get("since_anchor_commits", 0) > 0 or new.get("since_anchor_force_push"))
    ):
        events.append(PushedSinceReview(
            commits=new.get("since_anchor_commits", 0),
            force_push=new.get("since_anchor_force_push", False),
        ))

    if (
        not new.get("is_author")
        and old.get("head_sha")
        and new.get("head_sha")
        and old.get("head_sha") != new.get("head_sha")
    ):
        events.append(HeadChanged(
            previous=old["head_sha"],
            head=new["head_sha"],
            force_push=bool(new.get("since_anchor_force_push")),
            away_seconds=_seconds_away(old, new, poll_interval),
        ))

    return events


def diff_ci_failures(
    old_state: dict[str, Any],
    current: dict[str, Any],
    pending_checks: set[str],
) -> tuple[list[PrEvent], dict[str, str]]:
    head = current.get("head_sha")
    handled = dict(old_state.get("ci_failure_handled", {}))
    checks = current.get("checks", [])

    keep = {c["name"] for c in checks if not c.get("passed")}
    handled = {name: sha for name, sha in handled.items() if name in keep}

    events: list[PrEvent] = []
    for check in checks:
        if not check.get("failed"):
            continue
        name = check["name"]
        if handled.get(name) == head:
            continue
        if name in pending_checks:
            handled[name] = head
            continue
        events.append(CiFailed(check=name, summary=check.get("summary")))
        handled[name] = head
    return events, handled


def _requested(old: dict[str, Any] | None, poll: Poll) -> list[PrEvent]:
    lapsed = old is None or old.get("review_requested") is False
    if lapsed and poll.review_requested:
        return [ReviewRequested(title=poll.state.title, url=poll.state.url)]
    return []


def _initial_events(current: dict[str, Any]) -> list[PrEvent]:
    state = words_of(current).mergeability
    return [UNMERGEABLE[state]] if state in UNMERGEABLE else []


def _carry_known_mergeability(old: dict[str, Any] | None, current: dict[str, Any]) -> None:
    if (
        old
        and words_of(current).mergeability is Mergeability.UNKNOWN
        and words_of(old).mergeability not in (None, Mergeability.UNKNOWN)
    ):
        current["mergeable_state"] = old["mergeable_state"]
        current["mergeable"] = old.get("mergeable", False)


def advance(
    pr: Pr, old: dict[str, Any] | None, poll: Poll, pending_ci_checks: set[str],
    now: str, *, account: str, poll_interval: int,
) -> Step:
    current = snapshot_of(pr, poll, old, account=account)
    _carry_known_mergeability(old, current)

    if old is None:
        events = _initial_events(current)
    else:
        events = diff_state(old, current, poll_interval=poll_interval)

    ci_events, ci_handled = diff_ci_failures(old or {}, current, pending_ci_checks)
    events.extend(ci_events)
    current["ci_failure_handled"] = ci_handled

    if events:
        current["last_event_at"] = now
    elif old and "last_event_at" in old:
        current["last_event_at"] = old["last_event_at"]

    return Step(snapshot=current, events=_requested(old, poll) + events)


def ended(*, still_open: bool, merged: bool) -> PrClosed:
    if still_open:
        return PrClosed(merged=False, no_longer_relevant=True)
    return PrClosed(merged=merged)


def closing(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    return {**(snapshot or {}), "pending_teardown": True}


def is_closing(snapshot: dict[str, Any] | None) -> bool:
    return bool(snapshot and snapshot.get("pending_teardown"))
