from pathlib import Path

from github_orchestrator.domain import Pr, Repo, ThreadName


def repo_dir(base: Path, repo: Repo) -> Path:
    return Path(base) / repo.owner / repo.name


def thread_slug(key: str) -> str:
    return str(ThreadName(key))


def pr_worktrees(thread_worktrees_dir: Path, pr: Pr) -> Path:
    return repo_dir(thread_worktrees_dir, pr.repo) / str(pr.number)


def thread_worktree(thread_worktrees_dir: Path, pr: Pr, key: str) -> Path:
    return pr_worktrees(thread_worktrees_dir, pr) / thread_slug(key)


def thread_branch_prefix(pr: Pr) -> str:
    return f"orchestrator/thread/{pr.number}/"


def thread_branch(pr: Pr, key: str) -> str:
    return f"{thread_branch_prefix(pr)}{thread_slug(key)}"
