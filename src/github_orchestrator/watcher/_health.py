import datetime
import fcntl
from pathlib import Path

from github_orchestrator.domain import Fault, Repo, UtcClock
from github_orchestrator.watcher._config import WatcherConfig
from github_orchestrator.watcher._diagnosis import diagnose, names_in
from github_orchestrator.watcher._failures import WatcherFailures, read_failures
from github_orchestrator.watcher.interface import Health


class HealthFiles:
    def __init__(self, config: WatcherConfig, clock: UtcClock) -> None:
        self._heartbeat = config.heartbeat
        self._lock = config.lock
        self._failures = config.failures
        self._mentions_failure = config.mentions_failure
        self._poll_interval = config.poll_interval
        self._names = names_in(config)
        self._account = config.gh_account
        self._config_path = config.config_location
        self._clock = clock

    def health(self) -> Health:
        failures = read_failures(self._failures)
        fault = self._fault(failures)
        mentions = read_failures(self._mentions_failure)
        mentions_fault = Fault.CONFIG if mentions.consecutive else None
        return Health(
            alive=_watcher_lock_held(self._lock) is True,
            polled_at=_polled_at(self._heartbeat),
            read_at=self._clock(),
            last_error=failures.last_error if fault else None,
            polls_every=datetime.timedelta(seconds=self._poll_interval),
            mentions_error=mentions.last_error if mentions_fault else None,
            last_error_fault=fault,
            mentions_error_fault=mentions_fault,
            hidden_repo=_repo(failures.hidden_repo) if fault is Fault.ACCESS else None,
            account=self._account,
            config_path=self._config_path,
        )

    def _fault(self, failures: WatcherFailures) -> Fault | None:
        if not failures.consecutive:
            return None
        return failures.fault or diagnose(failures.last_error, self._names)


def _repo(named: str | None) -> Repo | None:
    try:
        return None if named is None else Repo.parse(named)
    except ValueError:
        return None


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
