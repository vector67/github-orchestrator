import fcntl
import json
import logging
import os
import select
import signal
import socket
import struct
import subprocess
import sys
import termios
import threading
import time
from pathlib import Path

from github_orchestrator.terminal_sessions._frames import (
    EXIT,
    INPUT,
    OUTPUT,
    RESIZE,
    RESUME,
    Unframer,
    framed,
    size_of,
)

log = logging.getLogger(__name__)

KEPT_BYTES = 1024 * 1024
READ_BYTES = 64 * 1024
KILL_SECONDS = 5.0
FLUSH_SECONDS = 5.0
ACCEPT_SECONDS = 0.5
SEND_SECONDS = 0.5
TERMINAL = {"TERM": "xterm-256color", "COLORTERM": "truecolor"}
TAKE_THE_TERMINAL = ("import fcntl, os, sys, termios; fcntl.ioctl(0, termios.TIOCSCTTY, 0); "
                     "os.execvp(sys.argv[1], sys.argv[1:])")
RECORD = ".json"
SOCKET = ".sock"
LOG = ".log"


class _Held:
    def __init__(self, directory: Path, session: str, process: "subprocess.Popen[bytes]",
                 master: int, server: socket.socket) -> None:
        self._directory = directory
        self._session = session
        self._process = process
        self._master = master
        self._server = server
        self._changed = threading.Condition()
        self._io = threading.Lock()
        self._closed = False
        self._kept = bytearray()
        self._dropped = 0
        self._connections = 0
        self._exit_code: int | None = None
        self._over = False
        self._hung_up = False
        self._handlers: list[threading.Thread] = []
        self._ended, self._ending = os.pipe()

    def _pump(self) -> None:
        while True:
            try:
                chunk = os.read(self._master, READ_BYTES)
            except OSError:
                chunk = b""
            if not chunk:
                break
            with self._changed:
                self._kept += chunk
                excess = len(self._kept) - KEPT_BYTES
                if excess > 0:
                    del self._kept[:excess]
                    self._dropped += excess
                self._changed.notify_all()
        exit_code = self._process.wait()
        with self._io:
            self._closed = True
            os.close(self._master)
        for suffix in (RECORD, SOCKET):
            (self._directory / f"{self._session}{suffix}").unlink(missing_ok=True)
        with self._changed:
            self._exit_code = exit_code
            self._over = True
            self._changed.notify_all()
        os.write(self._ending, b"\0")
        log.info("terminal session %s ended with exit code %d", self._session, exit_code)

    def _hang_up_unless_connected(self) -> None:
        with self._changed:
            waiting = self._connections == 0
        if waiting:
            log.info("terminal session %s: no page connected, so it ends", self._session)
            self._hang_up()

    def _hang_up(self) -> None:
        with self._changed:
            if self._over or self._hung_up:
                return
            self._hung_up = True
        self._signal(signal.SIGHUP)
        killer = threading.Timer(KILL_SECONDS, self._signal, [signal.SIGKILL])
        killer.daemon = True
        killer.start()

    def _signal(self, number: int) -> None:
        if self._process.poll() is not None:
            return
        try:
            os.killpg(self._process.pid, number)
        except (ProcessLookupError, PermissionError):
            pass

    def _output_after(self, offset: int, timeout: float) -> tuple[bytes | None, int]:
        with self._changed:
            end = self._dropped + len(self._kept)
            if offset >= end and not self._over:
                self._changed.wait(timeout)
                end = self._dropped + len(self._kept)
            start = max(offset, self._dropped)
            if start >= end:
                return (None if self._over else b""), start
            return bytes(self._kept[start - self._dropped:]), end

    def _write(self, data: bytes) -> None:
        with self._io:
            if self._closed:
                return
            try:
                os.write(self._master, data)
            except OSError:
                log.info("terminal session %s: input lost, the command has gone", self._session)

    def _resize(self, columns: int, rows: int) -> None:
        with self._io:
            if self._closed:
                return
            try:
                fcntl.ioctl(self._master, termios.TIOCSWINSZ,
                            struct.pack("HHHH", rows, columns, 0, 0))
            except OSError:
                log.info("terminal session %s: resize lost, the command has gone", self._session)

    def _resumed_after(self, connection: socket.socket, frames: Unframer) -> int:
        while data := connection.recv(READ_BYTES):
            for kind, payload in frames.fed(data):
                if kind == RESUME:
                    return int(payload)
        raise ConnectionResetError("the connection closed before saying where to resume")

    def _served(self, connection: socket.socket) -> None:
        frames = Unframer()
        try:
            after = self._resumed_after(connection, frames)
        except (OSError, ValueError):
            connection.close()
            return
        with self._changed:
            self._connections += 1
            offset = max(after, self._dropped)
        gone = threading.Event()
        typing = threading.Thread(target=self._typed, args=(connection, frames, gone),
                                  daemon=True)
        typing.start()
        try:
            while not gone.is_set():
                chunk, offset = self._output_after(offset, SEND_SECONDS)
                if chunk is None:
                    connection.sendall(framed(EXIT, str(self._exit_code).encode()))
                    break
                if chunk:
                    connection.sendall(framed(OUTPUT, chunk))
        except OSError:
            pass
        finally:
            with self._changed:
                self._connections -= 1
            connection.close()

    def _typed(self, connection: socket.socket, frames: Unframer,
               gone: threading.Event) -> None:
        data = b""
        try:
            while True:
                for kind, payload in frames.fed(data):
                    if kind == INPUT:
                        self._write(payload)
                    elif kind == RESIZE:
                        self._resize(*size_of(payload))
                data = connection.recv(READ_BYTES)
                if not data:
                    break
        except OSError:
            pass
        gone.set()

    def _hang_up_when_told(self, number: int, frame: object) -> None:
        threading.Thread(target=self._hang_up, daemon=True).start()

    def serve(self, first_connection_seconds: float) -> None:
        threading.Thread(target=self._pump, daemon=True).start()
        waiting = threading.Timer(first_connection_seconds, self._hang_up_unless_connected)
        waiting.daemon = True
        waiting.start()
        self._server.settimeout(ACCEPT_SECONDS)
        while True:
            with self._changed:
                if self._over:
                    break
            listening = self._server.fileno()
            waiting_on, _, _ = select.select([listening, self._ended], [], [], ACCEPT_SECONDS)
            if listening not in waiting_on:
                continue
            try:
                connection, _ = self._server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            connection.settimeout(None)
            handler = threading.Thread(target=self._served, args=(connection,), daemon=True)
            self._handlers.append(handler)
            handler.start()
        self._server.close()
        deadline = time.monotonic() + FLUSH_SECONDS
        for handler in self._handlers:
            handler.join(max(0.0, deadline - time.monotonic()))


def _held(directory: Path, session: str, worktree: str, argv: list[str]) -> _Held:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    master, slave = os.openpty()
    try:
        process = subprocess.Popen(
            [sys.executable, "-c", TAKE_THE_TERMINAL, *argv],
            stdin=slave, stdout=slave, stderr=slave, cwd=worktree,
            env={**os.environ, **TERMINAL}, start_new_session=True, close_fds=True)
    except OSError:
        os.close(master)
        raise
    finally:
        os.close(slave)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(directory / f"{session}{SOCKET}"))
    server.listen()
    record = directory / f"{session}{RECORD}"
    written = record.with_suffix(".writing")
    written.write_text(json.dumps({"pid": os.getpid(), "argv": argv, "worktree": worktree,
                                   "started": time.time_ns()}))
    written.replace(record)
    log.info("terminal session %s started in %s: %s", session, worktree, argv)
    return _Held(directory, session, process, master, server)


def _detached(directory: Path, session: str) -> None:
    quiet = os.open(os.devnull, os.O_RDWR)
    os.dup2(quiet, 0)
    written = os.open(directory / f"{session}{LOG}", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.dup2(written, 1)
    os.dup2(written, 2)
    os.close(quiet)
    os.close(written)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(message)s")


def main(arguments: list[str]) -> int:
    directory, session, wait, worktree, *argv = arguments
    told, telling = os.pipe()
    if os.fork() > 0:
        os.close(telling)
        with os.fdopen(told, "rb") as answer:
            trouble = answer.read()
        if trouble:
            sys.stderr.write(trouble.decode(errors="replace"))
            return 1
        return 0
    os.close(told)
    os.setsid()
    try:
        held = _held(Path(directory), session, worktree, argv)
    except OSError as exc:
        os.write(telling, (str(exc) or "the session could not start").encode())
        os._exit(1)
    signal.signal(signal.SIGTERM, held._hang_up_when_told)
    _detached(Path(directory), session)
    os.close(telling)
    held.serve(float(wait))
    (Path(directory) / f"{session}{LOG}").unlink(missing_ok=True)
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
