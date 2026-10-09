from dataclasses import dataclass
from typing import Protocol

from github_orchestrator.domain import Pr


@dataclass(frozen=True)
class Session:
    id: str
    argv: tuple[str, ...]
    worktree: str


class Connection(Protocol):
    def read(self, timeout: float) -> bytes | None: ...

    def write(self, data: bytes) -> None: ...

    def resize(self, columns: int, rows: int) -> None: ...

    def exit_code(self) -> int | None: ...

    def close(self) -> None: ...


class TerminalSessions(Protocol):
    def start(self, worktree: str, argv: list[str]) -> str: ...

    def listed(self) -> list[Session]: ...

    def attach(self, session: str, after: int = 0) -> Connection | None: ...

    def hang_up(self) -> None: ...


class Terminals(Protocol):
    def of(self, pr: Pr) -> TerminalSessions: ...

    def everywhere(self) -> list[TerminalSessions]: ...
