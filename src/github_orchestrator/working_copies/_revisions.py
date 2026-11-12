import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime

from github_orchestrator.domain import Sha
from github_orchestrator.working_copies.interface import PrCommit

log = logging.getLogger(__name__)

REVISION_TIMEOUT = 30


@dataclass(frozen=True)
class ShownCommit:
    sha: str
    parent: str
    shown: str


def _git(worktree: str, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "--no-optional-locks", "-C", worktree, *args],
        capture_output=True, timeout=REVISION_TIMEOUT,
        stdin=subprocess.DEVNULL,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


def has_commit(worktree: str, sha: str) -> bool:
    if Sha.parse(sha) is None or not os.path.isdir(worktree):
        return False
    try:
        return _git(worktree, "cat-file", "-e", f"{sha}^{{commit}}",
                    "--end-of-options").returncode == 0
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("git cat-file for %s in %s failed to run: %s", sha,
                    worktree, exc)
        return False


def blob(worktree: str, sha: str, path: str) -> bytes | None:
    """The file's bytes at that commit, or None where it is not there.

    Bytes rather than text, because whether a file can be shown as lines is
    the caller's refusal to make and a decode that throws inside the adapter
    would look like the commit being missing.
    """
    if Sha.parse(sha) is None or not os.path.isdir(worktree) or "\0" in path:
        return None
    try:
        shown = _git(worktree, "cat-file", "blob", f"{sha}:{path}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("git show %s:%s in %s failed to run: %s", sha, path,
                    worktree, exc)
        return None
    return shown.stdout if shown.returncode == 0 else None


def line_count(content: bytes | None) -> int | None:
    return None if content is None else len(content.removesuffix(b"\n").split(b"\n"))


def commits_between(worktree: str, base: str, head: str) -> tuple[PrCommit, ...] | None:
    if Sha.parse(base) is None or Sha.parse(head) is None or not os.path.isdir(worktree):
        return None
    try:
        logged = _git(worktree, "log", "--reverse", "--format=%H%x1f%P%x1f%an%x1f%aI%x1f%s",
                      "--end-of-options", f"{base}..{head}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("git log %s..%s in %s failed to run: %s", base, head, worktree, exc)
        return None
    if logged.returncode != 0:
        return None
    return tuple(_commit(line) for line in logged.stdout.decode(errors="replace").splitlines())


def authored_at(worktree: str, sha: str) -> datetime | None:
    if Sha.parse(sha) is None or not os.path.isdir(worktree):
        return None
    try:
        logged = _git(worktree, "log", "-1", "--no-walk", "--format=%aI", "--end-of-options", sha)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("git log %s in %s failed to run: %s", sha, worktree, exc)
        return None
    if logged.returncode != 0:
        return None
    return datetime.fromisoformat(logged.stdout.decode().strip())


def _commit(line: str) -> PrCommit:
    sha, parents, author, authored_at, subject = line.split("\x1f", 4)
    return PrCommit(Sha(sha), tuple(Sha(parent) for parent in parents.split()), subject,
                    author, datetime.fromisoformat(authored_at))


def named_commit(worktree: str, sha: str) -> ShownCommit | None:
    if Sha.parse(sha) is None or not os.path.isdir(worktree):
        return None
    try:
        logged = _git(worktree, "log", "-1", "--format=%H %P", "--end-of-options",
                      f"{sha}^{{commit}}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("git log %s in %s failed to run: %s", sha, worktree, exc)
        return None
    if logged.returncode != 0:
        return None
    full, *parents = logged.stdout.decode().split()
    if not parents:
        return None
    try:
        shown = _git(worktree, "show", "--end-of-options", full)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("git show %s in %s failed to run: %s", full, worktree, exc)
        return None
    if shown.returncode != 0:
        return None
    return ShownCommit(full, parents[0], shown.stdout.decode(errors="replace"))


def diff_text(worktree: str, base: str, head: str) -> str | None:
    if Sha.parse(base) is None or Sha.parse(head) is None or not os.path.isdir(worktree):
        return None
    try:
        diffed = _git(worktree, "diff", "--end-of-options", base, head)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("git diff %s %s in %s failed to run: %s", base, head, worktree, exc)
        return None
    if diffed.returncode != 0:
        return None
    return diffed.stdout.decode(errors="replace")
