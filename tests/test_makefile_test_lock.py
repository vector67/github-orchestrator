import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until

REPO_ROOT = Path(__file__).resolve().parents[1]
STUBS = Path(__file__).parent / "stubs" / "test-lock"

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="needs make")


def _run(tmp_path, *, hold_until=None, exit_code=0, new_session=False, target="test-python"):
    env = {
        **os.environ,
        "PATH": f"{STUBS}:{os.environ['PATH']}",
        "STUB_LOG": str(tmp_path / "stub.log"),
        "STUB_EXIT": str(exit_code),
        "STUB_HOLD_UNTIL": str(hold_until) if hold_until else "",
    }
    env.pop("HOLDING_TEST_LOCK", None)
    return subprocess.Popen(
        ["make", "--no-print-directory", target, "WARM_WORKTREE=true",
         f"TEST_LOCK={tmp_path / 'make-test.lock'}"],
        cwd=REPO_ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, start_new_session=new_session)


def _suites_started(tmp_path):
    log = tmp_path / "stub.log"
    return len(log.read_text().splitlines()) if log.exists() else 0


@pytest.mark.parametrize("first_target", ["test-python", "measure-test-speed"])
def test_a_second_run_says_which_tree_it_waits_for_and_runs_once_the_first_ends(tmp_path, first_target):
    release = tmp_path / "release"
    first = _run(tmp_path, hold_until=release, target=first_target)
    assert until(lambda: _suites_started(tmp_path) == 1)

    second = _run(tmp_path)
    assert second.stdout is not None
    assert second.stdout.readline() == f"waiting for another make test, running in {REPO_ROOT}\n"
    assert _suites_started(tmp_path) == 1

    release.touch()
    assert first.wait(timeout=30) == 0
    assert second.wait(timeout=30) == 0
    assert _suites_started(tmp_path) == 2


def test_a_waiting_run_names_the_holders_tree_even_before_the_holder_has_started(tmp_path):
    holders_tree = (tmp_path / "other-tree").resolve()
    holders_tree.mkdir()
    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import fcntl, sys\n"
         f"lock = open({str(tmp_path / 'make-test.lock')!r}, 'w')\n"
         "fcntl.flock(lock, fcntl.LOCK_EX)\n"
         "print('held', flush=True)\n"
         "sys.stdin.readline()\n"],
        cwd=holders_tree, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    assert holder.stdout is not None and holder.stdin is not None
    assert holder.stdout.readline() == "held\n"

    waiting = _run(tmp_path)
    assert waiting.stdout is not None
    assert waiting.stdout.readline() == f"waiting for another make test, running in {holders_tree}\n"

    holder.stdin.close()
    holder.wait(timeout=10)
    assert waiting.wait(timeout=30) == 0


def test_an_interrupted_run_lets_the_next_one_start_at_once(tmp_path):
    interrupted = _run(tmp_path, hold_until=tmp_path / "never", new_session=True)
    assert until(lambda: _suites_started(tmp_path) == 1)
    os.killpg(interrupted.pid, signal.SIGINT)
    interrupted.wait(timeout=30)

    after, _ = _run(tmp_path).communicate(timeout=30)

    assert "waiting" not in after
    assert _suites_started(tmp_path) == 2


def test_a_failed_run_lets_the_next_one_start_at_once(tmp_path):
    assert _run(tmp_path, exit_code=1).wait(timeout=30) != 0

    after, _ = _run(tmp_path).communicate(timeout=30)

    assert "waiting" not in after
    assert _suites_started(tmp_path) == 2
