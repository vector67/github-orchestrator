import tomllib

import pytest

from tests.cli.scripted_system import Job

HUB = "http://127.0.0.1:8720"
MANAGER = "/tools/bin/python -m github_orchestrator.pr_manager --repo acme/app --pr 12"


def _toml(path):
    return tomllib.loads(path.read_text())


def _from_tmux_mode(machine):
    machine.configure('pr_windows = "browser"\nidle_threshold = 30\n')


def _restartable_instance(machine, name):
    other = machine.another_instance(name)
    other.configure('pr_windows = "tmux"\n')
    plist = machine.home / "Library" / "LaunchAgents" / f"com.github-orchestrator.watcher.{name}.plist"
    plist.write_text("<plist/>")
    machine.system.jobs[f"com.github-orchestrator.watcher.{name}"] = Job()
    other.settings().watcher_heartbeat.write_text(machine.now.isoformat())
    return other


@pytest.mark.parametrize("command", ["restart", "restart-all"])
def test_a_restart_migrates_the_config_before_it_restarts_the_watcher(
        machine, run_cli, restartable, command):
    _from_tmux_mode(machine)
    old = machine.config_path.read_text()

    ran = run_cli(command)

    assert ran.code == 0, ran.out
    assert "pr_windows" not in _toml(machine.config_path)
    assert "idle_threshold" not in _toml(machine.config_path)
    backup = machine.config_path.with_name("config.toml.bak")
    assert backup.read_text() == old
    assert ran.out.startswith(
        f"==> Migrating the config\nRewrote {machine.config_path} for this release; "
        f"the old one is {backup}\n==> Restarting the agent managers\n")


def test_restart_all_migrates_every_instance(machine, run_cli, restartable):
    _from_tmux_mode(machine)
    other = _restartable_instance(machine, "second")

    ran = run_cli("restart-all")

    assert ran.code == 0, ran.out
    assert "pr_windows" not in _toml(other.config_path)
    assert other.config_path.with_name("second.toml.bak").exists()
    assert "==> Migrating the config for second\n" in ran.out


def test_restart_migrates_only_this_instance(machine, run_cli, restartable):
    other = _restartable_instance(machine, "second")

    run_cli("restart")

    assert "pr_windows" in _toml(other.config_path)


def test_start_migrates_the_config_and_starts(machine, run_cli):
    _from_tmux_mode(machine)
    machine.while_asleep.append(lambda: machine.answering_hubs.add(HUB))

    ran = run_cli("start")

    assert ran.code == 0, ran.out + ran.err
    assert "pr_windows" not in _toml(machine.config_path)
    assert ran.out.endswith(f"Started the watcher. Hub: {HUB} (watching)\n")


def test_a_restart_with_nothing_to_migrate_says_nothing_about_it(machine, run_cli, restartable):
    ran = run_cli("restart")

    assert "Migrating" not in ran.out
    assert not machine.config_path.with_name("config.toml.bak").exists()


def test_a_command_that_does_not_migrate_refuses_a_config_from_tmux_mode(machine, run_cli):
    _from_tmux_mode(machine)

    ran = run_cli("queue", "12")

    assert ran.code == 2
    assert "pr_windows and idle_threshold are no longer read" in ran.err
    assert "`github-orchestrator restart`" in ran.err
    assert "pr_windows" in _toml(machine.config_path)


def test_a_restart_stops_the_agent_managers_tmux_mode_left_in_the_prs_session(
        machine, run_cli, restartable):
    machine.system.tmux_sessions = {"prs": {"301": [MANAGER], "302": ["zsh"]}}

    ran = run_cli("restart")

    assert ran.code == 0, ran.out
    assert machine.system.tmux_sessions == {"prs": {"301": [], "302": ["zsh"]}}
    assert ("Stopped 1 agent manager tmux mode left in the prs session; the watcher starts "
            "it again in the background.\n") in ran.out


def test_a_tmux_session_other_than_prs_is_never_touched(machine, run_cli, restartable):
    sessions = {"main-1": {"401": [MANAGER]}, "prs-2": {"402": [MANAGER]}}
    machine.system.tmux_sessions = {name: {pane: list(children) for pane, children in panes.items()}
                                    for name, panes in sessions.items()}

    ran = run_cli("restart")

    assert ran.code == 0, ran.out
    assert machine.system.tmux_sessions == sessions
    assert [call.cmd for call in machine.system.calls if call.cmd[0] == "pkill"] == []
    assert not any(call.cmd[:2] in (["tmux", "kill-session"], ["tmux", "kill-window"])
                   for call in machine.system.calls)


def test_restart_all_migrates_every_instance_before_it_restarts_any(machine, run_cli, restartable):
    other = _restartable_instance(machine, "second")
    machine.settings().watcher_heartbeat.unlink()

    ran = run_cli("restart-all")

    assert ran.code == 1
    assert "pr_windows" not in _toml(other.config_path)
    assert ran.out.index("==> Migrating the config for second") < ran.out.index(
        "==> Restarting the agent managers\n")
