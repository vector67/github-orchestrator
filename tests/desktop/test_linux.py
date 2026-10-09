from pathlib import Path

from github_orchestrator.desktop import Badge, Desktop
from github_orchestrator.wiring import DesktopWiring, wire
from tests.desktop.scripted_linux import ScriptedLinux

URL = "http://127.0.0.1:8720/"


def _desktop(linux):
    desktop: Desktop = wire(DesktopWiring(linux, Path("/nowhere"), platform="linux")).get(Desktop)
    return desktop


def test_a_url_is_opened_with_xdg_open():
    linux = ScriptedLinux()

    assert _desktop(linux).open_url(URL) is None
    assert linux.ran == [(["xdg-open", URL], None)]


def test_opening_without_xdg_open_says_it_is_missing():
    linux = ScriptedLinux(installed=set())

    assert _desktop(linux).open_url(URL) == "xdg-open is not on PATH"


def test_an_announcement_goes_through_notify_send_without_a_click_action():
    linux = ScriptedLinux()

    reason = _desktop(linux).announce(Badge.COMMENTS, "2 comments on widgets#101",
                                      "alice: why?", "n-1", URL)

    assert reason is None
    assert linux.ran == [(["notify-send", "--app-name", "github-orchestrator",
                           "2 comments on widgets#101", "alice: why?"], None)]


def test_without_notify_send_an_announcement_is_skipped_quietly():
    linux = ScriptedLinux(installed={"xdg-open"})

    assert _desktop(linux).announce(Badge.READY, "3 fixes ready", "", "n-1", None) is None
    assert linux.ran == []


def test_notifications_are_ready_when_notify_send_is_on_the_path(tmp_path):
    notify_send = tmp_path / "notify-send"
    notify_send.write_text("#!/bin/sh\n")
    notify_send.chmod(0o755)

    assert _desktop(ScriptedLinux()).notifications(str(tmp_path)) is None


def test_without_notify_send_on_the_path_the_fix_names_its_package(tmp_path):
    problem, fix = _desktop(ScriptedLinux()).notifications(str(tmp_path))

    assert "notify-send" in problem
    assert "libnotify-bin" in fix
