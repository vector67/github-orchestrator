from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass

from github_orchestrator.domain import Sha

log = logging.getLogger(__name__)

DIFF_TIMEOUT = 60

FALLBACK_BASE_REFS = ("origin/HEAD", "origin/main", "origin/master", "main", "master")


@dataclass(frozen=True)
class DiffSource:
    worktree: str
    left: str
    right: str
    path: str | None = None


BRANCH_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")

NOT_A_COMMIT = "not a commit"


def _is_rev(value: str | None) -> bool:
    return value == "HEAD" or Sha.parse(value) is not None


def is_branch_name(value: str | None) -> bool:
    if not value or value.startswith("-") or value.endswith(("/", ".lock")):
        return False
    if ".." in value or "@{" in value or value == "@":
        return False
    return BRANCH_RE.fullmatch(value) is not None


class _GitUnavailable(Exception):
    pass


def _run_git(worktree: str, *args: str) -> subprocess.CompletedProcess[str]:
    argv = ["git", "--no-optional-locks", "-C", worktree, *args]
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=DIFF_TIMEOUT,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.warning("git %s failed to run in %s: %s", args[0], worktree, exc)
        raise _GitUnavailable(
            "git failed to run, check the PR manager's log for details") from exc


def _last_stderr_line(result: subprocess.CompletedProcess[str]) -> str:
    return result.stderr.strip().split("\n")[-1] if result.stderr.strip() else ""


def raw_diff(source: DiffSource, unified: int) -> tuple[str | None, str]:
    for rev in (source.left, source.right):
        if not _is_rev(rev):
            log.warning("refusing to diff %r in %s: it is not a commit",
                        rev, source.worktree)
            return None, NOT_A_COMMIT
    pathspec = ["--", source.path] if source.path else []
    try:
        diff = _run_git(source.worktree, "diff", "--no-color",
                        f"-U{unified}",
                        "--src-prefix=a/", "--dst-prefix=b/",
                        "--end-of-options",
                        source.left, source.right, *pathspec)
    except _GitUnavailable as exc:
        return None, str(exc)
    if diff.returncode != 0:
        detail = _last_stderr_line(diff)
        log.warning("git diff %s..%s exited %d: %s",
                    source.left, source.right, diff.returncode, detail)
        return None, "git diff failed, check the PR manager's log for details"
    return diff.stdout, ""


CODE_NOT_FOUND = "couldn't find the code that this comment references"


def resolve_pr_base(
    worktree: str, base_branch: str | None, head: str
) -> tuple[str | None, str]:
    if base_branch and not is_branch_name(base_branch):
        log.warning("refusing to look for the PR base %r: it is not a branch "
                    "name", base_branch)
        base_branch = None
    refs = (f"origin/{base_branch}", base_branch) if base_branch else FALLBACK_BASE_REFS
    found = None
    for ref in refs:
        try:
            rev = _run_git(worktree, "rev-parse", "--verify", "--quiet",
                           "--end-of-options", f"{ref}^{{commit}}")
        except _GitUnavailable as exc:
            return None, str(exc)
        if rev.returncode == 0 and rev.stdout.strip():
            found = ref
            break
    if found is None:
        log.warning("could not resolve the PR base branch in %s (tried %s)",
                    worktree, ", ".join(refs))
        return None, CODE_NOT_FOUND

    if not _is_rev(head):
        log.warning("refusing to look for the PR base of %r: it is not a "
                    "commit", head)
        return None, NOT_A_COMMIT
    try:
        merge_base = _run_git(worktree, "merge-base", "--end-of-options",
                              found, head)
    except _GitUnavailable as exc:
        return None, str(exc)
    if merge_base.returncode != 0 or not merge_base.stdout.strip():
        detail = _last_stderr_line(merge_base)
        log.warning("git merge-base %s %s exited %d: %s",
                    found, head, merge_base.returncode, detail)
        return None, CODE_NOT_FOUND
    return merge_base.stdout.strip(), ""
