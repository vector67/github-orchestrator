import enum
from collections.abc import Set
from datetime import datetime
from pathlib import Path
from typing import Protocol

from github_orchestrator.domain import Pr, Repo


class ManagerPane(enum.Enum):
    NO_WINDOW = "no-window"
    EXITED = "exited"
    RUNNING = "running"
    UNREADABLE = "unreadable"


class PrProcesses(Protocol):
    def open(self, pr: Pr, worktree: Path) -> None: ...

    def revive(self, pr: Pr) -> None: ...

    def manager(self, pr: Pr) -> ManagerPane: ...

    def stop_managers(self) -> list[Pr]: ...

    def manager_path(self, pr: Pr) -> str | None: ...

    def detach(self, pr: Pr) -> str | None: ...

    def close(self, pr: Pr) -> bool: ...

    def split(self, pr: Pr, worktree: str, argv: list[str]) -> str | None: ...

    def close_other_repos(self, keep: Set[Repo]) -> dict[Pr, str | None]: ...


class AgentChanges(Protocol):
    def file_name(self) -> str: ...

    def note(self, worktree: Path, text: str, at: datetime) -> None: ...

    def read(self, worktree: Path) -> str | None: ...
