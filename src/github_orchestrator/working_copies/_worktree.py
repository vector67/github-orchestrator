import logging
import os
import subprocess
from pathlib import Path

from github_orchestrator.domain import Pr
from github_orchestrator.github import PullRequests
from github_orchestrator.notifications import Worktrees
from github_orchestrator.working_copies._diff import is_branch_name

log = logging.getLogger(__name__)

GIT_TIMEOUT = 60
NEW_WORKTREE_TIMEOUT = 300
FALLBACK_NAMES = 20


def _git(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            capture_output=True, text=True, timeout=GIT_TIMEOUT,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env or {})},
        )
    except subprocess.TimeoutExpired:
        log.warning("git %s timed out after %ds", " ".join(args), GIT_TIMEOUT)
        return None


def _candidate_paths(repo_dir: Path, branch: str, pr: int | None) -> list[Path]:
    names = [branch]
    if pr is not None:
        names.append(f"{branch}-pr{pr}")
    names += [f"{branch}-{i}" for i in range(1, FALLBACK_NAMES + 1)]
    return [repo_dir.parent / name for name in names]


def run_new_worktree_command(worktree: Path, source_repo: Path, command: str,
                              notifications: Worktrees) -> None:
    if not command:
        return
    log.info("Initialising %s with new_worktree_command: %s",
             worktree, command)
    try:
        result = subprocess.run(
            ["sh", "-c", command],
            cwd=str(worktree), capture_output=True, text=True,
            timeout=NEW_WORKTREE_TIMEOUT, stdin=subprocess.DEVNULL,
            env={**os.environ, "GITHUB_ORCHESTRATOR_SOURCE_REPO": str(source_repo)},
        )
    except subprocess.TimeoutExpired as exc:
        raw = exc.stderr or b""
        printed = raw.decode(errors="replace") if isinstance(raw, bytes) else raw
        log.error("new_worktree_command timed out after %ds in %s: %s\n%s",
                  NEW_WORKTREE_TIMEOUT, worktree, command,
                  printed.strip())
        notifications.init_timed_out(worktree, NEW_WORKTREE_TIMEOUT)
        return
    if result.returncode != 0:
        log.error("new_worktree_command failed (rc=%d) in %s: %s\n%s",
                  result.returncode, worktree, command,
                  result.stderr.strip())
        notifications.init_failed(worktree, result.returncode)


def fetch_branch(worktree: Path, branch: str) -> None:
    fetched = _git("-C", str(worktree), "fetch", "origin", branch)
    if fetched is None:
        raise RuntimeError(
            f"git fetch origin {branch} in {worktree} timed out after {GIT_TIMEOUT}s"
        )
    if fetched.returncode != 0:
        raise RuntimeError(
            f"git fetch origin {branch} in {worktree} failed: {fetched.stderr.strip()}"
        )


def fetch_base(worktree: Path, base_branch: str | None) -> None:
    if not base_branch:
        return
    if not is_branch_name(base_branch):
        log.warning("refusing to fetch the PR base %r: it is not a branch name", base_branch)
        return
    try:
        fetch_branch(worktree, base_branch)
    except RuntimeError as exc:
        log.warning("could not fetch the base %s, so the PR's diff is drawn against "
                    "the last one fetched: %s", base_branch, exc)


def create_worktree(repo_dir: Path, branch: str, base_branch: str | None,
                    pr: int | None = None, *, notifications: Worktrees,
                    new_worktree_command: str) -> Path:
    fetch_branch(repo_dir, branch)
    fetch_base(repo_dir, base_branch)

    last_error = ""
    for candidate in _candidate_paths(repo_dir, branch, pr):
        added = _git("-C", str(repo_dir), "worktree", "add", str(candidate), branch)
        if added is None:
            raise RuntimeError(
                f"git worktree add {candidate} timed out after {GIT_TIMEOUT}s"
            )
        if added.returncode == 0:
            log.info("Created worktree for %s at %s", branch, candidate)
            run_new_worktree_command(candidate, repo_dir, new_worktree_command, notifications)
            return candidate
        last_error = added.stderr.strip()
    raise RuntimeError(
        f"no free directory beside {repo_dir} for a {branch} worktree; "
        f"the last attempt said: {last_error}"
    )


def create_pr_worktree(repo_dir: Path, pr: Pr, base_branch: str | None, *,
                       github: PullRequests, notifications: Worktrees,
                       new_worktree_command: str) -> Path:
    branch = github.head_branch(pr)
    if branch is None:
        raise RuntimeError(f"GitHub would not name the head branch of {pr}")
    return create_worktree(repo_dir, branch, base_branch, pr.number,
                           notifications=notifications,
                           new_worktree_command=new_worktree_command)


def remove_worktree(worktree: str) -> None:
    if not Path(worktree).exists():
        log.debug("Worktree %s already removed; skipping", worktree)
        return
    listed = _git("-C", worktree, "worktree", "list", "--porcelain")
    if listed is None:
        log.error(
            "Failed to remove worktree %s: listing its worktrees timed out "
            "after %ds", worktree, GIT_TIMEOUT,
        )
        return
    main_worktree = listed.stdout.split("\n")[0].replace("worktree ", "")
    if Path(worktree).resolve() == Path(main_worktree).resolve():
        log.warning("Refusing to remove main worktree: %s", worktree)
        return
    result = _git("-C", main_worktree, "worktree", "remove", "--force", worktree)
    if result is None:
        log.error(
            "Failed to remove worktree %s: git worktree remove timed out after %ds",
            worktree, GIT_TIMEOUT,
        )
    elif result.returncode == 0:
        log.info("Removed worktree: %s", worktree)
    else:
        log.error("Failed to remove worktree %s: %s", worktree, result.stderr)


def worktree_for_branch(repo_dir: Path, branch: str) -> Path | None:
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
    )

    current_path = None
    for line in result.stdout.split("\n"):
        if line.startswith("worktree "):
            current_path = line.split(" ", 1)[1]
        elif line.startswith("branch refs/heads/") and current_path:
            wt_branch = line.split("refs/heads/", 1)[1]
            if wt_branch == branch:
                path = Path(current_path)
                return path if path.is_dir() else None

    return None


def switch_branch(worktree: Path, branch: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(worktree), "checkout", branch],
        capture_output=True,
        text=True,
    )
    return None if result.returncode == 0 else result.stderr.strip()


def delete_branch(repo_dir: Path, branch: str) -> bool:
    exists = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "--verify",
         "--quiet", f"refs/heads/{branch}"],
        capture_output=True, text=True,
    )
    if exists.returncode != 0:
        return True
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "branch", "-D", branch],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        log.error("Failed to delete thread branch %s: %s",
                  branch, result.stderr.strip())
        return False
    log.info("Deleted thread branch %s", branch)
    return True
