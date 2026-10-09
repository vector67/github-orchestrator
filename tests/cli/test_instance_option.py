import sys

import pytest

import github_orchestrator.cli.__main__ as cli_main
from tests.cli.support import Machine


@pytest.fixture
def entry(monkeypatch, tmp_path):
    machine = Machine(data_dir=tmp_path, home=tmp_path)
    machine.configure()
    seen: list[dict[str, str]] = []

    def built(env, home):
        seen.append(dict(env))
        return machine.container()

    monkeypatch.setattr(cli_main, "make_container", built)
    monkeypatch.delenv("GITHUB_ORCHESTRATOR_INSTANCE", raising=False)

    def run(*argv: str) -> tuple[int, dict[str, str] | None]:
        monkeypatch.setattr(sys, "argv", ["github-orchestrator", *argv])
        code = cli_main.main()
        return code, seen[-1] if seen else None

    return run


@pytest.mark.parametrize("argv", [
    ("--instance", "work", "queue", "1"),
    ("queue", "1", "--instance", "work"),
    ("queue", "--instance=work", "1"),
])
def test_instance_names_the_instance_every_command_acts_on(entry, argv):
    code, env = entry(*argv)

    assert code == 0
    assert env["GITHUB_ORCHESTRATOR_INSTANCE"] == "work"


def test_without_instance_the_environment_is_left_as_it_is(entry):
    code, env = entry("queue", "1")

    assert code == 0
    assert "GITHUB_ORCHESTRATOR_INSTANCE" not in env


def test_the_name_config_is_reserved_for_the_default_instance(entry, capsys):
    code, env = entry("--instance", "config", "status")

    assert code == 2
    assert env is None
    assert "config is reserved" in capsys.readouterr().err


def test_the_reserved_name_is_refused_from_the_environment_too(entry, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ORCHESTRATOR_INSTANCE", "config")

    code, env = entry("status")

    assert code == 2
    assert "config is reserved" in capsys.readouterr().err


def test_an_instance_name_that_is_not_a_plain_name_is_refused(entry, capsys):
    code, _ = entry("--instance", "../work", "status")

    assert code == 2
    assert "letters, digits" in capsys.readouterr().err


def test_every_command_s_help_lists_instance(run_cli):
    for command in ("status", "start", "logs", "doctor", "queue"):
        assert "--instance NAME" in run_cli(command, "--help").out
