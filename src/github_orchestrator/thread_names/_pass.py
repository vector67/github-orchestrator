import logging
import os
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote, unquote

from github_orchestrator.domain import Pr, Repo

log = logging.getLogger(__name__)

GIT_TIMEOUT = 60
BRANCHES = "orchestrator/thread/"
_KIND = re.compile(r"[a-z]+")


def _uppercase_letters(key: str) -> str:
    letters = "".join("1" if c.isupper() else "0" for c in key if c.isalpha())
    return format(int(letters or "0", 2), "x")


def _valid(key: str) -> bool:
    return bool(key.strip("."))


def new_name(key: str) -> str:
    return f"{quote(key, safe='')}-{_uppercase_letters(key)}"


def key_of(name: str) -> str | None:
    quoted, _, _ = name.rpartition("-")
    if _valid(quoted) and new_name(unquote(quoted)) == name:
        return unquote(quoted)
    key = unquote(name)
    return key if _valid(key) else None


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


def _rename_branches(clone: Path, repo: Repo, worktrees_dir: Path) -> None:
    listed = _git(clone, "for-each-ref", "--format=%(refname:short)", f"refs/heads/{BRANCHES}")
    if listed.returncode != 0:
        log.error("Could not list the thread branches of %s in %s: %s", repo, clone,
                  _said(listed))
        return
    branches = set(listed.stdout.split())
    checked_out = _checked_out(clone)
    ours = worktrees_dir.resolve()
    for branch in sorted(branches):
        number, _, name = branch.removeprefix(BRANCHES).partition("/")
        key = key_of(name) if number.isdigit() and "/" not in name else None
        if key is None:
            continue
        pr = Pr(repo, int(number))
        target_branch = f"{BRANCHES}{number}/{new_name(key)}"
        target_folder = _pr_folder(worktrees_dir, pr) / new_name(key)
        if branch != target_branch and target_branch in branches:
            log.warning("Left %s under its old name: %s is already there", branch, target_branch)
            continue
        folder = checked_out.get(branch)
        if (folder is not None and folder.exists() and folder.resolve().is_relative_to(ours)
                and folder.resolve() != target_folder.resolve()):
            if target_folder.exists():
                log.warning("Left %s under its old name: %s is already there", folder,
                            target_folder)
                continue
            moved = _git(clone, "worktree", "move", str(folder), str(target_folder))
            if moved.returncode != 0:
                log.warning("Left %s under its old name: %s", folder, _said(moved))
                continue
            log.info("Moved %s to %s", folder, target_folder)
        if branch != target_branch:
            renamed = _git(clone, "branch", "-m", branch, target_branch)
            if renamed.returncode != 0:
                log.error("Could not rename %s to %s: %s", branch, target_branch,
                          _said(renamed))
                continue
            log.info("Renamed %s to %s", branch, target_branch)


def _report_dead_folders(worktrees_dir: Path) -> None:
    for folder in sorted(worktrees_dir.glob("*/*/*/*")):
        key = key_of(folder.name)
        if key is not None and new_name(key) != folder.name:
            log.warning("Left %s under its old name: no thread branch is checked out there",
                        folder)


def rename_thread_names(threads_dir: Path, worktrees_dir: Path,
                        clones: Mapping[Repo, Path]) -> None:
    _rename_records(threads_dir)
    for repo, clone in clones.items():
        if clone.is_dir():
            _rename_branches(clone, repo, worktrees_dir)
    _report_dead_folders(worktrees_dir)
