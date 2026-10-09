import re
from pathlib import Path

import pytest

from github_orchestrator.desktop import Badge
from tests.cli.scripted_system import Job

AGENTS = ("Library", "LaunchAgents")
BUILD = (Path(__file__).parents[2] / "src" / "github_orchestrator" / "desktop" / "notifier"
         / "build.sh")


@pytest.fixture(autouse=True)
def data_dir_apart_from_home(machine):
    machine.data_dir = machine.home.parent / "data"
    machine.data_dir.mkdir()
    machine.configure()


@pytest.fixture
def two_instances(machine):
    work = machine.another_instance("work")
    agents = machine.home.joinpath(*AGENTS)
    agents.mkdir(parents=True)
    for label in ("com.github-orchestrator.watcher", "com.github-orchestrator.watcher.work"):
        (agents / f"{label}.plist").write_text("<plist/>")
        machine.system.jobs[label] = Job()
    (agents / "com.github-orchestrator.restart.plist").write_text("<plist/>")
    return work


@pytest.fixture
def apps(machine):
    folder = machine.home / "Applications"
    for name in ("GHO Ready", "GHO Needs You"):
        (folder / f"{name}.app" / "Contents").mkdir(parents=True)
    (folder / "Other.app").mkdir()
    return folder


def _uv(machine):
    return [call.cmd for call in machine.system.calls if call.cmd[0] == machine.uv]


def test_uninstall_says_what_it_removes_and_what_it_keeps_before_asking(
        machine, run_cli, two_instances, apps):
    machine.answers = ["n"]

    ran = run_cli("uninstall")

    assert ran.code == 0, ran.out
    assert ran.out.startswith(
        "This stops every instance and removes:\n"
        "  the LaunchAgents for the default instance and work\n"
        "  the github-orchestrator command (uv tool uninstall)\n"
        "It keeps, unless you say otherwise:\n")
    assert str(machine.config_path.parent) in ran.out
    assert str(machine.data_dir) in ran.out
    assert str(two_instances.data_dir) in ran.out
    assert "Your clones are never touched.\n" in ran.out
    assert machine.prompts == ["Remove the config and data too? [y/N] "]


def test_uninstall_boots_out_and_removes_every_instance_s_launchagent_and_only_those(
        machine, run_cli, two_instances):
    machine.answers = ["n"]

    run_cli("uninstall")

    agents = machine.home.joinpath(*AGENTS)
    assert sorted(path.name for path in agents.iterdir()) == [
        "com.github-orchestrator.restart.plist"]
    assert machine.system.jobs["com.github-orchestrator.watcher"] is None
    assert machine.system.jobs["com.github-orchestrator.watcher.work"] is None


def test_uninstall_removes_the_command_with_uv_last(machine, run_cli, two_instances):
    machine.answers = ["n"]

    run_cli("uninstall")

    assert _uv(machine) == [[machine.uv, "tool", "uninstall", "github-orchestrator"]]
    assert machine.system.calls[-1].cmd[0] == machine.uv


def test_saying_no_keeps_the_config_the_data_and_the_apps(machine, run_cli, two_instances, apps):
    machine.answers = ["n"]

    run_cli("uninstall")

    assert machine.config_path.exists()
    assert two_instances.config_path.exists()
    assert machine.data_dir.exists()
    assert (apps / "GHO Ready.app").exists()


def test_saying_yes_removes_the_config_folder_every_data_dir_and_the_notifier_apps(
        machine, run_cli, two_instances, apps):
    machine.answers = ["y"]
    clone = machine.home / "repositories" / "hello-world"
    clone.mkdir(parents=True)

    ran = run_cli("uninstall")

    assert ran.code == 0, ran.out
    assert not two_instances.config_path.parent.exists()
    assert not two_instances.data_dir.exists()
    assert not machine.data_dir.exists()
    assert sorted(path.name for path in apps.iterdir()) == ["Other.app"]
    assert clone.exists()


def test_yes_removes_the_config_and_data_without_asking(machine, run_cli, two_instances):
    ran = run_cli("uninstall", "--yes")

    assert ran.code == 0, ran.out
    assert machine.prompts == []
    assert not two_instances.data_dir.exists()


def test_no_terminal_to_ask_on_keeps_the_config_and_data(machine, run_cli, two_instances):
    machine.answers = [EOFError]

    run_cli("uninstall")

    assert two_instances.data_dir.exists()


def test_uninstall_on_linux_disables_and_removes_each_unit_then_reloads(machine, run_cli):
    machine.platform = "linux"
    machine.another_instance("work")
    units = machine.home / ".config" / "systemd" / "user"
    units.mkdir(parents=True)
    for unit in ("github-orchestrator.service", "github-orchestrator-work.service"):
        (units / unit).write_text("[Service]\n")
        machine.system.units[unit] = "active"
    machine.answers = ["n"]

    ran = run_cli("uninstall")

    assert ran.code == 0, ran.out
    assert "the systemd units for the default instance and work" in ran.out
    assert list(units.iterdir()) == []
    assert machine.system.units == {}
    systemctl = [call.cmd[2:] for call in machine.system.calls if call.cmd[0] == "systemctl"]
    assert ["disable", "--now", "github-orchestrator.service"] in systemctl
    assert systemctl[-1] == ["daemon-reload"]


def test_without_uv_uninstall_says_how_to_remove_the_command(machine, run_cli):
    machine.uv = None
    machine.answers = ["n"]

    ran = run_cli("uninstall")

    assert ran.code == 1
    assert "uv tool uninstall github-orchestrator" in ran.out + ran.err


def test_every_notifier_app_the_build_makes_matches_what_uninstall_removes(
        machine, run_cli, apps):
    built = re.findall(r'^build \S+ "([^"]+)"$', BUILD.read_text(), re.MULTILINE)
    for name in built:
        (apps / f"{name}.app").mkdir(exist_ok=True)

    run_cli("uninstall", "--yes")

    assert len(built) == len(Badge)
    assert sorted(path.name for path in apps.iterdir()) == ["Other.app"]


def test_uninstall_keeps_the_rebase_skill_and_says_how_to_remove_it(machine, run_cli, two_instances):
    run_cli("skill")
    skill = machine.home / ".claude" / "skills" / "rebase-on-main"

    ran = run_cli("uninstall", "--yes")

    assert ran.code == 0, ran.out
    assert skill.is_dir()
    assert f"rm -rf {skill}" in ran.out


def test_uninstall_says_nothing_of_the_rebase_skill_when_it_is_not_there(
        machine, run_cli, two_instances):
    ran = run_cli("uninstall", "--yes")

    assert "rebase-on-main" not in ran.out
