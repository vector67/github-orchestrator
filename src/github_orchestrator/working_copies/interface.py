from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from github_orchestrator.domain import Pr, Sha


class ThreadGitError(Exception):
    pass


@dataclass(frozen=True, kw_only=True)
class Verdict:
    hands_off: bool
    seconds_left: float
    trouble: str
    run_working: bool = False
    release_requested: bool = False


@dataclass(frozen=True, kw_only=True)
class WrongBranch(Verdict):
    worktree: str
    here: str
    expected: str


@dataclass(frozen=True, kw_only=True)
class Picked:
    landed_base: Sha | None = None
    landed_sha: Sha | None = None
    conflict_head: Sha | None = None
    conflict: str | None = None
    diagnostic: str = ""
    missing_branch: str | None = None
    not_commits: bool = False
    changed_since_review: bool = False
    refusal: str | None = None


@dataclass(frozen=True)
class DiffLine:
    kind: str
    old_line: int | None
    new_line: int | None
    text: str


@dataclass(frozen=True)
class DiffHunk:
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    section: str | None
    lines: tuple[DiffLine, ...]


@dataclass(frozen=True)
class FileDiff:
    path: str
    old_path: str | None
    status: str
    added: int
    removed: int
    is_binary: bool
    hunks: tuple[DiffHunk, ...]


@dataclass(frozen=True)
class PrDiff:
    base: Sha
    head: Sha
    files: tuple[FileDiff, ...]


@dataclass(frozen=True)
class Cut:
    workspace: "ThreadWorkspace | None"
    failure: str = ""


class ThreadWorkspace(Protocol):
    @property
    def path(self) -> str | None: ...

    @property
    def branch(self) -> str | None: ...

    @property
    def base_sha(self) -> Sha | None: ...

    def ensure(self) -> Cut: ...

    def pick(self, thread_sha: Sha | None, message: str = "") -> Picked: ...

    def head_sha(self) -> Sha | None: ...

    def descends(self, onto: Sha, head: Sha) -> bool: ...

    def progress(self) -> str | None: ...

    def drop(self) -> str | None: ...


class PrCheckout(Protocol):
    def no_worktree(self) -> str | None: ...

    def workspace(self, key: str, base_sha: Sha | None) -> ThreadWorkspace: ...

    def is_clean(self) -> bool: ...

    def push(self) -> str | None: ...

    def unpick(self, landed_base: Sha, landed_sha: Sha) -> str | None: ...

    def fetch(self, base_branch: str | None) -> str | None: ...

    def origin_head(self) -> Sha | None: ...

    def local_head(self) -> Sha | None: ...

    def commit_message(self, sha: Sha) -> str | None: ...

    def diff_files(self, base: Sha, head: Sha) -> tuple[FileDiff, ...] | None: ...

    def pr_diff(self, base_branch: str | None, head: Sha) -> PrDiff | None: ...

    def has_commit(self, sha: Sha) -> bool: ...

    def blob(self, sha: Sha, path: str) -> bytes | None: ...


class WorkingCopies(Protocol):
    def forget_pr(self, repo_dir: Path, pr: Pr, branch: str | None) -> bool: ...

    def pr_worktree(self, repo_dir: Path, pr: Pr, branch: str | None,
                    base_branch: str | None, *, fetch: bool = False) -> Path | None: ...

    def fetch_pr_branch(self, repo_dir: Path, pr: Pr, branch: str,
                        base_branch: str | None) -> None: ...

    def report_branch(self, pr: Pr, worktree: str, expected: str | None, *,
                      now: float, run_output_at: float | None) -> WrongBranch | None: ...

    def verdict(self, pr: Pr, worktree: Path | str | None, *, now: float,
                window_open: bool, manager_running: bool = False,
                expected: str | None = None,
                others: Mapping[Pr, str] | None = None) -> Verdict | None: ...

    def handed_off(self, pr: Pr, kept_as: str) -> None: ...

    def request_release(self, pr: Pr) -> bool: ...

    def wrong_branch(self, pr: Pr, *, now: float) -> WrongBranch | None: ...

    def commits_since(self, worktree: Path | str, sha: str | None) -> tuple[str, ...] | None: ...

    def checkout(self, pr: Pr) -> PrCheckout: ...
