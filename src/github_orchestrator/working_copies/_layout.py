from pathlib import Path
from urllib.parse import quote

from github_orchestrator.domain import Pr, Repo


def repo_dir(base: Path, repo: Repo) -> Path:
    return Path(base) / repo.owner / repo.name


def _uppercase_letters(key: str) -> str:
    letters = "".join("1" if c.isupper() else "0" for c in key if c.isalpha())
    return format(int(letters or "0", 2), "x")


def thread_slug(key: str) -> str:
    if not key or key.strip(".") == "":
        raise ValueError(f"invalid thread key {key!r}")
    return f"{quote(key, safe='')}-{_uppercase_letters(key)}"


def pr_worktrees(thread_worktrees_dir: Path, pr: Pr) -> Path:
    return repo_dir(thread_worktrees_dir, pr.repo) / str(pr.number)


def thread_worktree(thread_worktrees_dir: Path, pr: Pr, key: str) -> Path:
    return pr_worktrees(thread_worktrees_dir, pr) / thread_slug(key)


def thread_branch_prefix(pr: Pr) -> str:
    return f"orchestrator/thread/{pr.number}/"


def thread_branch(pr: Pr, key: str) -> str:
    return f"{thread_branch_prefix(pr)}{thread_slug(key)}"
