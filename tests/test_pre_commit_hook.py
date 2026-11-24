import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STUBS = Path(__file__).parent / "stubs" / "pre_commit"


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=octocat", "-c", "user.email=octocat@example.com", *args],
                   cwd=cwd, check=True, capture_output=True)


@pytest.mark.replays_while_unchanged(".githooks/pre-commit", "tests/stubs/pre_commit")
def test_a_worktrees_hook_checks_types_against_the_main_checkouts_shared_mypy_cache(tmp_path):
    main, tree = tmp_path / "main", tmp_path / "tree"
    main.mkdir()
    _git(main, "init", "-q")
    _git(main, "commit", "-q", "--allow-empty", "-m", "start")
    _git(main, "worktree", "add", "-q", str(tree))
    (tree / "widget.py").write_text("WIDGETS = 1\n")
    _git(tree, "add", "widget.py")
    log = tmp_path / "stub.log"
    outside_make = {name: value for name, value in os.environ.items() if name != "MYPY_CACHE_DIR"}

    subprocess.run(
        ["sh", str(REPO_ROOT / ".githooks/pre-commit")], cwd=tree, check=True,
        env={**outside_make, "PATH": f"{STUBS}:{os.environ['PATH']}", "STUB_LOG": str(log)})

    mypy_runs = [line for line in log.read_text().splitlines() if " mypy" in line]
    assert mypy_runs == [f"uv run --quiet mypy MYPY_CACHE_DIR={main.resolve()}/.shared-cache/mypy"], (
        "make lint keeps mypy's cache in the main checkout's .shared-cache; a hook "
        "with its own cache checks a new worktree from cold")
