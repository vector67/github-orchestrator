import json
import threading
from pathlib import Path

import pytest
from pr_summary.witnesses import (
    PROMPT,
    RETRY_WAIT_SECONDS,
    Launch,
    command,
    run_witnesses,
)

PLUGIN_ROOT = Path(__file__).resolve().parents[2] / "plugins" / "pr-summary"

AGENT = """---
name: why
description: Why the change was needed.
tools: Read, Write, Glob, mcp__atlassian__getJiraIssue, mcp__claude_ai_Atlassian_MCP__searchConfluence
model: opus
---
You are the why witness.
"""


def test_a_witness_runs_restricted_as_its_plugin_agent_with_its_atlassian_tools_allowed(tmp_path: Path) -> None:
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "why.md").write_text(AGENT)

    argv = command("why", tmp_path)

    assert argv[:3] == ["claude", "-p", "--restricted"]
    assert argv[argv.index("--plugin-dir") + 1] == str(tmp_path)
    assert argv[argv.index("--agent") + 1] == "pr-summary:why"
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert argv[argv.index("--allowedTools") + 1 :] == ["mcp__atlassian__getJiraIssue", "mcp__claude_ai_Atlassian_MCP__searchConfluence"]


def test_a_witness_without_atlassian_tools_allows_nothing_extra(tmp_path: Path) -> None:
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "claimed.md").write_text(AGENT.replace(", mcp__atlassian__getJiraIssue, mcp__claude_ai_Atlassian_MCP__searchConfluence", ""))

    assert "--allowedTools" not in command("claimed", tmp_path)


def no_wait(seconds: float) -> None:
    pass


def manifest_in(tmp_path: Path, names: list[str]) -> dict[str, Path]:
    manifest = {}
    for name in names:
        manifest[name] = tmp_path / name
        manifest[name].mkdir()
    return manifest


def test_the_witnesses_run_together_then_the_judge_reads_their_outputs(tmp_path: Path) -> None:
    manifest = manifest_in(tmp_path, ["requested", "claimed", "implementation", "tests", "why", "alignment"])
    started: list[str] = []
    together = threading.Barrier(5, timeout=5)
    seen_by_judge: list[str] = []

    def launch(witness: str, folder: Path) -> bool:
        started.append(witness)
        if witness == "alignment":
            seen_by_judge.extend(sorted(path.name for path in folder.iterdir()))
            return True
        together.wait()
        (folder / "output.json").write_text(f'{{"witness": "{witness}"}}')
        return True

    run_witnesses(manifest, launch, no_wait)

    assert started[-1] == "alignment"
    assert sorted(started[:5]) == ["claimed", "implementation", "requested", "tests", "why"]
    assert seen_by_judge == ["claimed.json", "implementation.json", "requested.json", "tests.json", "why.json"]


def test_a_failed_witness_leaves_the_rest_and_the_judge_running(tmp_path: Path) -> None:
    manifest = manifest_in(tmp_path, ["claimed", "implementation", "tests", "why", "alignment"])
    judged: list[str] = []

    def launch(witness: str, folder: Path) -> bool:
        if witness == "why":
            raise TimeoutError
        if witness == "alignment":
            judged.extend(sorted(path.name for path in folder.iterdir()))
            return True
        (folder / "output.json").write_text("{}")
        return True

    failures = run_witnesses(manifest, launch, no_wait)

    assert failures == {"why": "TimeoutError"}
    assert judged == ["claimed.json", "implementation.json", "tests.json"]


def test_the_prompt_names_no_pull_request() -> None:
    assert "output.json" in PROMPT


UNAVAILABLE = json.dumps({"witness": "requested", "unavailable": "the Atlassian tools never connected"})


def judging(unavailable_launches: int) -> tuple[list[str], dict[str, str], Launch]:
    launches: list[str] = []
    judged: dict[str, str] = {}

    def launch(witness: str, folder: Path) -> bool:
        launches.append(witness)
        if witness == "alignment":
            judged.update({path.name: path.read_text() for path in folder.iterdir()})
            return True
        if witness == "requested" and launches.count("requested") <= unavailable_launches:
            (folder / "output.json").write_text(UNAVAILABLE)
        else:
            (folder / "output.json").write_text(f'{{"witness": "{witness}"}}')
        return True

    return launches, judged, launch


def test_a_witness_whose_tools_were_unavailable_runs_again_after_a_wait_and_its_second_answer_is_judged(tmp_path: Path) -> None:
    manifest = manifest_in(tmp_path, ["requested", "claimed", "alignment"])
    launches, judged, launch = judging(unavailable_launches=1)
    waits: list[float] = []

    failures = run_witnesses(manifest, launch, waits.append)

    assert failures == {}
    assert launches.count("requested") == 2
    assert waits == [RETRY_WAIT_SECONDS]
    assert judged["requested.json"] == '{"witness": "requested"}'


def test_a_witness_whose_tools_stay_unavailable_fails_with_the_reason_and_is_not_judged(tmp_path: Path) -> None:
    manifest = manifest_in(tmp_path, ["requested", "claimed", "alignment"])
    launches, judged, launch = judging(unavailable_launches=2)

    failures = run_witnesses(manifest, launch, no_wait)

    assert failures == {"requested": "its tools stayed unavailable: the Atlassian tools never connected"}
    assert launches.count("requested") == 2
    assert sorted(judged) == ["claimed.json"]


@pytest.mark.parametrize("agent", sorted(path.name for path in (PLUGIN_ROOT / "agents").glob("*.md")))
def test_every_agent_names_each_of_its_tools_and_how_to_report_one_unavailable(agent: str) -> None:
    _, frontmatter, body = (PLUGIN_ROOT / "agents" / agent).read_text().split("---", 2)
    tools = next(line for line in frontmatter.splitlines() if line.startswith("tools:")).removeprefix("tools:").split(",")

    assert [tool.strip() for tool in tools if f"`{tool.strip()}`" not in body] == []
    assert '"unavailable"' in body


def test_a_retried_witness_starts_without_its_first_answer(tmp_path: Path) -> None:
    manifest = manifest_in(tmp_path, ["requested", "alignment"])
    found_on_launch: list[bool] = []

    def launch(witness: str, folder: Path) -> bool:
        if witness == "requested":
            found_on_launch.append((folder / "output.json").exists())
            (folder / "output.json").write_text(UNAVAILABLE)
        return True

    run_witnesses(manifest, launch, no_wait)

    assert found_on_launch == [False, False]
