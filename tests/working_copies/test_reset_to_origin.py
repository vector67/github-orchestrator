from pathlib import Path

import pytest

from github_orchestrator.domain import Sha
from tests.working_copies.support import (
    BRANCH,
    THE_PR,
    FakeWorld,
    GitWorld,
    build_origin,
    git,
)


@pytest.fixture(params=["fake", "git"])
def world(request, tmp_path, settings, git_template):
    if request.param == "fake":
        return FakeWorld(tmp_path)
    git_template(build_origin)
    return GitWorld(tmp_path, settings)


@pytest.fixture
def pr_worktree(world):
    return world.copies.pr_worktree(world.repo_dir, THE_PR, None, None)


@pytest.fixture
def pr_checkout(world, pr_worktree):
    return world.copies.checkout(THE_PR)


def _meanwhile(monkeypatch, world, step, act):
    real = getattr(world.copies, step)
    done = []

    def and_meanwhile(*args):
        found = real(*args)
        if not done:
            done.append(act())
        return found

    monkeypatch.setattr(world.copies, step, and_meanwhile)
    return done


def test_a_reset_refuses_when_a_commit_lands_while_it_fetches_and_keeps_that_commit(
        world, pr_worktree, pr_checkout, monkeypatch):
    seen = Sha(world.commit(pr_worktree, {"h": "x\n"}, "local work the page showed"))
    world.advance_base()
    landed = _meanwhile(monkeypatch, world, "_fetch", lambda: world.commit(
        pr_worktree, {"i": "made mid-fetch\n"}, "a commit nobody saw"))

    refused = pr_checkout.reset_to_origin(BRANCH, "main", seen)

    assert refused is not None and "moved" in refused
    assert world.head_of(pr_worktree) == landed[0]


def test_a_reset_refuses_when_the_worktree_switches_branch_while_origin_is_read(
        world, pr_worktree, pr_checkout, monkeypatch):
    seen = Sha(world.commit(pr_worktree, {"h": "x\n"}, "local work"))
    world.advance_base()

    def switch_to_a_hotfix():
        world.start_branch(pr_worktree, "hotfix")
        return world.commit(pr_worktree, {"hot": "fix\n"}, "unpushed hotfix")

    hotfix = _meanwhile(monkeypatch, world, "_origin_head", switch_to_a_hotfix)

    refused = pr_checkout.reset_to_origin(BRANCH, "main", seen)

    assert refused is not None
    assert world.head_of(pr_worktree) == hotfix[0]


def test_a_reset_refuses_a_worktree_whose_commits_are_only_unpushed(
        world, pr_worktree, pr_checkout):
    unpushed = Sha(world.commit(pr_worktree, {"h": "a day of work\n"}, "unpushed"))

    refused = pr_checkout.reset_to_origin(BRANCH, "main", None)

    assert refused is not None and "only unpushed" in refused
    assert pr_checkout.local_head() == unpushed


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

    assert git_checkout.reset_to_origin(BRANCH, "main", None) is None

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

    refused = git_checkout.reset_to_origin(BRANCH, "main", None)

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

    refused = git_checkout.reset_to_origin(BRANCH, "main", None)

    assert refused is not None and "notes.md" in refused
    assert (git_worktree / "notes.md").read_text() == "hours of notes\n"
