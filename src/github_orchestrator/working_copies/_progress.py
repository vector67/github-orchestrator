from __future__ import annotations

import logging
import os
import subprocess
import threading
import time

from github_orchestrator.domain import Sha

log = logging.getLogger(__name__)

PROGRESS_TIMEOUT = 5

PROGRESS_TTL_SECONDS = 20

def _git(worktree: str, *args: str) -> str | None:
    argv = ["git", "--no-optional-locks", "-C", worktree, *args]
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, timeout=PROGRESS_TIMEOUT,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("thread progress: git %s in %s failed to run: %s",
                    " ".join(args), worktree, exc)
        return None
    if completed.returncode != 0:
        detail = completed.stderr.strip().split("\n")[-1] if completed.stderr.strip() else ""
        log.warning("thread progress: git %s in %s exited %d: %s",
                    " ".join(args), worktree, completed.returncode, detail)
        return None
    return completed.stdout


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _compute(worktree: str, base_sha: str) -> str | None:
    counted = _git(worktree, "rev-list", "--count", "--end-of-options",
                   f"{base_sha}..HEAD")
    if counted is None:
        return None
    try:
        commits = int(counted.strip())
    except ValueError:
        log.warning("thread progress: git rev-list in %s printed %r",
                    worktree, counted[:80])
        return None

    status = _git(worktree, "status", "--porcelain", "--untracked-files=no")
    if status is None:
        return None
    files = sum(1 for line in status.splitlines() if line.strip())

    parts = []
    if commits:
        parts.append(_count(commits, "commit"))
    if files:
        parts.append(f"{_count(files, 'file')} changed")
    return ", ".join(parts) or None


class Progress:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], tuple[float, str | None]] = {}
        self._counting: set[tuple[str, str]] = set()
        self._lock = threading.Lock()

    def line(self, worktree: str | None, base_sha: str | None) -> str | None:
        if not worktree or not base_sha:
            return None
        if Sha.parse(base_sha) is None:
            log.warning("thread progress: %r is not a commit; nothing to count "
                        "from", base_sha)
            return None
        key = (str(worktree), str(base_sha))
        with self._lock:
            entry = self._cache.get(key)
            fresh = entry is not None and time.monotonic() - entry[0] < PROGRESS_TTL_SECONDS
            if not fresh and key not in self._counting:
                self._counting.add(key)
                threading.Thread(target=self._recount, args=(key,), daemon=True,
                                 name=f"thread progress {key[0]}").start()
        return None if entry is None else entry[1]

    def _recount(self, key: tuple[str, str]) -> None:
        line = self._count(key)
        with self._lock:
            self._cache[key] = (time.monotonic(), line)
            self._counting.discard(key)

    def _count(self, key: tuple[str, str]) -> str | None:
        if not os.path.isdir(key[0]):
            log.debug("thread progress: %s is gone; nothing to count", key[0])
            return None
        try:
            return _compute(*key)
        except Exception:
            log.exception("thread progress: computing %s failed", key)
            return None
