import fcntl
import json
import subprocess
import sys

from tests.builders import a_pr


def _lock_is_free(machine):
    with open(machine.settings().restart_lock, "a") as probe:
        try:
            fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(probe, fcntl.LOCK_UN)
        return True


def _hold_the_lock(machine, holder):
    lock = open(machine.settings().restart_lock, "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    lock.write(json.dumps(holder))
    lock.flush()
    return lock


def _a_running_manager(machine):
    worktree = machine.data_dir / "feature-12"
    worktree.mkdir()
    machine.processes().open(a_pr(12, "acme/app"), worktree)


def test_restart_all_restarts_without_syncing_or_building(machine, run_cli, restartable):
    ran = run_cli("restart-all")

    assert ran.code == 0
    assert ran.out == (
        "==> Restarting the agent managers\n"
        "No agent manager processes running.\n"
        "==> Restarting the watcher\n"
        "Restarted the watcher daemon. Agent managers were left running.\n"
        "==> Confirming the agent managers came back\n"
        "0 agent manager(s) back up; no event has failed since the restart.\n")
    assert [call.cmd[:2] for call in machine.system.calls] == [
        ["tmux", "list-panes"], ["launchctl", "bootout"], ["launchctl", "bootstrap"],
        ["launchctl", "kickstart"], ["launchctl", "print"]]


def test_restart_all_restarts_while_holding_the_restart_lock(machine, run_cli, restartable):
    free_while_restarting = []
    machine.system.on_kickstart = lambda: free_while_restarting.append(_lock_is_free(machine))

    ran = run_cli("restart-all")

    assert ran.code == 0
    assert free_while_restarting == [False]
    assert _lock_is_free(machine)


def test_restart_all_takes_no_command_to_run(machine, run_cli, restartable):
    ran = run_cli("restart-all", "make", "restart-all-stages")

    assert ran.code == 2
    assert machine.system.calls == []


def test_a_second_restart_all_waits_for_the_first_then_does_its_own_restart(machine, run_cli,
                                                                            restartable):
    first = _hold_the_lock(machine, {"pid": 4242, "started": "2026-09-28T13:56:01+02:00"})
    machine.while_asleep.append(lambda: None)
    machine.while_asleep.append(first.close)

    ran = run_cli("restart-all")

    assert ran.code == 0
    assert ran.out.startswith(
        "Waiting for the restart started at 2026-09-28T13:56:01+02:00 by pid 4242 "
        "to finish; then this run does its own full restart.\n"
        "==> Restarting the agent managers\n")
    assert machine.slept == [2.0, 2.0]


def test_a_lock_left_by_a_killed_run_does_not_hold_up_the_next(machine, run_cli, restartable):
    lock_path = machine.settings().restart_lock
    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import fcntl, sys, time\n"
         f"lock = open({str(lock_path)!r}, 'w')\n"
         "fcntl.flock(lock, fcntl.LOCK_EX)\n"
         "lock.write('{\"pid\": 1}'); lock.flush()\n"
         "print('locked', flush=True)\n"
         "time.sleep(60)\n"],
        stdout=subprocess.PIPE, text=True)
    assert holder.stdout is not None
    assert holder.stdout.readline() == "locked\n"
    holder.kill()
    holder.wait()

    ran = run_cli("restart-all")

    assert ran.code == 0
    assert ran.out.startswith("==> Restarting the agent managers\n")
    assert machine.slept == []
