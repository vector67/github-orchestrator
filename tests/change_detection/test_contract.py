import pytest

from github_orchestrator.change_detection import (
    BecameUnmergeable,
    CiFailed,
    HeadChanged,
    PrClosed,
    PushedSinceReview,
    ReviewRequested,
)
from github_orchestrator.change_detection.fake import Stored, UnmergeableReason
from github_orchestrator.github import ReviewState
from github_orchestrator.github.fake import PushEvent, Review
from tests.builders import a_pr
from tests.change_detection.support import (
    ACCOUNT,
    NOW,
    PR,
    REPO,
    disk_change_detection,
    failing,
    fake_change_detection,
    passing,
    poll,
    pr_state,
    types,
)

THE_PR = a_pr(PR, REPO)


@pytest.fixture(params=["fake", "disk"])
def detection(request, tmp_path):
    if request.param == "fake":
        return fake_change_detection()
    return disk_change_detection(tmp_path / "state")


def test_a_pr_never_polled_is_not_known(detection):
    assert detection.facts(THE_PR) is None
    assert detection.tracked() == []
    assert detection.stored() == []
    assert detection.closing(THE_PR) is False


def test_a_first_poll_of_a_pr_in_good_shape_raises_nothing_and_remembers_it(detection):
    events = detection.advance(THE_PR, poll(), set())

    facts = detection.facts(THE_PR)
    assert events == []
    assert facts.branch == "PROJ-7-widgets"
    assert (facts.ci_passed, facts.is_author) == (True, True)
    assert detection.tracked() == [(THE_PR)]


def test_a_first_poll_raises_only_what_the_pr_already_needs(detection):
    events = detection.advance(THE_PR, poll(pr_state(mergeable_state="dirty")), set())

    assert events == [BecameUnmergeable(UnmergeableReason.CONFLICTS)]
    assert events[0].rebase is True


def test_a_pr_that_turns_conflicted_raises_it_once(detection):
    detection.advance(THE_PR, poll(), set())

    turned = detection.advance(THE_PR, poll(pr_state(mergeable_state="dirty")), set())
    stayed = detection.advance(THE_PR, poll(pr_state(mergeable_state="dirty")), set())

    assert turned == [BecameUnmergeable(UnmergeableReason.CONFLICTS)]
    assert stayed == []


def test_a_pr_blocked_by_something_a_rebase_cannot_fix_says_so(detection):
    detection.advance(THE_PR, poll(), set())

    turned = detection.advance(THE_PR, poll(pr_state(mergeable_state="blocked")), set())

    assert turned == [BecameUnmergeable(UnmergeableReason.BLOCKED)]
    assert turned[0].rebase is False


def test_each_failing_check_raises_once_per_commit(detection):
    detection.advance(THE_PR, poll(), set())
    broken = poll(pr_state(head_sha="sha1", checks=(failing("tests"), passing("lint"))))

    first = detection.advance(THE_PR, broken, set())
    again = detection.advance(THE_PR, broken, set())
    next_commit = detection.advance(
        THE_PR, poll(pr_state(head_sha="sha2", checks=(failing("tests"),))), set())

    assert [e for e in first if e.kind == "ci-failed"] == [
        CiFailed(check="tests", summary="tests failed")]
    assert "ci-failed" not in types(again)
    assert types(next_commit) == ["ci-failed"]


def test_a_check_already_waiting_in_the_event_queue_raises_nothing_and_stays_handled(detection):
    detection.advance(THE_PR, poll(), set())
    broken = poll(pr_state(head_sha="sha1", checks=(failing("tests"),)))

    waiting = detection.advance(THE_PR, broken, {"tests"})
    after = detection.advance(THE_PR, broken, set())

    assert "ci-failed" not in types(waiting)
    assert "ci-failed" not in types(after)


def test_a_review_request_seen_for_the_first_time_asks_for_the_review(detection):
    events = detection.advance(THE_PR, poll(pr_state(author="alice"), review_requested=True),
                               set())

    assert events == [ReviewRequested(title="Add widgets",
                                      url="https://github.com/acme/widgets/pull/7")]


def test_a_review_request_asks_first_and_then_says_what_the_pr_already_needs(detection):
    events = detection.advance(
        THE_PR, poll(pr_state(author="alice", mergeable_state="dirty"), review_requested=True),
        set())

    assert types(events) == ["review-requested", "became-unmergeable"]


def test_a_review_request_already_known_asks_for_nothing_again(detection):
    detection.advance(THE_PR, poll(pr_state(author="alice"), review_requested=True), set())

    events = detection.advance(THE_PR, poll(pr_state(author="alice"), review_requested=True),
                               set())

    assert events == []


def test_a_review_requested_again_after_it_lapsed_asks_for_the_review_again(detection):
    detection.advance(THE_PR, poll(pr_state(author="alice"), review_requested=True), set())
    detection.advance(THE_PR, poll(pr_state(author="alice"), review_requested=False), set())

    events = detection.advance(THE_PR, poll(pr_state(author="alice"), review_requested=True),
                               set())

    assert events == [ReviewRequested(title="Add widgets",
                                      url="https://github.com/acme/widgets/pull/7")]


def test_a_pr_watched_before_it_was_requested_asks_for_the_review_when_it_is(detection):
    detection.advance(THE_PR, poll(pr_state(author="alice"), review_requested=False), set())

    events = detection.advance(THE_PR, poll(pr_state(author="alice"), review_requested=True),
                               set())

    assert types(events) == ["review-requested"]


def test_a_closed_pr_ends_merged_or_not(detection):
    assert detection.ended(still_open=False, merged=True) == PrClosed(merged=True)
    assert detection.ended(still_open=False, merged=False) == PrClosed(merged=False)


def test_an_open_pr_that_left_the_watch_list_ends_as_no_longer_relevant(detection):
    assert detection.ended(still_open=True, merged=False) == PrClosed(
        merged=False, no_longer_relevant=True)


def test_a_poll_that_raised_something_is_stamped_and_a_quiet_one_carries_it(detection):
    detection.advance(THE_PR, poll(), set())
    assert detection.facts(THE_PR).last_event_at is None

    detection.advance(THE_PR, poll(pr_state(mergeable_state="dirty")), set())
    detection.advance(THE_PR, poll(pr_state(mergeable_state="dirty")), set())

    assert detection.facts(THE_PR).last_event_at == NOW.isoformat()


def test_unknown_mergeability_keeps_the_last_known_verdict_and_raises_nothing(detection):
    detection.advance(THE_PR, poll(pr_state(mergeable_state="blocked")), set())

    events = detection.advance(
        THE_PR, poll(pr_state(mergeable_state="unknown", mergeable=False)), set())

    facts = detection.facts(THE_PR)
    assert (facts.merge_state.value, facts.mergeable) == ("blocked", True)
    assert events == []


def test_a_reviewer_is_told_of_the_pushes_since_their_review(detection):
    reviewed = pr_state(author="alice", head_sha="sha1",
                        reviews=(Review(ACCOUNT, ReviewState.CHANGES_REQUESTED,
                                        "2026-09-20T00:00:00Z", "sha1"),),
                        review_decision="CHANGES_REQUESTED")
    detection.advance(THE_PR, poll(reviewed), set())

    events = detection.advance(THE_PR, poll(pr_state(
        author="alice", head_sha="sha2", reviews=reviewed.reviews,
        review_decision="CHANGES_REQUESTED",
        push_events=(PushEvent("committed", "2026-09-21T00:00:00Z"),
                     PushEvent("committed", "2026-09-21T00:01:00Z")),
    )), set())

    assert [e for e in events if e.kind == "pushed-since-review"] == [
        PushedSinceReview(commits=2, force_push=False)]
    assert [e for e in events if e.kind == "head-changed"] == [
        HeadChanged(previous="sha1", head="sha2", force_push=False, away_seconds=None)]
    assert detection.facts(THE_PR).since_review.commits == 2


def test_a_closing_pr_keeps_what_it_knew(detection):
    detection.advance(THE_PR, poll(), set())

    detection.close(THE_PR)

    assert detection.closing(THE_PR) is True
    assert detection.facts(THE_PR).branch == "PROJ-7-widgets"


def test_a_pr_never_polled_can_still_be_closed(detection):
    detection.close(THE_PR)

    assert detection.closing(THE_PR) is True
    assert detection.tracked() == [(THE_PR)]


def test_a_forgotten_pr_is_no_longer_known(detection):
    detection.advance(THE_PR, poll(), set())

    assert detection.forget(THE_PR) is True

    assert detection.facts(THE_PR) is None
    assert detection.tracked() == []


def test_forgetting_a_pr_never_polled_succeeds(detection):
    assert detection.forget(THE_PR) is True


def test_every_stored_snapshot_is_listed_in_pr_order(detection):
    detection.advance(a_pr(10, "acme/widgets"), poll(), set())
    detection.advance(a_pr(9, "acme/widgets"), poll(), set())
    detection.advance(a_pr(1, "acme/gadgets"), poll(), set())

    assert detection.stored() == [
        Stored(a_pr(1, "acme/gadgets"),
               detection.facts(a_pr(1, "acme/gadgets")), None),
        Stored(a_pr(9, "acme/widgets"),
               detection.facts(a_pr(9, "acme/widgets")), None),
        Stored(a_pr(10, "acme/widgets"),
               detection.facts(a_pr(10, "acme/widgets")), None),
    ]
    assert sorted(detection.tracked()) == [(a_pr(1, "acme/gadgets")), (a_pr(9, "acme/widgets")),
                                           (a_pr(10, "acme/widgets"))]


def test_archiving_moves_every_unwatched_repos_snapshots_and_keeps_every_watched_one(
        detection, tmp_path):
    detection.advance(THE_PR, poll(), set())
    detection.advance(a_pr(2, "acme/gadgets"), poll(), set())
    detection.advance(a_pr(3, "octocat/third"), poll(), set())
    detection.advance(a_pr(4, "acme/fourth"), poll(), set())
    into = tmp_path / "archive" / "state"

    archived = detection.archive_other_repos({THE_PR.repo, a_pr(4, "acme/fourth").repo}, into)

    assert sorted(archived) == [into / "acme" / "gadgets", into / "octocat" / "third"]
    assert sorted(detection.tracked()) == sorted([THE_PR, a_pr(4, "acme/fourth")])
    assert detection.facts(a_pr(2, "acme/gadgets")) is None


def test_archiving_when_only_the_named_repo_is_tracked_moves_nothing(detection, tmp_path):
    detection.advance(THE_PR, poll(), set())

    assert detection.archive_other_repos({THE_PR.repo}, tmp_path / "archive" / "state") == []
    assert detection.tracked() == [THE_PR]
