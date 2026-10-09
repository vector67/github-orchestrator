from datetime import timedelta

import pytest

from github_orchestrator.agent_runs.fake import CommentsAsked, FixesAsked
from github_orchestrator.desktop import Badge
from github_orchestrator.desktop.fake import FakeDesktop
from github_orchestrator.notifications import FixProgress
from tests.builders import a_pr
from tests.conftest import fake_agent_runs
from tests.desktop.scripted_mac import Failure, ScriptedMac
from tests.desktop.support import real_desktop
from tests.notifications.support import LONG_AWAKE, Board, Clock, opened


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def desktop():
    return FakeDesktop()


@pytest.fixture
def runs():
    return fake_agent_runs()


@pytest.fixture
def store(tmp_path, desktop, clock, runs):
    return opened(tmp_path, desktop, clock, runs)


def _fix(notifications, key="PRRT_1", gist="rename the helper", pr=101,
         repo="acme/widgets"):
    notifications.thread_news.fix_ready(a_pr(pr, repo), key, gist=gist,
                                        comments=[("Ada", f"please {gist}")],
                                        fix_summary=f"did: {gist}")


def _shown(desktop):
    return [(a.badge, a.title, a.body) for a in desktop.announcements]


def test_a_fix_ready_waits_three_minutes_from_the_first(store, desktop, clock, runs):
    notifications, courier = store
    runs.answer("rename the helper")

    _fix(notifications)
    clock.advance(minutes=2, seconds=59)
    courier.deliver(LONG_AWAKE, None)

    assert desktop.announcements == []


def test_three_minutes_after_the_first_every_fix_so_far_goes_out_as_one(store, desktop, clock,
                                                                          runs):
    notifications, courier = store
    runs.answer("general cleanup and missing tests")

    _fix(notifications, "PRRT_1", "rename the helper")
    clock.advance(minutes=2)
    _fix(notifications, "PRRT_2", "add a test")
    clock.advance(minutes=1)
    courier.deliver(LONG_AWAKE, None)

    assert _shown(desktop) == [
        (Badge.READY, "2 fixes ready on widgets#101", "general cleanup and missing tests"),
    ]


def test_the_summary_is_asked_about_every_comment_and_fix_in_the_batch(store, clock, runs):
    notifications, courier = store
    runs.answer("general cleanup")

    _fix(notifications, "PRRT_1", "rename the helper")
    _fix(notifications, "PRRT_2", "add a test")
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert runs.asked == [FixesAsked((
        ((("Ada", "please rename the helper"),), "did: rename the helper"),
        ((("Ada", "please add a test"),), "did: add a test"),
    ), 100)]


def test_a_fix_after_a_batch_went_out_opens_a_batch_of_its_own(store, desktop, clock, runs):
    notifications, courier = store
    runs.answer("rename the helper", "add a test")

    _fix(notifications, "PRRT_1", "rename the helper")
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)
    _fix(notifications, "PRRT_2", "add a test")
    clock.advance(minutes=2)
    courier.deliver(LONG_AWAKE, None)

    assert [a.title for a in desktop.announcements] == ["1 fix ready on widgets#101"]

    clock.advance(minutes=1)
    courier.deliver(LONG_AWAKE, None)

    assert [a.body for a in desktop.announcements] == ["rename the helper", "add a test"]


def test_each_pr_gets_its_own_batch(store, desktop, clock, runs):
    notifications, courier = store
    runs.answer("one", "two")

    _fix(notifications, "PRRT_1", pr=101)
    _fix(notifications, "PRRT_2", pr=84)
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert sorted(a.title for a in desktop.announcements) == [
        "1 fix ready on widgets#101", "1 fix ready on widgets#84"]


def test_without_a_summary_within_a_minute_the_gists_stand_in(store, desktop, clock, runs):
    notifications, courier = store

    _fix(notifications, "PRRT_1", "rename the helper")
    _fix(notifications, "PRRT_2", "add a test")
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)
    clock.advance(seconds=59)
    courier.deliver(LONG_AWAKE, None)

    assert desktop.announcements == []

    clock.advance(seconds=1)
    courier.deliver(LONG_AWAKE, None)

    assert [a.body for a in desktop.announcements] == ["rename the helper; add a test"]


def test_a_summary_too_long_for_the_banner_is_cut_short(store, desktop, clock, runs):
    notifications, courier = store
    runs.answer("x" * 200)

    _fix(notifications)
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    [shown] = desktop.announcements
    assert len(shown.body) == 110
    assert shown.body.endswith("…")


def test_a_batch_gathered_before_a_restart_goes_out_after_it(tmp_path, desktop, clock, runs):
    before, _ = opened(tmp_path, FakeDesktop(), clock)
    _fix(before)
    clock.advance(minutes=3)
    runs.answer("rename the helper")

    _, after = opened(tmp_path, desktop, clock, runs)
    after.deliver(LONG_AWAKE, None)

    assert _shown(desktop) == [(Badge.READY, "1 fix ready on widgets#101", "rename the helper")]


def test_a_batch_that_fell_due_while_asleep_waits_for_a_poll_after_waking(store, desktop, clock,
                                                                         runs):
    notifications, courier = store
    runs.answer("rename the helper")
    _fix(notifications)
    clock.advance(hours=2)
    woke = clock()
    polled_before_sleep = woke - timedelta(hours=2)

    courier.deliver(woke, polled_before_sleep)

    assert desktop.announcements == []

    clock.advance(seconds=30)
    courier.deliver(woke, woke + timedelta(seconds=1))

    assert [a.title for a in desktop.announcements] == ["1 fix ready on widgets#101 (from 17:46)"]


def test_a_batch_that_falls_due_after_waking_goes_out_on_time(store, desktop, clock, runs):
    notifications, courier = store
    runs.answer("rename the helper")
    woke = clock()
    _fix(notifications)
    clock.advance(minutes=3)

    courier.deliver(woke, None)

    assert [a.title for a in desktop.announcements] == ["1 fix ready on widgets#101"]


def test_what_a_poll_after_waking_found_joins_the_overdue_batch(store, desktop, clock, runs):
    notifications, courier = store
    runs.answer("both")
    _fix(notifications, "PRRT_1")
    clock.advance(hours=2)
    woke = clock()
    _fix(notifications, "PRRT_2")

    courier.deliver(woke, woke + timedelta(seconds=5))

    assert [a.title for a in desktop.announcements] == ["2 fixes ready on widgets#101 (from 17:46)"]


def test_a_batch_the_badge_app_could_not_show_is_tried_again(tmp_path, clock, runs):
    mac = ScriptedMac().answer("open", Failure(1, "LSOpenURLsWithRole() failed"))
    notifications, courier = opened(tmp_path, real_desktop(mac=mac), clock, runs)
    runs.answer("rename the helper")

    _fix(notifications)
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)
    courier.deliver(LONG_AWAKE, None)

    assert [a.title for a in mac.world.announcements] == ["1 fix ready on widgets#101"]


def test_claude_being_disabled_is_one_batch_across_every_pr(store, desktop, clock):
    notifications, courier = store

    notifications.runs.agent_skipped(a_pr(101, "acme/widgets"), "thread-activity")
    notifications.runs.agent_skipped(a_pr(84, "acme/widgets"), "ci-failed")
    notifications.runs.agent_skipped(a_pr(101, "acme/widgets"), "became-unmergeable")
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert _shown(desktop) == [(
        Badge.INFO, "Agents disabled — skipped events on #101, #84",
        "widgets#101: thread-activity, became-unmergeable; widgets#84: ci-failed",
    )]


def test_fixes_ready_open_their_pr_on_its_board(store, desktop, clock, runs):
    notifications, courier = store
    runs.answer("rename the helper")

    _fix(notifications, pr=101)
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert [a.link for a in desktop.announcements] == ["http://127.0.0.1:8721/pr/acme/widgets/101"]


def test_claude_skipping_events_on_one_pr_opens_that_pr_on_its_board(store, desktop, clock):
    notifications, courier = store

    notifications.runs.agent_skipped(a_pr(101, "acme/widgets"), "thread-activity")
    notifications.runs.agent_skipped(a_pr(101, "acme/widgets"), "ci-failed")
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert [a.link for a in desktop.announcements] == ["http://127.0.0.1:8721/pr/acme/widgets/101"]


def test_claude_skipping_events_on_several_prs_opens_none_of_them(store, desktop, clock):
    notifications, courier = store

    notifications.runs.agent_skipped(a_pr(101, "acme/widgets"), "thread-activity")
    notifications.runs.agent_skipped(a_pr(84, "acme/widgets"), "ci-failed")
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert [a.link for a in desktop.announcements] == [None]


def test_a_fix_seen_or_acted_on_before_its_batch_went_out_is_left_out(tmp_path, desktop, clock,
                                                                       runs):
    board = Board()
    notifications, courier = opened(tmp_path, desktop, clock, runs, board)
    runs.answer("rename the helper")

    _fix(notifications, "PRRT_1", "rename the helper")
    _fix(notifications, "PRRT_2", "add a test")
    board.handled.add("PRRT_2")
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert [a.title for a in desktop.announcements] == ["1 fix ready on widgets#101"]
    assert runs.asked == [FixesAsked(
        (((("Ada", "please rename the helper"),), "did: rename the helper"),), 100)]


def test_a_batch_whose_every_fix_was_handled_is_dropped(tmp_path, desktop, clock, runs):
    board = Board()
    notifications, courier = opened(tmp_path, desktop, clock, runs, board)

    _fix(notifications, "PRRT_1")
    board.handled.add("PRRT_1")
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)
    board.handled.clear()
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert desktop.announcements == []
    assert runs.asked == []


def _comment(notifications, key="PRRT_1", body="the IN list could hit the 65k parameter limit",
             action="New thread", author="Ada", at="2026-09-24T15:46:00Z",
             review_comment=False, pr=84):
    notifications.thread_news.comment_arrived(
        a_pr(pr, "acme/widgets"), key, comment_id=1, author=author, body=body,
        created_at=at, opens_thread=action == "New thread", reopens=action == "Reopened",
        review_comment=review_comment)


def test_comments_three_minutes_apart_from_the_first_go_out_as_one_banner(tmp_path, desktop,
                                                                          clock, runs):
    board = Board()
    board.fixes = {"PRRT_1": FixProgress.STARTED, "PRRT_2": FixProgress.QUEUED}
    notifications, courier = opened(tmp_path, desktop, clock, runs, board)
    runs.answer(("this loop could be one query", "still flaky", "looks fine"))

    _comment(notifications, "PRRT_1", at="2026-09-24T15:46:00Z", review_comment=True)
    _comment(notifications, "PRRT_2", "this still fails on staging", "Reopened",
                                  "Reviewer B", at="2026-09-24T15:47:00Z")
    _comment(notifications, "PRRT_3", "thanks", "Reply", "Reviewer B",
                                  at="2026-09-24T15:48:00Z")
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert _shown(desktop) == [(
        Badge.COMMENTS, "3 comments on widgets#84 · 1 fix started, 1 queued",
        'New thread | Fix started | Ada (review comment): "this loop could be one query"\n'
        'Reopened | Fix queued | Reviewer B: "still flaky"\n'
        'Reply | No fix | Reviewer B: "looks fine"',
    )]


def test_comments_open_their_pr_on_its_board(store, desktop, clock, runs):
    notifications, courier = store
    runs.answer(("this loop could be one query",))

    _comment(notifications, pr=84)
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert [a.link for a in desktop.announcements] == ["http://127.0.0.1:8721/pr/acme/widgets/84"]


def test_the_gist_is_asked_of_each_new_comment_itself(tmp_path, desktop, clock, runs):
    notifications, courier = opened(tmp_path, desktop, clock, runs)
    runs.answer("still flaky")

    _comment(notifications, body="this still fails on staging", action="Reply")
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert runs.asked == [CommentsAsked(("this still fails on staging",), 60)]


def test_without_gists_within_a_minute_each_comment_stands_in_for_its_own(tmp_path, desktop,
                                                                          clock, runs):
    notifications, courier = opened(tmp_path, desktop, clock, runs)

    _comment(notifications, body="thanks, looks good to me")
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)
    clock.advance(minutes=1)
    courier.deliver(LONG_AWAKE, None)

    assert [a.body for a in desktop.announcements] == [
        'New thread | No fix | Ada: "thanks, looks good to me"']


def test_a_comment_the_account_has_answered_is_left_out(tmp_path, desktop, clock, runs):
    board = Board()
    notifications, courier = opened(tmp_path, desktop, clock, runs, board)
    runs.answer("still flaky")

    _comment(notifications, "PRRT_1")
    _comment(notifications, "PRRT_2", "this still fails on staging", "Reply")
    board.handled.add("PRRT_1")
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert [a.title for a in desktop.announcements] == ["1 comment on widgets#84"]


def test_comments_wait_for_the_pr_manager_to_take_them_in(tmp_path, desktop, clock, runs):
    board = Board()
    board.busy.add((a_pr(84, "acme/widgets")))
    notifications, courier = opened(tmp_path, desktop, clock, runs, board)
    runs.answer("this loop could be one query")

    _comment(notifications)
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert desktop.announcements == []

    board.busy.clear()
    board.fixes = {"PRRT_1": FixProgress.QUEUED}
    courier.deliver(LONG_AWAKE, None)

    assert [a.title for a in desktop.announcements] == [
        "1 comment on widgets#84 · 1 fix queued"]


def test_comments_stop_waiting_on_a_pr_manager_after_a_minute(tmp_path, desktop, clock, runs):
    board = Board()
    board.busy.add((a_pr(84, "acme/widgets")))
    notifications, courier = opened(tmp_path, desktop, clock, runs, board)
    runs.answer("this loop could be one query")

    _comment(notifications)
    clock.advance(minutes=4)
    courier.deliver(LONG_AWAKE, None)

    assert [a.title for a in desktop.announcements] == ["1 comment on widgets#84"]


class _Unreadable(Board):
    def settling(self, pr):
        raise RuntimeError(f"{pr} will not parse")


def test_a_batch_that_cannot_be_looked_up_does_not_hold_back_the_others(tmp_path, desktop,
                                                                         clock, runs):
    notifications, courier = opened(tmp_path, desktop, clock, runs, _Unreadable())
    runs.answer("rename the helper")

    _comment(notifications)
    _fix(notifications)
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert [a.title for a in desktop.announcements] == ["1 fix ready on widgets#101"]
