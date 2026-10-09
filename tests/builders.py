from github_orchestrator.domain import Pr, Repo


def a_pr(number: int = 1, repo: str = "o/n") -> Pr:
    return Pr(Repo.parse(repo), number)
