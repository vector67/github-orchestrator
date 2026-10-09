import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from github_orchestrator.agent_runs import Agent
from github_orchestrator.domain import Clone, Repo
from github_orchestrator.settings import ConfigFile

Run = Callable[..., subprocess.CompletedProcess[Any]]


class Which(Protocol):
    def __call__(self, program: str, *, path: str | None = None) -> str | None: ...


class OpenTerminals(Protocol):
    def count(self) -> int: ...

    def close(self) -> int: ...



@dataclass(frozen=True)
class CliConfig:
    python: str
    python_note: str | None
    child_environment: Mapping[str, str]
    shell_path: str
    archive_dir: Path
    data_dir: Path
    config_folder: Path
    restart_lock: Path
    repos: Mapping[Repo, Clone]
    gh_account: str
    agents_enabled: bool
    agent: Agent
    agent_argv: tuple[str, ...]
    agent_program: str
    summary_model: str
    home: Path
    platform: str
    uid: int
    hub_url: str
    instance: str | None
    font_problem: str | None
    version: str | None
    graphical: bool
    check_for_updates: bool


def print_agents_disabled_notice(config: CliConfig, config_file: ConfigFile) -> None:
    if not config.agents_enabled:
        print(
            f"Agents are disabled (agents_enabled = false in {config_file.location()}) — "
            "spawning events notify and drain without starting a run"
        )
