from datetime import timedelta

import pytest

from github_orchestrator.change_detection.fake import (
    MergeableReason,
    ReviewDecision,
    UnmergeableReason,
)
from github_orchestrator.domain import Repo
from github_orchestrator.pr_event_queue import Response
from github_orchestrator.pr_event_queue.fake import FakePrEventQueue, Waiting
from tests.builders import a_pr
from tests.pr_event_queue.support import (
    activity,
    ci_failed,
    ci_succeeded,
    closed,
    decision_changed,
    disk_event_queue,
    head_moved,
    in_flight_of,
    kinds,
    mergeable,
    now,
    pending_of,
    pushed,
    queue_of,
    review_requested,
    unmergeable,
)

REPO = "acme/widgets"
THE_PR = a_pr(1, REPO)


@pytest.fixture(params=["fake", "disk"])
def event_queue(request, tmp_path):
    if request.param == "fake":
        return FakePrEventQueue()
    return disk_event_queue(tmp_path / "queues")


def _add(event_queue, item, pr=THE_PR):
    if item.kind == "thread-activity":
        event_queue.add_thread_activity(pr, item)
    else:
        event_queue.add(pr, item)


def _take(event_queue, *, is_author=True, agents_enabled=True, busy=False, pr=1):
    return event_queue.next(a_pr(pr, REPO), is_author=is_author,
                            agents_enabled=agents_enabled, busy=busy)


def test_each_kind_of_event_comes_back_as_it_went_in(event_queue):
    added = [ci_succeeded("lint", "unit"), ci_failed("lint", None),
             unmergeable(UnmergeableReason.BASE_UPDATED), mergeable(MergeableReason.CI_PASSED),
             decision_changed(None, ReviewDecision.CHANGES_REQUESTED, None), pushed(3, True),
             head_moved("abc", "def"), review_requested("Add X", "https://x/1"),
             closed(False, True)]
    for item in added:
        event_queue.add(THE_PR, item)

    assert pending_of(event_queue, THE_PR) == added


def test_thread_activity_comes_back_as_conversation_gave_it(event_queue):
    found = activity("PRRT_one", stale=("PRRT_two",), cutoff="2026-09-24T10:00:00Z")

    event_queue.add_thread_activity(THE_PR, found)

    assert pending_of(event_queue, THE_PR) == [found]
    assert _take(event_queue).response.event == found


def test_events_come_out_in_the_order_they_went_in(event_queue):
    for item in (ci_failed(), mergeable(), ci_succeeded()):
        event_queue.add(THE_PR, item)

    taken = [_take(event_queue).response.event.kind for _ in range(3)]

    assert taken == ["ci-failed", "became-mergeable", "ci-succeeded"]


def test_each_pr_has_its_own_events(event_queue):
    event_queue.add(THE_PR, ci_failed())
    event_queue.add(a_pr(2, REPO), mergeable())
    event_queue.add(a_pr(1, "acme/other"), ci_succeeded())

    assert kinds(pending_of(event_queue, THE_PR)) == ["ci-failed"]
    assert kinds(pending_of(event_queue, a_pr(2, REPO))) == ["became-mergeable"]
    assert kinds(pending_of(event_queue, a_pr(1, "acme/other"))) == [
        "ci-succeeded"]


def test_an_empty_event_queue_has_nothing_to_do(event_queue):
    assert _take(event_queue) is None


def test_each_entry_says_when_it_was_queued_and_whether_it_waits_or_is_in_hand(event_queue):
    before = now()
    event_queue.add(THE_PR, ci_failed("lint"))
    event_queue.add(THE_PR, mergeable())
    _take(event_queue)

    [in_hand, waiting] = queue_of(event_queue, THE_PR).entries

    assert (in_hand.event, in_hand.in_flight, in_hand.pending) == (ci_failed("lint"), True, False)
    assert (waiting.event, waiting.pending, waiting.in_flight) == (mergeable(), True, False)
    assert before <= in_hand.queued_at <= waiting.queued_at <= now()


def test_a_taken_event_is_in_flight_until_it_is_done(event_queue):
    event_queue.add(THE_PR, ci_failed())

    taken = _take(event_queue)

    assert pending_of(event_queue, THE_PR) == []
    assert kinds(in_flight_of(event_queue, THE_PR)) == ["ci-failed"]

    taken.done()

    assert in_flight_of(event_queue, THE_PR) == []
    assert _take(event_queue) is None


def test_a_failed_event_is_kept_aside_and_listed_since_the_time_it_failed(event_queue):
    before = now()
    event_queue.add(THE_PR, ci_failed())

    _take(event_queue).failed()

    assert queue_of(event_queue, THE_PR).in_flight == []
    assert queue_of(event_queue, THE_PR).pending == []
    assert _take(event_queue) is None
    [failure] = event_queue.failed_since(before)
    assert (failure.pr, failure.event, failure.failed) == (THE_PR, ci_failed(), True)
    assert before <= failure.queued_at <= now()


def test_a_failure_before_the_time_asked_about_is_not_listed(event_queue):
    event_queue.add(THE_PR, ci_failed())
    _take(event_queue).failed()

    assert event_queue.failed_since(now() + timedelta(seconds=1)) == []


def test_an_event_in_flight_when_its_manager_died_is_recovered(event_queue):
    event_queue.add(THE_PR, unmergeable())
    _take(event_queue)

    event_queue.recover(THE_PR)

    assert pending_of(event_queue, THE_PR) == [unmergeable()]
    assert in_flight_of(event_queue, THE_PR) == []
    assert _take(event_queue).response.event.kind == "became-unmergeable"


def test_a_ci_fix_in_flight_when_its_manager_died_comes_back_as_its_next_attempt(event_queue):
    event_queue.add(THE_PR, ci_failed("tests", "boom", attempt=1))
    _take(event_queue)

    event_queue.recover(THE_PR)

    [retry] = pending_of(event_queue, THE_PR)
    assert (retry.check, retry.summary, retry.attempt) == ("tests", "boom", 2)
    assert retry.retry_reason == "the agent manager stopped before the run ended"
    assert in_flight_of(event_queue, THE_PR) == []


def test_dropping_what_is_in_flight_keeps_what_is_pending(event_queue):
    event_queue.add(THE_PR, ci_failed())
    event_queue.add(THE_PR, mergeable())
    _take(event_queue)

    event_queue.drop_in_flight(THE_PR)

    assert in_flight_of(event_queue, THE_PR) == []
    assert kinds(pending_of(event_queue, THE_PR)) == ["became-mergeable"]


def test_a_forgotten_pr_has_no_queue_left(event_queue):
    event_queue.add(THE_PR, ci_failed())
    event_queue.add(THE_PR, mergeable())
    _take(event_queue)
    event_queue.add(a_pr(2, REPO), ci_failed())

    assert event_queue.forget(THE_PR) is True

    assert pending_of(event_queue, THE_PR) == []
    assert in_flight_of(event_queue, THE_PR) == []
    assert [q.pr for q in event_queue.queues()] == [a_pr(2, REPO)]


def test_forgetting_a_pr_with_no_queue_succeeds(event_queue):
    assert event_queue.forget(THE_PR) is True


def test_a_pr_is_torn_down_once_its_closing_event_is_done(event_queue):
    event_queue.add(THE_PR, closed())
    assert event_queue.is_torn_down(THE_PR) is False

    taken = _take(event_queue)
    assert event_queue.is_torn_down(THE_PR) is False

    taken.done()
    assert event_queue.is_torn_down(THE_PR) is True


def test_a_closing_event_that_failed_does_not_tear_the_pr_down(event_queue):
    event_queue.add(THE_PR, closed())

    _take(event_queue).failed()

    assert event_queue.is_torn_down(THE_PR) is False


def test_a_forgotten_pr_is_no_longer_torn_down(event_queue):
    event_queue.add(THE_PR, closed())
    _take(event_queue).done()

    event_queue.forget(THE_PR)

    assert event_queue.is_torn_down(THE_PR) is False


def test_a_pr_never_added_to_has_nothing_waiting(event_queue):
    assert event_queue.waiting(THE_PR) == Waiting(count=0, closing=False,
                                                  failed_checks=frozenset())
    assert event_queue.settling(THE_PR) is False


def test_what_waits_counts_the_events_not_yet_taken(event_queue):
    event_queue.add(THE_PR, mergeable())
    event_queue.add(THE_PR, ci_succeeded())
    event_queue.add(THE_PR, decision_changed())
    _take(event_queue)

    assert event_queue.waiting(THE_PR).count == 2
    assert event_queue.waiting(a_pr(2, REPO)).count == 0


def test_a_pr_closed_next_in_line_is_waiting_to_close(event_queue):
    event_queue.add(THE_PR, closed())
    event_queue.add(THE_PR, ci_failed())

    assert event_queue.waiting(THE_PR).closing is True


def test_a_pr_closed_behind_another_event_is_not_next(event_queue):
    event_queue.add(THE_PR, ci_failed())
    event_queue.add(THE_PR, closed())

    assert event_queue.waiting(THE_PR).closing is False


def test_the_failed_checks_waiting_include_one_in_flight(event_queue):
    event_queue.add(THE_PR, ci_failed("lint"))
    event_queue.add(THE_PR, mergeable())
    event_queue.add(THE_PR, ci_failed("unit"))
    _take(event_queue)

    assert event_queue.waiting(THE_PR).failed_checks == frozenset({"lint", "unit"})
    assert event_queue.waiting(a_pr(2, REPO)).failed_checks == frozenset()


def test_thread_activity_waits_while_it_is_queued_or_in_flight(event_queue):
    event_queue.add_thread_activity(THE_PR, activity("PRRT_one"))

    queued = event_queue.settling(THE_PR)
    taken = _take(event_queue)
    in_flight = event_queue.settling(THE_PR)
    taken.done()

    assert (queued, in_flight, event_queue.settling(THE_PR)) == (True, True, False)


def test_thread_activity_found_again_while_the_first_waits_is_added_once(event_queue):
    event_queue.add_thread_activity(THE_PR, activity("PRRT_one", cutoff="2026-09-24T10:00:00Z"))
    event_queue.add_thread_activity(THE_PR, activity("PRRT_one", cutoff="2026-09-24T10:01:00Z"))

    assert [item.cutoff for item in pending_of(event_queue, THE_PR)] == [
        "2026-09-24T10:00:00Z"]


def test_thread_activity_found_again_while_the_first_is_carried_out_is_added_once(event_queue):
    event_queue.add_thread_activity(THE_PR, activity("PRRT_one"))
    _take(event_queue)

    event_queue.add_thread_activity(THE_PR, activity("PRRT_one"))

    assert event_queue.waiting(THE_PR).count == 0


def test_other_thread_activity_is_added_beside_what_waits(event_queue):
    event_queue.add_thread_activity(THE_PR, activity("PRRT_one"))
    event_queue.add_thread_activity(THE_PR, activity(stale=("PRRT_one",)))
    event_queue.add_thread_activity(a_pr(2, REPO), activity("PRRT_one"))

    assert (event_queue.waiting(THE_PR).count,
            event_queue.waiting(a_pr(2, REPO)).count) == (2, 1)


def test_thread_activity_carried_out_already_is_added_again(event_queue):
    event_queue.add_thread_activity(THE_PR, activity("PRRT_one"))
    _take(event_queue).done()

    event_queue.add_thread_activity(THE_PR, activity("PRRT_one"))

    assert event_queue.waiting(THE_PR).count == 1


def test_queues_lists_each_pr_that_has_a_queue_in_order(event_queue):
    event_queue.add(a_pr(3, "acme/zeta"), ci_failed())
    event_queue.add(a_pr(7, REPO), mergeable())
    event_queue.add(a_pr(7, REPO), ci_failed())
    event_queue.add(a_pr(5, REPO), ci_succeeded())
    event_queue.next(a_pr(7, REPO), is_author=True, agents_enabled=True)

    listed = [(q.pr, len(q.in_flight), len(q.pending)) for q in event_queue.queues()]

    assert listed == [(a_pr(5, REPO), 0, 1), (a_pr(7, REPO), 1, 1),
                      (a_pr(3, "acme/zeta"), 0, 1)]


def test_a_pr_whose_events_are_all_done_still_has_an_empty_queue(event_queue):
    event_queue.add(THE_PR, ci_failed())
    _take(event_queue).done()

    assert [(q.pr, q.in_flight, q.pending) for q in event_queue.queues()] == [
        (THE_PR, [], []),
    ]


def test_a_pr_never_added_to_lists_no_queue(event_queue):
    event_queue.waiting(a_pr(9, REPO))

    assert event_queue.queues() == []


def test_while_busy_events_that_start_or_stop_a_run_wait(event_queue):
    event_queue.add(THE_PR, review_requested())
    event_queue.add(THE_PR, closed())
    event_queue.add(THE_PR, ci_failed())
    event_queue.add(THE_PR, mergeable())

    taken = _take(event_queue, busy=True)

    assert taken.response.event.kind == "became-mergeable"
    assert kinds(pending_of(event_queue, THE_PR)) == [
        "review-requested", "pr-closed", "ci-failed"]


@pytest.mark.parametrize("item, is_author, waits", [
    (ci_failed(), True, True),
    (ci_failed(), False, False),
    (unmergeable(UnmergeableReason.CONFLICTS), True, True),
    (unmergeable(UnmergeableReason.BLOCKED), True, False),
    (unmergeable(UnmergeableReason.CONFLICTS), False, False),
    (review_requested(), True, True),
    (activity("PRRT_one"), True, False),
    (head_moved(), True, False),
    (closed(), True, True),
])
def test_while_busy_exactly_the_events_that_start_or_stop_a_run_wait(
    event_queue, item, is_author, waits,
):
    _add(event_queue, item)

    taken = _take(event_queue, is_author=is_author, busy=True)

    assert (taken is None) is waits


def test_while_busy_with_claude_disabled_launching_events_drain(event_queue):
    event_queue.add(THE_PR, review_requested())

    assert _take(event_queue, agents_enabled=False, busy=True).response.event.kind == "review-requested"


def _response(event_queue, item, *, is_author=True, agents_enabled=True):
    _add(event_queue, item)
    return _take(event_queue, is_author=is_author, agents_enabled=agents_enabled).response


@pytest.mark.parametrize("item, is_author", [
    (review_requested("Add X", "https://x/1"), False),
    (review_requested("Add X", "https://x/1"), True),
    (ci_failed("lint", "E501"), True),
    (unmergeable(UnmergeableReason.CONFLICTS), True),
    (unmergeable(UnmergeableReason.BASE_UPDATED), True),
])
def test_an_event_that_starts_a_run_for_the_prs_role_is_answered_as_its_launch(
        event_queue, item, is_author):
    response = _response(event_queue, item, is_author=is_author)

    assert response == Response(event=item, launch=item, skipped=False,
                                more_failures_wait=False)


def test_a_failing_check_knows_whether_other_failing_checks_wait_behind_it(event_queue):
    event_queue.add(THE_PR, ci_failed("lint"))
    event_queue.add(THE_PR, ci_failed("unit"))

    first = _take(event_queue).response
    second = _take(event_queue).response

    assert (first.more_failures_wait, second.more_failures_wait) == (True, False)


@pytest.mark.parametrize("item, is_author", [
    (ci_failed("lint", "E501"), False),
    (unmergeable(UnmergeableReason.BLOCKED), True),
    (unmergeable(UnmergeableReason.CONFLICTS), False),
    (ci_succeeded("lint", "unit"), True),
    (mergeable(MergeableReason.CI_PASSED), True),
    (decision_changed(), True),
    (pushed(1, False), False),
    (activity("PRRT_one"), True),
    (head_moved(), True),
    (closed(merged=True), True),
])
def test_an_event_that_starts_no_run_for_the_prs_role_launches_nothing(
        event_queue, item, is_author):
    response = _response(event_queue, item, is_author=is_author)

    assert (response.event, response.launch, response.skipped) == (item, None, False)


@pytest.mark.parametrize("item, is_author", [
    (review_requested(), False),
    (ci_failed("lint"), True),
])
def test_with_claude_disabled_a_launch_is_skipped_saying_what_it_would_have_been(
        event_queue, item, is_author):
    response = _response(event_queue, item, is_author=is_author, agents_enabled=False)

    assert (response.launch, response.skipped) == (item, True)


@pytest.mark.parametrize("item, closes", [(closed(merged=True), True), (ci_failed(), False)])
def test_only_a_closed_pr_closes(event_queue, item, closes):
    assert _response(event_queue, item).closes is closes


def test_archiving_moves_every_unwatched_repos_queues_and_keeps_every_watched_one(
        event_queue, tmp_path):
    event_queue.add(THE_PR, ci_failed())
    event_queue.add(a_pr(2, "acme/other"), ci_failed())
    event_queue.add(a_pr(3, "octocat/third"), mergeable())
    event_queue.add(a_pr(4, "acme/fourth"), mergeable())
    into = tmp_path / "archive" / "queues"

    archived = event_queue.archive_other_repos({Repo.parse(REPO), Repo.parse("acme/fourth")}, into)

    assert sorted(archived) == [into / "acme" / "other", into / "octocat" / "third"]
    assert sorted(queue.pr for queue in event_queue.queues()) == sorted(
        [THE_PR, a_pr(4, "acme/fourth")])
    assert pending_of(event_queue, a_pr(2, "acme/other")) == []


def test_archiving_when_only_the_named_repo_has_queues_moves_nothing(event_queue, tmp_path):
    event_queue.add(THE_PR, ci_failed())

    assert event_queue.archive_other_repos({Repo.parse(REPO)},
                                           tmp_path / "archive" / "queues") == []
    assert [queue.pr for queue in event_queue.queues()] == [THE_PR]
