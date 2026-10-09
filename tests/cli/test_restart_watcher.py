import plistlib

import pytest

from tests.cli.scripted_system import Job

TARGET = "gui/501/com.github-orchestrator.watcher"
WATCHER = "Restarting the watcher"
RESTARTED = "Restarted the watcher daemon. Agent managers were left running.\n"


@pytest.fixture
def uv(tmp_path):
    path = tmp_path / "uv"
    path.write_text("")
    return path


def test_the_watcher_is_reloaded_from_the_plist_and_started(machine, run_cli, restartable):
    ran = run_cli("restart-all")

    assert ran.code == 0
    assert ran.under(WATCHER) == RESTARTED
    assert machine.system.loaded_plist == str(restartable)
    assert machine.system.job.state == "running"


def test_bootstrap_is_retried_while_the_old_job_is_still_unloading(machine, run_cli, restartable):
    machine.system.bootstrap_refusals = 2

    ran = run_cli("restart-all")

    assert ran.code == 0
    assert ran.under(WATCHER) == RESTARTED
    assert machine.slept == [1, 1]


def test_a_failing_bootout_is_ignored(machine, run_cli, restartable):
    machine.system.bootout_exit = 3

    ran = run_cli("restart-all")

    assert ran.code == 0
    assert ran.under(WATCHER) == RESTARTED


def test_a_persistently_failing_bootstrap_gives_up_and_reports_the_last_refusal(
    machine, run_cli, restartable,
):
    machine.system.bootstrap_refusals = 10

    ran = run_cli("restart-all")

    assert ran.code == 1
    assert ran.under(WATCHER) == ("launchctl bootstrap kept failing; the watcher is not loaded.\n"
                                  "Bootstrap failed: 5: Input/output error\n")
    assert machine.system.job is None


def test_a_failing_kickstart_reports_what_launchctl_said(machine, run_cli, restartable):
    machine.system.kickstart_refusal = "Could not find service in domain\n"

    ran = run_cli("restart-all")

    assert ran.code == 1
    assert ran.under(WATCHER) == f"launchctl kickstart {TARGET} failed.\nCould not find service in domain\n"


def test_a_hanging_launchctl_times_out_rather_than_blocking(machine, run_cli, restartable):
    machine.system.hangs = {"kickstart"}

    ran = run_cli("restart-all")

    assert ran.code == 1
    assert ran.under(WATCHER) == f"launchctl kickstart {TARGET} timed out after 30s.\n"


def test_a_hanging_bootout_times_out_rather_than_blocking(machine, run_cli, restartable):
    machine.system.hangs = {"bootout"}

    ran = run_cli("restart-all")

    assert ran.code == 1
    assert "timed out" in ran.under(WATCHER)


def test_it_waits_for_a_slow_spawn_before_declaring_failure(machine, run_cli, restartable):
    machine.system.starting_reads = 2

    ran = run_cli("restart-all")

    assert ran.code == 0
    assert machine.slept == [0.5, 0.5]


def test_a_watcher_that_never_starts_is_reported_with_launchds_own_state(
    machine, run_cli, restartable, uv,
):
    machine.system.starts_as = Job("spawn scheduled", str(uv), "78: EX_CONFIG")

    ran = run_cli("restart-all")

    assert ran.code == 1
    assert ran.under(WATCHER) == (
        "The watcher was reloaded but is not running.\n"
        "  launchd state: spawn scheduled\n"
        "  last exit code: 78: EX_CONFIG\n"
        f"  program: {uv}\n"
    )
    assert len(machine.slept) == 9


def test_a_program_that_is_gone_is_named_as_the_reason(machine, run_cli, restartable, tmp_path):
    gone = tmp_path / "moved" / "uv"
    machine.system.starts_as = Job("spawn scheduled", str(gone), "78: EX_CONFIG")

    ran = run_cli("restart-all")

    assert ran.code == 1
    assert f"  program: {gone} — this file does not exist" in ran.under(WATCHER)
    assert "Reinstall github-orchestrator" in ran.under(WATCHER)
    assert "Restarted the watcher daemon" not in ran.under(WATCHER)


def _rendered(plist):
    return plistlib.loads(plist.read_bytes())


def test_the_restart_rewrites_the_launchagent_to_run_this_python_before_reloading_it(
        machine, run_cli, restartable):
    machine.shell_path = "/usr/bin:/bin"

    ran = run_cli("restart-all")

    assert ran.code == 0, ran.out
    assert _rendered(restartable) == {
        "Label": "com.github-orchestrator.watcher",
        "ProgramArguments": [machine.python, "-m", "github_orchestrator.watcher", "--loop"],
        "EnvironmentVariables": {
            "PATH": "/usr/bin:/bin",
            "GITHUB_ORCHESTRATOR_DATA_DIR": str(machine.data_dir),
            "GITHUB_ORCHESTRATOR_CONFIG": str(machine.config_path),
        },
        "KeepAlive": True,
        "ThrottleInterval": 1,
        "StandardOutPath": str(machine.data_dir / "logs" / "launchd.log"),
        "StandardErrorPath": str(machine.data_dir / "logs" / "launchd.log"),
    }
    assert (machine.data_dir / "logs").is_dir()


def test_the_rewritten_launchagent_needs_no_uv(machine, run_cli, restartable):
    machine.uv = None

    ran = run_cli("restart-all")

    assert ran.code == 0, ran.out
    assert _rendered(restartable)["EnvironmentVariables"]["PATH"] == machine.shell_path


def test_a_mac_with_no_launchagent_gets_one_written_and_loaded(machine, run_cli):
    machine.settings().watcher_heartbeat.parent.mkdir(parents=True, exist_ok=True)
    machine.settings().watcher_heartbeat.write_text(machine.now.isoformat())

    ran = run_cli("restart-all")

    plist = machine.home / "Library" / "LaunchAgents" / "com.github-orchestrator.watcher.plist"
    assert ran.code == 0, ran.out
    assert ran.under(WATCHER) == RESTARTED
    assert machine.system.loaded_plist == str(plist)
    assert _rendered(plist)["Label"] == "com.github-orchestrator.watcher"


@pytest.mark.parametrize("instance", [None, "config"])
def test_the_default_instance_keeps_the_watchers_label(machine, run_cli, restartable, instance):
    machine.instance = instance
    machine.configure()

    run_cli("restart-all")

    assert _rendered(restartable)["Label"] == "com.github-orchestrator.watcher"


def test_the_launchagent_path_keeps_only_existing_absolute_folders_once_in_order(
        machine, run_cli, restartable, tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    machine.shell_path = ":".join(
        [str(second), "~/x", str(tmp_path / "missing"), "", "relative/bin", str(first),
         str(second)])

    run_cli("restart-all")

    assert _rendered(restartable)["EnvironmentVariables"]["PATH"] == f"{second}:{first}"
