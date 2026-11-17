import re
from collections.abc import Iterable

from github_orchestrator.domain import Fault
from github_orchestrator.watcher._config import WatcherConfig

_SIGNS = (
    (Fault.DISK, re.compile(r"Errno 28|no space left on device", re.IGNORECASE)),
    (Fault.LOGIN, re.compile(r"HTTP 401|bad credentials|no oauth token", re.IGNORECASE)),
    (Fault.NETWORK, re.compile(r"rate limit|submitted too quickly", re.IGNORECASE)),
    (Fault.ACCESS, re.compile(
        r"HTTP 40[34]|not found|could not resolve to a repository"
        r"|do not have permission", re.IGNORECASE)),
    (Fault.NETWORK, re.compile(
        r"no such host|could not resolve host|\bTLS\b|unexpected EOF|connection (reset|refused)"
        r"|network is unreachable|\btimeout\b|timed out|deadline exceeded|HTTP 5\d\d",
        re.IGNORECASE)),
)

_ADDRESS = re.compile(r"https?://\S+")


def names_in(config: WatcherConfig) -> list[str]:
    return [config.gh_account, *(name for repo in config.repos
                                 for name in (str(repo), repo.owner, repo.name))]


def diagnose(error: str, names: Iterable[str]) -> Fault:
    said = _ADDRESS.sub(" ", error)
    for name in sorted(filter(None, names), key=len, reverse=True):
        said = re.sub(rf"(?<![\w.-]){re.escape(name)}(?![\w.-])", " ", said,
                      flags=re.IGNORECASE)
    for fault, sign in _SIGNS:
        if sign.search(said):
            return fault
    return Fault.UNKNOWN
