import sys

from github_orchestrator.domain import Pr


def defunct_name(pr: Pr) -> str:
    return f"{pr.repo.name}/{pr.in_repo}-defunct"


def manager_argv(pr: Pr) -> list[str]:
    return [sys.executable, "-m", "github_orchestrator.pr_manager",
            "--repo", str(pr.repo), "--pr", str(pr.number)]
