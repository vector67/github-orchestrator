import datetime
import fcntl
from pathlib import Path

from github_orchestrator.domain import Cause, UtcClock
from github_orchestrator.watcher._config import WatcherConfig
from github_orchestrator.watcher._diagnosis import diagnose
from github_orchestrator.watcher._failures import WatcherFailures, read_failures
from github_orchestrator.watcher.interface import Health


class HealthFiles:
    def __init__(self, config: WatcherConfig, clock: UtcClock) -> None:
        self._heartbeat = config.heartbeat
        self._lock = config.lock
        self._failures = config.failures
        self._mentions_failure = config.mentions_failure
        self._poll_interval = config.poll_interval
        self._clock = clock

    def health(self) -> Health:
        failures = read_failures(self._failures)
        cause = _cause(failures)
        mentions = read_failures(self._mentions_failure)
        return Health(
            alive=_watcher_lock_held(self._lock) is True,
            polled_at=_polled_at(self._heartbeat),
            read_at=self._clock(),
            last_error=failures.last_error if cause else None,
            fix=failures.fix if cause is Cause.OPERATOR else None,
            polls_every=datetime.timedelta(seconds=self._poll_interval),
            mentions_error=mentions.last_error if _cause(mentions) else None,
            last_error_cause=cause,
            mentions_error_cause=_cause(mentions),
        )


def _cause(failures: WatcherFailures) -> Cause | None:
    return diagnose(failures.last_error).cause if failures.consecutive else None


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
