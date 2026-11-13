import subprocess
from pathlib import Path

import pytest

from github_orchestrator.domain import Sha, fork_pr_branch
from github_orchestrator.github import PullRequestState
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.notifications.fake import FakeNotifications
from tests.builders import a_pr
from tests.working_copies.support import clone_of, real_working_copies

REPO = "owner/name"
PR = 83
THE_PR = a_pr(PR, REPO)
FORK_BRANCH = fork_pr_branch(THE_PR)
FORK_REFUSAL = ("owner/name#83 comes from another repository, so nothing is pushed to it "
                "from here: push from the fork")


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _commit(seed, text, message):
    (seed / "f").write_text(text)
    _git(seed, "commit", "-q", "-am", message)


def _build_a_fork_pr(root):
    origin = root / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seed = root / "seed"
    subprocess.run(["git", "clone", "-q", str(origin), str(seed)], check=True,
                   capture_output=True)
    _git(seed, "config", "user.email", "t@example.com")
    _git(seed, "config", "user.name", "T")
    (seed / "f").write_text("base")
    _git(seed, "add", "f")
    _git(seed, "commit", "-q", "-m", "base")
    _git(seed, "push", "-q", "origin", "main")
    _git(seed, "checkout", "-q", "-b", "origins-own-patch-1")
    _commit(seed, "origin's own patch-1", "origin's patch-1")
    _git(seed, "push", "-q", "origin", "origins-own-patch-1:patch-1")
    _git(seed, "checkout", "-q", "-b", "the-fork", "main")
    _commit(seed, "the fork's change", "fork change")
    _git(seed, "push", "-q", "origin", f"the-fork:refs/pull/{PR}/head")
    work = root / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True,
                   capture_output=True)
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "T")


@pytest.fixture
def fork(tmp_path, git_template):
    git_template(_build_a_fork_pr)
    return tmp_path


def _copies(settings, work, notifications=None):
    github = FakeGitHub()
    github.add_pr(THE_PR, PullRequestState(branch=FORK_BRANCH, base_branch="main"))
    return real_working_copies(settings, github, notifications or FakeNotifications(),
                               clone_of(THE_PR, work))


def test_a_fork_pr_is_cut_from_its_pull_head_even_where_origin_has_a_branch_of_its_name(
        fork, settings):
    created = _copies(settings, fork / "work").pr_worktree(fork / "work", THE_PR,
                                                           FORK_BRANCH, "main")

    assert created == fork / FORK_BRANCH
    assert (created / "f").read_text() == "the fork's change"


def test_a_push_to_a_fork_pr_reaches_its_worktree_on_the_next_fetch(fork, settings):
    notifications = FakeNotifications()
    copies = _copies(settings, fork / "work", notifications)
    created = copies.pr_worktree(fork / "work", THE_PR, FORK_BRANCH, "main")
    _git(fork / "seed", "checkout", "-q", "the-fork")
    _commit(fork / "seed", "the fork's second push", "second")
    _git(fork / "seed", "push", "-q", "-f", "origin", f"the-fork:refs/pull/{PR}/head")

    copies.pr_worktree(fork / "work", THE_PR, FORK_BRANCH, "main", fetch=True)

    assert _git(created, "show", f"refs/remotes/origin/{FORK_BRANCH}:f") == (
        "the fork's second push")
    assert notifications.posted == []


def _origin_branches(fork):
    return _git(fork / "origin.git", "for-each-ref", "--format=%(refname)", "refs/heads")


def test_a_fork_prs_worktree_is_never_pushed_to_origin(fork, settings):
    copies = _copies(settings, fork / "work")
    created = copies.pr_worktree(fork / "work", THE_PR, FORK_BRANCH, "main")
    _commit(created, "a fix of mine", "fix")

    refused = copies.checkout(THE_PR).push()

    assert refused == FORK_REFUSAL
    assert _origin_branches(fork) == "refs/heads/main\nrefs/heads/patch-1"


def test_a_plain_git_push_in_a_fork_prs_worktree_names_no_branch_on_origin(fork, settings):
    created = _copies(settings, fork / "work").pr_worktree(fork / "work", THE_PR,
                                                           FORK_BRANCH, "main")
    _commit(created, "a fix of mine", "fix")

    pushed = subprocess.run(["git", "-C", str(created), "push"], capture_output=True)

    assert pushed.returncode != 0
    assert _origin_branches(fork) == "refs/heads/main\nrefs/heads/patch-1"


def test_a_fix_is_never_landed_on_a_fork_prs_worktree(fork, settings):
    copies = _copies(settings, fork / "work")
    created = copies.pr_worktree(fork / "work", THE_PR, FORK_BRANCH, "main")
    head = _git(created, "rev-parse", "HEAD")
    cut = copies.checkout(THE_PR).workspace("PRRT_101", None).ensure().workspace
    _commit(Path(cut.path), "a fix of mine", "fix")

    picked = cut.pick(Sha(_git(cut.path, "rev-parse", "HEAD")))

    assert picked.refusal == FORK_REFUSAL
    assert _git(created, "rev-parse", "HEAD") == head
