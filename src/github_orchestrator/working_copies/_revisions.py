import logging
import os
import subprocess

from github_orchestrator.domain import Sha

log = logging.getLogger(__name__)

REVISION_TIMEOUT = 30


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
    if Sha.parse(sha) is None or not os.path.isdir(worktree):
        return None
    try:
        shown = _git(worktree, "show", f"{sha}:{path}", "--end-of-options")
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("git show %s:%s in %s failed to run: %s", sha, path,
                    worktree, exc)
        return None
    return shown.stdout if shown.returncode == 0 else None
