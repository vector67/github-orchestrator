import re
from collections.abc import Iterable
from enum import Enum

from github_orchestrator.domain import Cause
from github_orchestrator.watcher._config import WatcherConfig


class Diagnosis(Enum):
    NETWORK = "network"
    LOGIN = "login"
    ACCESS = "access"
    DISK = "disk"
    UNKNOWN = "unknown"

    @property
    def cause(self) -> Cause:
        return Cause.NETWORK if self is Diagnosis.NETWORK else Cause.OPERATOR


_SIGNS = (
    (Diagnosis.DISK, re.compile(r"Errno 28|no space left on device", re.IGNORECASE)),
    (Diagnosis.LOGIN, re.compile(r"HTTP 401|bad credentials|no oauth token", re.IGNORECASE)),
    (Diagnosis.NETWORK, re.compile(r"rate limit|submitted too quickly", re.IGNORECASE)),
    (Diagnosis.ACCESS, re.compile(
        r"HTTP 40[34]|not found|could not resolve to a repository"
        r"|do not have permission", re.IGNORECASE)),
    (Diagnosis.NETWORK, re.compile(
        r"no such host|could not resolve host|\bTLS\b|unexpected EOF|connection (reset|refused)"
        r"|network is unreachable|\btimeout\b|timed out|deadline exceeded|HTTP 5\d\d",
        re.IGNORECASE)),
)

_ADDRESS = re.compile(r"https?://\S+")


def names_in(config: WatcherConfig) -> list[str]:
    return [config.gh_account, *(name for repo in config.repos
                                 for name in (str(repo), repo.owner, repo.name))]


def diagnose(error: str, names: Iterable[str]) -> Diagnosis:
    said = _ADDRESS.sub(" ", error)
    for name in sorted(filter(None, names), key=len, reverse=True):
        said = re.sub(rf"(?<![\w.-]){re.escape(name)}(?![\w.-])", " ", said,
                      flags=re.IGNORECASE)
    for diagnosis, sign in _SIGNS:
        if sign.search(said):
            return diagnosis
    return Diagnosis.UNKNOWN
