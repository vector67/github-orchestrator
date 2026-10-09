from pathlib import Path
from urllib.parse import quote

from github_orchestrator.domain import Pr


def _repo_dir(base: Path, pr: Pr) -> Path:
    return Path(base) / pr.repo.owner / pr.repo.name


def manager_record_file(pr_managers_dir: Path, pr: Pr) -> Path:
    return _repo_dir(pr_managers_dir, pr) / f"{pr.number}.json"


def mismatched_file(mismatched_dir: Path, pr: Pr) -> Path:
    return _repo_dir(mismatched_dir, pr) / f"{pr.number}.flag"


def worktree_conflict_file(worktree_conflicts_dir: Path, pr: Pr) -> Path:
    return _repo_dir(worktree_conflicts_dir, pr) / f"{pr.number}.flag"


def thread_dir(threads_dir: Path, pr: Pr) -> Path:
    return _repo_dir(threads_dir, pr) / str(pr.number)


def thread_file(threads_dir: Path, pr: Pr, key: str) -> Path:
    return thread_dir(threads_dir, pr) / f"{quote(key, safe='')}.json"


def thread_lock_file(threads_dir: Path, pr: Pr, key: str) -> Path:
    return thread_dir(threads_dir, pr) / f"{quote(key, safe='')}.lock"


def thread_intent_file(threads_dir: Path, pr: Pr, key: str) -> Path:
    return thread_dir(threads_dir, pr) / f"{quote(key, safe='')}.intent"


def thread_action_file(threads_dir: Path, pr: Pr, key: str) -> Path:
    return thread_dir(threads_dir, pr) / f"{quote(key, safe='')}.action"


def thread_reply_file(threads_dir: Path, pr: Pr, key: str) -> Path:
    return thread_dir(threads_dir, pr) / f"{quote(key, safe='')}.reply"


def review_lock_file(threads_dir: Path, pr: Pr) -> Path:
    return thread_dir(threads_dir, pr) / "reviews.lock"


def thread_worktree(thread_worktrees_dir: Path, pr: Pr, key: str) -> Path:
    return thread_dir(thread_worktrees_dir, pr) / quote(key, safe="")


def on_hold_file(on_hold_dir: Path, pr: Pr) -> Path:
    return _repo_dir(on_hold_dir, pr) / f"{pr.number}.flag"


def dismissed_file(dismissed_dir: Path, pr: Pr) -> Path:
    return _repo_dir(dismissed_dir, pr) / f"{pr.number}.flag"


def board_port_file(board_dir: Path, pr: Pr) -> Path:
    return _repo_dir(board_dir, pr) / f"{pr.number}.port"


def board_flag_file(board_dir: Path, pr: Pr) -> Path:
    return _repo_dir(board_dir, pr) / f"{pr.number}.flag"
