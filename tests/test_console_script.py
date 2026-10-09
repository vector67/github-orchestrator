import sys
import tomllib
from importlib import import_module
from pathlib import Path

import github_orchestrator.cli.__main__ as cli_main
from tests.cli.support import Machine

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def console_scripts() -> dict[str, str]:
    return tomllib.loads(PYPROJECT.read_text())["project"].get("scripts", {})


def test_the_console_script_target_resolves_to_a_callable():
    module_path, _, attribute = console_scripts()["github-orchestrator"].partition(":")
    assert callable(getattr(import_module(module_path), attribute))


def test_the_help_usage_line_names_the_installed_command(monkeypatch, capsys, tmp_path):
    machine = Machine(data_dir=tmp_path, home=tmp_path)
    machine.configure()
    (name,) = console_scripts()
    monkeypatch.setattr(sys, "argv", [name, "--help"])
    monkeypatch.setattr(cli_main, "make_container", lambda env, home: machine.container())
    assert cli_main.main() == 0
    assert capsys.readouterr().out.startswith(f"usage: {name} ")


def test_the_entry_point_hands_the_cli_its_arguments_and_returns_its_exit_code(
    monkeypatch, capsys, tmp_path,
):
    machine = Machine(data_dir=tmp_path, home=tmp_path)
    machine.configure()
    monkeypatch.setattr(sys, "argv", ["github-orchestrator", "queue", "86"])
    monkeypatch.setattr(cli_main, "make_container", lambda env, home: machine.container())
    assert cli_main.main() == 0
    assert capsys.readouterr().out == "No queue found for a PR numbered 86\n"

    monkeypatch.setattr(sys, "argv", ["github-orchestrator", "no-such-command"])
    assert cli_main.main() == 2
