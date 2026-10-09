import fcntl
import logging
import os
import shutil
from logging.handlers import WatchedFileHandler
from pathlib import Path

from github_orchestrator.settings.interface import Process

DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5

_FORMAT = "%(asctime)s %(levelname)s [%(process)d%(context)s] [%(name)s] %(message)s"


_FILE_NAMES = {
    Process.WATCHER: "watcher.log",
    Process.PR_MANAGER: "agent-manager.log",
    Process.LAUNCHD: "launchd.log",
}


def log_path(logs_dir: Path, process: Process) -> Path:
    return logs_dir / _FILE_NAMES[process]


def _level(name: str) -> int:
    level = getattr(logging, name.upper(), logging.INFO)
    return level if isinstance(level, int) else logging.INFO


class _Context(logging.Filter):
    def __init__(self, context: str) -> None:
        super().__init__()
        self._context = f" {context}" if context else ""

    def filter(self, record: logging.LogRecord) -> bool:
        record.context = self._context
        return True


class SharedRotatingFileHandler(WatchedFileHandler):
    def __init__(self, filename: str, max_bytes: int, backup_count: int) -> None:
        super().__init__(filename)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._lock_path = f"{filename}.lock"

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self._full():
                self._rotate()
        except OSError:
            self.handleError(record)
        super().emit(record)

    def _full(self) -> bool:
        try:
            return os.stat(self.baseFilename).st_size >= self.max_bytes
        except FileNotFoundError:
            return False

    def _rotate(self) -> None:
        with open(self._lock_path, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not self._full():
                return
            for n in range(self.backup_count - 1, 0, -1):
                older = f"{self.baseFilename}.{n}"
                if os.path.exists(older):
                    os.replace(older, f"{self.baseFilename}.{n + 1}")
            os.replace(self.baseFilename, f"{self.baseFilename}.1")


def _trim(path: Path, max_bytes: int) -> None:
    try:
        if path.stat().st_size < max_bytes:
            return
    except FileNotFoundError:
        return
    shutil.copyfile(path, f"{path}.1")
    with open(path, "r+") as scheduler_log:
        scheduler_log.truncate(0)


class LogFiles:
    def __init__(self, logs_dir: Path, level: str, *, max_bytes: int = DEFAULT_MAX_BYTES,
                 backup_count: int = DEFAULT_BACKUP_COUNT) -> None:
        self._logs_dir = logs_dir
        self._level = _level(level)
        self._max_bytes = max_bytes
        self._backup_count = backup_count

    def path(self, process: Process) -> Path:
        return log_path(self._logs_dir, process)

    def configure_logging(self, process: Process, context: str = "") -> None:
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        if process is Process.WATCHER:
            _trim(self.path(Process.LAUNCHD), self._max_bytes)
        handler = SharedRotatingFileHandler(str(self.path(process)), self._max_bytes,
                                            self._backup_count)
        handler.setFormatter(logging.Formatter(_FORMAT))
        handler.addFilter(_Context(context))

        root = logging.getLogger()
        for existing in list(root.handlers):
            root.removeHandler(existing)
        root.addHandler(handler)
        root.setLevel(self._level)
