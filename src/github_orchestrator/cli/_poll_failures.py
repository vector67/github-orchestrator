from github_orchestrator.cli._findings import Finding, fail, warn
from github_orchestrator.domain import Cause

RETRYING = "can't reach GitHub, retrying each poll"
CLEARS_ITSELF = "none needed; the next poll that reaches GitHub clears it"
WHOLE_ERROR = "github-orchestrator logs shows the whole error"


def one_line(text: str) -> str:
    return " ".join(text.split())


def poll_failure(error: str, cause: Cause | None, fix: str | None) -> str:
    if cause is Cause.NETWORK:
        return f"{RETRYING}: {one_line(error)}"
    fixed_by = "" if fix is None else f"; fix: {fix}"
    return f"last error: {one_line(error)}{fixed_by}"


def watcher_finding(error: str, cause: Cause | None, fix: str | None, last_good: str) -> Finding:
    if cause is Cause.NETWORK:
        return warn(f"the watcher {RETRYING} ({last_good}): {one_line(error)}", CLEARS_ITSELF)
    return fail(f"the watcher is failing ({last_good}): {one_line(error)}", fix or WHOLE_ERROR)


def mentions_finding(error: str, cause: Cause | None, config: str) -> Finding:
    if cause is Cause.NETWORK:
        return warn(f"the mentions search {RETRYING}: {one_line(error)}", CLEARS_ITSELF)
    return fail(f"the mentions search is failing: {one_line(error)}",
                f"correct mentions_start in {config}; the next poll searches again")


def mentions_failure(error: str, cause: Cause | None) -> str:
    if cause is Cause.NETWORK:
        return f"{RETRYING}: {one_line(error)}"
    return f"failing — {one_line(error)}"
