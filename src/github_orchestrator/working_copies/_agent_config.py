import hashlib
import json
import logging
import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from github_orchestrator.atomic_write import write_atomically
from github_orchestrator.domain import Pr
from github_orchestrator.working_copies._layout import repo_dir
from github_orchestrator.working_copies.interface import AgentConfig

log = logging.getLogger(__name__)

DEFAULT_BRANCH = "refs/remotes/origin/HEAD"
GIT_TIMEOUT = 30


@dataclass(frozen=True)
class _Changes:
    changed: tuple[str, ...]
    digest: str


def _git(worktree: str, *args: str, quiet: bool = False) -> str | None:
    try:
        done = subprocess.run(
            ["git", "--no-optional-locks", "-C", worktree, *args],
            capture_output=True, timeout=GIT_TIMEOUT, stdin=subprocess.DEVNULL,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("git %s in %s failed to run: %s", args[0], worktree, exc)
        return None
    if done.returncode != 0:
        if quiet:
            return None
        log.warning("git %s in %s failed: %s", args[0], worktree,
                    done.stderr.decode(errors="replace").strip())
        return None
    return done.stdout.decode(errors="replace")


def _changes(worktree: str, head: str, default: str,
             paths: tuple[str, ...]) -> _Changes | None:
    base = _git(worktree, "merge-base", head, default)
    if base is None:
        return None
    named = _git(worktree, "diff", "--name-only", "-z", "--no-renames", base.strip(), head,
                 "--", *paths)
    if named is None:
        return None
    changed = tuple(sorted(name for name in named.split("\0") if name))
    if not changed:
        return _Changes((), "")
    listed = _git(worktree, "--literal-pathspecs", "ls-tree", "-r", "-z", head, "--", *changed)
    if listed is None:
        return None
    digest = hashlib.sha256("\0".join(changed).encode() + b"\0\0" + listed.encode()).hexdigest()
    return _Changes(changed, digest)


class AgentConfigs:
    def __init__(self, answers_dir: Path, paths: tuple[str, ...]) -> None:
        self._answers_dir = answers_dir
        self._paths = paths
        self._seen: dict[tuple[str, str, str], _Changes] = {}
        self._lock = threading.Lock()

    def unanswered_agent_config(self, pr: Pr, worktree: str,
                                branch: str | None) -> AgentConfig | None:
        fetched = () if branch is None else (f"refs/remotes/origin/{branch}",)
        for at in (*fetched, "HEAD"):
            config = self._config(pr, worktree, at, quiet=at != "HEAD")
            if config is not None and config.held:
                return config
        return None

    def agent_config(self, pr: Pr, worktree: str) -> AgentConfig | None:
        return self._config(pr, worktree, "HEAD", quiet=False)

    def _config(self, pr: Pr, worktree: str, at: str, *, quiet: bool) -> AgentConfig | None:
        if not os.path.isdir(worktree):
            return None
        tips = _git(worktree, "rev-parse", at, DEFAULT_BRANCH, quiet=quiet)
        if tips is None:
            return None
        head, default = tips.split()
        key = (worktree, head, default)
        with self._lock:
            changes = self._seen.get(key)
        if changes is None:
            changes = _changes(worktree, head, default, self._paths)
            if changes is None:
                return None
            with self._lock:
                self._seen[key] = changes
        return AgentConfig(changes.changed, changes.digest,
                           self._answer(pr, changes.digest) if changes.changed else None)

    def answer_agent_config(self, pr: Pr, digest: str, *, allowed: bool) -> None:
        with self._lock:
            answers = {**self._answers(pr), digest: allowed}
            write_atomically(self._path(pr), json.dumps(answers).encode())

    def _answer(self, pr: Pr, digest: str) -> bool | None:
        return self._answers(pr).get(digest)

    def _answers(self, pr: Pr) -> dict[str, bool]:
        try:
            stored = json.loads(self._path(pr).read_text())
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            log.warning("could not read the agent configuration answers for %s: %s", pr, exc)
            return {}
        if not isinstance(stored, dict):
            return {}
        return {digest: allowed for digest, allowed in stored.items()
                if isinstance(digest, str) and isinstance(allowed, bool)}

    def _path(self, pr: Pr) -> Path:
        return repo_dir(self._answers_dir, pr.repo) / f"{pr.number}.json"
