import logging
import subprocess
import threading
import time
from pathlib import Path

import pytest

from tests.builders import a_pr
from tests.working_copies.support import settle_progress

PROGRESS_TIMEOUT = 5
PROGRESS_TTL_SECONDS = 20


def _held(copies, worktree, base):
    held = copies.checkout(a_pr(1, "o/n")).workspace(
        "PRRT_1", base if worktree else None)
    if held.path is not None and not Path(held.path).is_symlink():
        Path(held.path).parent.mkdir(parents=True, exist_ok=True)
        Path(held.path).symlink_to(worktree)
    return held


def _progress(copies, worktree, base):
    held = _held(copies, worktree, base)
    held.progress()
    settle_progress()
    return held.progress()


@pytest.fixture
def stuck_git(monkeypatch):
    release = threading.Event()
    real = subprocess.run

    def _stuck(argv, **kwargs):
        if "--no-optional-locks" in argv:
            release.wait(timeout=10)
        return real(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _stuck)
    yield
    release.set()
    settle_progress()


def _counting_threads():
    return [alive for alive in threading.enumerate()
            if alive.name.startswith("thread progress")]


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True
    )


def _build_worktree(root):
    repo = root / "thread"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    (repo / "tracked.py").write_text("original\n")
    _git(repo, "add", "tracked.py")
    assert _git(repo, "commit", "-q", "-m", "base").returncode == 0


@pytest.fixture
def worktree(tmp_path, git_template):
    git_template(_build_worktree)
    return tmp_path / "thread"


def base_of(worktree):
    return _git(worktree, "rev-parse", "HEAD").stdout.strip()


def commit(worktree, name, body="x\n"):
    (worktree / name).write_text(body)
    _git(worktree, "add", name)
    assert _git(worktree, "commit", "-q", "-m", f"add {name}").returncode == 0


def test_two_commits_ahead_with_one_tracked_modification(copies, worktree):
    base = base_of(worktree)
    commit(worktree, "one.py")
    commit(worktree, "two.py")
    (worktree / "tracked.py").write_text("edited\n")

    assert _progress(copies, str(worktree), base) == "2 commits, 1 file changed"


def test_a_worktree_that_has_not_moved_says_nothing(copies, worktree):
    assert _progress(copies, str(worktree), base_of(worktree)) is None


def test_commits_with_a_clean_tree_reports_only_commits(copies, worktree):
    base = base_of(worktree)
    commit(worktree, "one.py")

    assert _progress(copies, str(worktree), base) == "1 commit"


def test_uncommitted_work_alone_reports_only_files(copies, worktree):
    base = base_of(worktree)
    (worktree / "tracked.py").write_text("edited\n")

    assert _progress(copies, str(worktree), base) == "1 file changed"


def test_singular_and_plural_agree_with_the_counts(copies, worktree):
    base = base_of(worktree)
    commit(worktree, "one.py")
    (worktree / "tracked.py").write_text("edited\n")
    (worktree / "one.py").write_text("edited\n")

    assert _progress(copies, str(worktree), base) == "1 commit, 2 files changed"


def test_untracked_files_are_not_counted_as_changes(copies, worktree):
    base = base_of(worktree)
    (worktree / "build-artefact.log").write_text("noise\n")
    (worktree / "junk").mkdir()
    (worktree / "junk" / "more").write_text("noise\n")

    assert _progress(copies, str(worktree), base) is None


def test_a_deleted_tracked_file_counts(copies, worktree):
    base = base_of(worktree)
    (worktree / "tracked.py").unlink()

    assert _progress(copies, str(worktree), base) == "1 file changed"


def test_no_worktree_or_no_base_needs_no_git(copies, worktree, monkeypatch):
    base = base_of(worktree)

    def _never(*args, **kwargs):
        raise AssertionError("git must not run without a worktree and a base")

    monkeypatch.setattr(subprocess, "run", _never)
    assert _progress(copies, None, base) is None
    assert _progress(copies, str(worktree), None) is None
    assert _progress(copies, "", "") is None


def test_a_base_that_is_not_a_commit_never_reaches_git(copies, worktree, monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run",
                        lambda argv, **kwargs: seen.append(argv))

    assert _progress(copies, str(worktree), "--output=/tmp/pwned") is None
    assert seen == []


def test_the_base_a_real_count_starts_from_ends_option_parsing(copies, worktree,
                                                                monkeypatch):
    base = base_of(worktree)
    seen = []
    real_run = subprocess.run

    def capture(argv, **kwargs):
        seen.append(argv)
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", capture)
    _progress(copies, str(worktree), base)

    counting = seen[0]
    assert "--end-of-options" in counting
    assert counting.index("--end-of-options") < counting.index(
        f"{base}..HEAD")


def test_a_timed_out_git_omits_the_line(copies, worktree, monkeypatch):
    base = base_of(worktree)

    def _timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, PROGRESS_TIMEOUT)

    monkeypatch.setattr(subprocess, "run", _timeout)
    assert _progress(copies, str(worktree), base) is None


def test_unparseable_output_omits_the_line(copies, worktree, monkeypatch):
    base = base_of(worktree)
    real = subprocess.run

    def _garbage(argv, **kwargs):
        if "rev-list" in argv:
            return subprocess.CompletedProcess(argv, 0, "not-a-number\n", "")
        return real(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _garbage)
    assert _progress(copies, str(worktree), base) is None


def test_repeat_calls_inside_the_ttl_do_not_re_run_git(copies, worktree, monkeypatch):
    base = base_of(worktree)
    commit(worktree, "one.py")
    calls = []
    real = subprocess.run

    def _counting(argv, **kwargs):
        calls.append(argv)
        return real(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", _counting)

    assert _progress(copies, str(worktree), base) == "1 commit"
    first = len(calls)
    assert first == 2
    assert _progress(copies, str(worktree), base) == "1 commit"
    assert _progress(copies, str(worktree), base) == "1 commit"
    assert len(calls) == first


def test_the_cache_expires_so_the_counts_keep_up(copies, worktree, monkeypatch):
    base = base_of(worktree)
    commit(worktree, "one.py")
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])

    assert _progress(copies, str(worktree), base) == "1 commit"

    commit(worktree, "two.py")
    now[0] += PROGRESS_TTL_SECONDS - 0.1
    assert _progress(copies, str(worktree), base) == "1 commit"

    now[0] += 0.2
    assert _progress(copies, str(worktree), base) == "2 commits"


def test_a_read_answers_without_waiting_for_git(copies, worktree, stuck_git):
    started = time.monotonic()

    assert _held(copies, str(worktree), base_of(worktree)).progress() is None
    assert time.monotonic() - started < 1


def test_overlapping_reads_start_one_count(copies, worktree, stuck_git):
    held = _held(copies, str(worktree), base_of(worktree))

    for _ in range(5):
        held.progress()

    assert len(_counting_threads()) == 1


def test_an_expired_line_is_answered_while_it_is_recounted(copies, worktree, monkeypatch):
    base = base_of(worktree)
    commit(worktree, "one.py")
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    assert _progress(copies, str(worktree), base) == "1 commit"

    commit(worktree, "two.py")
    now[0] += PROGRESS_TTL_SECONDS + 0.1

    assert _held(copies, str(worktree), base).progress() == "1 commit"
    settle_progress()


def test_a_new_base_is_not_answered_from_the_old_base_s_cache(copies, worktree):
    base = base_of(worktree)
    commit(worktree, "one.py")
    assert _progress(copies, str(worktree), base) == "1 commit"

    assert _progress(copies, str(worktree), base_of(worktree)) is None


def test_a_worktree_that_is_gone_is_not_worth_a_warning(copies, tmp_path, monkeypatch, caplog):
    def _never(*args, **kwargs):
        raise AssertionError("git must not run against a worktree that is gone")

    monkeypatch.setattr(subprocess, "run", _never)
    with caplog.at_level(logging.DEBUG):
        assert _progress(copies, str(tmp_path / "removed"), "a" * 40) is None
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


def test_a_worktree_that_exists_but_errors_still_warns(copies, worktree, monkeypatch, caplog):
    with caplog.at_level(logging.DEBUG):
        assert _progress(copies, str(worktree), "0" * 40) is None
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] != []
