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
