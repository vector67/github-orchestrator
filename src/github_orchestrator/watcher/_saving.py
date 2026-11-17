import logging
from collections.abc import Mapping
from typing import Protocol

from github_orchestrator.domain import Cause, HubState, Pr, Repo, UtcClock
from github_orchestrator.github import Access
from github_orchestrator.notifications import Polling, ThreadNews
from github_orchestrator.pr_processes import ManagerPane
from github_orchestrator.settings import Dismissals
from github_orchestrator.watcher._config import WatcherConfig
from github_orchestrator.watcher._diagnosis import Diagnosis, diagnose, names_in
from github_orchestrator.watcher._failures import Streak
from github_orchestrator.watcher._poll import Fetched
from github_orchestrator.watcher._told import ToldFiles

log = logging.getLogger(__name__)

NOTIFY_AT = 3


class Saving(Protocol):
    def began(self, state: HubState) -> None: ...

    def threads_seen(self, pr: Pr, fetched: Fetched) -> None: ...

    def polled(self, managers: Mapping[Pr, ManagerPane]) -> None: ...

    def failed(self, exc: BaseException) -> None: ...

    def mentions_unread(self, exc: BaseException) -> None: ...

    def mentions_read(self) -> None: ...


class CycleSaving:
    def __init__(self, config: WatcherConfig, clock: UtcClock, *, dismissals: Dismissals,
                 thread_news: ThreadNews, polling: Polling, access: Access,
                 told: ToldFiles) -> None:
        self._config = config
        self._told = told
        self._access = access
        self._clock = clock
        self._dismissals = dismissals
        self._thread_news = thread_news
        self._polling = polling
        self._cycles = Streak(config.failures)
        self._searches = Streak(config.mentions_failure)

    def began(self, state: HubState) -> None:
        self._told.begin(state)

    def threads_seen(self, pr: Pr, fetched: Fetched) -> None:
        fetched.commit()
        if not self._dismissals.is_dismissed_forever(pr):
            fetched.announce(self._thread_news)

    def polled(self, managers: Mapping[Pr, ManagerPane]) -> None:
        self._told.show(managers)
        config = self._config
        try:
            config.heartbeat.write_text(self._clock().isoformat())
        except OSError as exc:
            log.warning("Could not write the heartbeat to %s: %s", config.heartbeat, exc)
        ended = self._cycles.ended()
        if ended.consecutive:
            log.info("recovered; failed cycles in a row: %d; last error: %s",
                     ended.consecutive, ended.last_error)

    def failed(self, exc: BaseException) -> None:
        try:
            error = _one_line(exc)
            diagnosis = diagnose(error, names_in(self._config))
            fix = self._fix(diagnosis)
            if (self._cycles.failed(error, fix) == NOTIFY_AT
                    and diagnosis.cause is Cause.OPERATOR):
                self._polling.failed(NOTIFY_AT, error, fix, self._config.log_file)
        except Exception:
            log.exception("Could not report the failed cycle")

    def mentions_unread(self, exc: BaseException) -> None:
        error = _one_line(exc)
        if (self._searches.failed(error, None) == NOTIFY_AT
                and diagnose(error, names_in(self._config)).cause is Cause.OPERATOR):
            self._polling.mentions_failed(NOTIFY_AT, error, self._config.log_file)

    def mentions_read(self) -> None:
        self._searches.ended()

    def _fix(self, diagnosis: Diagnosis) -> str | None:
        account = self._config.gh_account
        where = self._config.config_location
        match diagnosis:
            case Diagnosis.LOGIN:
                return (f"GitHub turned down the login for {account}. "
                        f"Run `gh auth login` as {account}.")
            case Diagnosis.DISK:
                return "The disk is full. Free some space and the watcher carries on."
            case Diagnosis.ACCESS:
                hidden = self._hidden_repo()
                if hidden is not None:
                    return (f"You can't see {hidden} as {account}. Remove it from [[repos]] "
                            f"in {where}, or ask for access.")
                return (f"GitHub refused a request as {account}. Check [[repos]] and "
                        f"gh_account in {where}.")
        return None

    def _hidden_repo(self) -> Repo | None:
        account = self._config.gh_account
        try:
            for repo in sorted(self._config.repos):
                if self._access.check_access(account, repo) is not None:
                    return repo
        except Exception:
            log.exception("Could not tell which repo the account cannot see")
        return None


def _one_line(exc: BaseException) -> str:
    return " ".join(str(exc).split()) or type(exc).__name__
