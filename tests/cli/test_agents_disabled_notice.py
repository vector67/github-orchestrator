import pytest

from tests.builders import a_pr


@pytest.fixture
def disabled(machine):
    machine.configure("agents_enabled = false\n")
    return machine


THE_PR = a_pr(7, "o/n")


def test_status_says_claude_is_disabled(disabled, run_cli):
    lines = run_cli("status").out.splitlines()
    assert lines[2].startswith("Watcher:")
    assert lines[3] == (
        f"Agents are disabled (agents_enabled = false in {disabled.config_path}) — "
        "spawning events notify and drain without starting a run")


def test_status_says_nothing_when_claude_is_enabled(run_cli):
    assert "Agents are disabled" not in run_cli("status").out


def test_runs_explains_no_runs_when_claude_is_disabled(disabled, run_cli):
    out = run_cli("runs").out
    assert "0 runs" in out
    assert "Agents are disabled (agents_enabled = false in " in out


def test_the_notice_never_orphans_the_runs_summary_lines(disabled, run_cli):
    disabled.runs().ran(THE_PR, "ci-failed", 60, disabled.now, cost_usd=0.4)
    disabled.runs().ran(THE_PR, "ci-failed", 30, disabled.now)
    lines = run_cli("runs").out.splitlines()
    assert lines[0].startswith("Runs today")
    assert lines[-1].startswith("Agents are disabled")
    assert all(line.startswith("  ") for line in lines[1:-1])
