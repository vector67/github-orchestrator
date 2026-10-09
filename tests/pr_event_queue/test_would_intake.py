import pytest

from github_orchestrator.change_detection.fake import UnmergeableReason
from tests.change_detection.support import (
    ACCOUNT,
    THE_PR,
    disk_change_detection,
    poll,
    pr_state,
)
from tests.pr_event_queue.support import (
    activity,
    ci_failed,
    ci_succeeded,
    closed,
    head_moved,
    review_requested,
    unmergeable,
    would_intake,
)


def _whose(state_dir, is_author):
    author = ACCOUNT if is_author else "alice"
    disk_change_detection(state_dir).advance(THE_PR, poll(pr_state(author=author)), set())


def _said(tmp_path, item, *, is_author=True, agents_enabled=True):
    if is_author is not None:
        _whose(tmp_path, is_author)
    said: list[str] = []
    intake = would_intake(tmp_path, said, agents_enabled=agents_enabled)
    if item.kind == "thread-activity":
        intake.add_thread_activity(THE_PR, item)
    else:
        intake.add(THE_PR, item)
    return said


@pytest.mark.parametrize("item, is_author, agents_enabled, line", [
    (ci_failed(), True, True, "would enqueue ci-failed for {pr} — would launch an agent run"),
    (ci_failed(), True, False,
     "would enqueue ci-failed for {pr} — would start no run: agents are disabled"),
    (ci_failed(), False, True, "would enqueue ci-failed for {pr}"),
    (review_requested(), False, True,
     "would enqueue review-requested for {pr} — would launch an agent run"),
    (ci_succeeded(), True, True, "would enqueue ci-succeeded for {pr}"),
    (activity("a", "b", stale=("c",)), True, True,
     "would enqueue thread-activity (2 thread(s), 1 stale record(s)) for {pr}"),
    (head_moved("abcdef0123", "9876543210"), True, True,
     "would enqueue head-changed (abcdef0..9876543) for {pr}"),
    (closed(), True, True, "would enqueue pr-closed for {pr}"),
    (ci_failed(), None, True,
     "would enqueue ci-failed for {pr} — what it does waits for a poll to save whose PR this is"),
])
def test_an_event_that_would_be_enqueued_says_whether_it_starts_a_run(
    tmp_path, item, is_author, agents_enabled, line,
):
    assert _said(tmp_path, item, is_author=is_author, agents_enabled=agents_enabled) == [
        line.format(pr=THE_PR)]


@pytest.mark.parametrize("item, label", [
    (unmergeable(UnmergeableReason.BLOCKED), "became-unmergeable (blocked by branch protection)"),
    (unmergeable(UnmergeableReason.CONFLICTS), "became-unmergeable (conflicts)"),
    (closed(merged=False, no_longer_relevant=True), "pr-closed (no-longer-relevant)"),
])
def test_an_event_that_would_be_enqueued_is_named_with_why(tmp_path, item, label):
    assert _said(tmp_path, item, is_author=False) == [f"would enqueue {label} for {THE_PR}"]

