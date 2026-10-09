from dataclasses import replace
from datetime import datetime, timezone

from github_orchestrator.change_detection import Poll
from github_orchestrator.github import PullRequestState, ReviewState
from github_orchestrator.github.fake import Check, PushEvent, Review
from github_orchestrator.settings.fake import Settings
from tests.change_detection.support import ACCOUNT
from tests.pr_manager.support import POLLED_AT, polled

Seen = tuple[Poll, ...]

BRANCH = "PROJ-34-remove-changes"
REVIEWED_AT = "2026-06-09T12:00:00Z"


def _at_the_last_event() -> datetime:
    return datetime(2026, 6, 10, 10, 30, tzinfo=timezone.utc)


def _passed(check: Check) -> Check:
    return replace(check, status="completed", conclusion="success")


_CHECKS = (
    Check("unit-tests", "completed", "failure", "https://ci/unit", "2 failed"),
    Check("lint", "completed", "success", "https://ci/lint", "ok"),
    Check("e2e", "in_progress", None, "https://ci/e2e", None),
)

_POLLED = PullRequestState(
    title="Remove the changes field", url="https://github.com/o/n/pull/1", author=ACCOUNT,
    branch=BRANCH, base_branch="main", head_sha="abc123",
    body="Detailed reviewer: @carol", changed_files=12, additions=40, deletions=7,
    mergeable=False, mergeable_state="unstable", checks=_CHECKS,
    reviews=(Review("bob", ReviewState.CHANGES_REQUESTED), Review("carol", ReviewState.APPROVED)),
    review_decision="CHANGES_REQUESTED", pending_reviewers=("dave",),
    ready_for_review_at="2026-06-09T08:00:00Z",
)

_REVIEWED = replace(
    _POLLED, author="alice", body="Detailed reviewer: @octocat", mergeable=True,
    mergeable_state="blocked", checks=tuple(_passed(check) for check in _CHECKS),
    review_decision=None, pending_reviewers=("dave", "erin"),
)

_MY_APPROVAL = Review(ACCOUNT, ReviewState.APPROVED, REVIEWED_AT, "abc000")


def polled_pr(*, unresolved: int = 3, **state: object) -> Seen:
    return (Poll(replace(_POLLED, **state), POLLED_AT, unresolved_thread_count=unresolved),)


def reviewed(*, force_push: bool = False, **state: object) -> Seen:
    before = replace(_REVIEWED, head_sha="abc000", reviews=(_MY_APPROVAL,))
    pushes = (PushEvent("committed", "2026-06-09T15:00:00Z"),
              PushEvent("committed", "2026-06-09T16:00:00Z"))
    if force_push:
        pushes += (PushEvent("head_ref_force_pushed", "2026-06-09T17:00:00Z"),)
    after = replace(_REVIEWED, push_events=pushes, reviews=(
        _MY_APPROVAL,
        Review("bob", ReviewState.CHANGES_REQUESTED, "2026-06-09T13:00:00Z"),
        Review("bob", ReviewState.DISMISSED, "2026-06-09T13:30:00Z"),
        Review("bob", ReviewState.COMMENTED, "2026-06-09T14:00:00Z"),
    ), **state)
    return (Poll(before, POLLED_AT, unresolved_thread_count=2),
            Poll(after, POLLED_AT, unresolved_thread_count=1, comments_by_others=4))


POLLED = polled_pr()

WAITING_ON_REVIEW = polled_pr(
    unresolved=0, checks=tuple(_passed(check) for check in _CHECKS), mergeable=True,
    mergeable_state="blocked", review_decision=None, reviews=(),
    pending_reviewers=("grace",))

REVIEWED = reviewed()


def seed(settings: Settings, seen: Seen) -> None:
    polled(settings, *seen, now=_at_the_last_event)
