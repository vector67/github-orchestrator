import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from github_orchestrator.domain import Pr


@dataclass(frozen=True)
class Session:
    id: str
    argv: tuple[str, ...]
    worktree: str
    branch: str | None
    thread: str | None


class Activity(enum.StrEnum):
    WORKING = "working"
    WAITING = "waiting"
    IDLE = "idle"


@dataclass(frozen=True)
class Watched:
    session: Session
    started_at: datetime
    activity: Activity
    waiting_since: datetime | None


class Connection(Protocol):
    def read(self, timeout: float) -> bytes | None: ...

    def write(self, data: bytes) -> None: ...

    def resize(self, columns: int, rows: int) -> None: ...

    def exit_code(self) -> int | None: ...

    def close(self) -> None: ...


class TerminalSessions(Protocol):
    def start(self, worktree: str, argv: list[str], *, thread: str | None = None) -> str: ...

    def start_kept(self, worktree: str, argv: list[str], *, thread: str | None = None) -> str: ...

    def listed(self) -> list[Session]: ...

    def watched(self, now: datetime, agent: str) -> list[Watched]: ...

    def attach(self, session: str, after: int = 0) -> Connection | None: ...

    def close(self, session: str) -> bool: ...

    def hang_up(self) -> None: ...


class Terminals(Protocol):
    def of(self, pr: Pr) -> TerminalSessions: ...

    def everywhere(self) -> list[TerminalSessions]: ...
