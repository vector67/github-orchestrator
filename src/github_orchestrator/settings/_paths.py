from pathlib import Path

from github_orchestrator.domain import Repo


def repo_subdir(base: Path, repo: Repo) -> Path:
    return Path(base) / repo.owner / repo.name
