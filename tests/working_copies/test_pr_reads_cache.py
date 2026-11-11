import subprocess

import pytest

from github_orchestrator.domain import Sha
from tests.working_copies.support import BRANCH, THE_PR, GitWorld, build_origin


@pytest.fixture
def world(tmp_path, settings, git_template):
    git_template(build_origin)
    return GitWorld(tmp_path, settings)


@pytest.fixture
def pr_worktree(world):
    return world.copies.pr_worktree(world.repo_dir, THE_PR, None, None)


@pytest.fixture
def revisions(world, pr_worktree):
    return world.copies.checkout(THE_PR).revisions


def _verb(argv):
    words = iter(argv[1:])
    for word in words:
        if word in ("-C", "-c"):
            next(words)
        elif not word.startswith("-"):
            return word
    return None


@pytest.fixture
def spawned(monkeypatch):
    verbs: list[str | None] = []
    run = subprocess.run

    def counted(argv, *args, **kwargs):
        verbs.append(_verb(argv))
        return run(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", counted)
    return verbs


def _fetched(world):
    world.copies.fetch_pr_branch(world.repo_dir, THE_PR, BRANCH, "main")


def test_reading_the_diff_again_with_nothing_moved_runs_one_rev_parse(revisions, spawned):
    first = revisions.head_diff("main", local=False)
    spawned.clear()

    again = revisions.head_diff("main", local=False)

    assert (again, spawned) == (first, ["rev-parse"])


def test_the_line_counts_of_the_diff_just_read_run_no_git(revisions, spawned):
    diff = revisions.head_diff("main", local=False)
    [revisions.line_count(diff.head, file.path) for file in diff.files]
    spawned.clear()

    counts = [revisions.line_count(diff.head, file.path) for file in diff.files]

    assert (counts, spawned) == ([3], [])


def test_a_push_to_the_branch_diffs_it_again(world, revisions, spawned):
    revisions.head_diff("main", local=False)
    pushed = world.push_to_branch({"h": "x\n"}, "more work")
    _fetched(world)
    spawned.clear()

    diff = revisions.head_diff("main", local=False)

    assert (diff.head, [file.path for file in diff.files], spawned) == (
        Sha(pushed), ["g", "h"], ["rev-parse", "merge-base", "diff"])


def test_a_moved_base_diffs_the_branch_again(world, revisions, spawned):
    revisions.head_diff("main", local=False)
    world.advance_main({"m": "more\n"}, "more main")
    _fetched(world)
    spawned.clear()

    revisions.head_diff("main", local=False)

    assert spawned == ["rev-parse", "merge-base", "diff"]


def test_a_rebased_branch_diffs_against_its_new_merge_base(world, revisions):
    revisions.head_diff("main", local=False)
    base, head = world.advance_base()
    _fetched(world)

    diff = revisions.head_diff("main", local=False)

    assert (diff.base, diff.head) == (Sha(base), Sha(head))


def test_asking_the_merge_base_again_with_nothing_moved_runs_one_rev_parse(
        world, pr_worktree, revisions, spawned):
    head = Sha(world.head_of(pr_worktree))
    first = revisions.pr_base("main", head)
    spawned.clear()

    again = revisions.pr_base("main", head)

    assert (again, spawned) == (first, ["rev-parse"])


def test_a_moved_base_asks_for_the_merge_base_again(world, pr_worktree, revisions, spawned):
    head = Sha(world.head_of(pr_worktree))
    revisions.pr_base("main", head)
    world.advance_main({"m": "more\n"}, "more main")
    _fetched(world)
    spawned.clear()

    revisions.pr_base("main", head)

    assert spawned == ["rev-parse", "merge-base"]
