from dataclasses import dataclass

from github_orchestrator.pr_manager._command_file import Command

FROZEN = "refused: the worktree holds another PR's branch"

AGENTS_DISABLED = "agents are disabled in config.toml"

AGENT_RUNNING = "an agent is already running"

MANAGER_DOWN = "the manager is down, your actions can't be recorded"

_STARTS_AN_AGENT = frozenset({Command.CARRY_ON, Command.START_REVIEW})


@dataclass(frozen=True)
class Conditions:
    frozen: bool
    running: bool
    answering: bool


DOWN = Conditions(frozen=False, running=False, answering=False)


def refusal(conditions: Conditions, command: Command | None, *,
            agents_enabled: bool) -> str | None:
    if command is not None and not conditions.answering:
        return MANAGER_DOWN
    if conditions.frozen:
        return FROZEN
    if command not in _STARTS_AN_AGENT:
        return None
    if not agents_enabled:
        return AGENTS_DISABLED
    if conditions.running:
        return AGENT_RUNNING
    return None
