import subprocess
from unittest.mock import patch

import pytest

from tests.builders import a_pr

GIT_TIMEOUT = 60


def _completed(stdout="worktree /main\n", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


def _porcelain(path, branch):
    return f"worktree {path}\nHEAD deadbeef\nbranch refs/heads/{branch}\n\n"


def _fetch(copies, tmp_path, branch, fetched):
    listed = _completed(_porcelain(tmp_path, branch))
    with patch("subprocess.run", side_effect=[listed, fetched]) as run:
        copies.fetch_pr_branch(tmp_path / "repo", a_pr(7, "owner/name"), branch, None)
    return run


def test_the_head_fetch_is_bounded_and_never_prompts(copies, tmp_path):
    run = _fetch(copies, tmp_path, "PROJ-1 my-branch", _completed(stdout=""))

    assert len(run.call_args_list) == 2
    call = run.call_args_list[1]
    assert call.args[0] == ["git", "-C", str(tmp_path), "fetch", "origin", "PROJ-1 my-branch"]
    assert call.kwargs["timeout"] == GIT_TIMEOUT
    assert call.kwargs["stdin"] is subprocess.DEVNULL
    assert call.kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_a_failed_head_fetch_is_logged_in_gits_own_words(copies, tmp_path, caplog):
    failed = subprocess.CompletedProcess([], 128, stdout="", stderr="fatal: no such ref")

    _fetch(copies, tmp_path, "gone", failed)

    assert "Failed to fetch gone" in caplog.text
    assert "fatal: no such ref" in caplog.text


def test_a_timed_out_head_fetch_is_logged(copies, tmp_path, caplog):
    _fetch(copies, tmp_path, "slow", subprocess.TimeoutExpired(cmd="git", timeout=GIT_TIMEOUT))

    assert "timed out" in caplog.text


def test_a_listed_worktree_whose_directory_was_deleted_is_not_fetched(copies, tmp_path):
    branch = "dependabot/npm/widgets-minor-patch-1a2b3c4d5e"
    with patch("subprocess.run",
               return_value=_completed(_porcelain(tmp_path / "gone", branch))) as run:
        copies.fetch_pr_branch(tmp_path, a_pr(7, "owner/name"), branch, None)
    assert len(run.call_args_list) == 1


def test_a_listed_worktree_still_on_disk_is_fetched(copies, tmp_path):
    branch = "dependabot/npm/widgets-minor-patch-1a2b3c4d5e"
    live = tmp_path / "live"
    live.mkdir()
    with patch("subprocess.run", return_value=_completed(_porcelain(live, branch))) as run:
        copies.fetch_pr_branch(tmp_path, a_pr(7, "owner/name"), branch, None)
    assert run.call_args_list[1].args[0][:3] == ["git", "-C", str(live)]


@pytest.mark.parametrize("base_branch", ["--upload-pack=touch /tmp/pwned", "-x", "a b", ".."])
def test_a_base_branch_that_is_no_branch_name_is_never_fetched(copies, tmp_path, base_branch):
    listed = _completed(_porcelain(tmp_path, "feature"))
    with patch("subprocess.run", side_effect=[listed, _completed(stdout="")]) as run:
        copies.fetch_pr_branch(tmp_path / "repo", a_pr(7, "owner/name"), "feature", base_branch)

    assert [call.args[0][-1] for call in run.call_args_list[1:]] == ["feature"]
