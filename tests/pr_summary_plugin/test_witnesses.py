import threading
from pathlib import Path

from pr_summary.witnesses import PROMPT, command, run_witnesses

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

    run_witnesses(manifest, launch)

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

    failures = run_witnesses(manifest, launch)

    assert failures == {"why": "TimeoutError"}
    assert judged == ["claimed.json", "implementation.json", "tests.json"]


def test_the_prompt_names_no_pull_request() -> None:
    assert "output.json" in PROMPT
