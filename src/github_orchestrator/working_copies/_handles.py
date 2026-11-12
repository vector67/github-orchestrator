from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol

from github_orchestrator.domain import Pr, Sha
from github_orchestrator.working_copies._diff import PrBase, is_branch_name
from github_orchestrator.working_copies._layout import thread_branch
from github_orchestrator.working_copies._revisions import ShownCommit
from github_orchestrator.working_copies.interface import (
    BaseStanding,
    Changes,
    Cut,
    Diverged,
    FileDiff,
    NamedCommit,
    Picked,
    PrCommit,
    PrCommits,
    PrDiff,
    ResetRefused,
    ResetRefusedCode,
    Stack,
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

    def _serialized(self, pr: Pr) -> AbstractContextManager[None]: ...

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

    def _in_the_way(self, worktree: str, head: str, target: str) -> tuple[str, ...] | None: ...

    def _branch_at(self, worktree: str) -> str | None: ...

    def _base_standing(self, worktree: str, base_branch: str) -> BaseStanding | None: ...

    def _descends(self, path: str | None, onto: str, head: str) -> bool: ...

    def _unmatched(self, worktree: str, upstream: str, head: str) -> tuple[str, ...] | None: ...

    def _branch_head(self, path: str | None, branch: str) -> str | None: ...

    def _progress_of(self, path: str | None, base_sha: str | None) -> str | None: ...

    def _commit_message(self, worktree: str, sha: str | None) -> str | None: ...

    def _named_commit(self, worktree: str, sha: str) -> ShownCommit | None: ...

    def _diff_text(self, worktree: str, base: str, head: str) -> str | None: ...

    def _diff_files(self, worktree: str, base: str, head: str,
                    merged: str | None = None) -> tuple[FileDiff, ...] | None: ...

    def _pr_base(self, worktree: str, base_branch: str | None,
                 head: str) -> PrBase | None: ...

    def _merge_base(self, worktree: str, base_branch: str | None, head: str) -> str | None: ...

    def _head_diff(self, worktree: str, base_branch: str | None, local: bool) -> PrDiff | None: ...

    def _line_count(self, worktree: str, sha: str, path: str) -> int | None: ...

    def _authored_at(self, worktree: str, sha: str) -> datetime | None: ...

    def _commits_between(self, worktree: str, base: str,
                         head: str) -> tuple[PrCommit, ...] | None: ...

    def _has_commit(self, worktree: str, sha: str) -> bool: ...

    def _blob(self, worktree: str, sha: str, path: str) -> bytes | None: ...

    def _reset_workspace(self, path: str | None, to: str) -> str | None: ...

    def _workspace_diff(self, path: str | None, since: str) -> tuple[FileDiff, ...] | None: ...


def _text(sha: Sha | None) -> str | None:
    return None if sha is None else str(sha)


def _caught_up_with_origin(git: Git, path: str, outcome: str) -> str | Diverged | None:
    origin, head = git._origin_head(path), git._head_sha(path)
    if origin is None or head is None or git._descends(path, origin, head):
        return None
    if not git._descends(path, head, origin):
        unmatched = git._unmatched(path, origin, head)
        if unmatched is None:
            return (f"origin's PR branch was rewritten to {origin[:12]}, and the PR worktree "
                    f"at {head[:12]} could not be compared with it, so {outcome}")
        if unmatched:
            return Diverged(origin=Sha(origin), head=Sha(head),
                            unmatched=tuple(Sha(sha) for sha in unmatched))
    if not git._is_clean(path):
        return (f"the PR worktree has changes of its own, so it was not caught up with "
                f"origin and {outcome}")
    return git._reset(path, origin)


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
    def _branch(self) -> str | None:
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
        with self.git._serialized(self.pr):
            landable = (self._branch and Sha.parse(_text(self.base_sha)) is not None
                        and Sha.parse(_text(thread_sha)) is not None)
            behind = self._caught_up_with_origin(located.path) if landable else None
            if isinstance(behind, Diverged):
                return Picked(diverged=behind)
            if behind is not None:
                return Picked(refusal=behind)
            return self.git._pick(located.path, self._branch, _text(self.base_sha),
                                  _text(thread_sha), message)

    def _caught_up_with_origin(self, path: str) -> str | Diverged | None:
        failed = self.git._fetch(path, None)
        if failed is not None:
            return f"the PR branch would not fetch before landing, so nothing landed: {failed}"
        return _caught_up_with_origin(self.git, path, "nothing landed")

    def head_sha(self) -> Sha | None:
        return Sha.parse(self.git._head_sha(self.path))

    def descends(self, onto: Sha, head: Sha) -> bool:
        return self.git._descends(self.path, str(onto), str(head))

    def branch_head(self, branch: str) -> Sha | None:
        return Sha.parse(self.git._branch_head(self.path, branch))

    def progress(self) -> str | None:
        return self.git._progress_of(self.path, _text(self.base_sha))

    def reset(self, to: Sha) -> str | None:
        return self.git._reset_workspace(self.path, str(to))

    def diff_since(self, since: Sha) -> tuple[FileDiff, ...] | None:
        return self.git._workspace_diff(self.path, str(since))

    def drop(self) -> str | None:
        located = self.git._pr_worktree(self.pr)
        if located.path is None:
            return located.missing
        try:
            self.git._drop_workspace(located.path, self.path, self._branch)
        except ThreadGitError as exc:
            return str(exc)
        return None


@dataclass(frozen=True)
class BoundRevisions:
    git: Git
    pr: Pr

    def _path(self) -> str | None:
        return self.git._pr_worktree(self.pr).path

    def origin_head(self) -> Sha | None:
        path = self._path()
        return None if path is None else Sha.parse(self.git._origin_head(path))

    def local_head(self) -> Sha | None:
        return Sha.parse(self.git._head_sha(self._path()))

    def commit_message(self, sha: Sha) -> str | None:
        path = self._path()
        return None if path is None else self.git._commit_message(path, str(sha))

    def named_commit(self, sha: Sha) -> NamedCommit | None:
        path = self._path()
        read = None if path is None else self.git._named_commit(path, str(sha))
        if path is None or read is None:
            return None
        return NamedCommit(Sha(read.sha), Sha(read.parent), path, read.shown)

    def changes(self, base: Sha, head: Sha) -> Changes | None:
        path = self._path()
        shown = None if path is None else self.git._diff_text(path, str(base), str(head))
        return None if path is None or shown is None else Changes(path, shown)

    def diff_files(self, base: Sha, head: Sha,
                   merged: Sha | None = None) -> tuple[FileDiff, ...] | None:
        path = self._path()
        return None if path is None else self.git._diff_files(path, str(base), str(head),
                                                              _text(merged))

    def pr_base(self, base_branch: str | None, head: Sha) -> Sha | None:
        path = self._path()
        return None if path is None else Sha.parse(self.git._merge_base(path, base_branch,
                                                                        str(head)))

    def head_diff(self, base_branch: str | None, *, local: bool) -> PrDiff | None:
        path = self._path()
        return None if path is None else self.git._head_diff(path, base_branch, local)

    def line_count(self, sha: Sha, path: str) -> int | None:
        worktree = self._path()
        return None if worktree is None else self.git._line_count(worktree, str(sha), path)

    def pr_diff(self, base_branch: str | None, head: Sha) -> PrDiff | None:
        base = self.pr_base(base_branch, head)
        path = self._path()
        if base is None or path is None:
            return None
        files = self.git._diff_files(path, str(base), str(head))
        return None if files is None else PrDiff(base, head, files)

    def pr_commits(self, base_branch: str | None, head: Sha) -> PrCommits | None:
        path = self._path()
        if path is None:
            return None
        found = self.git._pr_base(path, base_branch, str(head))
        if found is None:
            return None
        fork, tip = found.merge_base, found.tip
        commits = self.git._commits_between(path, fork, str(head))
        base_commits = self.git._commits_between(path, fork, tip)
        fork_at = self.git._authored_at(path, fork)
        if commits is None or base_commits is None or fork_at is None:
            return None
        return PrCommits(Sha(fork), commits, Sha(tip), base_commits, fork_at,
                         self._stack(path, base_branch, fork))

    def _stack(self, path: str, base_branch: str | None, fork: str) -> Stack | None:
        found = None if base_branch is None else self.git._pr_base(path, None, fork)
        if found is None or found.branch == base_branch or found.merge_base == fork:
            return None
        commits = self.git._commits_between(path, found.merge_base, fork)
        return None if commits is None else Stack(found.branch, Sha(found.merge_base),
                                                  commits)

    def has_commit(self, sha: Sha) -> bool:
        path = self._path()
        return path is not None and self.git._has_commit(path, str(sha))

    def blob(self, sha: Sha, path: str) -> bytes | None:
        worktree = self._path()
        return None if worktree is None else self.git._blob(worktree, str(sha), path)


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

    def path(self) -> str | None:
        return self._path()

    def push(self) -> str | Diverged | None:
        located = self.git._pr_worktree(self.pr)
        if located.path is None:
            return located.missing
        with self.git._serialized(self.pr):
            behind = (None if self.git._fetch(located.path, None) is not None
                      else _caught_up_with_origin(self.git, located.path,
                                                  "nothing was pushed"))
            return behind if behind is not None else self.git._push(located.path)

    def unpick(self, landed_base: Sha, landed_sha: Sha) -> str | None:
        located = self.git._pr_worktree(self.pr)
        if located.path is None:
            return located.missing
        with self.git._serialized(self.pr):
            if not self.git._is_clean(located.path):
                return "the PR worktree has changes of its own"
            head = self.git._head_sha(located.path)
            if head != str(landed_sha):
                return (f"the PR branch has moved on to {(head or 'no commit')[:12]} since "
                        f"{str(landed_sha)[:12]} was picked onto it")
            return self.git._reset(located.path, str(landed_base))

    def fetch(self, base_branch: str | None) -> str | None:
        located = self.git._pr_worktree(self.pr)
        if located.path is None:
            return located.missing
        return self.git._fetch(located.path, base_branch)

    def reset_to_origin(self, branch: str, seen: Sha) -> ResetRefused | None:
        located = self.git._pr_worktree(self.pr)
        if located.path is None:
            return ResetRefused(ResetRefusedCode.WORKTREE_MISSING)
        with self.git._serialized(self.pr):
            return self._reset(located.path, branch, seen)

    def _reset(self, path: str, branch: str, seen: Sha) -> ResetRefused | None:
        origin = self.git._origin_head(path)
        if origin is None:
            return ResetRefused(ResetRefusedCode.NO_ORIGIN_BRANCH)
        here = self.git._branch_at(path)
        if here != branch:
            return ResetRefused(ResetRefusedCode.ON_ANOTHER_BRANCH, here or None)
        if not self.git._is_clean(path):
            return ResetRefused(ResetRefusedCode.UNCOMMITTED_CHANGES)
        head = self.git._head_sha(path)
        if head is None:
            return ResetRefused(ResetRefusedCode.HEAD_UNREADABLE)
        held_back = self._holds_back(path, seen, head, origin)
        if held_back is not None:
            return held_back
        refused = self.git._reset(path, origin)
        return None if refused is None else ResetRefused(ResetRefusedCode.RESET_REFUSED, refused)

    def _holds_back(self, path: str, seen: Sha, head: str, origin: str) -> ResetRefused | None:
        if head != str(seen):
            return ResetRefused(ResetRefusedCode.WORKTREE_MOVED, head)
        if self.git._descends(path, origin, head):
            return ResetRefused(ResetRefusedCode.NOT_DIVERGED)
        in_the_way = self.git._in_the_way(path, head, origin)
        if in_the_way is None:
            return ResetRefused(ResetRefusedCode.ORIGIN_ADDS_UNKNOWN)
        if in_the_way:
            return ResetRefused(ResetRefusedCode.UNTRACKED_IN_THE_WAY, ", ".join(in_the_way))
        return None

    def base_standing(self, base_branch: str | None) -> BaseStanding | None:
        path = self._path()
        if path is None or not base_branch or not is_branch_name(base_branch):
            return None
        return self.git._base_standing(path, base_branch)

    @property
    def revisions(self) -> BoundRevisions:
        return BoundRevisions(self.git, self.pr)
