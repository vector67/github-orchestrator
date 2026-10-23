from pathlib import Path

import pytest

from github_orchestrator.domain import Sha
from tests.working_copies.support import (
    BRANCH,
    THE_PR,
    GitWorld,
    build_origin,
    git,
)


@pytest.fixture
def git_world(tmp_path, settings, git_template):
    git_template(build_origin)
    return GitWorld(tmp_path, settings)


@pytest.fixture
def git_worktree(git_world):
    return git_world.copies.pr_worktree(git_world.repo_dir, THE_PR, None, None)


@pytest.fixture
def git_checkout(git_world, git_worktree):
    return git_world.copies.checkout(THE_PR)


def test_a_reset_in_a_clone_that_fetches_only_main_lands_on_origins_current_head(
        git_world, git_worktree, git_checkout):
    git(git_world.repo_dir, "config", "remote.origin.fetch",
        "+refs/heads/main:refs/remotes/origin/main")
    git_world.commit(git_worktree, {"h": "x\n"}, "local work")
    _, rewritten = git_world.advance_base()

    assert git_checkout.reset_to_origin(BRANCH, "main") is None

    assert git_checkout.local_head() == Sha(rewritten)


def _origin_tracks(world, name, text):
    seed = world.root / "seed"
    (seed / name).write_text(text)
    git(seed, "add", "-f", name)
    git(seed, "commit", "-q", "-m", f"track {name}")
    git(seed, "push", "-q", "--force", "origin", BRANCH)


def test_a_reset_leaves_an_ignored_file_that_origin_now_tracks_as_it_is(
        git_world, git_worktree, git_checkout):
    git_world.commit(git_worktree, {".gitignore": "secret.env\n"}, "ignore the secret")
    (git_worktree / "secret.env").write_text("the only copy of the key\n")
    _origin_tracks(git_world, "secret.env", "placeholder\n")

    refused = git_checkout.reset_to_origin(BRANCH, "main")

    assert refused is not None and "secret.env" in refused
    assert (git_worktree / "secret.env").read_text() == "the only copy of the key\n"


def test_a_reset_leaves_a_file_excluded_in_info_exclude_that_origin_now_tracks_as_it_is(
        git_world, git_worktree, git_checkout):
    common = Path(git(git_worktree, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    (common / "info").mkdir(exist_ok=True)
    (common / "info" / "exclude").write_text("notes.md\n")
    git_world.commit(git_worktree, {"h": "local\n"}, "local work")
    (git_worktree / "notes.md").write_text("hours of notes\n")
    _origin_tracks(git_world, "notes.md", "origin's notes\n")

    refused = git_checkout.reset_to_origin(BRANCH, "main")

    assert refused is not None and "notes.md" in refused
    assert (git_worktree / "notes.md").read_text() == "hours of notes\n"
