from pathlib import Path

from github_orchestrator.agent_runs import Agent

APP = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"


def test_codex_on_the_path_is_the_codex_command():
    assert Agent.CODEX.default_command(which=lambda name: f"/opt/tools/{name}",
                                       exists=lambda path: True) == "/opt/tools/codex"


def test_without_codex_on_the_path_the_chatgpt_apps_codex_is_the_command():
    assert Agent.CODEX.default_command(which=lambda name: None,
                                       exists=lambda path: path == APP) == APP


def test_with_no_codex_anywhere_the_command_is_plain_codex():
    assert Agent.CODEX.default_command(which=lambda name: None,
                                       exists=lambda path: False) == "codex"


def test_claudes_command_is_claude_wherever_it_is():
    assert Agent.CLAUDE.default_command(which=lambda name: None,
                                        exists=lambda path: False) == "claude"


def test_each_agent_keeps_its_skills_in_its_own_folder():
    home = Path("/home/me")

    assert (Agent.CLAUDE.skill_folder(home), Agent.CODEX.skill_folder(home)) == (
        Path("/home/me/.claude/skills"), Path("/home/me/.agents/skills"))
