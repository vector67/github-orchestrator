import re
from pathlib import Path

from tests.agent_runs.cli_flags import assert_the_cli_takes, invocations, usage

SKILL = (Path(__file__).resolve().parents[2] / ".claude" / "skills"
         / "handle-pull-request-feedback-autonomous" / "SKILL.md")

_RELAYED_VERDICT = re.compile(r"thread ready[^\n]*?--tests ([a-z]+)")


def _relayed_verdicts() -> list[str]:
    return _RELAYED_VERDICT.findall(SKILL.read_text().replace("\\\n", " "))


def test_the_skill_reports_through_the_commands_the_cli_takes():
    found = invocations(SKILL.read_text())
    assert {verb for verb, _ in found} == {"open", "plan", "step", "skip",
                                           "ready", "fail"}
    for verb, flags in found:
        assert_the_cli_takes(verb, flags)


def test_every_verdict_the_skill_relays_is_one_the_cli_accepts():
    accepted = re.search(r"--tests\s+\{([^}]*)\}", usage("ready")).group(1)

    relayed = _relayed_verdicts()
    assert relayed
    assert set(relayed) <= set(accepted.split(","))


def test_the_skill_never_relays_a_verdict_the_subagent_did_not_report():
    assert "passed" not in _relayed_verdicts(), (
        "the RESULT: grammar has nowhere to report a test outcome, so a "
        "relayed 'passed' is the orchestrator's assertion and not the "
        "agent's observation"
    )


def test_the_skill_reports_the_fix_through_the_summary_the_panel_draws():
    ready = [flags for verb, flags in invocations(SKILL.read_text())
             if verb == "ready"]

    assert ready
    assert all("--note" not in flags for flags in ready)
