from pathlib import Path
from urllib.parse import quote

from github_orchestrator.domain import Pr


def _uppercase_letters(key: str) -> str:
    letters = "".join("1" if c.isupper() else "0" for c in key if c.isalpha())
    return format(int(letters or "0", 2), "x")


def disk_name(key: str) -> str:
    if not key or key.strip(".") == "":
        raise ValueError(f"invalid thread key {key!r}")
    return f"{quote(key, safe='')}-{_uppercase_letters(key)}"


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
    return thread_dir(threads_dir, pr) / f"{disk_name(key)}.json"


def thread_lock_file(threads_dir: Path, pr: Pr, key: str) -> Path:
    return thread_dir(threads_dir, pr) / f"{disk_name(key)}.lock"


def thread_intent_file(threads_dir: Path, pr: Pr, key: str) -> Path:
    return thread_dir(threads_dir, pr) / f"{disk_name(key)}.intent"


def thread_action_file(threads_dir: Path, pr: Pr, key: str) -> Path:
    return thread_dir(threads_dir, pr) / f"{disk_name(key)}.action"


def thread_reply_file(threads_dir: Path, pr: Pr, key: str) -> Path:
    return thread_dir(threads_dir, pr) / f"{disk_name(key)}.reply"


def review_lock_file(threads_dir: Path, pr: Pr) -> Path:
    return thread_dir(threads_dir, pr) / f"{disk_name('reviews')}.lock"


def thread_worktree(thread_worktrees_dir: Path, pr: Pr, key: str) -> Path:
    return thread_dir(thread_worktrees_dir, pr) / disk_name(key)


def on_hold_file(on_hold_dir: Path, pr: Pr) -> Path:
    return _repo_dir(on_hold_dir, pr) / f"{pr.number}.flag"


def dismissed_file(dismissed_dir: Path, pr: Pr) -> Path:
    return _repo_dir(dismissed_dir, pr) / f"{pr.number}.flag"


def status_file(data_dir: Path, pr: Pr) -> Path:
    return _repo_dir(Path(data_dir) / "status", pr) / f"{pr.number}.json"


def command_file(data_dir: Path, pr: Pr, name: str) -> Path:
    return _repo_dir(Path(data_dir) / "commands", pr) / str(pr.number) / f"{name}.json"
