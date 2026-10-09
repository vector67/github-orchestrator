import fcntl
import plistlib

from tests.builders import a_pr
from tests.cli.scripted_system import Job

SECOND = "com.github-orchestrator.watcher.second"
IN_SECOND = a_pr(22, "acme/gadgets")


def _restartable_instance(machine, name):
    other = machine.another_instance(name)
    plist = machine.home / "Library" / "LaunchAgents" / f"com.github-orchestrator.watcher.{name}.plist"
    plist.write_text("<plist/>")
    machine.system.jobs[f"com.github-orchestrator.watcher.{name}"] = Job()
    other.settings().watcher_heartbeat.write_text(machine.now.isoformat())
    return other, plist


def _launchctl(machine):
    return [call.cmd[1:] for call in machine.system.calls if call.cmd[0] == "launchctl"]


def test_restart_all_restarts_every_other_instance_after_this_one(machine, run_cli, restartable):
    _, plist = _restartable_instance(machine, "second")

    ran = run_cli("restart-all")

    assert ran.code == 0, ran.out
    assert ran.out.endswith(
        "==> Confirming the agent managers came back\n"
        "0 agent manager(s) back up; no event has failed since the restart.\n"
        "==> Restarting the agent managers for second\n"
        "No agent manager processes running.\n"
        "==> Restarting the watcher for second\n"
        "Restarted the watcher daemon. Agent managers were left running.\n"
        "==> Confirming the agent managers came back for second\n"
        "0 agent manager(s) back up; no event has failed since the restart.\n")
    assert _launchctl(machine)[4:] == [
        ["bootout", f"gui/501/{SECOND}"],
        ["bootstrap", "gui/501", str(plist)],
        ["kickstart", f"gui/501/{SECOND}"],
        ["print", f"gui/501/{SECOND}"]]
    assert plistlib.loads(plist.read_bytes())["Label"] == SECOND


def test_another_instances_managers_are_stopped_and_awaited_through_its_own_windows(
        machine, run_cli, restartable, tmp_path):
    other, _ = _restartable_instance(machine, "second")
    worktree = tmp_path / "feature-22"
    worktree.mkdir()
    other.processes().open(IN_SECOND, worktree)
    machine.system.on_kickstart = lambda: other.processes().open(IN_SECOND, worktree)

    ran = run_cli("restart-all")

    assert ran.code == 0, ran.out
    assert ran.under("Restarting the agent managers for second") == (
        "Killed agent manager processes. Watcher will restart them within 1 minute.\n")
    assert ran.under("Confirming the agent managers came back for second") == (
        "1 agent manager(s) back up; no event has failed since the restart.\n")


def test_restart_restarts_only_this_instance(machine, run_cli, restartable):
    _restartable_instance(machine, "second")

    ran = run_cli("restart")

    assert ran.code == 0, ran.out
    assert ran.out == (
        "==> Restarting the agent managers\n"
        "No agent manager processes running.\n"
        "==> Restarting the watcher\n"
        "Restarted the watcher daemon. Agent managers were left running.\n"
        "==> Confirming the agent managers came back\n"
        "0 agent manager(s) back up; no event has failed since the restart.\n")
    assert SECOND not in " ".join(" ".join(call) for call in _launchctl(machine))


def test_restart_waits_for_a_restart_all_holding_the_restart_lock(machine, run_cli, restartable):
    lock = open(machine.settings().restart_lock, "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    machine.while_asleep.append(lock.close)

    ran = run_cli("restart")

    assert ran.code == 0, ran.out
    assert ran.out.startswith("Waiting for another restart to finish")
    assert machine.slept == [2.0]


def test_restart_all_does_not_wait_for_a_poll_from_an_instance_in_setup(
        machine, run_cli, restartable):
    other, _ = _restartable_instance(machine, "second")
    other.config_path.write_text("hub_port = 8899\n")

    ran = run_cli("restart-all")

    assert ran.code == 0, ran.out
    assert ran.under("Confirming the agent managers came back for second") == (
        "The watcher is back in setup; it polls nothing until its config is complete.\n")


def test_restart_brings_back_a_watcher_whose_config_is_not_complete(
        machine, run_cli, restartable):
    machine.config_path.write_text("")

    ran = run_cli("restart")

    assert ran.code == 0, ran.out
    assert ran.out.endswith(
        "The watcher is back in setup; it polls nothing until its config is complete.\n")
