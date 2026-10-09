from datetime import datetime, timedelta, timezone

from github_orchestrator.change_detection import (
    ReviewDecisionChanged,
)
from github_orchestrator.change_detection.fake import ReviewDecision
from github_orchestrator.github import ReviewState
from github_orchestrator.github.fake import Check, PushEvent, Review
from tests.builders import a_pr
from tests.change_detection.support import (
    ACCOUNT,
    POLLED_AT,
    PR,
    REPO,
    failing,
    passing,
    poll,
    pr_state,
    types,
)

THE_PR = a_pr(PR, REPO)

OTHER = "alice"
REVIEWED_AT = "2026-09-20T00:00:00Z"
AFTER_REVIEW = "2026-09-21T00:00:00Z"
MY_REVIEW = Review(ACCOUNT, ReviewState.CHANGES_REQUESTED, REVIEWED_AT, "sha1")


def _state(ci="success", **fields):
    checks = {"success": (passing(),), "failure": (failing(),), "pending": ()}[ci]
    return pr_state(checks=checks, **fields)


def _changes(detection, old, new, *, old_at=POLLED_AT, new_at=POLLED_AT):
    detection.advance(THE_PR, poll(old, at=old_at), set())
    return detection.advance(THE_PR, poll(new, at=new_at), set())


def _of(events, event_type):
    return [e for e in events if e.kind == event_type]


def test_a_failing_check_raises_its_own_event_and_no_aggregate_one(detection):
    events = _changes(detection,
                      _state(review_decision="APPROVED"),
                      _state("failure", mergeable_state="unstable", review_decision="APPROVED"))

    assert [e.check for e in _of(events, "ci-failed")] == ["tests"]
    assert _of(events, "became-unmergeable") == []


def test_checks_still_running_on_an_unstable_pr_raise_nothing(detection):
    events = _changes(detection,
                      _state(mergeable_state="clean", review_decision="APPROVED"),
                      _state("pending", mergeable_state="unstable", review_decision="APPROVED"))

    assert events == []


def test_a_pr_falling_behind_its_base_is_unmergeable_for_the_base(detection):
    events = _changes(detection, _state(review_decision="APPROVED"),
                      _state(mergeable_state="behind", review_decision="APPROVED"))

    assert [e.reason.value for e in _of(events, "became-unmergeable")] == [
        "base-updated"]


def test_ci_turning_green_raises_ci_succeeded_with_the_checks(detection):
    events = _changes(detection, _state("failure"), _state("success"))

    [succeeded] = _of(events, "ci-succeeded")
    assert succeeded.checks == ("tests",)


def test_a_conflict_raises_became_unmergeable(detection):
    events = _changes(detection, _state(), _state(mergeable=False, mergeable_state="dirty"))

    assert [(e.reason.value, e.rebase) for e in _of(events, "became-unmergeable")] == [
        ("conflicts", True)]


def test_a_blocked_pr_that_conflicts_raises_became_unmergeable_for_the_conflict(detection):
    events = _changes(detection, _state(mergeable=False, mergeable_state="blocked"),
                      _state(mergeable=False, mergeable_state="dirty"))

    assert [e.reason.value for e in _of(events, "became-unmergeable")] == [
        "conflicts"]


def test_a_blocked_pr_whose_ci_turns_unstable_raises_no_second_unmergeable(detection):
    events = _changes(detection, _state(mergeable=False, mergeable_state="blocked"),
                      _state(mergeable=False, mergeable_state="unstable"))

    assert _of(events, "became-unmergeable") == []


def test_a_conflicted_pr_that_falls_behind_raises_no_second_unmergeable(detection):
    events = _changes(detection, _state(mergeable=False, mergeable_state="dirty"),
                      _state(mergeable=False, mergeable_state="behind"))

    assert _of(events, "became-unmergeable") == []


def test_an_approval_that_unblocks_the_merge_says_so(detection):
    events = _changes(detection,
                      _state(mergeable=False, mergeable_state="blocked", review_decision="REVIEW_REQUIRED"),
                      _state(mergeable_state="clean", review_decision="APPROVED"))

    assert [e.reason.value for e in _of(events, "became-mergeable")] == ["approved"]


def test_a_changed_review_decision_names_both_sides_and_the_reviewer(detection):
    events = _changes(detection, _state(review_decision="REVIEW_REQUIRED"),
                      _state(review_decision="APPROVED",
                             reviews=(Review("bob", ReviewState.APPROVED),)))

    assert _of(events, "review-decision-changed") == [ReviewDecisionChanged(
        before=ReviewDecision.REVIEW_REQUIRED, after=ReviewDecision.APPROVED, reviewer="bob")]


def test_nothing_changed_raises_nothing(detection):
    assert _changes(detection, _state(review_decision="REVIEW_REQUIRED"),
                    _state(review_decision="REVIEW_REQUIRED")) == []


def test_mergeability_settling_on_blocked_raises_neither_mergeable_nor_a_pair(detection):
    events = _changes(detection,
                      _state(mergeable=False, mergeable_state="unknown",
                             review_decision="REVIEW_REQUIRED"),
                      _state(mergeable=True, mergeable_state="blocked",
                             review_decision="REVIEW_REQUIRED"))

    assert "became-mergeable" not in types(events)


def test_mergeability_resolving_from_unknown_says_the_status_resolved(detection):
    events = _changes(detection,
                      _state(mergeable=False, mergeable_state="unknown", review_decision="APPROVED"),
                      _state(mergeable=True, mergeable_state="clean", review_decision="APPROVED"))

    assert [e.reason.value for e in _of(events, "became-mergeable")] == [
        "status-resolved"]


def test_ci_passing_that_unblocks_the_merge_says_ci_passed(detection):
    events = _changes(detection,
                      _state("failure", mergeable=False, mergeable_state="blocked",
                             review_decision=None),
                      _state("success", mergeable=True, mergeable_state="clean",
                             review_decision=None))

    assert [e.reason.value for e in _of(events, "became-mergeable")] == ["ci-passed"]


def test_resolved_conflicts_say_so(detection):
    events = _changes(detection,
                      _state(mergeable=False, mergeable_state="dirty", review_decision="APPROVED"),
                      _state(mergeable=True, mergeable_state="clean", review_decision="APPROVED"))

    assert [e.reason.value for e in _of(events, "became-mergeable")] == [
        "conflicts-resolved"]


def test_an_unknown_mergeability_with_no_ci_raises_nothing(detection):
    unknown = _state("pending", mergeable=False, mergeable_state="unknown", review_decision=None)

    assert _changes(detection, unknown, unknown) == []


def test_a_first_review_decision_is_a_change(detection):
    events = _changes(detection,
                      _state(mergeable=False, mergeable_state="blocked", review_decision=None),
                      _state(mergeable=True, mergeable_state="clean", review_decision="APPROVED"))

    assert types(_of(events, "review-decision-changed")) == ["review-decision-changed"]


def test_an_approval_withdrawn_raises_the_change_and_not_mergeable(detection):
    events = _changes(detection, _state(review_decision="APPROVED"),
                      _state(review_decision="CHANGES_REQUESTED"))

    [changed] = _of(events, "review-decision-changed")
    assert (changed.before.value, changed.after.value) == (
        "approved", "changes-requested")
    assert _of(events, "became-mergeable") == []


def test_an_approval_withdrawn_that_blocks_the_merge_raises_both(detection):
    events = _changes(detection, _state(review_decision="APPROVED"),
                      _state(mergeable=False, mergeable_state="blocked",
                             review_decision="CHANGES_REQUESTED"))

    assert [e.reason.value for e in _of(events, "became-unmergeable")] == ["blocked"]
    assert types(_of(events, "review-decision-changed")) == ["review-decision-changed"]


def _reviewed(head="sha1", pushes=(), reviews=(MY_REVIEW,), **fields):
    return _state(author=OTHER, head_sha=head, review_decision="CHANGES_REQUESTED",
                  reviews=reviews, push_events=tuple(pushes), **fields)


def _commits(count):
    return [PushEvent("committed", AFTER_REVIEW) for _ in range(count)]


FORCE_PUSH = PushEvent("head_ref_force_pushed", AFTER_REVIEW)


def test_a_push_to_a_pr_i_never_reviewed_is_not_a_push_since_review(detection):
    events = _changes(detection, _reviewed(reviews=()), _reviewed("sha2", _commits(2), reviews=()))

    assert _of(events, "pushed-since-review") == []


def test_an_unmoved_head_is_not_a_push_since_review(detection):
    assert _of(_changes(detection, _reviewed(), _reviewed()), "pushed-since-review") == []


def test_a_force_push_after_my_review_is_flagged(detection):
    events = _changes(detection, _reviewed(), _reviewed("sha2", [FORCE_PUSH]))

    [pushed] = _of(events, "pushed-since-review")
    assert pushed.force_push is True


def test_a_force_push_back_onto_the_reviewed_commit_is_still_a_push(detection):
    review = Review(ACCOUNT, ReviewState.CHANGES_REQUESTED, REVIEWED_AT, "eefd72f")
    events = _changes(detection, _reviewed("old_head", reviews=(review,)),
                      _reviewed("eefd72f", [FORCE_PUSH], reviews=(review,)))

    [pushed] = _of(events, "pushed-since-review")
    assert pushed.force_push is True


def test_a_moved_head_carries_the_force_push_flag(detection):
    events = _changes(detection, _reviewed(), _reviewed("sha2", [FORCE_PUSH]))

    assert [e.force_push for e in _of(events, "head-changed")] == [True]


def test_a_moved_head_on_my_own_pr_raises_no_head_changed(detection):
    events = _changes(detection, _state(head_sha="sha1"), _state(head_sha="sha2"))

    assert _of(events, "head-changed") == []


def test_a_pr_with_no_head_before_raises_no_head_changed(detection):
    assert _of(_changes(detection, _reviewed(None), _reviewed("sha2")), "head-changed") == []


def test_an_unmoved_head_raises_no_head_changed(detection):
    assert _of(_changes(detection, _reviewed(), _reviewed()), "head-changed") == []


def _away(detection, seconds):
    stamp = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    events = _changes(detection, _reviewed(), _reviewed("sha2"), old_at=stamp.isoformat(),
                      new_at=(stamp + timedelta(seconds=seconds)).isoformat())
    return [e.away_seconds for e in _of(events, "head-changed")]


def test_a_long_gap_between_polls_is_carried_as_seconds_away(detection):
    assert _away(detection, 900) == [900]


def test_a_short_gap_between_polls_carries_no_seconds_away(detection):
    assert _away(detection, 61) == [None]


def _checks(*checks, head="sha1"):
    return pr_state(head_sha=head, checks=checks)


def test_each_failing_check_raises_its_own_event(detection):
    detection.advance(THE_PR, poll(), set())

    events = detection.advance(THE_PR, poll(_checks(
        failing("tests"), failing("lint"), passing("build"))), set())

    assert sorted(e.check for e in _of(events, "ci-failed")) == ["lint", "tests"]


def test_a_check_that_passed_and_fails_again_on_the_same_commit_raises_again(detection):
    detection.advance(THE_PR, poll(_checks(failing("tests"))), set())
    detection.advance(THE_PR, poll(_checks(passing("tests"))), set())

    events = detection.advance(THE_PR, poll(_checks(failing("tests"))), set())

    assert types(_of(events, "ci-failed")) == ["ci-failed"]


def test_a_failed_check_rerunning_on_the_same_commit_stays_handled(detection):
    detection.advance(THE_PR, poll(_checks(failing("tests"))), set())
    detection.advance(THE_PR, poll(_checks(Check("tests", "in_progress", None))), set())

    events = detection.advance(THE_PR, poll(_checks(failing("tests"))), set())

    assert _of(events, "ci-failed") == []


def test_a_partial_fix_with_the_rest_already_waiting_raises_nothing_new(detection):
    detection.advance(THE_PR, poll(_checks(failing("A"), failing("B"))), set())

    fixed_one = detection.advance(THE_PR, poll(_checks(passing("A"), failing("B"), head="sha2")),
                                  {"B"})
    later = detection.advance(THE_PR, poll(_checks(passing("A"), failing("B"), head="sha2")),
                              set())

    assert _of(fixed_one, "ci-failed") == []
    assert _of(later, "ci-failed") == []
