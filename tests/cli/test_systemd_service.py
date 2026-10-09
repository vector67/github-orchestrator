import pytest

HUB = "http://127.0.0.1:8720"
UNIT = "github-orchestrator.service"
RESTARTED = "Restarted the watcher daemon. Agent managers were left running.\n"


@pytest.fixture
def linux(machine):
    machine.platform = "linux"
    return machine


def _unit_file(machine, name=UNIT):
    return machine.home / ".config" / "systemd" / "user" / name


def _systemctl(machine):
    return [call.cmd[2:] for call in machine.system.calls if call.cmd[0] == "systemctl"]


def test_start_writes_the_unit_enables_it_and_waits_for_the_hub(linux, run_cli):
    linux.while_asleep.append(lambda: linux.answering_hubs.add(HUB))

    ran = run_cli("start")

    assert ran.code == 0, ran.out
    assert ran.out == f"Started the watcher. Hub: {HUB} (watching)\n"
    assert _unit_file(linux).read_text() == (
        "[Unit]\n"
        "Description=github-orchestrator watcher\n"
        "\n"
        "[Service]\n"
        f'ExecStart="{linux.python}" -m github_orchestrator.watcher --loop\n'
        'Environment="PATH=/usr/bin:/bin"\n'
        f'Environment="GITHUB_ORCHESTRATOR_DATA_DIR={linux.data_dir}"\n'
        f'Environment="GITHUB_ORCHESTRATOR_CONFIG={linux.config_path}"\n'
        "Restart=always\n"
        "RestartSec=1\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )
    assert _systemctl(linux) == [
        ["is-active", UNIT], ["daemon-reload"], ["reset-failed", UNIT], ["is-active", UNIT],
        ["enable", "--now", UNIT], ["is-active", UNIT]]
    assert linux.system.units[UNIT] == "active"


@pytest.fixture
def running(linux):
    linux.system.units[UNIT] = "active"
    linux.settings().watcher_heartbeat.write_text(linux.now.isoformat())
    return linux


def test_restart_rewrites_the_unit_and_restarts_the_running_watcher(running, run_cli):
    _unit_file(running).parent.mkdir(parents=True)
    _unit_file(running).write_text("stale")

    ran = run_cli("restart")

    assert ran.code == 0, ran.out
    assert ran.under("Restarting the watcher") == RESTARTED
    assert "ExecStart" in _unit_file(running).read_text()
    assert ["restart", UNIT] in _systemctl(running)
    assert ["enable", "--now", UNIT] not in _systemctl(running)


def test_a_watcher_that_never_comes_up_is_reported_with_systemds_own_state(linux, run_cli):
    linux.system.unit_starts_as = "activating"
    linux.system.exit_status = "2"

    ran = run_cli("start")

    assert ran.code == 1
    assert ran.out == (
        "The watcher was started but is not running.\n"
        "  systemd state: activating (auto-restart)\n"
        "  last exit status: 2\n"
        "github-orchestrator logs service shows why.\n")
    assert linux.slept == [0.5] * 9


def test_without_a_user_manager_start_says_so_and_offers_the_foreground(linux, run_cli):
    linux.system.user_manager = False

    ran = run_cli("start")

    assert ran.code == 1
    assert ran.out == (
        "systemctl --user cannot reach a user manager here, so the watcher cannot run "
        "as a service:\n"
        "  Failed to connect to bus: No medium found\n"
        "Run github-orchestrator start --foreground to run it in this terminal instead.\n")


def test_stop_stops_the_unit(running, run_cli):
    ran = run_cli("stop")

    assert ran.code == 0, ran.out
    assert ran.under("Stopping the watcher") == "Stopped the watcher daemon.\n"
    assert running.system.units[UNIT] == "inactive"


def test_stop_says_so_when_the_unit_was_not_running(linux, run_cli):
    ran = run_cli("stop")

    assert ran.code == 0, ran.out
    assert ran.under("Stopping the watcher") == "The watcher was not running.\n"
    assert ["stop", UNIT] not in _systemctl(linux)


def test_another_instance_gets_a_unit_of_its_own(running, run_cli):
    second = running.another_instance("second")
    second.settings().watcher_heartbeat.write_text(running.now.isoformat())

    ran = run_cli("restart-all")

    assert ran.code == 0, ran.out
    unit = _unit_file(running, "github-orchestrator-second.service").read_text()
    assert "Description=github-orchestrator watcher (second)\n" in unit
    assert f'Environment="GITHUB_ORCHESTRATOR_CONFIG={second.config_path}"\n' in unit


def test_quotes_backslashes_percents_and_dollars_reach_the_watcher_as_written(linux, run_cli, tmp_path):
    odd = tmp_path / 'a "b" 50% \\c'
    odd.mkdir()
    linux.shell_path = str(odd)
    linux.python = "/opt/$HOME/py"
    linux.answering_hubs.add(HUB)

    run_cli("start")

    unit = _unit_file(linux).read_text()
    assert 'ExecStart="/opt/$$HOME/py" -m github_orchestrator.watcher --loop\n' in unit
    assert f'Environment="PATH={tmp_path}/a \\"b\\" 50%% \\\\c"\n' in unit
