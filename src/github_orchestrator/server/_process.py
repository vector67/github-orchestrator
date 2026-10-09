import fcntl
import logging
import os
import signal
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)

STOP_SECONDS = 30.0
STOP_POLL_SECONDS = 0.1
MODULE = "github_orchestrator.server"


class Started(Protocol):
    def poll(self) -> int | None: ...


Spawn = Callable[[list[str], Mapping[str, str], Path], Started]


def detached(argv: list[str], env: Mapping[str, str], log_file: Path) -> Started:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a") as output:
        return subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=output,
                                stderr=subprocess.STDOUT, start_new_session=True)


class ServerProcess:
    def __init__(self, *, lock: Path, pid_file: Path, log_file: Path, python: str,
                 environment: Mapping[str, str], spawn: Spawn,
                 sleep: Callable[[float], None]) -> None:
        self._lock = lock
        self._pid_file = pid_file
        self._log_file = log_file
        self._python = python
        self._environment = environment
        self._spawn = spawn
        self._sleep = sleep
        self._started: Started | None = None

    def keep_running(self) -> None:
        if self._started is not None and self._started.poll() is None:
            return
        self._started = None
        if self._held():
            return
        self._started = self._spawn([self._python, "-m", MODULE],
                                    {**os.environ, **self._environment}, self._log_file)
        log.info("started the server; it logs to %s", self._log_file)

    def pid(self) -> int | None:
        if not self._held():
            return None
        try:
            text = self._pid_file.read_text().strip()
        except OSError:
            return None
        return int(text) if text.isdigit() else None

    def stop(self) -> int | None:
        pid = self.pid()
        if pid is None:
            return None
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return None
        waited = 0.0
        while self._held() and waited < STOP_SECONDS:
            self._sleep(STOP_POLL_SECONDS)
            waited += STOP_POLL_SECONDS
        return pid

    def _held(self) -> bool:
        try:
            probe = open(self._lock)
        except FileNotFoundError:
            return False
        with probe:
            try:
                fcntl.flock(probe, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(probe, fcntl.LOCK_UN)
            return False
