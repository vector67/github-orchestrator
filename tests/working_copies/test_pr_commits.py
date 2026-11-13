from pathlib import Path

import pytest

from github_orchestrator.domain import Sha
from tests.working_copies.support import THE_PR, GitWorld, build_origin, git

ODD_SUBJECTS = [
    "form\x0cfeed in the subject",
    "carriage\rreturn in the subject",
    "unit\x1fseparator in the subject",
    "file\x1cseparator in the subject",
    "group\x1dseparator in the subject",
    "record\x1eseparator in the subject",
    "line\u2028separator in the subject",
    "next\u0085line in the subject",
]


@pytest.fixture
def world(tmp_path, settings, git_template):
    git_template(build_origin)
    return GitWorld(tmp_path, settings)


@pytest.fixture
def pr_worktree(world):
    return world.copies.pr_worktree(world.repo_dir, THE_PR, None, None)


@pytest.fixture
def pr_checkout(world, pr_worktree):
    return world.copies.checkout(THE_PR)


def _commit_as(worktree: Path, author: str, message: str) -> Sha:
    (worktree / "h").write_text(message)
    git(worktree, "add", "h")
    git(worktree, "-c", f"user.name={author}", "commit", "-q", "-m", message)
    return Sha(git(worktree, "rev-parse", "HEAD"))


@pytest.mark.parametrize("subject", ODD_SUBJECTS)
def test_a_pr_commit_whose_subject_holds_a_line_break_python_knows_is_listed_whole(
        pr_worktree, pr_checkout, subject):
    head = _commit_as(Path(pr_worktree), "T", subject)

    history = pr_checkout.revisions.pr_commits("main", head)

    assert history is not None
    assert [(commit.subject, commit.author) for commit in history.commits] == [
        ("feature work", "T"), (subject, "T")]


def test_a_pr_commit_whose_author_holds_a_unit_separator_is_listed_whole(
        pr_worktree, pr_checkout):
    head = _commit_as(Path(pr_worktree), "Octo\x1fCat", "odd author")

    history = pr_checkout.revisions.pr_commits("main", head)

    assert history is not None
    assert [(commit.sha, commit.subject, commit.author)
            for commit in history.commits][-1] == (head, "odd author", "Octo\x1fCat")


def test_a_main_commit_whose_subject_holds_a_carriage_return_is_listed_whole(
        world, pr_worktree, pr_checkout):
    head = Sha(world.head_of(pr_worktree))
    tip = Sha(world.advance_main({"m": "more\n"}, "more\rmain"))
    assert pr_checkout.fetch("main") is None

    history = pr_checkout.revisions.pr_commits("main", head)

    assert history is not None
    assert [(commit.sha, commit.subject) for commit in history.base_commits] == [
        (tip, "more\rmain")]
