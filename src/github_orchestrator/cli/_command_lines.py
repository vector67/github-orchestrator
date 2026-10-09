from github_orchestrator.domain import Pr

MODULE = "github_orchestrator.cli"
OPERATOR = "github-orchestrator"


def setup_line() -> str:
    return f"{OPERATOR} setup"


def restart_line() -> str:
    return f"{OPERATOR} restart"


def undismiss_line(pr: Pr) -> str:
    return f"{OPERATOR} undismiss --repo {pr.repo} {pr.number}"
