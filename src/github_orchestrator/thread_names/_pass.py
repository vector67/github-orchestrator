import logging
import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from github_orchestrator.domain import Pr, Repo, ThreadName
from github_orchestrator.thread_names.interface import StuckBranch

log = logging.getLogger(__name__)

GIT_TIMEOUT = 60
BRANCHES = "orchestrator/thread/"
_KIND = re.compile(r"[a-z]+")


def new_name(key: str) -> str:
    return str(ThreadName(key))


def key_of(name: str) -> str | None:
    named = ThreadName.parse(name)
    if named is not None:
        return named.key
    key = unquote(name)
    return key if key.strip(".") else None


def _pr_folder(base: Path, pr: Pr) -> Path:
    return base / pr.repo.owner / pr.repo.name / str(pr.number)


def _rename_records(threads_dir: Path) -> None:
    for path in sorted(threads_dir.glob("*/*/*/*")):
        stem, dot, kind = path.name.rpartition(".")
        if not dot or _KIND.fullmatch(kind) is None or kind == "tmp" or not path.is_file():
            continue
        key = key_of(stem)
        if key is None or new_name(key) == stem:
            continue
        target = path.with_name(f"{new_name(key)}.{kind}")
        if target.exists():
            log.warning("Left %s under its old name: %s is already there", path, target)
            continue
        os.rename(path, target)
        log.info("Renamed %s to %s", path, target.name)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          timeout=GIT_TIMEOUT, stdin=subprocess.DEVNULL,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


def _said(done: subprocess.CompletedProcess[str]) -> str:
    return done.stderr.strip() or done.stdout.strip() or f"exit {done.returncode}"


def _checked_out(clone: Path) -> dict[str, Path]:
    listed = _git(clone, "worktree", "list", "--porcelain")
    found: dict[str, Path] = {}
    folder: Path | None = None
    for line in listed.stdout.splitlines():
        if line.startswith("worktree "):
            folder = Path(line.removeprefix("worktree "))
        elif line.startswith("branch refs/heads/") and folder is not None:
            found[line.removeprefix("branch refs/heads/")] = folder
    return found


@dataclass(frozen=True)
class ThreadRename:
    clone: Path
    pr: Pr
    key: str
    branch: str
    target_branch: str
    folder: Path | None
    target_folder: Path
    left: str | None


def _planned(clone: Path, repo: Repo, worktrees_dir: Path) -> list[ThreadRename]:
    listed = _git(clone, "for-each-ref", "--format=%(refname:short)", f"refs/heads/{BRANCHES}")
    if listed.returncode != 0:
        log.error("Could not list the thread branches of %s in %s: %s", repo, clone,
                  _said(listed))
        return []
    branches = set(listed.stdout.split())
    checked_out = _checked_out(clone)
    ours = worktrees_dir.resolve()
    planned = []
    for branch in sorted(branches):
        number, _, name = branch.removeprefix(BRANCHES).partition("/")
        key = key_of(name) if number.isdigit() and "/" not in name else None
        if key is None:
            continue
        pr = Pr(repo, int(number))
        target_branch = f"{BRANCHES}{number}/{new_name(key)}"
        target_folder = _pr_folder(worktrees_dir, pr) / new_name(key)
        folder = checked_out.get(branch)
        if (folder is None or not folder.exists() or not folder.resolve().is_relative_to(ours)
                or folder.resolve() == target_folder.resolve()):
            folder = None
        left = None
        if branch != target_branch and target_branch in branches:
            left = f"Left {branch} under its old name: {target_branch} is already there"
        elif folder is not None and target_folder.exists():
            left = f"Left {folder} under its old name: {target_folder} is already there"
        if folder is not None or branch != target_branch:
            planned.append(ThreadRename(clone, pr, key, branch, target_branch, folder,
                                        target_folder, left))
    return planned


def _stuck(thread: ThreadRename) -> StuckBranch | None:
    if thread.left is not None:
        log.warning("%s", thread.left)
        return None
    if thread.folder is not None:
        moved = _git(thread.clone, "worktree", "move", str(thread.folder),
                     str(thread.target_folder))
        if moved.returncode != 0:
            log.warning("Left %s under its old name: %s", thread.folder, _said(moved))
            return None
        log.info("Moved %s to %s", thread.folder, thread.target_folder)
    if thread.branch != thread.target_branch:
        renamed = _git(thread.clone, "branch", "-m", thread.branch, thread.target_branch)
        if renamed.returncode != 0:
            log.error("Could not rename %s to %s: %s", thread.branch, thread.target_branch,
                      _said(renamed))
            return StuckBranch(thread.pr, thread.key, thread.branch, thread.target_branch,
                               str(thread.clone), _said(renamed).splitlines()[0])
        log.info("Renamed %s to %s", thread.branch, thread.target_branch)
    return None


def _report_dead_folders(worktrees_dir: Path) -> None:
    for folder in sorted(worktrees_dir.glob("*/*/*/*")):
        key = key_of(folder.name)
        if key is not None and new_name(key) != folder.name:
            log.warning("Left %s under its old name: no thread branch is checked out there",
                        folder)


class ThreadNames:
    def __init__(self, threads_dir: Path, worktrees_dir: Path,
                 clones: Mapping[Repo, Path]) -> None:
        self._threads_dir = threads_dir
        self._worktrees_dir = worktrees_dir
        self._clones = clones

    def planned(self) -> list[ThreadRename]:
        return [thread for repo, clone in self._clones.items() if clone.is_dir()
                for thread in _planned(clone, repo, self._worktrees_dir)]

    def rename(self, planned: list[ThreadRename]) -> list[StuckBranch]:
        _rename_records(self._threads_dir)
        stuck = [one for thread in planned if (one := _stuck(thread)) is not None]
        _report_dead_folders(self._worktrees_dir)
        return stuck
