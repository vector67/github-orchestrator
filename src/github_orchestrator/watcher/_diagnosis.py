import re
from enum import Enum

from github_orchestrator.domain import Cause


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
    (Diagnosis.NETWORK, re.compile(
        r"no such host|could not resolve host|TLS|unexpected EOF|connection (reset|refused)"
        r"|network is unreachable|timeout|timed out|deadline exceeded|HTTP 5\d\d"
        r"|rate limit|submitted too quickly", re.IGNORECASE)),
    (Diagnosis.LOGIN, re.compile(r"HTTP 401|bad credentials|no oauth token", re.IGNORECASE)),
    (Diagnosis.ACCESS, re.compile(
        r"HTTP 40[34]|not found|could not resolve to a repository"
        r"|do not have permission", re.IGNORECASE)),
    (Diagnosis.DISK, re.compile(r"Errno 28|no space left on device", re.IGNORECASE)),
)


def diagnose(error: str) -> Diagnosis:
    for diagnosis, sign in _SIGNS:
        if sign.search(error):
            return diagnosis
    return Diagnosis.UNKNOWN
