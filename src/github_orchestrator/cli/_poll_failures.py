from github_orchestrator.domain import Cause

RETRYING = "can't reach GitHub, retrying each poll"


def one_line(text: str) -> str:
    return " ".join(text.split())


def poll_failure(error: str, cause: Cause | None, fix: str | None) -> str:
    if cause is Cause.NETWORK:
        return f"{RETRYING}: {one_line(error)}"
    fixed_by = "" if fix is None else f"; fix: {fix}"
    return f"last error: {one_line(error)}{fixed_by}"


def mentions_failure(error: str, cause: Cause | None) -> str:
    if cause is Cause.NETWORK:
        return f"{RETRYING}: {one_line(error)}"
    return f"failing — {one_line(error)}"
