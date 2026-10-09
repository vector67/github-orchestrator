import logging
import shutil
import subprocess
import threading
from collections.abc import Mapping
from pathlib import Path

from github_orchestrator.domain import Clone, Pr, Repo, Sha
from github_orchestrator.github import PullRequests
from github_orchestrator.notifications import Worktrees
from github_orchestrator.working_copies import (
    _git_status,
    _hunks,
    _revisions,
    _threads,
    _worktree,
)
from github_orchestrator.working_copies._diff import resolve_pr_base
from github_orchestrator.working_copies._flags import DiskFlags
from github_orchestrator.working_copies._handles import (
    BoundCheckout,
    Located,
    not_found,
)
from github_orchestrator.working_copies._layout import pr_worktrees, thread_worktree
from github_orchestrator.working_copies._progress import Progress
from github_orchestrator.working_copies._trouble import BranchTrouble, Grace
from github_orchestrator.working_copies.interface import (
    FileDiff,
    Picked,
    ThreadGitError,
    Verdict,
    WrongBranch,
)

log = logging.getLogger(__name__)


class GitWorkingCopies:
    def __init__(self, github: PullRequests, notifications: Worktrees,
                 mismatched_dir: Path, worktree_conflicts_dir: Path,
                 thread_worktrees_dir: Path, clones: Mapping[Repo, Clone], *, grace_seconds: int,
                 run_idle_seconds: int) -> None:
        self._github = github
        self._clones = clones
        self._pr_worktrees: dict[Pr, Path] = {}
        self._notifications = notifications
        self._status = _git_status.GitStatus()
        self._trouble = BranchTrouble(
            DiskFlags(mismatched_dir, worktree_conflicts_dir),
            Grace(grace_seconds, run_idle_seconds), notifications,
            self._status.current_branch,
        )
        self._thread_worktrees_dir = thread_worktrees_dir
        self._cutting = threading.Lock()
        self._progress = Progress()

    def _create_pr_worktree(self, repo_dir: Path, pr: Pr, base_branch: str | None) -> Path:
        return _worktree.create_pr_worktree(
            repo_dir, pr, base_branch, github=self._github,
            notifications=self._notifications,
            new_worktree_command=self._clones[pr.repo].new_worktree_command,
        )

    def forget_pr(self, repo_dir: Path, pr: Pr, branch: str | None) -> bool:
        worktree_gone = self._forget_pr_worktree(repo_dir, pr, branch)
        forgotten = self._forget_thread_workspaces(repo_dir, pr) and worktree_gone
        if forgotten:
            self._trouble.forget(pr)
        return forgotten

    def _forget_pr_worktree(self, repo_dir: Path, pr: Pr,
                            branch: str | None) -> bool:
        worktree = _worktree.worktree_for_branch(repo_dir, branch) if branch else None
        if worktree is None:
            return True
        try:
            _worktree.remove_worktree(str(worktree))
        except Exception:
            log.exception("reap %s: failed to remove worktree %s", pr, worktree)
            return False
        return True

    def _forget_thread_workspaces(self, repo_dir: Path, pr: Pr) -> bool:
        directory = pr_worktrees(self._thread_worktrees_dir, pr)
        forgotten = True
        for checkout in sorted(directory.iterdir()) if directory.is_dir() else []:
            if not (checkout / ".git").exists():
                continue
            try:
                _worktree.remove_worktree(str(checkout))
            except Exception:
                log.exception("reap %s: failed to drop the thread workspace %s",
                              pr, checkout)
                forgotten = False
        branches = _threads.thread_branches(repo_dir, pr)
        if branches is None:
            return False
        for thread_branch in branches:
            if not _worktree.delete_branch(repo_dir, thread_branch):
                forgotten = False
        if not forgotten:
            return False
        if not directory.exists():
            return True
        try:
            shutil.rmtree(directory)
        except OSError:
            log.exception("reap %s: failed to remove %s", pr, directory)
            return False
        return True

    def pr_worktree(self, repo_dir: Path, pr: Pr, branch: str | None,
                    base_branch: str | None, *, fetch: bool = False) -> Path | None:
        worktree = _worktree.worktree_for_branch(repo_dir, branch) if branch else None
        if worktree is not None and worktree.resolve() == repo_dir.resolve():
            log.warning(
                "Main worktree has PR %s's branch checked out; switching it to main "
                "so the branch can be adopted into a fresh worktree",
                pr.in_repo,
            )
            refused = _worktree.switch_branch(repo_dir, "main")
            if refused is not None:
                log.error("Failed to switch main worktree to main for PR %s: %s", pr.in_repo, refused)
                self._notifications.blocked(pr)
                return None
            worktree = None
        if worktree is None:
            try:
                created = self._create_pr_worktree(repo_dir, pr, base_branch)
            except RuntimeError as e:
                log.error("Failed to create worktree for PR %s: %s", pr.in_repo, e)
                return None
            log.info("Created worktree for PR %s at %s", pr.in_repo, created)
            return created
        log.info("Reusing existing worktree for PR %s at %s", pr.in_repo, worktree)
        if fetch and branch:
            self._fetch_pr_branch(worktree, pr, branch, base_branch)
        return worktree

    def fetch_pr_branch(self, repo_dir: Path, pr: Pr, branch: str,
                        base_branch: str | None) -> None:
        worktree = _worktree.worktree_for_branch(repo_dir, branch)
        if worktree is None:
            log.debug("ensure_pr_window %s: nothing to fetch (worktree=%s, branch=%s)",
                      pr, worktree, branch)
            return
        self._fetch_pr_branch(worktree, pr, branch, base_branch)

    def _fetch_pr_branch(self, worktree: Path, pr: Pr, branch: str,
                         base_branch: str | None) -> None:
        try:
            _worktree.fetch_branch(worktree, branch)
        except RuntimeError as exc:
            log.error("Failed to fetch %s for %s in %s: %s", branch, pr, worktree, exc)
            self._notifications.fetch_failed(pr, branch)
        _worktree.fetch_base(worktree, base_branch)

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

    def commits_since(self, worktree: Path | str, sha: str | None) -> tuple[str, ...] | None:
        return self._status.commits_since(worktree, sha)

    def checkout(self, pr: Pr) -> BoundCheckout:
        return BoundCheckout(self, pr)

    def _pr_worktree(self, pr: Pr) -> Located:
        known = self._pr_worktrees.get(pr)
        if known is not None and known.is_dir():
            return Located(str(known))
        if pr.repo not in self._clones:
            return Located(None, f"{pr.repo} is not one of the watched repos in [[repos]], "
                                 "so there is no clone of it to work in")
        branch = self._github.head_branch(pr)
        clone = self._clones[pr.repo].path
        found = _worktree.worktree_for_branch(clone, branch) if branch else None
        if found is None:
            missing = not_found(pr, branch, f"of {clone} ")
            log.warning("%s", missing.missing)
            return missing
        self._pr_worktrees[pr] = found
        return Located(str(found))

    def _is_clean(self, worktree: str) -> bool:
        try:
            status = _threads.run_git(worktree, "status", "--porcelain",
                                      "--untracked-files=no")
        except (OSError, subprocess.TimeoutExpired):
            return False
        return status.returncode == 0 and not status.stdout.strip()

    def _thread_path(self, pr: Pr, key: str) -> str:
        return str(thread_worktree(self._thread_worktrees_dir, pr, key))

    def _ensure_workspace(self, worktree: str, pr: Pr, key: str,
                          base_sha: str | None) -> str:
        if base_sha and Path(self._thread_path(pr, key)).exists():
            return base_sha
        try:
            base = _threads.create_thread_worktree(
                worktree, self._thread_worktrees_dir, pr, key, self._cutting,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ThreadGitError(f"git could not cut a worktree for {key}: {exc}") from exc
        clone = self._clones[pr.repo]
        _worktree.run_new_worktree_command(Path(self._thread_path(pr, key)), clone.path,
                                           clone.new_worktree_command, self._notifications)
        return base

    def _drop_workspace(self, worktree: str, path: str | None, branch: str | None) -> None:
        try:
            _threads.drop_checkout(worktree, path, branch)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ThreadGitError(f"git could not drop {path}: {exc}") from exc

    def _pick(self, worktree: str, branch: str | None, base_sha: str | None,
              thread_sha: str | None, message: str) -> Picked:
        try:
            return _threads.pick(worktree, branch, base_sha, thread_sha, message)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return Picked(refusal=f"git could not land the fix: {exc}")

    def _push(self, worktree: str) -> str | None:
        try:
            pushed = _threads.run_git(worktree, "push")
        except (OSError, subprocess.TimeoutExpired) as exc:
            return str(exc)
        return None if pushed.returncode == 0 else _threads.git_diagnostic(pushed)

    def _reset(self, worktree: str, sha: str) -> str | None:
        return _threads.restore_head(worktree, sha)

    def _head_sha(self, path: str | None) -> str | None:
        return _threads.worktree_head(path)

    def _fetch(self, worktree: str, base_branch: str | None) -> str | None:
        branch = self._status.current_branch(worktree)
        if branch is None:
            return f"{worktree} is on no branch, so there is none to fetch"
        try:
            _worktree.fetch_branch(Path(worktree), branch)
        except RuntimeError as exc:
            return str(exc)
        _worktree.fetch_base(Path(worktree), base_branch)
        return None

    def _origin_head(self, worktree: str) -> str | None:
        branch = self._status.current_branch(worktree)
        if branch is None:
            return None
        try:
            found = _threads.run_git(worktree, "rev-parse", "--verify", "--quiet",
                                     f"refs/remotes/origin/{branch}^{{commit}}")
        except (OSError, subprocess.TimeoutExpired):
            return None
        return found.stdout.strip() or None if found.returncode == 0 else None

    def _descends(self, path: str | None, onto: str, head: str) -> bool:
        return _threads.is_ancestor(path, onto, head)

    def _progress_of(self, path: str | None, base_sha: str | None) -> str | None:
        return self._progress.line(path, base_sha)

    def _commit_message(self, worktree: str, sha: str | None) -> str | None:
        if Sha.parse(sha) is None:
            return None
        try:
            shown = _threads.run_git(worktree, "log", "-1", "--format=%B",
                                     "--end-of-options", str(sha))
        except (OSError, subprocess.TimeoutExpired):
            return None
        return shown.stdout.rstrip("\n") if shown.returncode == 0 else None

    def _diff_files(self, worktree: str, base: str,
                    head: str) -> tuple[FileDiff, ...] | None:
        return _hunks.diff_files(worktree, base, head)

    def _pr_base(self, worktree: str, base_branch: str | None, head: str) -> str | None:
        found, _ = resolve_pr_base(worktree, base_branch, head)
        return found

    def _has_commit(self, worktree: str, sha: str) -> bool:
        return _revisions.has_commit(worktree, sha)

    def _blob(self, worktree: str, sha: str, path: str) -> bytes | None:
        return _revisions.blob(worktree, sha, path)

