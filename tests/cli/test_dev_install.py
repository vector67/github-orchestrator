import plistlib
from pathlib import Path

import pytest

from github_orchestrator.wiring import uv_tool_dir

TOOL = "github-orchestrator"


@pytest.fixture
def checkout(machine, tmp_path):
    folder = tmp_path / "checkout"
    (folder / ".venv" / "bin").mkdir(parents=True)
    (folder / ".venv" / "bin" / "python").touch()
    (folder / "pyproject.toml").touch()
    machine.python = str(folder / ".venv" / "bin" / "python")
    return folder


def _tool(machine, requirement):
    venv = machine.tool_dir / TOOL
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").touch()
    (venv / "uv-receipt.toml").write_text(
        f'[tool]\nrequirements = [{{ name = "{TOOL}", {requirement} }}]\n')
    return venv / "bin" / "python"


def _program(plist):
    return plistlib.loads(plist.read_bytes())["ProgramArguments"][0]


def test_restart_all_from_a_checkout_runs_the_watcher_on_its_editable_uv_tool(
        machine, run_cli, restartable, checkout):
    tool_python = _tool(machine, f'editable = "{checkout}"')

    ran = run_cli("restart-all")

    assert ran.code == 0
    assert _program(restartable) == str(tool_python)
    assert ran.under("Restarting the watcher").startswith(
        f"The watcher runs on {tool_python}: the uv tool {TOOL} is an editable install of "
        f"this checkout ({checkout}).\n")


@pytest.mark.parametrize(("requirement", "source"), [
    ('editable = "/elsewhere/gho"', "/elsewhere/gho (editable)"),
    ('path = "/dl/gho-0.4.0-py3-none-any.whl"', "/dl/gho-0.4.0-py3-none-any.whl"),
])
def test_a_uv_tool_installed_from_anywhere_else_is_left_alone_and_restart_says_why(
        machine, run_cli, restartable, checkout, requirement, source):
    _tool(machine, requirement)

    ran = run_cli("restart")

    assert ran.code == 0
    assert _program(restartable) == machine.python
    assert ran.under("Restarting the watcher").startswith(
        f"The watcher runs on {machine.python}: the uv tool {TOOL} in "
        f"{machine.tool_dir / TOOL} is installed from {source}, not from this checkout "
        f"({checkout}).\n")


def test_without_a_uv_tool_a_checkout_restarts_on_its_own_python_and_says_nothing_of_it(
        machine, run_cli, restartable, checkout):
    ran = run_cli("restart-all")

    assert ran.code == 0
    assert _program(restartable) == machine.python
    assert "The watcher runs on" not in ran.out


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_start_from_a_checkout_writes_the_service_on_its_editable_uv_tool_and_says_so(
        machine, run_cli, checkout, platform):
    machine.platform = platform
    tool_python = _tool(machine, f'editable = "{checkout}"')
    machine.answering_hubs.add("http://127.0.0.1:8720")

    ran = run_cli("start")

    assert ran.code == 0, ran.out
    assert ran.out.startswith(f"The watcher runs on {tool_python}: ")
    assert str(tool_python) in _written_service(machine, platform)


def _written_service(machine, platform):
    if platform == "darwin":
        return _program(machine.home / "Library" / "LaunchAgents"
                        / "com.github-orchestrator.watcher.plist")
    return (machine.home / ".config" / "systemd" / "user" / "github-orchestrator.service"
            ).read_text()


def test_doctor_run_from_a_checkout_with_its_editable_uv_tool_finds_the_tool_install(
        machine, run_cli, checkout, tmp_path):
    tool_python = _tool(machine, f'editable = "{checkout}"')
    command = tool_python.parent / TOOL
    command.touch()
    link = tmp_path / "local-bin" / TOOL
    link.parent.mkdir()
    link.symlink_to(command)
    machine.located[TOOL] = str(link)

    ran = run_cli("doctor")

    assert f"ok    {TOOL} " in ran.out
    assert f"a uv tool in {tool_python.parent.parent}, installed from {checkout} (editable)" in ran.out
    assert f"ok    {TOOL} on PATH ({link}) is the uv tool's command" in ran.out
    assert "not a uv tool install" not in ran.out



@pytest.mark.parametrize(("variables", "tools"), [
    ({"UV_TOOL_DIR": "/uv-tool-dir", "XDG_DATA_HOME": "/xdg"}, "/uv-tool-dir"),
    ({"UV_TOOL_DIR": "", "XDG_DATA_HOME": "/xdg"}, "/xdg/uv/tools"),
    ({}, "/home/me/.local/share/uv/tools"),
])
def test_the_uv_tool_is_looked_for_where_uv_keeps_it(variables, tools):
    assert uv_tool_dir(variables, Path("/home/me")) == Path(tools)
