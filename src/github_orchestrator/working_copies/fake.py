import difflib
import itertools
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from github_orchestrator.domain import Pr, Sha
from github_orchestrator.github import PullRequests
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.notifications import Worktrees
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.working_copies._diff import FALLBACK_BASE_REFS, is_branch_name
from github_orchestrator.working_copies._handles import (
    BoundCheckout,
    Located,
    not_found,
)
from github_orchestrator.working_copies._hunks import parse_diff
from github_orchestrator.working_copies._layout import (
    pr_worktrees,
    thread_branch,
    thread_branch_prefix,
    thread_worktree,
)
from github_orchestrator.working_copies._threads import SQUASH_EMPTY
from github_orchestrator.working_copies._trouble import (
    BranchTrouble,
    Conflict,
    Grace,
    Mismatch,
)
from github_orchestrator.working_copies.interface import (
    DiffHunk as DiffHunk,
)
from github_orchestrator.working_copies.interface import (
    DiffLine as DiffLine,
)
from github_orchestrator.working_copies.interface import (
    FileDiff,
    Picked,
    ThreadGitError,
    Verdict,
    WrongBranch,
)


@dataclass(frozen=True)
class FakeCommit:
    sha: str
    parent: str | None
    message: str
    tree: dict[str, str]


@dataclass
class FakeCheckout:
    branch: str | None
    detached: str | None = None
    main: bool = False
    edits: dict[str, str] = field(default_factory=dict)


def _key(path: Path | str) -> str:
    return str(Path(path))


class FakeFlags:
    def __init__(self) -> None:
        self.mismatches: dict[Pr, Mismatch] = {}
        self.conflicts: dict[Pr, Conflict] = {}

    def mismatch(self, pr: Pr) -> Mismatch | None:
        return self.mismatches.get(pr)

    def save_mismatch(self, pr: Pr, mismatch: Mismatch) -> None:
        self.mismatches[pr] = mismatch

    def clear_mismatch(self, pr: Pr) -> None:
        self.mismatches.pop(pr, None)

    def conflict(self, pr: Pr) -> Conflict | None:
        return self.conflicts.get(pr)

    def save_conflict(self, pr: Pr, conflict: Conflict) -> None:
        self.conflicts[pr] = conflict

    def clear_conflict(self, pr: Pr) -> None:
        self.conflicts.pop(pr, None)


class FakeWorkingCopies:
    def __init__(self, github: PullRequests | None = None,
                 thread_worktrees_dir: Path = Path("/fake/thread-worktrees"), *,
                 notifications: Worktrees | None = None, grace_seconds: int = 3600,
                 run_idle_seconds: int = 300) -> None:
        self.github = github or FakeGitHub()
        self.notifications = notifications or FakeNotifications()
        self.thread_worktrees_dir = thread_worktrees_dir
        self.commits: dict[str, FakeCommit] = {}
        self.origin: dict[str, str] = {}
        self.fetched: dict[str, str] = {}
        self.branches: dict[str, str] = {}
        self.checkouts: dict[str, FakeCheckout] = {}
        self.flags = FakeFlags()
        self.placed: dict[Pr, str] = {}
        self._trouble = BranchTrouble(self.flags, Grace(grace_seconds, run_idle_seconds),
                                      self.notifications, self.branch_at)
        self._numbers = itertools.count(1)
        self.pushes = 0
        self.on_push: Callable[[], None] | None = None
        self.on_pick: Callable[[], None] | None = None
        self.on_cut: Callable[[], None] | None = None
        self._push_refusal: str | None = None
        self._push_refusals_left: int | None = None
        self._push_error: Exception | None = None
        self._refused_workspaces: dict[str, str] = {}
        self._drop_error: Exception | None = None
        self._removal_refusal: str | None = None
        self._read_error: Exception | None = None
        self._shown_diff: tuple[FileDiff, ...] | None = None
        self._diff_shown = False
        self._binary_paths: set[str] = set()

    def refuse_pushes(self, reason: str | None, *, times: int | None = None) -> None:
        self._push_refusal = reason
        self._push_refusals_left = times

    def fail_pushes(self, error: Exception | None) -> None:
        self._push_error = error

    def refuse_workspace(self, key: str, reason: str = "git worktree add failed") -> None:
        self._refused_workspaces[key] = reason

    def fail_removals(self, reason: str | None) -> None:
        self._removal_refusal = reason

    def lose_worktree(self, worktree: Path | str) -> None:
        self._remove_worktree(str(worktree))

    def fail_drops(self, error: Exception | None) -> None:
        self._drop_error = error

    def fail_reads(self, error: Exception | None) -> None:
        self._read_error = error

    def show_diff(self, files: tuple[FileDiff, ...] | None) -> None:
        self._shown_diff = files
        self._diff_shown = True

    def serve_as_binary(self, path: str) -> None:
        self._binary_paths.add(path)

    def _refused_push(self) -> str | None:
        if self._push_refusal is None:
            return None
        reason = self._push_refusal
        if self._push_refusals_left is not None:
            self._push_refusals_left -= 1
            if self._push_refusals_left <= 0:
                self._push_refusal = None
                self._push_refusals_left = None
        return reason

    def add_repo(self, repo_dir: Path, files: dict[str, str], message: str) -> str:
        sha = self._new_commit(None, files, message)
        self.origin["main"] = sha
        self.fetched["main"] = sha
        self.branches["main"] = sha
        self.checkouts[_key(repo_dir)] = FakeCheckout(branch="main", main=True)
        return sha

    def place(self, pr: Pr, worktree: Path | str) -> None:
        self.placed[pr] = _key(worktree)

    def add_worktree(self, worktree: Path | str, branch: str | None) -> None:
        self.checkouts[_key(worktree)] = FakeCheckout(branch=branch)

    def check_out(self, worktree: Path | str, branch: str) -> None:
        self.branches.setdefault(branch, self.origin.get(branch, ""))
        self.checkouts[_key(worktree)].branch = branch

    def publish(self, branch: str, onto: str, files: dict[str, str], message: str) -> str:
        sha = self._new_commit(onto, files, message)
        self.origin[branch] = sha
        return sha

    def commit(self, worktree: Path | str, files: dict[str, str], message: str) -> str:
        checkout = self.checkouts[_key(worktree)]
        sha = self._new_commit(self._head(worktree), files, message)
        for name in files:
            checkout.edits.pop(name, None)
        self._advance(checkout, sha)
        return sha

    def edit(self, worktree: Path | str, name: str, text: str) -> None:
        self.checkouts[_key(worktree)].edits[name] = text

    def _create_pr_worktree(self, repo_dir: Path, pr: Pr, base_branch: str | None) -> Path:
        branch = self.github.head_branch(pr)
        if branch is None:
            raise RuntimeError(f"GitHub would not name the head branch of {pr}")
        self._fetch_branch(repo_dir, branch)
        self._fetch_base(base_branch)
        if self._holder(branch) is not None:
            raise RuntimeError(
                f"no free directory beside {repo_dir} for a {branch} worktree; "
                f"the last attempt said: fatal: '{branch}' is already used by worktree"
            )
        names = [branch, f"{branch}-pr{pr.number}", *(f"{branch}-{i}" for i in range(1, 21))]
        path = next(repo_dir.parent / name for name in names
                    if _key(repo_dir.parent / name) not in self.checkouts)
        self.branches.setdefault(branch, self.origin[branch])
        self.checkouts[_key(path)] = FakeCheckout(branch=branch)
        return path

    def _fetch_branch(self, worktree: Path, branch: str) -> None:
        if branch not in self.origin:
            raise RuntimeError(
                f"git fetch origin {branch} in {worktree} failed: "
                f"fatal: couldn't find remote ref {branch}"
            )
        self.fetched[branch] = self.origin[branch]

    def _fetch_base(self, base_branch: str | None) -> None:
        if base_branch in self.origin:
            self.fetched[base_branch] = self.origin[base_branch]

    def _switch_branch(self, worktree: Path, branch: str) -> str | None:
        if branch not in self.branches and branch not in self.origin:
            return (f"error: pathspec '{branch}' did not match any file(s) "
                    f"known to git")
        holder = self._holder(branch)
        if holder is not None and holder != _key(worktree):
            return f"fatal: '{branch}' is already used by worktree at '{holder}'"
        self.branches.setdefault(branch, self.origin.get(branch, ""))
        self.checkouts[_key(worktree)].branch = branch
        return None

    def _remove_worktree(self, worktree: str) -> None:
        checkout = self.checkouts.get(_key(worktree))
        if checkout is None or checkout.main:
            return
        del self.checkouts[_key(worktree)]

    def _delete_branch(self, branch: str) -> bool:
        if branch not in self.branches:
            return True
        if self._holder(branch) is not None:
            return False
        del self.branches[branch]
        return True

    def forget_pr(self, repo_dir: Path, pr: Pr, branch: str | None) -> bool:
        holder = None if branch is None else self._holder(branch)
        if holder is not None:
            if self._removal_refusal is not None:
                return False
            self._remove_worktree(holder)
        directory = pr_worktrees(self.thread_worktrees_dir, pr)
        for key in list(self.checkouts):
            if Path(key).is_relative_to(directory):
                del self.checkouts[key]
        prefix = thread_branch_prefix(pr)
        kept = [name for name in list(self.branches)
                if name.startswith(prefix) and not self._delete_branch(name)]
        if not kept:
            self._trouble.forget(pr)
        return not kept

    def pr_worktree(self, repo_dir: Path, pr: Pr, branch: str | None,
                    base_branch: str | None, *, fetch: bool = False) -> Path | None:
        holder = None if branch is None else self._holder(branch)
        if holder is not None and self.checkouts[holder].main:
            if self._switch_branch(repo_dir, "main") is not None:
                self.notifications.blocked(pr)
                return None
            holder = None
        if holder is None:
            try:
                return self._create_pr_worktree(repo_dir, pr, base_branch)
            except RuntimeError:
                return None
        if fetch and branch:
            self._fetch_pr_branch(pr, branch, base_branch)
        return Path(holder)

    def fetch_pr_branch(self, repo_dir: Path, pr: Pr, branch: str,
                        base_branch: str | None) -> None:
        if self._holder(branch) is not None:
            self._fetch_pr_branch(pr, branch, base_branch)

    def _fetch_pr_branch(self, pr: Pr, branch: str, base_branch: str | None) -> None:
        if branch in self.origin:
            self.fetched[branch] = self.origin[branch]
        else:
            self.notifications.fetch_failed(pr, branch)
        self._fetch_base(base_branch)

    def report_branch(self, pr: Pr, worktree: str, expected: str | None, *,
                      now: float, run_output_at: float | None) -> WrongBranch | None:
        return self._trouble.report_branch(pr, worktree, expected, now=now,
                                           run_output_at=run_output_at)

    def verdict(self, pr: Pr, worktree: Path | str | None, *, now: float,
                window_open: bool, manager_running: bool = False,
                expected: str | None = None,
                others: Mapping[Pr, str] | None = None) -> Verdict | None:
        return self._trouble.verdict(pr, worktree, now=now, window_open=window_open,
                                     manager_running=manager_running,
                                     expected=expected, others=others)

    def handed_off(self, pr: Pr, kept_as: str) -> None:
        self._trouble.handed_off(pr, kept_as)

    def request_release(self, pr: Pr) -> bool:
        return self._trouble.request_release(pr)

    def wrong_branch(self, pr: Pr, *, now: float) -> WrongBranch | None:
        return self._trouble.wrong_branch(pr, now=now)

    def thread_checkout(self, pr: Pr, key: str) -> str:
        return self._thread_path(pr, key)

    def holds_thread(self, pr: Pr, key: str) -> bool:
        return _key(self._thread_path(pr, key)) in self.checkouts

    def head_of(self, worktree: Path | str) -> str | None:
        return self._head(worktree)

    def branch_at(self, worktree: Path | str) -> str | None:
        checkout = self.checkouts.get(_key(worktree))
        return None if checkout is None else checkout.branch

    def commits_since(self, worktree: Path | str, sha: str | None) -> tuple[str, ...] | None:
        if not sha or _key(worktree) not in self.checkouts:
            return None
        since = self._resolve(sha)
        head = self._head(worktree)
        if since is None or head is None:
            return None
        return tuple(f"{commit[:7]} {self.commits[commit].message.splitlines()[0]}"
                     for commit in self._range(since, head))

    def checkout(self, pr: Pr) -> BoundCheckout:
        return BoundCheckout(self, pr)

    def _pr_worktree(self, pr: Pr) -> Located:
        if pr in self.placed:
            return Located(self.placed[pr])
        branch = self.github.head_branch(pr)
        holder = self._holder(branch) if branch else None
        return Located(holder) if holder is not None else not_found(pr, branch, "")

    def _is_clean(self, worktree: str) -> bool:
        return self._changed_files(worktree) == 0

    def _thread_path(self, pr: Pr, key: str) -> str:
        return str(thread_worktree(self.thread_worktrees_dir, pr, key))

    def _ensure_workspace(self, worktree: str, pr: Pr, key: str,
                          base_sha: str | None) -> str:
        if self.on_cut is not None:
            self.on_cut()
        if key in self._refused_workspaces:
            raise ThreadGitError(self._refused_workspaces[key])
        if base_sha and _key(self._thread_path(pr, key)) in self.checkouts:
            return base_sha
        base = self._head(worktree)
        if base is None:
            raise ThreadGitError(f"git rev-parse HEAD failed in {worktree}: "
                                 f"fatal: not a git repository")
        cut_branch = thread_branch(pr, key)
        cut = thread_worktree(self.thread_worktrees_dir, pr, key)
        self.checkouts.pop(_key(cut), None)
        self.branches[cut_branch] = base
        self.checkouts[_key(cut)] = FakeCheckout(branch=cut_branch)
        return base

    def _drop_workspace(self, worktree: str, path: str | None, branch: str | None) -> None:
        if self._drop_error is not None:
            raise self._drop_error
        if path:
            self._remove_worktree(path)
        if branch:
            self.branches.pop(branch, None)

    def _pick(self, worktree: str, branch: str | None, base_sha: str | None,
              thread_sha: str | None, message: str) -> Picked:
        if self.on_pick is not None:
            self.on_pick()
        if not branch or not base_sha:
            return Picked(refusal="approve intent on a thread with no branch or base_sha")
        if Sha.parse(base_sha) is None or Sha.parse(thread_sha) is None:
            return Picked(not_commits=True)
        tip = self.branches.get(branch)
        if tip is None:
            return Picked(missing_branch=branch, diagnostic="fatal: Needed a single revision")
        if tip != self._resolve(str(thread_sha)):
            return Picked(changed_since_review=True)
        landed_base = self._head(worktree)
        base = self._resolve(base_sha)
        if landed_base is None or base is None:
            return Picked(refusal="fatal: bad revision")
        tree = dict(self.commits[landed_base].tree)
        picked = list(reversed(self._range(base, tip)))
        for sha in picked:
            commit = self.commits[sha]
            before = self.commits[commit.parent].tree if commit.parent else {}
            for path in sorted(set(before) | set(commit.tree)):
                old, new = before.get(path), commit.tree.get(path)
                if old == new:
                    continue
                if tree.get(path) not in (old, new):
                    conflict = f"CONFLICT (content): Merge conflict in {path}"
                    return Picked(conflict_head=Sha.parse(landed_base), conflict=conflict,
                                        diagnostic=conflict)
                if new is None:
                    tree.pop(path, None)
                else:
                    tree[path] = new
        checkout = self.checkouts[_key(worktree)]
        if message or len(picked) > 1:
            if tree == self.commits[landed_base].tree:
                return Picked(refusal=f"{SQUASH_EMPTY}; the PR branch is back at "
                                   f"{landed_base[:12]} and nothing landed")
            worded = message or self.commits[tip].message
            landed = self._store(landed_base, tree, worded)
        else:
            landed = landed_base
            for sha in picked:
                landed = self._store(landed, dict(tree), self.commits[sha].message)
        self._advance(checkout, landed)
        return Picked(landed_base=Sha.parse(landed_base), landed_sha=Sha.parse(landed))

    def _push(self, worktree: str) -> str | None:
        self.pushes += 1
        if self.on_push is not None:
            self.on_push()
        if self._push_error is not None:
            raise self._push_error
        refused = self._refused_push()
        if refused is not None:
            return refused
        checkout = self.checkouts.get(_key(worktree))
        if checkout is None or checkout.branch is None:
            return "fatal: You are not currently on a branch."
        self.origin[checkout.branch] = self.branches[checkout.branch]
        self.fetched[checkout.branch] = self.branches[checkout.branch]
        return None

    def _reset(self, worktree: str, sha: str) -> str | None:
        self._advance(self.checkouts[_key(worktree)], sha)
        return None

    def _head_sha(self, path: str | None) -> str | None:
        return None if not path else self._head(path)

    def _fetch(self, worktree: str, base_branch: str | None) -> str | None:
        branch = self.branch_at(worktree)
        if branch is None:
            return f"{worktree} is on no branch, so there is none to fetch"
        try:
            self._fetch_branch(Path(worktree), branch)
        except RuntimeError as exc:
            return str(exc)
        self._fetch_base(base_branch)
        return None

    def _origin_head(self, worktree: str) -> str | None:
        branch = self.branch_at(worktree)
        return None if branch is None else self.fetched.get(branch)

    def _descends(self, path: str | None, onto: str, head: str) -> bool:
        if not path or not (Sha.parse(onto) is not None and Sha.parse(head) is not None):
            return False
        ancestor, descendant = self._resolve(onto), self._resolve(head)
        if ancestor is None or descendant is None:
            return False
        return ancestor in self._ancestors(descendant)

    def _progress_of(self, path: str | None, base_sha: str | None) -> str | None:
        if not path or not base_sha or Sha.parse(base_sha) is None:
            return None
        head = self._head(path)
        base = self._resolve(base_sha)
        if head is None or base is None:
            return None
        commits = len(self._range(base, head))
        files = self._changed_files(path)
        parts = []
        if commits:
            parts.append(f"{commits} commit" if commits == 1 else f"{commits} commits")
        if files:
            parts.append(f"{files} file changed" if files == 1 else f"{files} files changed")
        return ", ".join(parts) or None

    def _commit_message(self, worktree: str, sha: str | None) -> str | None:
        if Sha.parse(sha) is None:
            return None
        resolved = self._resolve(str(sha))
        return None if resolved is None else self.commits[resolved].message

    def _diff_files(self, worktree: str, base: str,
                    head: str) -> tuple[FileDiff, ...] | None:
        if self._diff_shown:
            return self._shown_diff
        old = self._rev_tree(worktree, base)
        new = self._rev_tree(worktree, head)
        if old is None or new is None:
            return None
        printed = "".join(_unified(path, old.get(path), new.get(path))
                          for path in _changed_paths(old, new))
        return parse_diff(printed)

    def _pr_base(self, worktree: str, base_branch: str | None, head: str) -> str | None:
        if base_branch and not is_branch_name(base_branch):
            base_branch = None
        refs = (f"origin/{base_branch}", base_branch) if base_branch else FALLBACK_BASE_REFS
        found = next((sha for sha in map(self._ref, refs) if sha is not None), None)
        head_sha = self._rev(worktree, head)
        if found is None or head_sha is None:
            return None
        reachable = set(self._ancestors(found))
        return next((sha for sha in self._ancestors(head_sha) if sha in reachable), None)

    def _has_commit(self, worktree: str, sha: str) -> bool:
        if self._read_error is not None:
            raise self._read_error
        return (Sha.parse(sha) is not None and _key(worktree) in self.checkouts
                and self._resolve(sha) is not None)

    def _blob(self, worktree: str, sha: str, path: str) -> bytes | None:
        if not self._has_commit(worktree, sha):
            return None
        text = self._tree(sha)
        found = None if text is None else text.get(path)
        if found is not None and path in self._binary_paths:
            return b"\x89PNG\r\n\x1a\n\xff\xfe"
        return None if found is None else found.encode()

    def _new_commit(self, parent: str | None, files: dict[str, str], message: str) -> str:
        tree = dict(self.commits[parent].tree) if parent else {}
        tree.update(files)
        return self._store(parent, tree, message)

    def _store(self, parent: str | None, tree: dict[str, str], message: str) -> str:
        sha = f"{next(self._numbers):040x}"
        self.commits[sha] = FakeCommit(sha=sha, parent=parent, message=message, tree=tree)
        return sha

    def _advance(self, checkout: FakeCheckout, sha: str) -> None:
        if checkout.branch is None:
            checkout.detached = sha
        else:
            self.branches[checkout.branch] = sha

    def _head(self, worktree: Path | str) -> str | None:
        checkout = self.checkouts.get(_key(worktree))
        if checkout is None:
            return None
        if checkout.branch is None:
            return checkout.detached
        return self.branches.get(checkout.branch)

    def _holder(self, branch: str) -> str | None:
        return next((path for path, checkout in self.checkouts.items()
                     if checkout.branch == branch), None)

    def _resolve(self, sha: str) -> str | None:
        if sha in self.commits:
            return sha
        matches = [known for known in self.commits if known.startswith(sha.lower())]
        return matches[0] if len(matches) == 1 else None

    def _ref(self, ref: str) -> str | None:
        if ref == "origin/HEAD":
            return self.fetched.get("main")
        if ref.startswith("origin/"):
            return self.fetched.get(ref.removeprefix("origin/"))
        return self.branches.get(ref)

    def _rev(self, worktree: str, rev: str) -> str | None:
        if rev == "HEAD":
            return self._head(worktree)
        return self._resolve(rev) if Sha.parse(rev) is not None else None

    def _rev_tree(self, worktree: str, rev: str) -> dict[str, str] | None:
        sha = self._rev(worktree, rev)
        return None if sha is None else self.commits[sha].tree

    def _tree(self, sha: str) -> dict[str, str] | None:
        resolved = self._resolve(sha)
        return None if resolved is None else self.commits[resolved].tree

    def _ancestors(self, sha: str) -> list[str]:
        found: list[str] = []
        current: str | None = sha
        while current is not None:
            found.append(current)
            current = self.commits[current].parent
        return found

    def _range(self, base: str, head: str) -> list[str]:
        excluded = set(self._ancestors(base))
        return [sha for sha in self._ancestors(head) if sha not in excluded]

    def _changed_files(self, worktree: str) -> int:
        checkout = self.checkouts.get(_key(worktree))
        head = self._head(worktree)
        if checkout is None or head is None:
            return 0
        tree = self.commits[head].tree
        return sum(1 for name, text in checkout.edits.items()
                   if name in tree and tree[name] != text)


def _changed_paths(old: dict[str, str], new: dict[str, str]) -> list[str]:
    return sorted(path for path in set(old) | set(new) if old.get(path) != new.get(path))


def _unified(path: str, old: str | None, new: str | None) -> str:
    header = [f"diff --git a/{path} b/{path}"]
    if old is None:
        header.append("new file mode 100644")
    if new is None:
        header.append("deleted file mode 100644")
    header += [f"--- {'/dev/null' if old is None else 'a/' + path}",
               f"+++ {'/dev/null' if new is None else 'b/' + path}"]
    body = list(difflib.unified_diff((old or "").splitlines(), (new or "").splitlines(),
                                     lineterm="", n=3))[2:]
    return "\n".join(header + body) + "\n"
