from dataclasses import dataclass, replace
from typing import Protocol

from github_orchestrator.domain import Pr, Sha
from github_orchestrator.working_copies._layout import thread_branch
from github_orchestrator.working_copies.interface import (
    Cut,
    FileDiff,
    Picked,
    PrDiff,
    ThreadGitError,
)


@dataclass(frozen=True)
class Located:
    path: str | None
    missing: str = ""


def not_found(pr: Pr, branch: str | None, where: str) -> Located:
    if branch is None:
        return Located(None, f"GitHub would not name the head branch of {pr}, so its "
                             f"worktree is not known")
    return Located(None, f"no worktree {where}holds {branch}, the head branch of {pr}")


class Git(Protocol):
    def _pr_worktree(self, pr: Pr) -> Located: ...

    def _is_clean(self, worktree: str) -> bool: ...

    def _thread_path(self, pr: Pr, key: str) -> str: ...

    def _ensure_workspace(self, worktree: str, pr: Pr, key: str,
                          base_sha: str | None) -> str: ...

    def _drop_workspace(self, worktree: str, path: str | None, branch: str | None) -> None: ...

    def _pick(self, worktree: str, branch: str | None, base_sha: str | None,
              thread_sha: str | None, message: str) -> Picked: ...

    def _push(self, worktree: str) -> str | None: ...

    def _reset(self, worktree: str, sha: str) -> str | None: ...

    def _head_sha(self, path: str | None) -> str | None: ...

    def _fetch(self, worktree: str, base_branch: str | None) -> str | None: ...

    def _origin_head(self, worktree: str) -> str | None: ...

    def _descends(self, path: str | None, onto: str, head: str) -> bool: ...

    def _progress_of(self, path: str | None, base_sha: str | None) -> str | None: ...

    def _commit_message(self, worktree: str, sha: str | None) -> str | None: ...

    def _diff_files(self, worktree: str, base: str, head: str) -> tuple[FileDiff, ...] | None: ...

    def _pr_base(self, worktree: str, base_branch: str | None, head: str) -> str | None: ...

    def _has_commit(self, worktree: str, sha: str) -> bool: ...

    def _blob(self, worktree: str, sha: str, path: str) -> bytes | None: ...


def _text(sha: Sha | None) -> str | None:
    return None if sha is None else str(sha)


@dataclass(frozen=True)
class BoundWorkspace:
    git: Git
    pr: Pr
    key: str
    base_sha: Sha | None

    @property
    def path(self) -> str | None:
        return self.git._thread_path(self.pr, self.key) if self.base_sha else None

    @property
    def branch(self) -> str | None:
        return thread_branch(self.pr, self.key) if self.base_sha else None

    def ensure(self) -> Cut:
        located = self.git._pr_worktree(self.pr)
        if located.path is None:
            return Cut(None, located.missing)
        try:
            base_sha = self.git._ensure_workspace(located.path, self.pr, self.key,
                                                  _text(self.base_sha))
        except ThreadGitError as exc:
            return Cut(None, str(exc))
        cut = Sha.parse(base_sha)
        if cut is None:
            return Cut(None, f"the thread was cut at {base_sha!r}, which is no commit hash")
        return Cut(replace(self, base_sha=cut))

    def pick(self, thread_sha: Sha | None, message: str = "") -> Picked:
        located = self.git._pr_worktree(self.pr)
        if located.path is None:
            return Picked(refusal=located.missing)
        return self.git._pick(located.path, self.branch, _text(self.base_sha),
                              _text(thread_sha), message)

    def head_sha(self) -> Sha | None:
        return Sha.parse(self.git._head_sha(self.path))

    def descends(self, onto: Sha, head: Sha) -> bool:
        return self.git._descends(self.path, str(onto), str(head))

    def progress(self) -> str | None:
        return self.git._progress_of(self.path, _text(self.base_sha))

    def drop(self) -> str | None:
        located = self.git._pr_worktree(self.pr)
        if located.path is None:
            return located.missing
        try:
            self.git._drop_workspace(located.path, self.path, self.branch)
        except ThreadGitError as exc:
            return str(exc)
        return None


@dataclass(frozen=True)
class BoundCheckout:
    git: Git
    pr: Pr

    def _path(self) -> str | None:
        return self.git._pr_worktree(self.pr).path

    def no_worktree(self) -> str | None:
        located = self.git._pr_worktree(self.pr)
        return None if located.path is not None else located.missing

    def workspace(self, key: str, base_sha: Sha | None) -> BoundWorkspace:
        return BoundWorkspace(self.git, self.pr, key, base_sha)

    def is_clean(self) -> bool:
        path = self._path()
        return path is not None and self.git._is_clean(path)

    def push(self) -> str | None:
        located = self.git._pr_worktree(self.pr)
        if located.path is None:
            return located.missing
        return self.git._push(located.path)

    def unpick(self, landed_base: Sha, landed_sha: Sha) -> str | None:
        located = self.git._pr_worktree(self.pr)
        if located.path is None:
            return located.missing
        head = self.git._head_sha(located.path)
        if head != str(landed_sha):
            return (f"the PR branch has moved on to {(head or 'no commit')[:12]} since "
                    f"{str(landed_sha)[:12]} was picked onto it")
        if not self.git._is_clean(located.path):
            return "the PR worktree has changes of its own"
        return self.git._reset(located.path, str(landed_base))

    def fetch(self, base_branch: str | None) -> str | None:
        located = self.git._pr_worktree(self.pr)
        if located.path is None:
            return located.missing
        return self.git._fetch(located.path, base_branch)

    def origin_head(self) -> Sha | None:
        path = self._path()
        return None if path is None else Sha.parse(self.git._origin_head(path))

    def local_head(self) -> Sha | None:
        return Sha.parse(self.git._head_sha(self._path()))

    def commit_message(self, sha: Sha) -> str | None:
        path = self._path()
        return None if path is None else self.git._commit_message(path, str(sha))

    def diff_files(self, base: Sha, head: Sha) -> tuple[FileDiff, ...] | None:
        path = self._path()
        return None if path is None else self.git._diff_files(path, str(base), str(head))

    def pr_diff(self, base_branch: str | None, head: Sha) -> PrDiff | None:
        path = self._path()
        if path is None:
            return None
        base = Sha.parse(self.git._pr_base(path, base_branch, str(head)))
        if base is None:
            return None
        files = self.git._diff_files(path, str(base), str(head))
        return None if files is None else PrDiff(base, head, files)

    def has_commit(self, sha: Sha) -> bool:
        path = self._path()
        return path is not None and self.git._has_commit(path, str(sha))

    def blob(self, sha: Sha, path: str) -> bytes | None:
        worktree = self._path()
        return None if worktree is None else self.git._blob(worktree, str(sha), path)
