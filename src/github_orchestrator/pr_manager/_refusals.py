from dataclasses import dataclass

from github_orchestrator.board_api.interface import ManagerRefusal
from github_orchestrator.pr_manager._command_file import Command

_STARTS_AN_AGENT = frozenset({Command.CARRY_ON, Command.START_REVIEW})


@dataclass(frozen=True)
class Conditions:
    frozen: bool
    running: bool
    answering: bool
    fork: bool = False


DOWN = Conditions(frozen=False, running=False, answering=False)


def refusal(conditions: Conditions, command: Command | None, *,
            agents_enabled: bool, pushes: bool = False) -> ManagerRefusal | None:
    if command is not None and not conditions.answering:
        return ManagerRefusal.MANAGER_DOWN
    if conditions.frozen:
        return ManagerRefusal.WORKTREE_FROZEN
    if pushes and conditions.fork:
        return ManagerRefusal.FORK_PULL_REQUEST
    if command not in _STARTS_AN_AGENT:
        return None
    if not agents_enabled:
        return ManagerRefusal.AGENTS_DISABLED
    if conditions.running:
        return ManagerRefusal.AGENT_RUNNING
    return None
