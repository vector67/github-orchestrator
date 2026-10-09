import subprocess
from pathlib import Path

import pytest

from tests.builders import a_pr

PUSHED = "a" * 40
OURS = "b" * 40
NEWER = "c" * 40


def _lines(count):
    return "".join(f"{index:07x} commit {index}\n" for index in range(count))


def _counted(copies, worktree, sha):
    commits = copies.commits_since(worktree, sha)
    return None if commits is None else len(commits)


class Git:
    def __init__(self, answers):
        self.answers = answers
        self.asked: list[str] = []

    def __call__(self, argv, *args, **kwargs):
        verb = argv[3]
        self.asked.append(verb)
        answer = self.answers[verb]
        if answer is None:
            raise subprocess.CalledProcessError(128, argv, "", "fatal: bad revision")
        return subprocess.CompletedProcess(argv, 0, answer, "")


@pytest.fixture
def git(monkeypatch):
    fake = Git({"rev-list": _lines(2), "rev-parse": "feat\n"})
    monkeypatch.setattr(subprocess, "run", fake)
    return fake


def _linked_worktree(root: Path) -> tuple[Path, Path]:
    common = root / "repo" / ".git"
    gitdir = common / "worktrees" / "wt"
    gitdir.mkdir(parents=True)
    (gitdir / "commondir").write_text("../..\n")
    (gitdir / "HEAD").write_text("ref: refs/heads/feat\n")
    (common / "refs" / "heads").mkdir(parents=True)
    (common / "refs" / "heads" / "feat").write_text(f"{OURS}\n")
    worktree = root / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {gitdir}\n")
    return worktree, common


def _branch(copies, worktree):
    verdict = copies.report_branch(a_pr(1, "o/n"), str(worktree), "elsewhere", now=1.0,
                                   run_output_at=None)
    return None if verdict is None else verdict.here


def test_counting_twice_with_nothing_changed_runs_git_once(copies, tmp_path, git):
    worktree, _ = _linked_worktree(tmp_path)
    assert _counted(copies, worktree, PUSHED) == 2
    assert _counted(copies, worktree, PUSHED) == 2
    assert git.asked == ["rev-list"]


def test_a_new_commit_on_the_branch_is_counted_again(copies, tmp_path, git):
    worktree, common = _linked_worktree(tmp_path)
    _counted(copies, worktree, PUSHED)
    (common / "refs" / "heads" / "feat").write_text(f"{NEWER}\n")
    git.answers["rev-list"] = _lines(3)
    assert _counted(copies, worktree, PUSHED) == 3


def test_a_push_is_counted_again(copies, tmp_path, git):
    worktree, _ = _linked_worktree(tmp_path)
    _counted(copies, worktree, PUSHED)
    git.answers["rev-list"] = _lines(0)
    assert _counted(copies, worktree, OURS) == 0


def test_a_checkout_is_seen_by_both_questions(copies, tmp_path, git):
    worktree, common = _linked_worktree(tmp_path)
    assert (_branch(copies, worktree), _counted(copies, worktree, PUSHED)) == ("feat", 2)
    (common / "refs" / "heads" / "other").write_text(f"{OURS}\n")
    (common / "worktrees" / "wt" / "HEAD").write_text("ref: refs/heads/other\n")
    git.answers.update({"rev-parse": "other\n", "rev-list": _lines(5)})
    assert (_branch(copies, worktree), _counted(copies, worktree, PUSHED)) == ("other", 5)


def test_the_branch_is_asked_once_while_head_stands_still(copies, tmp_path, git):
    worktree, _ = _linked_worktree(tmp_path)
    _branch(copies, worktree)
    _branch(copies, worktree)
    assert git.asked == ["rev-parse"]


def test_a_packed_ref_is_followed(copies, tmp_path, git):
    worktree, common = _linked_worktree(tmp_path)
    (common / "refs" / "heads" / "feat").unlink()
    (common / "packed-refs").write_text(f"# pack-refs with: peeled\n{OURS} refs/heads/feat\n")
    _counted(copies, worktree, PUSHED)
    _counted(copies, worktree, PUSHED)
    (common / "packed-refs").write_text(f"# pack-refs with: peeled\n{NEWER} refs/heads/feat\n")
    git.answers["rev-list"] = _lines(3)
    assert _counted(copies, worktree, PUSHED) == 3
    assert git.asked == ["rev-list", "rev-list"]


def test_a_detached_head_is_counted_again_when_it_moves(copies, tmp_path, git):
    worktree, common = _linked_worktree(tmp_path)
    (common / "worktrees" / "wt" / "HEAD").write_text(f"{OURS}\n")
    _counted(copies, worktree, PUSHED)
    _counted(copies, worktree, PUSHED)
    (common / "worktrees" / "wt" / "HEAD").write_text(f"{NEWER}\n")
    git.answers["rev-list"] = _lines(3)
    assert _counted(copies, worktree, PUSHED) == 3
    assert git.asked == ["rev-list", "rev-list"]


def test_a_main_checkout_is_watched_through_its_git_directory(copies, tmp_path, git):
    (tmp_path / ".git" / "refs" / "heads").mkdir(parents=True)
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/feat\n")
    (tmp_path / ".git" / "refs" / "heads" / "feat").write_text(f"{OURS}\n")
    _counted(copies, tmp_path, PUSHED)
    _counted(copies, tmp_path, PUSHED)
    (tmp_path / ".git" / "refs" / "heads" / "feat").write_text(f"{NEWER}\n")
    _counted(copies, tmp_path, PUSHED)
    assert git.asked == ["rev-list", "rev-list"]


def test_a_count_git_refused_is_asked_again(copies, tmp_path, git):
    worktree, _ = _linked_worktree(tmp_path)
    git.answers["rev-list"] = None
    assert _counted(copies, worktree, PUSHED) is None
    git.answers["rev-list"] = _lines(2)
    assert _counted(copies, worktree, PUSHED) == 2


def test_a_worktree_whose_head_cannot_be_read_is_asked_every_time(copies, tmp_path, git):
    _counted(copies, tmp_path, PUSHED)
    _counted(copies, tmp_path, PUSHED)
    assert git.asked == ["rev-list", "rev-list"]


def test_the_commits_since_a_sha_are_its_one_line_summaries_newest_first(copies, tmp_path, git):
    worktree, _ = _linked_worktree(tmp_path)
    git.answers["rev-list"] = "c0ffee1 Second change\nbadf00d First change\n"
    assert copies.commits_since(worktree, PUSHED) == ("c0ffee1 Second change", "badf00d First change")
