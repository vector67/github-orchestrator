import json
import os
import tomllib
from pathlib import Path
from typing import Protocol

from github_orchestrator.agent_runs._agents import Agent
from github_orchestrator.agent_runs._pr_prompts import REBASE_ON_MAIN

READ_ONLY_TOOLS = "Read,Grep,Glob"


class CommandLines(Protocol):
    def headless(self, model: str, *, carrying_on: bool, thread: str | None,
                 project_settings: bool, cwd: str) -> list[str]: ...

    def gist(self, model: str) -> list[str]: ...

    def read_only(self, model: str, cwd: str) -> list[str]: ...

    def rebase_session(self) -> list[str]: ...

    def answering(self, session: str | None, first: str | None) -> list[str]: ...

    def env(self) -> dict[str, str]: ...


def _without(key: str) -> dict[str, str]:
    return {name: value for name, value in os.environ.items() if name != key}


class ClaudeCommandLines:
    def headless(self, model: str, *, carrying_on: bool, thread: str | None,
                 project_settings: bool, cwd: str) -> list[str]:
        argv = ["--print", "--output-format", "stream-json", "--verbose",
                "--permission-mode", "auto", "--model", model]
        if not project_settings:
            argv += ["--setting-sources", "user"]
        return [*argv, "--continue"] if carrying_on else argv

    def gist(self, model: str) -> list[str]:
        return ["--print", "--model", model, "--tools", "", "--strict-mcp-config"]

    def read_only(self, model: str, cwd: str) -> list[str]:
        return ["--print", "--model", model, "--tools", READ_ONLY_TOOLS,
                "--setting-sources", "user", "--strict-mcp-config"]

    def rebase_session(self) -> list[str]:
        return [REBASE_ON_MAIN]

    def answering(self, session: str | None, first: str | None) -> list[str]:
        resumed = ["--resume", session] if session else ["--continue"]
        return resumed if first is None else [*resumed, first]

    def env(self) -> dict[str, str]:
        return _without("ANTHROPIC_API_KEY")


def _untrusted_project(cwd: str) -> list[str]:
    root = Path(cwd).resolve()
    argv = ["-c", f"projects={{{json.dumps(str(root))}={{trust_level=\"untrusted\"}}}}"]
    skills = sorted((root / ".agents" / "skills").rglob("SKILL.md"))
    if skills:
        off = ",".join(f"{{path={json.dumps(str(skill))},enabled=false}}" for skill in skills)
        argv += ["-c", f"skills.config=[{off}]"]
    return argv


def _user_mcp_servers_off() -> list[str]:
    config = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"
    if not config.is_file():
        return []
    servers = tomllib.loads(config.read_text()).get("mcp_servers", {})
    if not servers:
        return []
    off = ",".join(f"{json.dumps(name)}={{enabled=false}}" for name in servers)
    return ["-c", f"mcp_servers={{{off}}}"]


class CodexCommandLines:
    def headless(self, model: str, *, carrying_on: bool, thread: str | None,
                 project_settings: bool, cwd: str) -> list[str]:
        argv = ["exec", "--json", "--approve-for-me", "-m", model]
        if not project_settings:
            argv += _untrusted_project(cwd)
        if carrying_on:
            argv += ["resume", thread or "--last"]
        return [*argv, "-"]

    def gist(self, model: str) -> list[str]:
        return ["exec", "--ephemeral", "--skip-git-repo-check", "-s", "read-only",
                "-m", model, *_user_mcp_servers_off(), "-"]

    def read_only(self, model: str, cwd: str) -> list[str]:
        return ["exec", "--ephemeral", "-s", "read-only", "-m", model,
                *_untrusted_project(cwd), *_user_mcp_servers_off(), "-"]

    def rebase_session(self) -> list[str]:
        return ["$" + REBASE_ON_MAIN.removeprefix("/")]

    def answering(self, session: str | None, first: str | None) -> list[str]:
        resumed = ["resume", session or "--last"]
        return resumed if first is None else [*resumed, first]

    def env(self) -> dict[str, str]:
        return _without("OPENAI_API_KEY")


def command_lines_of(agent: Agent) -> CommandLines:
    lines: dict[Agent, CommandLines] = {Agent.CLAUDE: ClaudeCommandLines(),
                                        Agent.CODEX: CodexCommandLines()}
    return lines[agent]
