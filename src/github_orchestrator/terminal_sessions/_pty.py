import hashlib
import json
import logging
import os
import secrets
import select
import signal
import socket
import string
import subprocess
import sys
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path

from github_orchestrator.domain import Pr
from github_orchestrator.terminal_sessions._frames import (
    EXIT,
    INPUT,
    OUTPUT,
    RESIZE,
    RESUME,
    Unframer,
    framed,
    sized,
)
from github_orchestrator.terminal_sessions._holder import (
    KEPT,
    LOG,
    OUTPUT_MARK,
    RECORD,
    SOCKET,
    TURN,
)
from github_orchestrator.terminal_sessions.interface import (
    Activity,
    Session,
    TerminalSessions,
    Watched,
)

log = logging.getLogger(__name__)

Popen = Callable[..., "subprocess.Popen[bytes]"]

HOLDER = "github_orchestrator.terminal_sessions._holder"
READ_BYTES = 64 * 1024
PLACE = 12
UNMANAGED = "unmanaged"
QUIET_AFTER = timedelta(seconds=30)
TURNS = {"working": Activity.WORKING, "waiting": Activity.WAITING}


def _changed_at(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError:
        return None


def _turn_in(path: Path) -> Activity | None:
    try:
        return TURNS.get(path.read_text().strip())
    except (OSError, UnicodeDecodeError):
        return None


def _named(word: str, program: str) -> bool:
    return os.path.basename(word) == os.path.basename(program)


class _Connection:
    def __init__(self, connected: socket.socket) -> None:
        self._socket = connected
        self._frames = Unframer()
        self._exit_code: int | None = None
        self._over = False
        self._closed = False

    def read(self, timeout: float) -> bytes | None:
        if self._over:
            return None
        ready, _, _ = select.select([self._socket], [], [], timeout)
        if not ready:
            return b""
        try:
            data = self._socket.recv(READ_BYTES)
        except OSError:
            data = b""
        printed = bytearray()
        for kind, payload in self._frames.fed(data):
            if kind == OUTPUT:
                printed += payload
            elif kind == EXIT:
                self._exit_code = int(payload)
                self._over = True
        if not data:
            self._over = True
        if printed:
            return bytes(printed)
        return None if self._over else b""

    def _send(self, data: bytes) -> None:
        try:
            self._socket.sendall(data)
        except OSError:
            pass

    def write(self, data: bytes) -> None:
        self._send(framed(INPUT, data))

    def resize(self, columns: int, rows: int) -> None:
        self._send(framed(RESIZE, sized(columns, rows)))

    def exit_code(self) -> int | None:
        return self._exit_code

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._socket.close()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class _Processes:
    def __init__(self, popen: Popen) -> None:
        self._popen = popen
        self._listed: list[tuple[int, int, list[str]]] | None = None

    def _all(self) -> list[tuple[int, int, list[str]]]:
        if self._listed is None:
            listing = self._popen(["ps", "-A", "-o", "pid=,ppid=,args="],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL)
            printed, _ = listing.communicate()
            self._listed = []
            for line in printed.decode(errors="replace").splitlines():
                pid, ppid, *args = line.split()
                self._listed.append((int(pid), int(ppid), args))
        return self._listed

    def runs(self, holder: int, program: str) -> bool:
        under = {holder}
        found = True
        while found:
            found = False
            for pid, ppid, args in self._all():
                if ppid in under and pid not in under:
                    under.add(pid)
                    found = True
        return any(any(_named(word, program) for word in args[:2])
                   for pid, _, args in self._all() if pid in under and pid != holder)


class PtySessions:
    def __init__(self, popen: Popen, environment: Mapping[str, str], directory: Path, *,
                 first_connection_seconds: float, clamp: tuple[str, ...]) -> None:
        self._popen = popen
        self._environment = environment
        self._directory = directory
        self._first_connection_seconds = first_connection_seconds
        self._clamp = clamp

    def start(self, worktree: str, argv: list[str]) -> str:
        return self._started(str(self._first_connection_seconds), worktree, argv)

    def start_kept(self, worktree: str, argv: list[str]) -> str:
        return self._started(KEPT, worktree, argv)

    def _started(self, wait: str, worktree: str, argv: list[str]) -> str:
        session = secrets.token_hex(6)
        holder = self._popen(
            [*self._clamp, sys.executable, "-m", HOLDER, str(self._directory), session,
             wait, worktree, *argv],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            env={**os.environ, **self._environment}, cwd="/", close_fds=True)
        _, trouble = holder.communicate()
        if holder.returncode != 0:
            raise OSError(trouble.decode(errors="replace").strip()
                          or f"the terminal holder exited with {holder.returncode}")
        log.info("terminal session %s started in %s: %s", session, worktree, argv)
        return session

    def _forget(self, session: str) -> None:
        for suffix in (RECORD, SOCKET, LOG, OUTPUT_MARK, TURN):
            (self._directory / f"{session}{suffix}").unlink(missing_ok=True)

    def _recorded(self) -> list[tuple[int, int, Session]]:
        found = []
        for record in self._directory.glob(f"*{RECORD}"):
            session = record.name.removesuffix(RECORD)
            try:
                fields = json.loads(record.read_text())
            except (OSError, ValueError):
                continue
            if not _alive(fields["pid"]):
                log.info("terminal session %s: its holder has gone", session)
                self._forget(session)
                continue
            found.append((fields["started"], fields["pid"],
                          Session(session, tuple(fields["argv"]), fields["worktree"],
                                  fields.get("branch"))))
        return [(started, pid, held) for started, pid, held in sorted(found, key=lambda one: one[0])]

    def _held(self) -> list[tuple[int, Session]]:
        return [(pid, held) for _, pid, held in self._recorded()]

    def listed(self) -> list[Session]:
        return [held for _, held in self._held()]

    def watched(self, now: datetime, agent: str) -> list[Watched]:
        processes = _Processes(self._popen)
        return [self._watched(started, pid, held, now, agent, processes)
                for started, pid, held in self._recorded()]

    def _watched(self, started: int, pid: int, held: Session, now: datetime, agent: str,
                 processes: _Processes) -> Watched:
        started_at = datetime.fromtimestamp(started / 1e9, timezone.utc)
        turn_file = self._directory / f"{held.id}{TURN}"
        turn = _turn_in(turn_file)
        if turn is not None:
            return Watched(held, started_at, turn,
                           _changed_at(turn_file) if turn is Activity.WAITING else None)
        quiet_since = _changed_at(self._directory / f"{held.id}{OUTPUT_MARK}") or started_at
        if now - quiet_since < QUIET_AFTER:
            return Watched(held, started_at, Activity.WORKING, None)
        if (held.argv and _named(held.argv[0], "git")) or processes.runs(pid, agent):
            return Watched(held, started_at, Activity.WAITING, quiet_since)
        return Watched(held, started_at, Activity.IDLE, None)

    def close(self, session: str) -> bool:
        for pid, held in self._held():
            if held.id == session:
                log.info("terminal session %s: closing", session)
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    return False
                return True
        return False

    def hang_up(self) -> None:
        for pid, held in self._held():
            log.info("terminal session %s: hanging up", held.id)
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def attach(self, session: str, after: int = 0) -> _Connection | None:
        if not session or not all(character in string.hexdigits for character in session):
            return None
        connected = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            connected.connect(str(self._directory / f"{session}{SOCKET}"))
            connected.sendall(framed(RESUME, str(after).encode()))
        except OSError:
            connected.close()
            return None
        return _Connection(connected)


class PtyTerminals:
    def __init__(self, popen: Popen, environment: Mapping[str, str], directory: Path, *,
                 first_connection_seconds: float, clamp: tuple[str, ...]) -> None:
        self._popen = popen
        self._environment = environment
        self._directory = directory
        self._first_connection_seconds = first_connection_seconds
        self._clamp = clamp

    def _in(self, directory: Path) -> PtySessions:
        return PtySessions(self._popen, self._environment, directory,
                           first_connection_seconds=self._first_connection_seconds,
                           clamp=self._clamp)

    def of(self, pr: Pr) -> PtySessions:
        return self._in(self._directory / hashlib.sha256(str(pr).encode()).hexdigest()[:PLACE])

    def unmanaged(self) -> PtySessions:
        return self._in(self._directory / UNMANAGED)

    def everywhere(self) -> list[TerminalSessions]:
        if not self._directory.is_dir():
            return []
        return [self._in(place) for place in sorted(self._directory.iterdir()) if place.is_dir()]
