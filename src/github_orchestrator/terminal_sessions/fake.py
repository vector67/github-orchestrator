import itertools
from dataclasses import dataclass, field

from github_orchestrator.domain import Pr
from github_orchestrator.terminal_sessions.interface import Session, TerminalSessions

HUNG_UP = 128 + 1


@dataclass
class FakeSession:
    session: Session
    printed: bytearray = field(default_factory=bytearray)
    typed: list[bytes] = field(default_factory=list)
    size: tuple[int, int] | None = None
    exit_code: int | None = None
    connections: int = 0
    connected_once: bool = False


class FakeConnection:
    def __init__(self, held: FakeSession, after: int) -> None:
        self._held = held
        self._offset = min(after, len(held.printed))
        self._closed = False

    def read(self, timeout: float) -> bytes | None:
        printed = bytes(self._held.printed[self._offset:])
        self._offset = len(self._held.printed)
        if printed:
            return printed
        return None if self._held.exit_code is not None else b""

    def write(self, data: bytes) -> None:
        self._held.typed.append(data)

    def resize(self, columns: int, rows: int) -> None:
        self._held.size = (columns, rows)

    def exit_code(self) -> int | None:
        return self._held.exit_code

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._held.connections -= 1


class FakeTerminalSessions:
    def __init__(self) -> None:
        self.sessions: dict[str, FakeSession] = {}
        self.refusal: str | None = None
        self._ids = itertools.count(1)

    def start(self, worktree: str, argv: list[str]) -> str:
        if self.refusal is not None:
            raise FileNotFoundError(2, self.refusal, worktree)
        session = Session(f"session-{next(self._ids)}", tuple(argv), worktree)
        self.sessions[session.id] = FakeSession(session)
        return session.id

    def listed(self) -> list[Session]:
        return [held.session for held in self.sessions.values() if held.exit_code is None]

    def attach(self, session: str, after: int = 0) -> FakeConnection | None:
        held = self.sessions.get(session)
        if held is None or held.exit_code is not None:
            return None
        held.connections += 1
        held.connected_once = True
        return FakeConnection(held, after)

    def print(self, session: str, output: bytes) -> None:
        self.sessions[session].printed += output

    def end(self, session: str, exit_code: int) -> None:
        self.sessions[session].exit_code = exit_code

    def hang_up(self) -> None:
        for held in self.sessions.values():
            if held.exit_code is None:
                held.exit_code = HUNG_UP

    def started(self) -> list[tuple[str, tuple[str, ...]]]:
        return [(held.session.worktree, held.session.argv) for held in self.sessions.values()]


class FakeTerminals:
    def __init__(self) -> None:
        self.held: dict[Pr, FakeTerminalSessions] = {}

    def of(self, pr: Pr) -> FakeTerminalSessions:
        return self.held.setdefault(pr, FakeTerminalSessions())

    def everywhere(self) -> list[TerminalSessions]:
        return list(self.held.values())
