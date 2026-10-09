import json
from datetime import timezone
from pathlib import Path

import pytest

from github_orchestrator.change_detection import CiFailed, CiSucceeded, PrClosed
from github_orchestrator.desktop import Badge
from github_orchestrator.desktop.fake import Announcement, FakeDesktop
from tests.builders import a_pr
from tests.desktop.scripted_mac import Failure, ScriptedMac
from tests.desktop.support import real_desktop
from tests.notifications.support import LONG_AWAKE, Clock, opened


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def desktop():
    return FakeDesktop()


@pytest.fixture
def store(tmp_path, desktop, clock):
    return opened(tmp_path, desktop, clock)


def _shown(desktop):
    return [(a.badge, a.title, a.body) for a in desktop.announcements]


def _ci_passed(notifications, number=84, *checks):
    notifications.pr_status.changed(a_pr(number, "acme/widgets"),
                                      CiSucceeded(checks or ("unit-tests",)))


def test_nothing_is_shown_until_the_courier_delivers(store, desktop):
    notifications, _ = store

    _ci_passed(notifications)

    assert desktop.announcements == []


def test_a_posted_notification_is_shown_under_its_badge_on_delivery(store, desktop):
    notifications, courier = store

    _ci_passed(notifications)
    courier.deliver(LONG_AWAKE, None)

    assert _shown(desktop) == [
        (Badge.INFO, "CI passed — PR #84", "Checks passed: unit-tests (success)")]


def test_a_delivered_notification_is_not_shown_again(store, desktop):
    notifications, courier = store

    _ci_passed(notifications)
    courier.deliver(LONG_AWAKE, None)
    courier.deliver(LONG_AWAKE, None)

    assert len(desktop.announcements) == 1


def test_notifications_are_shown_oldest_first(store, desktop, clock):
    notifications, courier = store

    _ci_passed(notifications, 1)
    clock.advance(seconds=1)
    _ci_passed(notifications, 2)
    clock.advance(seconds=1)
    _ci_passed(notifications, 3)
    courier.deliver(LONG_AWAKE, None)

    assert [a.title for a in desktop.announcements] == [
        "CI passed — PR #1", "CI passed — PR #2", "CI passed — PR #3"]


def test_each_notification_is_shown_under_a_key_of_its_own(store, desktop):
    notifications, courier = store

    _ci_passed(notifications, 1)
    _ci_passed(notifications, 2)
    courier.deliver(LONG_AWAKE, None)

    first, second = desktop.announcements
    assert first.key != second.key


def test_a_notification_posted_before_a_restart_is_shown_after_it(tmp_path, desktop, clock):
    before, _ = opened(tmp_path, FakeDesktop(), clock)
    before.worktrees.init_failed(Path("/work/feature-x"), 1)

    _, after = opened(tmp_path, desktop, clock)
    after.deliver(LONG_AWAKE, None)

    assert _shown(desktop) == [(
        Badge.FAILED, "Worktree init failed",
        "new_worktree_command exited 1 in feature-x; the worktree is usable but uninitialised")]


def test_a_notification_shown_more_than_half_an_hour_late_says_when_it_was_posted(store, desktop, clock):
    notifications, courier = store

    _ci_passed(notifications)
    clock.advance(minutes=31)
    courier.deliver(LONG_AWAKE, None)

    assert [a.title for a in desktop.announcements] == ["CI passed — PR #84 (from 17:46)"]


def test_a_notification_shown_within_half_an_hour_reads_as_posted(store, desktop, clock):
    notifications, courier = store

    _ci_passed(notifications)
    clock.advance(minutes=29)
    courier.deliver(LONG_AWAKE, None)

    assert [a.title for a in desktop.announcements] == ["CI passed — PR #84"]


def test_a_notification_posted_from_another_timezone_says_the_local_time(tmp_path, desktop, clock):
    def utc():
        return clock().astimezone(timezone.utc)

    posting, _ = opened(tmp_path, FakeDesktop(), utc)
    _ci_passed(posting)
    clock.advance(hours=2)

    _, courier = opened(tmp_path, desktop, clock)
    courier.deliver(LONG_AWAKE, None)

    assert [a.title for a in desktop.announcements] == ["CI passed — PR #84 (from 17:46)"]


def test_a_notification_the_badge_app_could_not_show_is_tried_again(tmp_path, clock):
    mac = ScriptedMac().answer("open", Failure(1, "LSOpenURLsWithRole() failed"))
    notifications, courier = opened(tmp_path, real_desktop(mac=mac), clock)

    _ci_passed(notifications)
    courier.deliver(LONG_AWAKE, None)
    courier.deliver(LONG_AWAKE, None)

    assert mac.world.announcements == [
        Announcement(Badge.INFO, "CI passed — PR #84", "Checks passed: unit-tests (success)",
                     mac.world.announcements[0].key, "http://127.0.0.1:8721/pr/acme/widgets/84"),
    ]


def test_a_notification_about_a_pr_opens_that_pr_on_its_board(store, desktop):
    notifications, courier = store

    _ci_passed(notifications, 84)
    courier.deliver(LONG_AWAKE, None)

    assert [a.link for a in desktop.announcements] == ["http://127.0.0.1:8721/pr/acme/widgets/84"]


def test_a_notification_about_no_pr_opens_nothing(store, desktop):
    notifications, courier = store

    notifications.polling.failed(3, "gh timed out", Path("/logs/watcher.log"))
    courier.deliver(LONG_AWAKE, None)

    assert [a.link for a in desktop.announcements] == [None]


def test_a_closed_pr_has_no_board_left_to_open(store, desktop):
    notifications, courier = store

    notifications.pr_status.changed(a_pr(84, "acme/widgets"),
                                   PrClosed(merged=True, no_longer_relevant=False))
    notifications.pr_status.changed(a_pr(85, "acme/widgets"),
                                   PrClosed(merged=False, no_longer_relevant=True))
    courier.deliver(LONG_AWAKE, None)

    assert [a.link for a in desktop.announcements] == [None, None]


def test_a_pr_in_every_watched_repo_calls_for_you_whatever_repos_the_board_shows(store, desktop):
    notifications, courier = store

    for repo in ("acme/widgets", "acme/gadgets"):
        notifications.thread_news.needs_your_call(a_pr(7, repo), author="carol",
                                                  classification="question", reason="unsure")
    courier.deliver(LONG_AWAKE, None)

    assert [(a.badge, a.link) for a in desktop.announcements] == [
        (Badge.NEEDS_YOU, "http://127.0.0.1:8721/pr/acme/widgets/7"),
        (Badge.NEEDS_YOU, "http://127.0.0.1:8721/pr/acme/gadgets/7")]


def test_a_notification_queued_before_it_named_its_pr_is_shown_opening_nothing(tmp_path,
                                                                             desktop, clock):
    tmp_path.joinpath("1-1-0.json").write_text(json.dumps({
        "badge": "info", "title": "CI passed — PR #84",
        "body": "Checks passed: unit-tests (success)", "posted_at": clock().isoformat()}))
    _, courier = opened(tmp_path, desktop, clock)

    courier.deliver(LONG_AWAKE, None)

    assert [(a.title, a.link) for a in desktop.announcements] == [("CI passed — PR #84", None)]


def test_a_failing_check_on_a_pr_is_not_shown(store, desktop):
    notifications, courier = store

    notifications.pr_status.changed(a_pr(84, "acme/widgets"),
                                      CiFailed("lint", "E501"))
    courier.deliver(LONG_AWAKE, None)

    assert desktop.announcements == []
