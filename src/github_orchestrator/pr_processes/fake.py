from collections.abc import Set
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from github_orchestrator.domain import Pr, Repo
from github_orchestrator.pr_processes._changes import CHANGES_FILE, entry, title
from github_orchestrator.pr_processes._layout import defunct_name
from github_orchestrator.pr_processes.interface import ManagerPane


@dataclass
class Manager:
    worktree: str
    running: bool = True
    starts: int = 1


@dataclass(frozen=True)
class Session:
    worktree: str
    argv: list[str]


@dataclass
class FakePrProcesses:
    managers: dict[Pr, Manager] = field(default_factory=dict)
    unreadable: set[Pr] = field(default_factory=set)
    sessions: dict[Pr, list[Session]] = field(default_factory=dict)
    changes: dict[Path, str] = field(default_factory=dict)
    refusal: str | None = None

    def open(self, pr: Pr, worktree: Path) -> None:
        self.managers[pr] = Manager(str(worktree))
        self.changes.setdefault(worktree, title(pr))

    def revive(self, pr: Pr) -> None:
        manager = self.managers.get(pr)
        if manager is not None and not manager.running:
            manager.running = True
            manager.starts += 1

    def manager(self, pr: Pr) -> ManagerPane:
        manager = self.managers.get(pr)
        if manager is None:
            return ManagerPane.NO_WINDOW
        if pr in self.unreadable:
            return ManagerPane.UNREADABLE
        return ManagerPane.RUNNING if manager.running else ManagerPane.EXITED

    def stop_managers(self) -> list[Pr]:
        stopped = []
        for pr in sorted(self.managers):
            if self.manager(pr) is ManagerPane.RUNNING:
                self.managers[pr].running = False
                stopped.append(pr)
        return stopped

    def manager_path(self, pr: Pr) -> str | None:
        manager = self.managers.get(pr)
        return None if manager is None else manager.worktree

    def _forget(self, pr: Pr) -> bool:
        self.sessions.pop(pr, None)
        return self.managers.pop(pr, None) is not None

    def detach(self, pr: Pr) -> str | None:
        return defunct_name(pr) if self._forget(pr) else None

    def close(self, pr: Pr) -> bool:
        self._forget(pr)
        return True

    def split(self, pr: Pr, worktree: str, argv: list[str]) -> str | None:
        if self.refusal is not None:
            return self.refusal
        self.sessions.setdefault(pr, []).append(Session(worktree, list(argv)))
        return None

    def file_name(self) -> str:
        return CHANGES_FILE

    def note(self, worktree: Path, text: str, at: datetime) -> None:
        if not worktree.is_dir():
            raise FileNotFoundError(2, "No such file or directory", str(worktree))
        self.changes[worktree] = self.changes.get(worktree, "") + entry(text, at)

    def read(self, worktree: Path) -> str | None:
        return self.changes.get(worktree)

    def close_other_repos(self, keep: Set[Repo]) -> dict[Pr, str | None]:
        closing = {pr: self.manager_path(pr) for pr in sorted(self.managers) if pr.repo not in keep}
        return {pr: worktree for pr, worktree in closing.items() if self._forget(pr)}
