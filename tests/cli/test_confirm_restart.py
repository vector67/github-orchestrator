import json
from datetime import datetime, timedelta
from pathlib import Path

from github_orchestrator.pr_processes import ManagerPane
from tests.builders import a_pr
from tests.pr_event_queue.support import ci_failed, disk_event_queue

MANAGERS = "Restarting the agent managers"
CONFIRM = "Confirming the agent managers came back"


def _running(machine, *prs):
    for pr in (12, *prs):
        worktree = machine.data_dir / f"feature-{pr}"
        worktree.mkdir()
        machine.processes().open(a_pr(pr, "acme/app"), worktree)


def _revive(machine, *prs):
    for pr in prs:
        machine.processes().open(a_pr(pr, "acme/app"), Path("/wt"))


def _back_once_the_watcher_starts(machine, *prs):
    machine.system.on_kickstart = lambda: _revive(machine, *prs)


def _fail_event(machine, pr):
    event_queue = disk_event_queue(machine.settings().queues_dir)
    event_queue.add(a_pr(pr, "acme/app"), ci_failed())
    event_queue.next(a_pr(pr, "acme/app"), is_author=True, agents_enabled=True).failed()


def _watcher_polled(machine, at=None):
    machine.settings().watcher_heartbeat.write_text((at or machine.now).isoformat())


def _watcher_failed(machine, error):
    machine.settings().watcher_failures.write_text(
        json.dumps({"consecutive": 1, "last_error": error}))


def _time_passes(machine, then=None):
    def tick():
        machine.now += timedelta(seconds=2)
        if then is not None:
            then()
    return tick


def test_restart_stops_the_managers_it_finds_and_confirms_each_came_back(machine, run_cli,
                                                                        restartable):
    _running(machine, 40)
    when_the_watcher_restarted = []

    def the_watcher_restarts():
        when_the_watcher_restarted.extend(
            machine.processes().manager(a_pr(pr, "acme/app")) for pr in (12, 40))
        _revive(machine, 12, 40)

    machine.system.on_kickstart = the_watcher_restarts

    ran = run_cli("restart-all")

    assert ran.code == 0
    assert ran.under(MANAGERS) == ("Killed agent manager processes. "
                                   "Watcher will restart them within 1 minute.\n")
    assert when_the_watcher_restarted == [ManagerPane.EXITED, ManagerPane.EXITED]
    assert ran.under(CONFIRM) == (
        "2 agent manager(s) back up; no event has failed since the restart.\n")


def test_restart_with_no_manager_running_says_so_and_waits_for_none(machine, run_cli,
                                                                    restartable):
    ran = run_cli("restart-all")

    assert ran.under(MANAGERS) == "No agent manager processes running.\n"
    assert ran.under(CONFIRM) == (
        "0 agent manager(s) back up; no event has failed since the restart.\n")
    assert machine.slept == []


def test_confirm_restart_waits_out_a_slow_first_poll_then_gives_the_managers_their_time(
        machine, run_cli, restartable):
    _watcher_polled(machine, machine.now - timedelta(minutes=1))
    _running(machine)
    machine.while_asleep.extend(_time_passes(machine) for _ in range(99))
    machine.while_asleep.append(_time_passes(machine, lambda: _watcher_polled(machine)))
    machine.while_asleep.extend(_time_passes(machine) for _ in range(49))
    machine.while_asleep.append(_time_passes(machine, lambda: _revive(machine, 12)))

    ran = run_cli("restart-all")

    assert ran.code == 0
    assert ran.under(CONFIRM) == (
        "Waiting for the watcher to finish its first poll since the restart.\n"
        "The watcher has polled; waiting for 1 agent manager(s) to come back: acme/app#12.\n"
        "1 agent manager(s) back up; no event has failed since the restart.\n")
    assert len(machine.slept) == 150


def test_confirm_restart_says_which_managers_it_is_still_waiting_for(machine, run_cli,
                                                                     restartable):
    _running(machine, 40)
    machine.while_asleep.append(lambda: _revive(machine, 12))
    machine.while_asleep.append(lambda: _revive(machine, 40))

    ran = run_cli("restart-all")

    assert ran.under(CONFIRM) == (
        "The watcher has polled; waiting for 2 agent manager(s) to come back: "
        "acme/app#12, acme/app#40.\n"
        "The watcher has polled; waiting for 1 agent manager(s) to come back: acme/app#40.\n"
        "2 agent manager(s) back up; no event has failed since the restart.\n")


def test_confirm_restart_fails_when_the_watcher_never_polls_after_the_restart(
        machine, run_cli, restartable):
    _watcher_polled(machine, machine.now - timedelta(minutes=1))
    _running(machine)

    ran = run_cli("restart-all")

    assert ran.code == 1
    assert ran.under(CONFIRM) == (
        "Waiting for the watcher to finish its first poll since the restart.\n"
        "The watcher has not finished a poll since the restart.\n"
        "Agent manager for acme/app#12 did not come back.\n")
    assert len(machine.slept) == 449


def test_a_watcher_that_never_polls_names_its_last_error(machine, run_cli, restartable):
    machine.settings().watcher_heartbeat.unlink()
    _watcher_failed(machine, "gh: rate limited")

    ran = run_cli("restart-all")

    assert ran.code == 1
    assert ("The watcher has not finished a poll since the restart; "
            "its last cycle failed: gh: rate limited\n") in ran.under(CONFIRM)


def test_confirm_restart_fails_naming_a_manager_that_never_came_back(machine, run_cli,
                                                                     restartable):
    _running(machine, 40, 99)
    _back_once_the_watcher_starts(machine, 12, 40)

    ran = run_cli("restart-all")

    assert ran.code == 1
    assert ran.under(CONFIRM) == (
        "The watcher has polled; waiting for 1 agent manager(s) to come back: acme/app#99.\n"
        "Agent manager for acme/app#99 did not come back.\n")
    assert len(machine.slept) == 59


def test_confirm_restart_fails_naming_an_event_that_failed_since_the_restart(
        machine, run_cli, restartable):
    _fail_event(machine, 12)
    _running(machine)
    _back_once_the_watcher_starts(machine, 12)

    ran = run_cli("restart-all")

    assert ran.code == 1
    assert ran.under(CONFIRM).startswith(
        "Event failed since the restart: acme/app#12 ci-failed (queued ")


def test_confirm_restart_passes_over_an_event_that_failed_before_the_restart(
        machine, run_cli, restartable):
    _fail_event(machine, 12)
    machine.now = datetime.now().astimezone()
    _watcher_polled(machine)
    _running(machine)
    _back_once_the_watcher_starts(machine, 12)

    ran = run_cli("restart-all")

    assert ran.code == 0
    assert "no event has failed since the restart" in ran.under(CONFIRM)
