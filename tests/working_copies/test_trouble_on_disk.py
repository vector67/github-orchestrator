import json
import subprocess
from pathlib import Path

import pytest

from tests.builders import a_pr
from tests.disk_layout import mismatched_file, worktree_conflict_file

THE_PR = a_pr(42, "owner/repo")
OTHER = a_pr(1, "owner/repo")
GRACE = 3600


def _git(worktree: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(worktree), *args], check=True, capture_output=True)


def _build_repo(root: Path) -> None:
    _git(root, "init", "-q", "-b", "a")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "f").write_text("1")
    _git(root, "add", "f")
    _git(root, "commit", "-q", "-m", "first")


@pytest.fixture
def worktree(git_template, tmp_path):
    git_template(_build_repo)
    return tmp_path


def _stored(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _report(copies, worktree, now):
    return copies.report_branch(THE_PR, str(worktree), "b", now=now, run_output_at=None)


def test_a_wrong_branch_is_kept_in_the_prs_mismatch_flag(copies, settings, worktree):
    _report(copies, worktree, 1000.0)

    assert json.loads(mismatched_file(settings.mismatched_dir, THE_PR).read_text()) == {
        "worktree": str(worktree), "actual_branch": "a", "expected_branch": "b",
        "since": 1000.0, "run_alive": False, "last_output_at": None,
        "release_requested": False,
    }


def test_a_mismatch_flag_already_on_disk_keeps_its_start_run_and_release(copies, settings):
    _stored(mismatched_file(settings.mismatched_dir, THE_PR), json.dumps({
        "worktree": "/wt", "actual_branch": "a", "expected_branch": "b", "since": 1000.0,
        "run_alive": True, "last_output_at": 1000.0 + GRACE - 10,
        "release_requested": False,
    }))

    verdict = copies.verdict(THE_PR, None, expected="b", window_open=True, now=1000.0 + GRACE, manager_running=True)

    assert (verdict.worktree, verdict.here, verdict.run_working) == ("/wt", "a", True)
    assert verdict.seconds_left == 290.0


@pytest.mark.parametrize("stored", [
    "{not json",
    '{"worktree": "/wt"}',
    '{"worktree": "/wt", "actual_branch": "a", "expected_branch": "b"}',
], ids=["corrupt", "missing fields", "written before since existed"])
def test_an_unreadable_mismatch_flag_counts_as_none(copies, settings, worktree, stored):
    _stored(mismatched_file(settings.mismatched_dir, THE_PR), stored)

    assert _report(copies, worktree, 2000.0).seconds_left == GRACE


def test_a_handed_off_mismatch_leaves_no_flag(copies, settings, worktree):
    _report(copies, worktree, 1000.0)

    copies.handed_off(THE_PR, "repo/#42-defunct")

    assert not mismatched_file(settings.mismatched_dir, THE_PR).exists()


def test_a_shared_worktree_is_kept_in_the_prs_conflict_flag(copies, settings, tmp_path):
    copies.verdict(THE_PR, tmp_path, others={OTHER: str(tmp_path)}, window_open=False, now=1000.0)

    assert json.loads(worktree_conflict_file(settings.worktree_conflicts_dir,
                                             THE_PR).read_text()) == {
        "worktree": str(tmp_path), "other_pr": 1, "since": 1000.0, "checks": 1,
    }


def test_a_conflict_flag_already_on_disk_keeps_counting(copies, settings, tmp_path):
    _stored(worktree_conflict_file(settings.worktree_conflicts_dir, THE_PR), json.dumps({
        "worktree": str(tmp_path), "other_pr": 1, "since": 900.0, "checks": 4,
    }))

    verdict = copies.verdict(THE_PR, tmp_path, others={OTHER: str(tmp_path)}, window_open=False, now=1000.0)

    assert verdict.seconds_left == 1100.0
    assert json.loads(worktree_conflict_file(settings.worktree_conflicts_dir,
                                             THE_PR).read_text())["checks"] == 5


@pytest.mark.parametrize("stored", ["{not json", '{"worktree": "/wt", "other_pr": 1}'],
                         ids=["corrupt", "missing its since"])
def test_an_unreadable_conflict_flag_counts_as_none(copies, settings, tmp_path, stored):
    _stored(worktree_conflict_file(settings.worktree_conflicts_dir, THE_PR), stored)

    verdict = copies.verdict(THE_PR, tmp_path, others={OTHER: str(tmp_path)}, window_open=False, now=2000.0)

    assert verdict.seconds_left == 1200.0


def test_a_worktree_no_longer_shared_leaves_no_flag(copies, settings, tmp_path):
    copies.verdict(THE_PR, tmp_path, others={OTHER: str(tmp_path)}, window_open=False, now=1000.0)

    copies.verdict(THE_PR, tmp_path, others={}, window_open=False, now=1060.0)

    assert not worktree_conflict_file(settings.worktree_conflicts_dir, THE_PR).exists()
