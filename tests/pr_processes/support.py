from collections.abc import Callable
from pathlib import Path
from typing import Any

from github_orchestrator.pr_processes import AgentChanges, PrProcesses
from github_orchestrator.settings.fake import Settings
from github_orchestrator.terminal_sessions import Terminals
from github_orchestrator.wiring import (
    AgentChangesProvider,
    BackgroundPrProcessesWiring,
    pr_processes_places,
    wire,
)
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.conftest import fake_provider


def background_pr_processes(settings: Settings, run: Callable[..., Any],
                          terminals: Terminals) -> PrProcesses:
    provider = BackgroundPrProcessesWiring(run, pr_processes_places(settings))
    pr_processes: PrProcesses = wire(
        provider, fake_provider(Terminals, terminals)).get(PrProcesses)
    return pr_processes


def real_agent_changes() -> AgentChanges:
    changes: AgentChanges = wire(AgentChangesProvider).get(AgentChanges)
    return changes


def checked_out(copies: FakeWorkingCopies, path: Path, branch: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    copies.add_worktree(path, branch)
    return path
