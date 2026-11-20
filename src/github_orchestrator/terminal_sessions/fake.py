import itertools
from dataclasses import dataclass, field
from datetime import datetime, timezone

from github_orchestrator.domain import Pr
from github_orchestrator.terminal_sessions._branch import branch_of
from github_orchestrator.terminal_sessions.interface import (
    Activity,
    Session,
    TerminalSessions,
    Watched,
)

HUNG_UP = 128 + 1
STARTED = datetime(2026, 11, 19, 9, 0, tzinfo=timezone.utc)


@dataclass
class FakeSession:
    session: Session
    printed: bytearray = field(default_factory=bytearray)
    typed: list[bytes] = field(default_factory=list)
    pinged: list[int] = field(default_factory=list)
    size: tuple[int, int] | None = None
    exit_code: int | None = None
    connections: int = 0
    connected_once: bool = False
    kept: bool = False
    started_at: datetime = STARTED
    activity: Activity = Activity.WORKING
    waiting_since: datetime | None = None


class FakeConnection:
    def __init__(self, held: FakeSession, after: int) -> None:
        self._held = held
        self._offset = min(after, len(held.printed))
        self._closed = False
        self._pongs: list[int] = []

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

    def ping(self, ping: int) -> None:
        self._held.pinged.append(ping)
        self._pongs.append(ping)

    def pongs(self) -> list[int]:
        heard, self._pongs = self._pongs, []
        return heard

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

    def start(self, worktree: str, argv: list[str], *, thread: str | None = None) -> str:
        return self._started(worktree, argv, thread, kept=False)

    def start_kept(self, worktree: str, argv: list[str], *, thread: str | None = None) -> str:
        return self._started(worktree, argv, thread, kept=True)

    def _started(self, worktree: str, argv: list[str], thread: str | None, *,
                 kept: bool) -> str:
        if self.refusal is not None:
            raise FileNotFoundError(2, self.refusal, worktree)
        session = Session(f"session-{next(self._ids)}", tuple(argv), worktree, branch_of(worktree),
                          thread)
        self.sessions[session.id] = FakeSession(session, kept=kept)
        return session.id

    def listed(self) -> list[Session]:
        return [held.session for held in self.sessions.values() if held.exit_code is None]

    def watched(self, now: datetime, agent: str) -> list[Watched]:
        return [Watched(held.session, held.started_at, held.activity, held.waiting_since)
                for held in self.sessions.values() if held.exit_code is None]

    def mark(self, session: str, activity: Activity, *, since: datetime | None = None,
             started_at: datetime = STARTED) -> None:
        held = self.sessions[session]
        held.activity, held.waiting_since, held.started_at = activity, since, started_at

    def close(self, session: str) -> bool:
        held = self.sessions.get(session)
        if held is None or held.exit_code is not None:
            return False
        held.exit_code = HUNG_UP
        return True

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

    def kept(self) -> list[tuple[str, tuple[str, ...]]]:
        return [(held.session.worktree, held.session.argv) for held in self.sessions.values()
                if held.kept]


class FakeTerminals:
    def __init__(self) -> None:
        self.held: dict[Pr, FakeTerminalSessions] = {}

    def of(self, pr: Pr) -> FakeTerminalSessions:
        return self.held.setdefault(pr, FakeTerminalSessions())

    def everywhere(self) -> list[TerminalSessions]:
        return list(self.held.values())
