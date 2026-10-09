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
from github_orchestrator.terminal_sessions._holder import LOG, RECORD, SOCKET
from github_orchestrator.terminal_sessions.interface import Session, TerminalSessions

log = logging.getLogger(__name__)

Popen = Callable[..., "subprocess.Popen[bytes]"]

HOLDER = "github_orchestrator.terminal_sessions._holder"
READ_BYTES = 64 * 1024
PLACE = 12
UNMANAGED = "unmanaged"


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


class PtySessions:
    def __init__(self, popen: Popen, environment: Mapping[str, str], directory: Path, *,
                 first_connection_seconds: float) -> None:
        self._popen = popen
        self._environment = environment
        self._directory = directory
        self._first_connection_seconds = first_connection_seconds

    def start(self, worktree: str, argv: list[str]) -> str:
        session = secrets.token_hex(6)
        holder = self._popen(
            [sys.executable, "-m", HOLDER, str(self._directory), session,
             str(self._first_connection_seconds), worktree, *argv],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            env={**os.environ, **self._environment}, cwd="/", close_fds=True)
        _, trouble = holder.communicate()
        if holder.returncode != 0:
            raise OSError(trouble.decode(errors="replace").strip()
                          or f"the terminal holder exited with {holder.returncode}")
        log.info("terminal session %s started in %s: %s", session, worktree, argv)
        return session

    def _forget(self, session: str) -> None:
        for suffix in (RECORD, SOCKET, LOG):
            (self._directory / f"{session}{suffix}").unlink(missing_ok=True)

    def _held(self) -> list[tuple[int, Session]]:
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
                          Session(session, tuple(fields["argv"]), fields["worktree"])))
        return [(pid, held) for _, pid, held in sorted(found, key=lambda one: one[0])]

    def listed(self) -> list[Session]:
        return [held for _, held in self._held()]

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
                 first_connection_seconds: float) -> None:
        self._popen = popen
        self._environment = environment
        self._directory = directory
        self._first_connection_seconds = first_connection_seconds

    def _in(self, directory: Path) -> PtySessions:
        return PtySessions(self._popen, self._environment, directory,
                           first_connection_seconds=self._first_connection_seconds)

    def of(self, pr: Pr) -> PtySessions:
        return self._in(self._directory / hashlib.sha256(str(pr).encode()).hexdigest()[:PLACE])

    def unmanaged(self) -> PtySessions:
        return self._in(self._directory / UNMANAGED)

    def everywhere(self) -> list[TerminalSessions]:
        if not self._directory.is_dir():
            return []
        return [self._in(place) for place in sorted(self._directory.iterdir()) if place.is_dir()]
