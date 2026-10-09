import plistlib

from tests.cli.scripted_system import Job

HUB = "http://127.0.0.1:8720"
PLIST = "com.github-orchestrator.watcher.plist"


def _launchctl(machine):
    return [call.cmd[1] for call in machine.system.calls if call.cmd[0] == "launchctl"]


def test_start_writes_and_loads_the_launchagent_and_waits_for_the_hub(machine, run_cli):
    machine.while_asleep.append(lambda: machine.answering_hubs.add(HUB))

    ran = run_cli("start")

    plist = machine.home / "Library" / "LaunchAgents" / PLIST
    assert ran.code == 0, ran.out
    assert ran.out == f"Started the watcher. Hub: {HUB} (watching)\n"
    assert machine.system.loaded_plist == str(plist)
    assert plistlib.loads(plist.read_bytes())["ProgramArguments"][0] == machine.python
    assert _launchctl(machine) == ["print", "bootout", "bootstrap", "kickstart", "print"]


def test_start_says_so_and_changes_nothing_when_the_watcher_is_already_running(
        machine, run_cli, restartable):
    ran = run_cli("start")

    assert ran.code == 0, ran.out
    assert ran.out == f"The watcher is already running. Hub: {HUB}\n"
    assert _launchctl(machine) == ["print"]
    assert restartable.read_text() == "<plist/>"


def test_start_reloads_a_watcher_launchd_holds_but_is_not_running(machine, run_cli, restartable):
    machine.system.job = Job("not running", "/gone/uv", "OS_REASON_CODESIGNING")
    machine.answering_hubs.add(HUB)

    ran = run_cli("start")

    assert ran.code == 0, ran.out
    assert ran.out == f"Started the watcher. Hub: {HUB} (watching)\n"
    assert machine.system.loaded_plist == str(restartable)


def test_start_fails_when_the_hub_does_not_answer_within_thirty_seconds(machine, run_cli):
    ran = run_cli("start")

    assert ran.code == 1
    assert ran.out == (f"The watcher started, but its hub at {HUB} did not answer within 30s. "
                       "github-orchestrator logs shows why.\n")
    assert machine.slept == [1.0] * 29


def test_start_in_the_foreground_runs_the_watcher_in_this_terminal(machine, run_cli):
    machine.platform = "linux"
    machine.system.watcher_exit = 3

    ran = run_cli("start", "--foreground")

    assert ran.code == 3
    [call] = [call for call in machine.system.calls if call.cmd[0] == machine.python]
    assert call.cmd == [machine.python, "-m", "github_orchestrator.watcher", "--loop"]
    assert call.env["GITHUB_ORCHESTRATOR_CONFIG"] == str(machine.config_path)
    assert call.env["GITHUB_ORCHESTRATOR_DATA_DIR"] == str(machine.data_dir)


def test_ctrl_c_ends_a_foreground_watcher_quietly(machine, run_cli):
    machine.system.watcher_interrupted = True

    ran = run_cli("start", "--foreground")

    assert ran.code == 0
    assert ran.out == ""
