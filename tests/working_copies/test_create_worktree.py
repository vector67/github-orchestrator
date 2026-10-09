import subprocess
from pathlib import Path

import pytest

from github_orchestrator.desktop import Badge
from github_orchestrator.github import PullRequestState
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.notifications.fake import FakeNotifications
from tests.builders import a_pr
from tests.working_copies.support import branch_at, clone_of, real_working_copies

REPO_ROOT = Path(__file__).resolve().parents[2]

REPO = "owner/name"
PR = 83
THE_PR = a_pr(PR, REPO)
NEW_WORKTREE_TIMEOUT = 300


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _build_clones(root):
    origin = root / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)

    seed = root / "seed"
    subprocess.run(["git", "clone", "-q", str(origin), str(seed)], check=True)
    _git(seed, "config", "user.email", "t@example.com")
    _git(seed, "config", "user.name", "T")
    (seed / "f").write_text("1")
    _git(seed, "add", "f")
    _git(seed, "commit", "-q", "-m", "first")
    _git(seed, "push", "-q", "origin", "main")
    for branch in ("feature-x", "feature-y"):
        _git(seed, "checkout", "-q", "-b", branch)
        _git(seed, "push", "-q", "origin", branch)
    _git(seed, "checkout", "-q", "main")

    work = root / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "T")
    for branch in ("feature-x", "feature-y"):
        _git(work, "branch", branch, f"origin/{branch}")


@pytest.fixture
def repo(tmp_path, git_template):
    git_template(_build_clones)
    return tmp_path / "work"


def _create(settings, repo, branch, command="", notifications=None):
    github = FakeGitHub()
    github.add_pr(THE_PR, PullRequestState(branch=branch))
    copies = real_working_copies(settings, github, notifications or FakeNotifications(),
                                 clone_of(THE_PR, repo, command))
    return copies.pr_worktree(repo, THE_PR, None, None)


def _occupy(path):
    path.mkdir()
    (path / "someone-elses-file").write_text("x")


def _spy_on_subprocesses(monkeypatch):
    ran = []
    real = subprocess.run

    def spy(argv, *args, **kwargs):
        ran.append((list(argv), kwargs))
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    return ran


def test_a_taken_directory_name_falls_back_to_the_pr_suffix(repo, settings):
    squatter = repo.parent / "feature-x"
    _occupy(squatter)

    assert _create(settings, repo, "feature-x") == repo.parent / "feature-x-pr83"
    assert (squatter / "someone-elses-file").read_text() == "x"


def test_falls_back_to_a_number_when_the_pr_suffix_is_also_taken(repo, settings):
    for name in ("feature-x", "feature-x-pr83"):
        _occupy(repo.parent / name)

    assert _create(settings, repo, "feature-x") == repo.parent / "feature-x-1"


def test_falls_back_again_when_the_first_number_is_also_taken(repo, settings):
    for name in ("feature-x", "feature-x-pr83", "feature-x-1"):
        _occupy(repo.parent / name)

    assert _create(settings, repo, "feature-x") == repo.parent / "feature-x-2"


def test_an_empty_directory_is_not_a_collision(repo, settings):
    (repo.parent / "feature-x").mkdir()

    assert _create(settings, repo, "feature-x") == repo.parent / "feature-x"


def test_fails_when_the_branch_is_already_checked_out_elsewhere(repo, settings, caplog):
    first = _create(settings, repo, "feature-x")

    assert _create(settings, repo, "feature-x") is None

    assert "Failed to create worktree for PR #83" in caplog.text
    assert "feature-x" in caplog.text
    assert first == repo.parent / "feature-x"
    assert not (repo.parent / "feature-x-pr83").exists()


def test_a_branch_the_remote_does_not_have_fails_with_gits_reason(repo, settings, caplog):
    assert _create(settings, repo, "no-such-branch") is None

    assert "no-such-branch" in caplog.text
    assert "fatal:" in caplog.text
    assert not (repo.parent / "no-such-branch").exists()


def test_the_new_worktree_command_initialises_the_worktree_it_just_cut(repo, settings):
    created = _create(settings, repo, "feature-x", command=(
        'printf %s "$GITHUB_ORCHESTRATOR_SOURCE_REPO" > initialised'))

    assert (created / "initialised").read_text() == str(repo)


def test_a_failing_new_worktree_command_is_reported_but_keeps_the_worktree(
    repo, settings, caplog, notifications,
):
    created = _create(settings, repo, "feature-x", command="echo boom >&2; exit 3",
                      notifications=notifications)

    assert created == repo.parent / "feature-x"
    assert created.is_dir()
    assert "boom" in caplog.text
    assert [(n.badge, n.title, n.body) for n in notifications.posted] == [
        (Badge.FAILED, "Worktree init failed",
         "new_worktree_command exited 3 in feature-x; the worktree is usable but uninitialised")]


def test_a_timed_out_new_worktree_command_still_reports_what_it_printed(
    repo, settings, caplog, notifications, monkeypatch,
):
    real = subprocess.run

    def slow_hook(argv, *args, **kwargs):
        if argv[0] == "sh":
            raise subprocess.TimeoutExpired(cmd="sh", timeout=NEW_WORKTREE_TIMEOUT,
                                            stderr=b"error: no such package\n")
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", slow_hook)

    created = _create(settings, repo, "feature-x", command="uv sync", notifications=notifications)

    assert created.is_dir()

    assert "timed out" in caplog.text
    assert "error: no such package" in caplog.text
    assert repr(b"error: no such package\n") not in caplog.text
    assert [(n.badge, n.title, n.body) for n in notifications.posted] == [
        (Badge.FAILED, "Worktree init timed out",
         "new_worktree_command gave up after 300s in feature-x; the worktree is usable but "
         "uninitialised")]


def test_nothing_is_run_when_no_new_worktree_command_is_configured(repo, settings,
                                                                  monkeypatch):
    ran = _spy_on_subprocesses(monkeypatch)

    _create(settings, repo, "feature-x")

    assert not any(argv[0] == "sh" for argv, _ in ran)


def test_the_new_worktree_command_does_not_run_when_the_worktree_was_not_cut(
    repo, settings, monkeypatch,
):
    ran = _spy_on_subprocesses(monkeypatch)

    assert _create(settings, repo, "no-such-branch", command="touch initialised") is None

    assert not any(argv[0] == "sh" for argv, _ in ran)


def test_nothing_is_added_when_the_fetch_fails(
    repo, settings, monkeypatch,
):
    ran = []
    failed_fetch = subprocess.CompletedProcess([], 1, stdout="", stderr="fatal: nope")

    def refuse(argv, *args, **kwargs):
        ran.append((argv, kwargs))
        return failed_fetch

    monkeypatch.setattr(subprocess, "run", refuse)

    assert _create(settings, repo, "feature-x") is None

    [(argv, kwargs)] = ran
    assert argv[:4] == ["git", "-C", str(repo), "fetch"]
    assert not (repo.parent / "feature-x").exists()


def test_a_main_checkout_that_will_not_leave_the_prs_branch_blocks_the_worktree(
    repo, settings, notifications,
):
    _git(repo, "checkout", "-q", "feature-x")
    (repo / "g").write_text("1")
    _git(repo, "add", "g")
    _git(repo, "commit", "-q", "-m", "g")
    (repo / "g").write_text("2")
    github = FakeGitHub()
    github.add_pr(THE_PR, PullRequestState(branch="feature-x"))
    copies = real_working_copies(settings, github, notifications, clone_of(THE_PR, repo))

    assert copies.pr_worktree(repo, THE_PR, "feature-x", None) is None

    assert [(n.badge, n.title, n.body) for n in notifications.posted] == [
        (Badge.FAILED, "PR #83 blocked",
         "Cannot create worktree because branch already checked out!")]
    assert branch_at(repo) == "feature-x"
