import logging
from typing import Protocol

from github_orchestrator.domain import Pr, UtcClock
from github_orchestrator.github import Access
from github_orchestrator.notifications import Polling, ThreadNews
from github_orchestrator.settings import Dismissals
from github_orchestrator.watcher._config import WatcherConfig
from github_orchestrator.watcher._failures import (
    clear_failures,
    read_failures,
    record_failure,
)
from github_orchestrator.watcher._poll import Fetched

log = logging.getLogger(__name__)

LOG_IN = "Log in with `gh auth login`, then this page retries."


class Saving(Protocol):
    def threads_seen(self, pr: Pr, fetched: Fetched) -> None: ...

    def polled(self) -> None: ...

    def failed(self, exc: BaseException) -> None: ...


class CycleSaving:
    def __init__(self, config: WatcherConfig, clock: UtcClock, *, dismissals: Dismissals,
                 thread_news: ThreadNews, polling: Polling, access: Access) -> None:
        self._config = config
        self._access = access
        self._clock = clock
        self._dismissals = dismissals
        self._thread_news = thread_news
        self._polling = polling

    def threads_seen(self, pr: Pr, fetched: Fetched) -> None:
        fetched.commit()
        if not self._dismissals.is_dismissed_forever(pr):
            fetched.announce(self._thread_news)

    def polled(self) -> None:
        config = self._config
        try:
            config.heartbeat.write_text(self._clock().isoformat())
        except OSError as exc:
            log.warning("Could not write the heartbeat to %s: %s", config.heartbeat, exc)
        ended = read_failures(config.failures)
        if ended.consecutive:
            log.info("recovered; failed cycles in a row: %d; last error: %s",
                     ended.consecutive, ended.last_error)
        try:
            clear_failures(config.failures)
        except OSError as exc:
            log.warning("Could not clear %s: %s", config.failures, exc)

    def failed(self, exc: BaseException) -> None:
        try:
            error = " ".join(str(exc).split()) or type(exc).__name__
            consecutive: int | None
            try:
                consecutive = record_failure(self._config.failures, error,
                                             self._fix()).consecutive
            except OSError:
                log.exception("Could not count the failed cycle in %s", self._config.failures)
                consecutive = None
            self._polling.failed(consecutive, error, self._config.log_file)
        except Exception:
            log.exception("Could not report the failed cycle")

    def _fix(self) -> str | None:
        account = self._config.gh_account
        try:
            if self._access.check_login(account) is not None:
                return LOG_IN
            for repo in sorted(self._config.repos):
                if self._access.check_access(account, repo) is not None:
                    return (f"You can't see {repo} as {account}. "
                            "Remove it from your repos, or ask for access.")
        except Exception:
            log.exception("Could not tell why the cycle failed")
        return None
