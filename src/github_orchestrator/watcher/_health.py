import datetime
import fcntl
from pathlib import Path

from github_orchestrator.domain import UtcClock
from github_orchestrator.watcher._config import WatcherConfig
from github_orchestrator.watcher._failures import read_failures
from github_orchestrator.watcher.interface import Health


class HealthFiles:
    def __init__(self, config: WatcherConfig, clock: UtcClock) -> None:
        self._heartbeat = config.heartbeat
        self._lock = config.lock
        self._failures = config.failures
        self._poll_interval = config.poll_interval
        self._clock = clock

    def health(self) -> Health:
        failures = read_failures(self._failures)
        return Health(
            alive=_watcher_lock_held(self._lock) is True,
            polled_at=_polled_at(self._heartbeat),
            read_at=self._clock(),
            last_error=failures.last_error if failures.consecutive else None,
            fix=failures.fix if failures.consecutive else None,
            polls_every=datetime.timedelta(seconds=self._poll_interval),
        )


def _watcher_lock_held(path: Path) -> bool | None:
    if not path.exists():
        return None
    try:
        with open(path, "a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(handle, fcntl.LOCK_UN)
            return False
    except OSError:
        return None


def _polled_at(path: Path) -> datetime.datetime | None:
    try:
        stamped = datetime.datetime.fromisoformat(path.read_text().strip())
    except (OSError, ValueError):
        return None
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=datetime.timezone.utc)
    return stamped
