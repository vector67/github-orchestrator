from github_orchestrator.cli._findings import Finding, fail, warn
from github_orchestrator.domain import Fault, Repo

RETRYING = "can't reach GitHub, retrying each poll"
RATE_LIMITED = "rate limited by GitHub, retrying each poll"
CLEARS_ITSELF = "none needed; the next poll that reaches GitHub clears it"
LIMIT_RESETS = "none needed; polls resume once GitHub's rate limit resets"
WHOLE_ERROR = "github-orchestrator logs shows the whole error"


def one_line(text: str) -> str:
    return " ".join(text.split())


def watcher_fix(fault: Fault | None, account: str, hidden_repo: Repo | None,
                config: str) -> str | None:
    match fault:
        case Fault.LOGIN:
            return (f"GitHub turned down the login for {account}. "
                    f"Run `gh auth login` as {account}.")
        case Fault.DISK:
            return "The disk is full. Free some space and the watcher carries on."
        case Fault.GH_MISSING:
            return ("The watcher can't run gh. Install it from https://cli.github.com, "
                    "or put it on the watcher's PATH.")
        case Fault.ACCESS if hidden_repo is not None:
            return (f"You can't see {hidden_repo} as {account}. Remove it from [[repos]] "
                    f"in {config}, or ask for access.")
        case Fault.ACCESS:
            return (f"GitHub refused a request as {account}. Check [[repos]] and "
                    f"gh_account in {config}.")
    return None


def poll_failure(error: str, fault: Fault | None, fix: str | None) -> str:
    if fault is Fault.RATE_LIMIT:
        return f"{RATE_LIMITED}: {one_line(error)}"
    if fault is Fault.NETWORK:
        return f"{RETRYING}: {one_line(error)}"
    fixed_by = "" if fix is None else f"; fix: {fix}"
    return f"last error: {one_line(error)}{fixed_by}"


def watcher_finding(error: str, fault: Fault | None, fix: str | None, last_good: str) -> Finding:
    if fault is Fault.RATE_LIMIT:
        return warn(f"the watcher is {RATE_LIMITED} ({last_good}): {one_line(error)}",
                    LIMIT_RESETS)
    if fault is Fault.NETWORK:
        return warn(f"the watcher {RETRYING} ({last_good}): {one_line(error)}", CLEARS_ITSELF)
    return fail(f"the watcher is failing ({last_good}): {one_line(error)}", fix or WHOLE_ERROR)


def mentions_finding(error: str, config: str) -> Finding:
    return fail(f"the mentions search is failing: {one_line(error)}",
                f"correct {config} where the error points; the next poll searches again")


def mentions_failure(error: str) -> str:
    return f"failing — {one_line(error)}"
