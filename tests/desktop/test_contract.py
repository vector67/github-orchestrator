import pytest

from github_orchestrator.desktop import Badge
from github_orchestrator.desktop.fake import Announcement, FakeDesktop
from tests.desktop.support import real_desktop


@pytest.fixture(params=["fake", "mac"])
def world_and_desktop(request):
    world = FakeDesktop()
    if request.param == "fake":
        return world, world
    return world, real_desktop(world)


@pytest.fixture
def world(world_and_desktop):
    return world_and_desktop[0]


@pytest.fixture
def desktop(world_and_desktop):
    return world_and_desktop[1]


@pytest.fixture
def away_from_the_mac(request):
    world = FakeDesktop(macos=False)
    return world, world if request.param == "fake" else real_desktop(world)


def test_an_opened_url_is_opened_and_nothing_is_reported(world, desktop):
    assert desktop.open_url("http://127.0.0.1:4321/") is None

    assert world.opened == ["http://127.0.0.1:4321/"]


@pytest.mark.parametrize("away_from_the_mac", ["fake", "mac"], indirect=True)
def test_away_from_the_mac_opening_says_open_is_missing(away_from_the_mac):
    world, desktop = away_from_the_mac

    assert desktop.open_url("http://127.0.0.1:4321/") == "open is not on PATH (macOS only)"
    assert world.opened == []


def test_an_announcement_is_shown_under_its_badge_with_its_title_body_and_key(world, desktop):
    desktop.announce(Badge.READY, "3 fixes ready on widgets#101",
                     "general cleanup and missing tests", "n-1", None)

    assert world.announcements == [
        Announcement(Badge.READY, "3 fixes ready on widgets#101",
                     "general cleanup and missing tests", "n-1", None),
    ]


def test_an_announcement_with_a_link_opens_it_when_clicked(world, desktop):
    desktop.announce(Badge.COMMENTS, "2 comments on widgets#101", "alice: why?", "n-1",
                     "http://127.0.0.1:8721/pr/acme/widgets/101")

    assert [a.link for a in world.announcements] == ["http://127.0.0.1:8721/pr/acme/widgets/101"]


def test_each_badge_is_shown_as_itself(world, desktop):
    desktop.announce(Badge.FAILED, "failed", "", "n-1", None)
    desktop.announce(Badge.NEEDS_YOU, "needs you", "", "n-2", None)
    desktop.announce(Badge.INFO, "info", "", "n-3", None)
    desktop.announce(Badge.COMMENTS, "comments", "", "n-4", None)

    assert [a.badge for a in world.announcements] == [
        Badge.FAILED, Badge.NEEDS_YOU, Badge.INFO, Badge.COMMENTS]


def test_quotes_and_dashes_in_an_announcement_are_shown_as_written(world, desktop):
    desktop.announce(Badge.READY, '--body "x"', "--title; rm -rf /", "--id", "--open")

    assert world.announcements == [
        Announcement(Badge.READY, '--body "x"', "--title; rm -rf /", "--id", "--open")]


@pytest.fixture(params=["fake", "mac"])
def without_the_notifier_apps(request, tmp_path):
    world = FakeDesktop(notifier_apps=False)
    return world, world if request.param == "fake" else real_desktop(world, apps=tmp_path)


def test_without_the_notifier_apps_an_announcement_is_skipped_with_nothing_to_report(
        without_the_notifier_apps):
    world, desktop = without_the_notifier_apps

    assert desktop.announce(Badge.READY, "3 fixes ready", "alice", "n-1", None) is None
    assert world.announcements == []


@pytest.mark.parametrize("away_from_the_mac", ["fake", "mac"], indirect=True)
def test_away_from_the_mac_an_announcement_is_skipped_quietly(away_from_the_mac):
    world, desktop = away_from_the_mac

    desktop.announce(Badge.READY, "3 fixes ready", "alice", "n-1", None)

    assert world.announcements == []
