import plistlib

import pytest

from tests.cli.scripted_system import Job
from tests.cli.support import CONFIGURED

HUB = "http://127.0.0.1:8720"
LABEL = "com.github-orchestrator.watcher"


@pytest.fixture
def unpinned(machine):
    machine.config_path.unlink()
    machine.pinned_config = False
    machine.answering_hubs.add(HUB)
    return machine


@pytest.fixture
def checkout(tmp_path):
    folder = tmp_path / "checkout"
    folder.mkdir()
    (folder / "pyproject.toml").write_text("[project]\n")
    (folder / "config.toml").write_text(CONFIGURED)
    return folder


def _plist(machine, label=LABEL):
    return machine.home / "Library" / "LaunchAgents" / f"{label}.plist"


def _old_plist(machine, arguments, environment=None, label=LABEL):
    plist = _plist(machine, label)
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_bytes(plistlib.dumps({
        "Label": label, "ProgramArguments": arguments,
        "EnvironmentVariables": environment or {"PATH": "/usr/bin"}, "KeepAlive": True}))
    machine.system.jobs[label] = Job(program=arguments[0])
    return plist


def _uv_run(checkout):
    return ["/opt/homebrew/bin/uv", "run", "--project", str(checkout), "python", "-m",
            "github_orchestrator.watcher", "--loop"]


def test_the_installer_s_start_moves_the_config_a_uv_run_launchagent_names(
        unpinned, run_cli, checkout):
    _old_plist(unpinned, _uv_run(checkout))

    ran = run_cli("start", "--from-installer")

    assert ran.code == 0, ran.out
    assert unpinned.config_path.read_text() == CONFIGURED
    assert not (checkout / "config.toml").exists()
    assert (checkout / "config.toml.bak").read_text() == CONFIGURED
    assert f"Moved {checkout / 'config.toml'} to {unpinned.config_path}" in ran.out
    assert unpinned.system.reran == 1


def test_the_config_a_launchagent_pins_in_its_environment_is_found_too(
        unpinned, run_cli, checkout):
    _old_plist(unpinned, [str(checkout / ".venv" / "bin" / "python"), "-m",
                          "github_orchestrator.watcher", "--loop"],
               {"PATH": "/usr/bin", "GITHUB_ORCHESTRATOR_CONFIG": str(checkout / "config.toml")})

    run_cli("start", "--from-installer")

    assert unpinned.config_path.read_text() == CONFIGURED


def test_a_config_already_in_the_config_folder_is_never_overwritten(unpinned, run_cli, checkout):
    _old_plist(unpinned, _uv_run(checkout))
    unpinned.configure('agent_model = "sonnet"\n')
    kept = unpinned.config_path.read_text()

    ran = run_cli("start", "--from-installer")

    assert unpinned.config_path.read_text() == kept
    assert (checkout / "config.toml").exists()
    assert f"{unpinned.config_path} is already there" in ran.out
    assert unpinned.system.reran == 0


def test_a_config_pinned_by_the_environment_is_left_where_it_is(machine, run_cli, checkout):
    _old_plist(machine, _uv_run(checkout))
    machine.answering_hubs.add(HUB)

    run_cli("start", "--from-installer")

    assert (checkout / "config.toml").exists()
    assert machine.system.reran == 0


def test_the_installer_s_start_rewrites_every_instance_s_service_keeping_the_old_one(
        unpinned, run_cli, checkout):
    unpinned.configure()
    old = _old_plist(unpinned, _uv_run(checkout))
    work = unpinned.another_instance("work")
    work_plist = _old_plist(unpinned, _uv_run(checkout), label=f"{LABEL}.work")
    before = old.read_bytes()

    ran = run_cli("start", "--from-installer")

    assert ran.code == 0, ran.out
    for plist in (old, work_plist):
        assert plistlib.loads(plist.read_bytes())["ProgramArguments"][0] == unpinned.python
        assert plist.with_name(f"{plist.name}.bak").exists()
    assert old.with_name(f"{old.name}.bak").read_bytes() == before
    assert unpinned.system.jobs[f"{LABEL}.work"] is not None
    assert work.config_path.exists()
    assert ran.out.endswith(f"Hub: {HUB} (watching)\n")


def test_a_service_already_in_the_new_layout_gets_no_backup(unpinned, run_cli):
    unpinned.configure()
    run_cli("start", "--from-installer")

    run_cli("start", "--from-installer")

    assert not _plist(unpinned).with_name(f"{LABEL}.plist.bak").exists()


def test_plain_start_and_restart_all_never_move_the_config_or_rewrite_other_services(
        unpinned, run_cli, checkout):
    plist = _old_plist(unpinned, _uv_run(checkout))
    unpinned.system.job = Job()

    run_cli("start")
    run_cli("restart-all")

    assert (checkout / "config.toml").exists()
    assert not unpinned.config_path.exists()
    assert unpinned.system.reran == 0
    assert not plist.with_name(f"{plist.name}.bak").exists()


def test_start_with_no_config_yet_starts_the_hub_in_setup(unpinned, run_cli):
    unpinned.hub_state = "setup"
    unpinned.while_asleep.append(lambda: None)

    ran = run_cli("start")

    assert ran.code == 0, ran.out + ran.err
    assert ran.out.endswith(f"Started the watcher. Hub: {HUB} (setup)\n")


CRON = ("MAILTO=me\n"
        "# github-orchestrator begin\n"
        "PATH=/usr/bin\n"
        "GITHUB_ORCHESTRATOR_DATA_DIR=/home/me/.local/share/github-orchestrator\n"
        "* * * * * /usr/bin/uv run --project {checkout} python -m github_orchestrator.watcher "
        ">> /tmp/watcher.log 2>&1\n"
        "# github-orchestrator end\n"
        "0 9 * * * backup\n")


def test_on_linux_the_crontab_block_names_the_old_config_and_is_removed(
        unpinned, run_cli, checkout):
    unpinned.platform = "linux"
    unpinned.system.crontab = CRON.format(checkout=checkout)

    moved = run_cli("start", "--from-installer")
    ran = run_cli("start", "--from-installer")

    assert (moved.code, ran.code) == (0, 0), ran.out
    assert unpinned.system.reran == 1
    assert unpinned.config_path.read_text() == CONFIGURED
    assert unpinned.system.crontab == "MAILTO=me\n0 9 * * * backup\n"
    assert (unpinned.config_path.parent / "crontab.bak").read_text() == CRON.format(
        checkout=checkout)
    assert unpinned.system.units["github-orchestrator.service"] == "active"
