from pathlib import Path

BRANCH_REF = "ref: refs/heads/"


def _git_dir(worktree: Path) -> Path | None:
    dot_git = worktree / ".git"
    if dot_git.is_dir():
        return dot_git
    if dot_git.is_file():
        pointer = dot_git.read_text().strip()
        if pointer.startswith("gitdir:"):
            return worktree / pointer.removeprefix("gitdir:").strip()
    return None


def branch_of(worktree: str) -> str | None:
    try:
        git_dir = _git_dir(Path(worktree))
        if git_dir is None:
            return None
        head = (git_dir / "HEAD").read_text().strip()
    except OSError:
        return None
    return head.removeprefix(BRANCH_REF) if head.startswith(BRANCH_REF) else None
