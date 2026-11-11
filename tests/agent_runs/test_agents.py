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

    assert (Agent.CLAUDE.skill_folder(home, "claude"), Agent.CODEX.skill_folder(home, "codex")) == (
        Path("/home/me/.claude/skills"), Path("/home/me/.agents/skills"))


def test_claude_keeps_its_skills_under_the_config_dir_its_command_names():
    home = Path("/home/me")

    assert [Agent.CLAUDE.skill_folder(home, command) for command in (
        "CLAUDE_CONFIG_DIR=~/.claude-work claude",
        "FORCE_COLOR=1 CLAUDE_CONFIG_DIR=/srv/claude claude --verbose",
        "claude CLAUDE_CONFIG_DIR=/srv/claude",
    )] == [Path("/home/me/.claude-work/skills"), Path("/srv/claude/skills"),
           Path("/home/me/.claude/skills")]
