import fcntl
import json
from contextlib import contextmanager
from datetime import timedelta, timezone
from importlib import metadata

import pytest


def _beat(machine, seconds_ago, *, naive_utc=False):
    stamp = machine.now - timedelta(seconds=seconds_ago)
    if naive_utc:
        stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
    machine.settings().watcher_heartbeat.write_text(stamp.isoformat())


@contextmanager
def _lock(machine, mode=fcntl.LOCK_EX):
    lock = machine.settings().watcher_lock
    if not lock.exists():
        lock.write_text("")
    holder = open(lock, "a")
    fcntl.flock(holder, mode | fcntl.LOCK_NB)
    try:
        yield lock
    finally:
        holder.close()


def _fail(machine, error="poll blew up", times=1):
    record = {"consecutive": times, "last_error": error}
    machine.settings().watcher_failures.write_text(json.dumps(record))


def _line(run_cli, starting):
    ran = run_cli("status")
    [line] = [line for line in ran.out.splitlines() if line.startswith(starting)]
    return line


def _health(run_cli):
    return _line(run_cli, "Watcher:")


def test_a_recent_poll_by_a_live_daemon_reads_alive(machine, run_cli):
    _beat(machine, 42)
    with _lock(machine):
        assert _health(run_cli) == "Watcher: alive, last polled 42s ago"


def test_a_heartbeat_written_without_a_zone_is_read_as_utc(machine, run_cli):
    _beat(machine, 42, naive_utc=True)
    with _lock(machine):
        assert _health(run_cli) == "Watcher: alive, last polled 42s ago"


def test_a_live_daemon_that_stopped_polling_says_so(machine, run_cli):
    _beat(machine, 720)
    with _lock(machine):
        assert _health(run_cli) == (
            "Watcher: running but has not polled for 12m (expected every 1m)")


def test_no_lock_holder_means_not_running(machine, run_cli):
    _beat(machine, 90)
    machine.settings().watcher_lock.write_text("")
    assert _health(run_cli) == "Watcher: not running — last polled 1m ago"


def test_a_lock_that_does_not_exist_reads_as_not_running(machine, run_cli):
    _beat(machine, 90)
    assert _health(run_cli).startswith("Watcher: not running")


def test_a_watcher_that_has_never_polled_says_so_either_way(machine, run_cli):
    assert _health(run_cli) == "Watcher: not running, no poll recorded yet"
    with _lock(machine):
        assert _health(run_cli) == (
            "Watcher: running but no cycle has ever succeeded — no poll recorded yet")


def test_a_corrupt_heartbeat_reads_as_no_poll_at_all(machine, run_cli):
    machine.settings().watcher_heartbeat.write_text("yesterday-ish")
    assert _health(run_cli) == "Watcher: not running, no poll recorded yet"


def test_a_second_status_check_is_not_mistaken_for_a_running_watcher(machine, run_cli):
    _beat(machine, 42)
    with _lock(machine, fcntl.LOCK_SH):
        assert _health(run_cli).startswith("Watcher: not running")


def test_the_lock_is_never_truncated_by_the_check(machine, run_cli):
    lock = machine.settings().watcher_lock
    lock.write_text("owner data")
    run_cli("status")
    assert lock.read_text() == "owner data"


def test_failures_name_the_last_error(machine, run_cli):
    _fail(machine, "watcher cannot search acme/widgets as octocat — "
                   "check [[repos]] and gh_account in config.toml", times=106)
    with _lock(machine):
        health = _health(run_cli)
    assert health.startswith("Watcher: failing — no cycle has ever succeeded; last error: ")
    assert health.endswith("check [[repos]] and gh_account in config.toml")


def test_failures_after_a_good_poll_still_date_the_last_good_poll(machine, run_cli):
    _beat(machine, 300)
    _fail(machine, times=2)
    with _lock(machine):
        assert _health(run_cli) == (
            "Watcher: failing — last good poll 5m ago; last error: poll blew up")


def test_a_stopped_watcher_with_a_streak_still_says_it_is_not_running(machine, run_cli):
    _beat(machine, 300)
    _fail(machine, times=3)
    health = _health(run_cli)
    assert health.startswith("Watcher: not running — last good poll 5m ago")
    assert "poll blew up" in health


def test_a_multi_line_error_stays_on_one_status_line(machine, run_cli):
    _fail(machine, "gh: Not Found\nrun gh auth login")
    assert _health(run_cli).endswith("last error: gh: Not Found run gh auth login")


@pytest.mark.parametrize("seconds,shown", [(59, "59s"), (3599, "59m"), (7300, "2h")])
def test_the_age_is_shown_in_its_largest_whole_unit(machine, run_cli, seconds, shown):
    machine.configure("watcher_poll_interval = 86400\n")
    _beat(machine, seconds)
    with _lock(machine):
        assert _health(run_cli) == f"Watcher: alive, last polled {shown} ago"


def _hub(run_cli):
    return _line(run_cli, "Hub:")


def test_status_gives_the_address_of_the_hub_a_live_watcher_serves(machine, run_cli):
    machine.answering_hubs.add("http://127.0.0.1:8720")
    _beat(machine, 42)
    with _lock(machine):
        assert _hub(run_cli) == "Hub: http://127.0.0.1:8720, watching 1 repo"


def test_status_gives_the_hub_on_the_port_the_config_names(machine, run_cli):
    machine.configure("hub_port = 9100\n")
    machine.answering_hubs.add("http://127.0.0.1:9100")
    _beat(machine, 42)
    with _lock(machine):
        assert _hub(run_cli) == "Hub: http://127.0.0.1:9100, watching 1 repo"


def test_a_hub_that_answers_is_up_while_its_watcher_fails_every_cycle(machine, run_cli):
    machine.answering_hubs.add("http://127.0.0.1:8720")
    _fail(machine, "gh: not logged in", times=40)
    assert _hub(run_cli) == "Hub: http://127.0.0.1:8720, watching 1 repo"


def test_a_hub_that_answers_is_up_whatever_the_watcher_lock_says(machine, run_cli):
    machine.answering_hubs.add("http://127.0.0.1:8720")
    _beat(machine, 90)
    assert _hub(run_cli) == "Hub: http://127.0.0.1:8720, watching 1 repo"


def test_a_hub_that_answers_has_its_watcher_running_whatever_the_lock_says(machine, run_cli):
    machine.answering_hubs.add("http://127.0.0.1:8720")
    _beat(machine, 42)
    assert _health(run_cli) == "Watcher: alive, last polled 42s ago"


def test_status_first_names_the_version_the_hub_runs_and_the_instance(machine, run_cli):
    machine.answering_hubs.add("http://127.0.0.1:8720")

    assert run_cli("status").out.splitlines()[0] == "github-orchestrator 0.4.0 (default instance)"


def test_status_names_this_command_s_version_when_no_hub_answers(machine, run_cli):
    assert run_cli("status").out.splitlines()[0] == (
        f"github-orchestrator {metadata.version('github-orchestrator')} (default instance)")


def test_status_names_another_instance_by_its_name(machine, run_cli):
    machine.instance = "work"
    machine.configure()
    machine.answering_hubs.add("http://127.0.0.1:8720")

    assert run_cli("status").out.splitlines()[0] == "github-orchestrator 0.4.0 (instance work)"


def test_status_says_a_hub_in_setup_and_what_its_config_lacks(machine, run_cli):
    machine.config_path.write_text("")
    machine.hub_state = "setup"
    machine.answering_hubs.add("http://127.0.0.1:8720")

    hub = _hub(run_cli)

    assert hub.startswith("Hub: http://127.0.0.1:8720, in setup — ")
    assert "gh_account, repos must be set" in hub


def test_status_says_a_hub_whose_config_does_not_parse_is_broken(machine, run_cli):
    machine.configure("claud_enabled = false\n")
    machine.hub_state = "broken"
    machine.answering_hubs.add("http://127.0.0.1:8720")

    hub = _hub(run_cli)

    assert hub.startswith("Hub: http://127.0.0.1:8720, config broken — ")
    assert "unknown key 'claud_enabled'" in hub


def test_a_running_watcher_whose_hub_does_not_answer_says_so(machine, run_cli):
    _beat(machine, 42)
    with _lock(machine):
        assert _hub(run_cli) == "Hub: http://127.0.0.1:8720 — not answering"


def test_the_hub_is_down_while_the_watcher_is_not_running(machine, run_cli):
    _beat(machine, 90)
    assert _hub(run_cli) == "Hub: http://127.0.0.1:8720 — down while the watcher is not running"


def _font_lines(run_cli):
    return [line for line in run_cli("status").out.splitlines() if line.startswith("Font:")]


def test_status_warns_when_the_font_directory_is_missing(machine, run_cli):
    missing = machine.home / "design" / "fonts"
    machine.configure(f'board_font_dir = "{missing}"\n')

    [line] = _font_lines(run_cli)

    assert str(missing) in line
    assert "cannot be listed" in line


def test_status_warns_when_the_font_directory_holds_no_face(machine, run_cli):
    fonts = machine.home / "fonts"
    fonts.mkdir()
    machine.configure(f'board_font_dir = "{fonts}"\n')

    [line] = _font_lines(run_cli)

    assert "no <Family>-<Style>.otf face" in line


def test_only_status_speaks_of_a_missing_font_directory(machine, run_cli, caplog):
    machine.configure(f'board_font_dir = "{machine.home / "nowhere"}"\n')

    ran = run_cli("runs")

    assert "board_font_dir" not in ran.out + ran.err + caplog.text


def test_status_says_nothing_of_the_font_when_none_is_configured(machine, run_cli):
    assert _font_lines(run_cli) == []

def test_a_linux_watcher_is_resident_so_its_lock_says_whether_it_runs(machine, run_cli):
    machine.platform = "linux"
    _beat(machine, 90)
    assert _health(run_cli) == "Watcher: not running — last polled 1m ago"
    with _lock(machine):
        assert _health(run_cli) == "Watcher: alive, last polled 1m ago"


def test_a_watcher_whose_hub_is_in_setup_polls_nothing(machine, run_cli):
    machine.config_path.write_text("")
    machine.hub_state = "setup"
    machine.answering_hubs.add("http://127.0.0.1:8720")

    assert _health(run_cli) == "Watcher: running, polling nothing until the config is complete"


def test_status_exits_0_while_the_hub_watches_and_the_watcher_polls(machine, run_cli):
    machine.answering_hubs.add("http://127.0.0.1:8720")
    _beat(machine, 42)

    assert run_cli("status").code == 0


def test_status_exits_1_when_no_hub_answers(machine, run_cli):
    _beat(machine, 42)
    with _lock(machine):
        assert run_cli("status").code == 1


def test_status_exits_1_while_the_hub_is_in_setup(machine, run_cli):
    machine.config_path.write_text("")
    machine.hub_state = "setup"
    machine.answering_hubs.add("http://127.0.0.1:8720")

    assert run_cli("status").code == 1


def test_status_exits_1_while_every_cycle_fails(machine, run_cli):
    machine.answering_hubs.add("http://127.0.0.1:8720")
    _fail(machine, "gh: not logged in", times=4)

    assert run_cli("status").code == 1


def test_status_exits_1_when_the_watcher_stopped_polling(machine, run_cli):
    machine.answering_hubs.add("http://127.0.0.1:8720")
    _beat(machine, 720)

    assert run_cli("status").code == 1


UPDATE = "Update available: 0.6.0. Run github-orchestrator update."


def test_status_says_an_update_is_available_when_the_hub_has_seen_a_newer_release(
        machine, run_cli):
    machine.answering_hubs.add("http://127.0.0.1:8720")
    machine.newest_release = {"version": "0.6.0", "checked_at": "2026-09-24T08:00:00+00:00",
                              "newer": True}

    assert run_cli("status").out.splitlines()[1] == UPDATE
    assert machine.releases_api.asked == []


def test_status_says_nothing_of_a_release_that_is_not_newer(machine, run_cli):
    machine.answering_hubs.add("http://127.0.0.1:8720")
    machine.newest_release = {"version": "0.4.0", "checked_at": "2026-09-24T08:00:00+00:00",
                              "newer": False}

    assert "Update available" not in run_cli("status").out


def test_with_the_daily_check_off_status_asks_github_itself(machine, run_cli):
    machine.configure("check_for_updates = false\n")
    machine.answering_hubs.add("http://127.0.0.1:8720")
    machine.releases_api.publish("0.6.0")

    assert run_cli("status").out.splitlines()[1] == UPDATE


def test_with_the_daily_check_off_and_github_unreachable_status_says_nothing_of_updates(
        machine, run_cli):
    machine.configure("check_for_updates = false\n")
    machine.answering_hubs.add("http://127.0.0.1:8720")

    assert "Update available" not in run_cli("status").out
