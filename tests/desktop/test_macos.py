import os
import subprocess
import time

from github_orchestrator.desktop import Badge
from github_orchestrator.desktop.fake import FakeDesktop
from tests.desktop.scripted_mac import BADGE_APPS, Failure, ScriptedMac
from tests.desktop.support import real_desktop


def test_opening_reports_a_non_zero_exit_with_the_stderr_on_one_line():
    mac = ScriptedMac().answer("open", Failure(1, "The file /nope does not exist.\n"))

    reason = real_desktop(mac=mac).open_url("http://127.0.0.1:4321/")

    assert reason == "open exited 1: The file /nope does not exist."


def test_opening_reports_a_timeout():
    mac = ScriptedMac().answer("open", subprocess.TimeoutExpired(cmd=["open"], timeout=10))

    reason = real_desktop(mac=mac).open_url("http://127.0.0.1:4321/")

    assert reason == "open timed out after 10s"


def test_opening_reports_a_program_that_would_not_start():
    mac = ScriptedMac().answer("open", OSError("no pty"))

    reason = real_desktop(mac=mac).open_url("http://127.0.0.1:4321/")

    assert reason == "open failed: no pty"


def test_a_failure_to_open_is_logged_once(caplog):
    desktop = real_desktop(FakeDesktop(macos=False))

    with caplog.at_level("WARNING"):
        reason = desktop.open_url("http://127.0.0.1:4321/")

    assert [r.getMessage() for r in caplog.records] == [reason]


def test_announcing_reports_a_badge_app_that_would_not_open():
    mac = ScriptedMac().answer("open", Failure(1, "Unable to find application named 'GHO Info'\n"))

    reason = real_desktop(mac=mac).announce(Badge.INFO, "CI passed — PR #1", "", "n-1", None)

    assert reason == "open exited 1: Unable to find application named 'GHO Info'"


def test_announcing_reports_nothing_once_the_badge_app_opens():
    assert real_desktop(mac=ScriptedMac()).announce(Badge.INFO, "CI passed — PR #1", "", "n-1", None) is None


def _built_apps(apps, *, stamped):
    for name in BADGE_APPS:
        info = apps / name / "Contents" / "Info.plist"
        info.parent.mkdir(parents=True)
        info.write_text("<plist/>")
        os.utime(info, (stamped, stamped))
    return apps


def test_notifications_are_ready_when_every_app_is_built_from_these_sources(tmp_path):
    apps = _built_apps(tmp_path, stamped=time.time() + 3600)

    assert real_desktop(apps=apps).notifications("/usr/bin") is None


def test_missing_apps_name_the_command_that_builds_them(tmp_path):
    problem, fix = real_desktop(apps=tmp_path).notifications("/usr/bin")

    assert str(tmp_path) in problem
    assert fix.startswith("sh ")
    assert fix.endswith("/desktop/notifier/build.sh")


def test_apps_older_than_this_versions_sources_are_rebuilt(tmp_path):
    apps = _built_apps(tmp_path, stamped=0)

    problem, fix = real_desktop(apps=apps).notifications("/usr/bin")

    assert "older than" in problem
    assert fix.endswith("/desktop/notifier/build.sh")


def test_without_the_command_line_tools_the_fix_installs_them_first(tmp_path):
    mac = ScriptedMac().answer("xcode-select", Failure(2, "error: unable to get active developer directory"))

    _, fix = real_desktop(mac=mac, apps=tmp_path).notifications("/usr/bin")

    assert fix.startswith("xcode-select --install, then sh ")
