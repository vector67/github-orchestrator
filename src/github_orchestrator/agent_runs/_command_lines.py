import os
from typing import Protocol

from github_orchestrator.agent_runs._agents import Agent
from github_orchestrator.agent_runs._pr_prompts import REBASE_ON_MAIN


class CommandLines(Protocol):
    def headless(self, model: str, *, carrying_on: bool, thread: str | None) -> list[str]: ...

    def gist(self, model: str) -> list[str]: ...

    def rebase_session(self) -> list[str]: ...

    def env(self) -> dict[str, str]: ...


def _without(key: str) -> dict[str, str]:
    return {name: value for name, value in os.environ.items() if name != key}


class ClaudeCommandLines:
    def headless(self, model: str, *, carrying_on: bool, thread: str | None) -> list[str]:
        argv = ["--print", "--output-format", "stream-json", "--verbose",
                "--permission-mode", "auto", "--model", model]
        return [*argv, "--continue"] if carrying_on else argv

    def gist(self, model: str) -> list[str]:
        return ["--print", "--model", model]

    def rebase_session(self) -> list[str]:
        return [REBASE_ON_MAIN]

    def env(self) -> dict[str, str]:
        return _without("ANTHROPIC_API_KEY")


class CodexCommandLines:
    def headless(self, model: str, *, carrying_on: bool, thread: str | None) -> list[str]:
        argv = ["exec", "--json", "--approve-for-me", "-m", model]
        if carrying_on:
            argv += ["resume", thread or "--last"]
        return [*argv, "-"]

    def gist(self, model: str) -> list[str]:
        return ["exec", "--ephemeral", "--skip-git-repo-check", "-s", "read-only",
                "-m", model, "-"]

    def rebase_session(self) -> list[str]:
        return ["$" + REBASE_ON_MAIN.removeprefix("/")]

    def env(self) -> dict[str, str]:
        return _without("OPENAI_API_KEY")


def command_lines_of(agent: Agent) -> CommandLines:
    lines: dict[Agent, CommandLines] = {Agent.CLAUDE: ClaudeCommandLines(),
                                        Agent.CODEX: CodexCommandLines()}
    return lines[agent]
