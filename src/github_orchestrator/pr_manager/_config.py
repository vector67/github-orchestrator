from dataclasses import dataclass

from github_orchestrator.domain import Pr


@dataclass(frozen=True)
class ManagerConfig:
    pr: Pr
    worktree: str
    account: str
    agents_enabled: bool
    agent_name: str
    refresh_interval: float
    undismiss_command: str
