import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="the reaper follows forks with macOS's kqueue")

CHECKOUT = Path(__file__).resolve().parent.parent

WATCHED = """
import subprocess, sys, time
from tests.reaping import reap_what_this_process_leaves, spare
reaper = reap_what_this_process_leaves()
mode = sys.argv[1]
if mode == "orphan":
    middle = subprocess.Popen([sys.executable, "-c",
        "import subprocess; print(subprocess.Popen(['sleep', '600'], start_new_session=True, stdout=subprocess.DEVNULL).pid)"],
        stdout=subprocess.PIPE, text=True)
    left = int(middle.communicate()[0])
else:
    left = subprocess.Popen(["sleep", "600"], start_new_session=True).pid
if mode == "spared":
    spare(left)
print(reaper, left, flush=True)
if mode == "killed":
    time.sleep(600)
"""


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _ps_lists(pid: int) -> bool:
    listed = subprocess.Popen(["ps", "-o", "stat=", "-p", str(pid)], stdout=subprocess.PIPE, text=True)
    printed, _ = listed.communicate(timeout=10)
    return bool(printed.strip()) and not printed.strip().startswith("Z")


def _watched(mode: str) -> tuple[subprocess.Popen[str], int, int]:
    watched = subprocess.Popen([sys.executable, "-c", WATCHED, mode], cwd=CHECKOUT,
                               env={**os.environ, "PYTHONPATH": str(CHECKOUT)},
                               stdout=subprocess.PIPE, text=True)
    assert watched.stdout is not None
    reaper, left = (int(pid) for pid in watched.stdout.readline().split())
    return watched, reaper, left


@pytest.fixture
def started():
    pids: list[int] = []
    yield pids
    for pid in pids:
        if _alive(pid):
            os.kill(pid, signal.SIGKILL)


def test_a_detached_process_ends_when_the_process_that_started_it_is_killed_outright(started):
    watched, reaper, left = _watched("killed")
    started += [reaper, left]

    watched.kill()
    watched.wait(timeout=10)

    assert until(lambda: not _ps_lists(left), 10)


def test_a_process_its_own_parent_orphaned_ends_when_the_watched_process_exits(started):
    watched, reaper, left = _watched("orphan")
    started += [reaper, left]

    assert watched.wait(timeout=30) == 0

    assert until(lambda: not _ps_lists(left), 10)


def test_a_spared_process_outlives_the_reaper(started):
    watched, reaper, left = _watched("spared")
    started += [reaper, left]
    watched.wait(timeout=30)

    assert until(lambda: not _ps_lists(reaper), 10)
    assert _ps_lists(left)
