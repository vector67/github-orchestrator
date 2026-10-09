import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

HeadState = tuple[str, str]


def _run(worktree: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(worktree), *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except subprocess.CalledProcessError as e:
        log.warning("git %s failed in %s: %s", " ".join(args), worktree,
                    (e.stderr or "").strip() or f"exit {e.returncode}")
    except subprocess.TimeoutExpired:
        log.warning("git %s timed out in %s", " ".join(args), worktree)
    except FileNotFoundError as e:
        log.warning("git %s could not run in %s: %s", " ".join(args), worktree, e)
    return None


def _git_dir(path: Path) -> Path | None:
    for directory in (path, *path.parents):
        dot_git = directory / ".git"
        if dot_git.is_dir():
            return dot_git
        if dot_git.is_file():
            pointer = dot_git.read_text().strip()
            if not pointer.startswith("gitdir:"):
                return None
            return directory / pointer.removeprefix("gitdir:").strip()
    return None


def _packed_ref(common: Path, ref: str) -> str | None:
    try:
        lines = (common / "packed-refs").read_text().splitlines()
    except FileNotFoundError:
        return None
    for line in lines:
        sha, _, name = line.partition(" ")
        if name == ref:
            return sha
    return None


def _ref_value(git_dir: Path, common: Path, ref: str) -> str | None:
    for home in (git_dir, common):
        try:
            return (home / ref).read_text().strip()
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
            continue
    return _packed_ref(common, ref)


def head_state(path: Path) -> HeadState | None:
    try:
        git_dir = _git_dir(path)
        if git_dir is None:
            return None
        head = (git_dir / "HEAD").read_text().strip()
        common = git_dir
        if (git_dir / "commondir").is_file():
            common = git_dir / (git_dir / "commondir").read_text().strip()
        if not head.startswith("ref:"):
            return head, head
        value = _ref_value(git_dir, common, head.removeprefix("ref:").strip())
    except OSError:
        return None
    if value is None:
        return None
    return head, value


class GitStatus:
    def __init__(self) -> None:
        self._answers: dict[tuple[Path, str], tuple[HeadState, str, str]] = {}

    def _git(self, worktree: Path, question: str, *args: str) -> str | None:
        state = head_state(worktree)
        asked = " ".join(args)
        known = self._answers.get((worktree, question))
        if state is not None and known is not None and known[:2] == (state, asked):
            return known[2]
        result = _run(worktree, *args)
        if result is None:
            return None
        answer = result.stdout.strip()
        if state is not None:
            self._answers[(worktree, question)] = (state, asked, answer)
        return answer

    def current_branch(self, worktree: Path | str) -> str | None:
        worktree = Path(worktree)
        if not worktree.exists():
            return None
        branch = self._git(worktree, "branch", "rev-parse", "--abbrev-ref", "HEAD")
        if not branch or branch == "HEAD":
            return None
        return branch

    def commits_since(self, worktree: Path | str, sha: str | None) -> tuple[str, ...] | None:
        if not sha:
            return None
        worktree = Path(worktree)
        if not worktree.exists():
            return None
        listed = self._git(worktree, "since", "rev-list", "--oneline", f"{sha}..HEAD")
        if listed is None:
            return None
        return tuple(listed.splitlines())
