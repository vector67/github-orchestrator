import threading
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


KEY = "PRRT_kwDOlock"


def _paused(monkeypatch, world, step):
    real = getattr(world.copies, step)
    inside, go_on = threading.Event(), threading.Event()

    def pausing(*args):
        inside.set()
        assert go_on.wait(timeout=10)
        return real(*args)

    monkeypatch.setattr(world.copies, step, pausing)
    return inside, go_on


def _in_a_thread(act):
    done = []
    thread = threading.Thread(target=lambda: done.append(act()))
    thread.start()
    return thread, done


@pytest.mark.parametrize("step", ["_pick", "_push"])
def test_a_reset_waits_for_a_pick_or_push_under_way_and_then_refuses_the_head_it_moved(
        world, pr_worktree, pr_checkout, monkeypatch, step):
    seen = Sha(world.commit(pr_worktree, {"h": "x\n"}, "local work"))
    world.advance_base()
    cut = pr_checkout.workspace(KEY, None).ensure().workspace
    tip = Sha(world.commit(cut.path, {"g": "one\n2\nthree\n"}, "fix the middle"))
    if step == "_push":
        assert cut.pick(tip).landed_sha is not None
    inside, go_on = _paused(monkeypatch, world, step)
    landing, landed = _in_a_thread(
        (lambda: cut.pick(tip)) if step == "_pick" else pr_checkout.push)
    assert inside.wait(timeout=10)

    resetting, reset = _in_a_thread(lambda: pr_checkout.reset_to_origin(BRANCH, "main", seen))
    resetting.join(timeout=0.2)
    waited = resetting.is_alive()
    go_on.set()
    landing.join(timeout=10)
    resetting.join(timeout=10)

    assert waited
    assert landed and reset and reset[0] is not None
    assert pr_checkout.local_head() != seen


def test_an_unpick_keeps_a_commit_made_after_it_checked_the_worktree_was_clean(
        world, pr_worktree, pr_checkout, monkeypatch):
    base = Sha(world.head_of(pr_worktree))
    landed = Sha(world.commit(pr_worktree, {"fix": "fix\n"}, "the fix"))
    later = _meanwhile(monkeypatch, world, "_is_clean", lambda: world.commit(
        pr_worktree, {"later": "later\n"}, "a commit after the fix"))

    refused = pr_checkout.unpick(base, landed)

    assert refused is not None
    assert world.head_of(pr_worktree) == later[0]
