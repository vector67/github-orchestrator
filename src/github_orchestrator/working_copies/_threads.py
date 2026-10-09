import logging
import os
import subprocess
import threading
from pathlib import Path

from github_orchestrator.domain import Pr, Sha
from github_orchestrator.working_copies._layout import (
    thread_branch,
    thread_branch_prefix,
    thread_worktree,
)
from github_orchestrator.working_copies._worktree import remove_worktree
from github_orchestrator.working_copies.interface import (
    Picked,
    ThreadGitError,
)

log = logging.getLogger(__name__)

GIT_TIMEOUT = 60

SQUASH_FAILED = "the fix's commits could not be squashed into one"
SQUASH_EMPTY = ("the fix's commits undo each other, so there was nothing left "
                "to land")
LANDING_UNREADABLE = (
    "the fix is on the PR branch, but the commit it landed as could not be "
    "read back, so nothing recorded it; check the PR worktree's log before "
    "approving again, which would cherry-pick work that is already committed"
)

def run_git(cwd: str, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True, text=True, timeout=GIT_TIMEOUT,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired:
        log.warning("git %s timed out after %ds in %s", " ".join(args),
                    GIT_TIMEOUT, cwd)
        raise
    except OSError as e:
        log.warning("git %s could not run in %s: %s", " ".join(args), cwd, e)
        raise


def create_thread_worktree(
    pr_worktree: str, worktrees_dir: Path, pr: Pr, key: str,
    lock: threading.Lock,
) -> str:
    with lock:
        rev = run_git(pr_worktree, "rev-parse", "HEAD")
        if rev.returncode != 0:
            raise ThreadGitError(
                f"git rev-parse HEAD failed in {pr_worktree}: {rev.stderr.strip()}"
            )
        base_sha = rev.stdout.strip()

        branch = thread_branch(pr, key)
        wt = thread_worktree(worktrees_dir, pr, key)
        if wt.exists():
            remove_worktree(str(wt))

        run_git(pr_worktree, "branch", "-D", branch)

        add = run_git(pr_worktree, "worktree", "add", "-b", branch, str(wt), base_sha)
        if add.returncode != 0:
            raise ThreadGitError(
                f"git worktree add failed for {wt}: {add.stderr.strip()}"
            )

        return base_sha


def thread_branches(repo_dir: Path, pr: Pr) -> list[str] | None:
    heads = f"refs/heads/{thread_branch_prefix(pr)}"
    try:
        listed = run_git(str(repo_dir), "for-each-ref", "--format=%(refname)", heads)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if listed.returncode != 0:
        log.error("Could not list the thread branches of PR %s: %s", pr.in_repo,
                  git_diagnostic(listed))
        return None
    return [ref.removeprefix("refs/heads/") for ref in listed.stdout.split()]


def drop_checkout(pr_worktree: str, worktree: str | None,
                  branch: str | None) -> None:
    if worktree:
        remove_worktree(worktree)
    if branch:
        run_git(pr_worktree, "branch", "-D", branch)


def error_text(completed: subprocess.CompletedProcess[str]) -> str:
    return completed.stderr.strip() or completed.stdout.strip() or "no output"


def git_diagnostic(completed: subprocess.CompletedProcess[str]) -> str:
    lines = [
        line for line in error_text(completed).splitlines()
        if not line.startswith("hint:")
    ]
    last = max(
        (i for i, line in enumerate(lines) if line.startswith(("fatal:", "error:"))),
        default=None,
    )
    kept = lines if last is None else lines[:last + 1]
    return "\n".join(kept).strip() or "no output"


def base_divergence(pr_worktree: str, base_sha: str) -> str:
    try:
        counted = run_git(pr_worktree, "rev-list", "--count",
                          "--end-of-options", f"{base_sha}...HEAD")
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("Could not measure divergence from base %s: %s", base_sha, e)
        return ""
    count = counted.stdout.strip()
    if counted.returncode != 0 or not count.isdigit():
        return ""
    n = int(count)
    distance = (
        f"is at the thread's base {base_sha[:12]}"
        if n == 0
        else f"is {n} commit{'' if n == 1 else 's'} "
             f"from the thread's base {base_sha[:12]}"
    )
    return f"the PR worktree's HEAD {distance}"


def conflict_reason(pr_worktree: str, base_sha: str,
                    pick: subprocess.CompletedProcess[str]) -> str:
    conflict = git_diagnostic(pick)
    diagnosis = base_divergence(pr_worktree, base_sha)
    return f"{diagnosis} — {conflict}" if diagnosis else conflict


def worktree_head(worktree: str | None) -> str | None:
    if not worktree:
        return None
    try:
        result = run_git(worktree, "rev-parse", "HEAD")
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        log.warning("git rev-parse HEAD failed in %s: %s", worktree,
                    git_diagnostic(result))
        return None
    return result.stdout.strip() or None


def is_ancestor(worktree: str | None, ancestor: str, descendant: str) -> bool:
    if not worktree:
        return False
    if not (Sha.parse(ancestor) is not None and Sha.parse(descendant) is not None):
        log.warning("refusing to judge %r against %r: they are not commits",
                    ancestor, descendant)
        return False
    try:
        result = run_git(worktree, "merge-base", "--is-ancestor",
                         "--end-of-options", ancestor, descendant)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode not in (0, 1):
        log.warning("git merge-base --is-ancestor %s %s failed in %s: %s",
                    ancestor, descendant, worktree, git_diagnostic(result))
    return result.returncode == 0


def commits_between(pr_worktree: str, base: str, head: str) -> int | None:
    try:
        counted = run_git(pr_worktree, "rev-list", "--count",
                          "--end-of-options", f"{base}..{head}")
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("could not count what %s..%s landed: %s", base, head, e)
        return None
    count = counted.stdout.strip()
    if counted.returncode != 0 or not count.isdigit():
        log.warning("could not count what %s..%s landed: %s", base, head,
                    git_diagnostic(counted))
        return None
    return int(count)


def nothing_staged(pr_worktree: str) -> bool:
    try:
        staged = run_git(pr_worktree, "diff", "--cached", "--quiet")
    except (OSError, subprocess.TimeoutExpired):
        return False
    return staged.returncode == 0


def squash_onto(pr_worktree: str, base: str, tip: str,
                message: str = "") -> str | None:
    worded = ("-m", message) if message else ("-C", tip)
    try:
        reset = run_git(pr_worktree, "reset", "--soft", "--end-of-options",
                        base)
        if reset.returncode != 0:
            return f"{SQUASH_FAILED} — {git_diagnostic(reset)}"
        committed = run_git(pr_worktree, "commit", "--no-verify", *worded)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"{SQUASH_FAILED} — {e}"
    if committed.returncode == 0:
        return None
    if nothing_staged(pr_worktree):
        return SQUASH_EMPTY
    return f"{SQUASH_FAILED} — {git_diagnostic(committed)}"


def restore_head(pr_worktree: str, base: str) -> str | None:
    try:
        reset = run_git(pr_worktree, "reset", "--hard", "--end-of-options",
                        base)
    except (OSError, subprocess.TimeoutExpired) as e:
        return str(e)
    return None if reset.returncode == 0 else git_diagnostic(reset)


def _aborted_timeout_reason(pr_worktree: str) -> str:
    try:
        abort = run_git(pr_worktree, "cherry-pick", "--abort")
    except (OSError, subprocess.TimeoutExpired) as e:
        return (f"cherry-pick timed out after {GIT_TIMEOUT}s and the "
                f"abort raised — the PR worktree may be left unclean: {e}")
    if abort.returncode != 0:
        return (f"cherry-pick timed out after {GIT_TIMEOUT}s and the "
                f"abort failed — the PR worktree may be left unclean: "
                f"{git_diagnostic(abort)}")
    return f"cherry-pick timed out after {GIT_TIMEOUT}s and was aborted"


def pick(worktree: str, branch: str | None, base_sha: str | None,
         thread_sha: str | None,
         message: str = "") -> Picked:
    if not branch or not base_sha:
        return Picked(refusal=
            "approve intent on a thread with no branch or base_sha"
        )
    if Sha.parse(base_sha) is None or Sha.parse(thread_sha) is None:
        return Picked(not_commits=True)
    tip_result = run_git(worktree, "rev-parse", "--verify",
                         "--end-of-options", f"{branch}^{{commit}}")
    tip = tip_result.stdout.strip()
    reviewed = run_git(worktree, "rev-parse", "--verify",
                       "--end-of-options",
                       f"{thread_sha}^{{commit}}").stdout.strip()
    if tip_result.returncode != 0 or not tip:
        return Picked(missing_branch=branch, diagnostic=git_diagnostic(tip_result))
    if tip != reviewed:
        return Picked(changed_since_review=True)
    landed_base = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    try:
        picked = run_git(worktree, "cherry-pick", "--end-of-options",
                         f"{base_sha}..{branch}")
    except subprocess.TimeoutExpired:
        return Picked(refusal=_aborted_timeout_reason(worktree))
    if picked.returncode != 0:
        run_git(worktree, "cherry-pick", "--abort")
        conflict = conflict_reason(worktree, str(base_sha), picked)
        head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
        return Picked(conflict_head=Sha.parse(head), conflict=conflict,
                            diagnostic=git_diagnostic(picked))
    if message or (commits_between(worktree, landed_base, "HEAD") or 0) > 1:
        failure = squash_onto(worktree, landed_base, tip, message)
        if failure:
            unrestored = restore_head(worktree, landed_base)
            if unrestored is None:
                return Picked(refusal=
                    f"{failure}; the PR branch is back at "
                    f"{landed_base[:12]} and nothing landed"
                )
            return Picked(refusal=
                f"{failure}, and the PR branch could not be put back to "
                f"{landed_base[:12]}, so check the PR worktree by hand "
                f"before approving again — {unrestored}"
            )
    landed = worktree_head(worktree)
    if landed is None:
        return Picked(refusal=LANDING_UNREADABLE)
    return Picked(landed_base=Sha.parse(landed_base), landed_sha=Sha.parse(landed))
