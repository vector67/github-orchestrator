import subprocess
from pathlib import Path

from tests.builders import a_pr


def _git(worktree: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(worktree), *args],
        text=True,
    ).strip()


def _build_repo(root: Path) -> str:
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "f").write_text("1")
    _git(root, "add", "f")
    _git(root, "commit", "-q", "-m", "first")
    return _git(root, "rev-parse", "HEAD")


def _init_repo(git_template) -> str:
    return git_template(_build_repo)


def test_returns_none_when_worktree_missing(copies, tmp_path):
    assert copies.commits_since(tmp_path / "does-not-exist", "abc123") is None


def _seen(copies, worktree, expected="elsewhere"):
    return copies.report_branch(a_pr(1, "o/n"), str(worktree), expected, now=1.0,
                                run_output_at=None)


def test_a_detached_worktree_is_no_mismatch(copies, tmp_path, git_template):
    sha = _init_repo(git_template)
    _git(tmp_path, "checkout", "-q", "--detach", sha)
    assert _seen(copies, tmp_path) is None


def test_a_directory_that_is_not_a_git_repo_is_no_mismatch(copies, tmp_path):
    (tmp_path / "f").write_text("not a repo")
    assert _seen(copies, tmp_path) is None


def test_a_subdirectory_is_on_its_worktrees_branch(copies, tmp_path, git_template):
    _init_repo(git_template)
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    sub = tmp_path / "src" / "deep"
    sub.mkdir(parents=True)
    assert _seen(copies, sub).here == "feature"
