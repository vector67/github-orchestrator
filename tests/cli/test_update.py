from pathlib import Path

from tests.cli.scripted_system import Job

NEWER = "99.0.0"
OLDER = "0.0.1"


def _uv_installs(machine):
    return [call.cmd for call in machine.system.calls
            if call.cmd[0] == machine.uv and call.cmd[1:3] == ["tool", "install"]]


def test_update_installs_the_newest_release_and_restarts_every_instance(machine, run_cli):
    machine.releases_api.publish(NEWER)

    ran = run_cli("update")

    assert ran.code == 0, ran.out + ran.err
    [install] = _uv_installs(machine)
    assert install[:6] == [machine.uv, "tool", "install", "--force", "--python", "3.12"]
    assert Path(install[6]).name == f"github_orchestrator-{NEWER}-py3-none-any.whl"
    assert machine.system.installed_wheels == [f"wheel {NEWER}".encode()]
    assert machine.system.reran == 1
    assert [call.cmd[1:] for call in machine.system.calls if call.cmd[0] == machine.python] == [
        ["-m", "github_orchestrator.cli", "start", "--from-installer"]]
    assert ran.out.splitlines()[1:] == [f"==> Installing {NEWER}",
                                        "==> Restarting every instance on the new version",
                                        f"Updated to {NEWER}."]
    assert ran.out.splitlines()[0].endswith(f", newest {NEWER}.")


def test_update_with_nothing_newer_says_so_and_installs_nothing(machine, run_cli):
    machine.releases_api.publish(OLDER)

    ran = run_cli("update")

    assert ran.code == 0
    assert ran.out.splitlines()[-1] == "Already up to date."
    assert _uv_installs(machine) == []


def test_check_only_reports(machine, run_cli):
    machine.releases_api.publish(NEWER)

    ran = run_cli("update", "--check")

    assert ran.code == 0
    assert ran.out.splitlines()[-1] == f"Run github-orchestrator update to install {NEWER}."
    assert _uv_installs(machine) == []


def test_version_installs_that_release_even_an_older_one(machine, run_cli):
    machine.releases_api.publish(OLDER, latest=False)

    ran = run_cli("update", "--version", OLDER)

    assert ran.code == 0, ran.out
    assert machine.system.installed_wheels == [f"wheel {OLDER}".encode()]


def test_a_release_github_cannot_find_fails_with_why(machine, run_cli):
    ran = run_cli("update")

    assert ran.code == 1
    assert "could not look up the newest release" in ran.out + ran.err
    assert _uv_installs(machine) == []


def test_a_failed_install_leaves_the_running_version_and_says_why(machine, run_cli):
    machine.releases_api.publish(NEWER)
    machine.system.uv_install_error = "error: no Python 3.12 found"

    ran = run_cli("update")

    assert ran.code == 1
    assert "no Python 3.12 found" in ran.out + ran.err
    assert machine.system.reran == 0


def test_update_needs_no_complete_config(machine, run_cli, restartable):
    machine.config_path.unlink()
    machine.releases_api.publish(OLDER)
    machine.system.job = Job()

    assert run_cli("update").code == 0
