import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


STUBS = Path(__file__).parent / "stubs" / "restart-all"

pytestmark = [
    pytest.mark.no_replay,
    pytest.mark.skipif(shutil.which("make") is None, reason="needs make"),
]


def _make(tmp_path, target):
    log = tmp_path / "stub.log"
    frontend = tmp_path / "frontend"
    (frontend / "dist").mkdir(parents=True)
    (frontend / "dist" / "index.html").write_text("built")

    result = subprocess.run(
        [
            "make",
            target,
            f"FRONTEND_DIR={frontend}",
            f"SERVED_APP={tmp_path / 'served'}",
            f"VENV_PYTHON={STUBS / 'python'}",
            f"RESTART_LOCK={tmp_path / 'restart-all.lock'}",
        ],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "PATH": f"{STUBS}:{os.environ['PATH']}",
            "STUB_LOG": str(log),
        },
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    return log.read_text().splitlines()


def test_restart_all_syncs_and_builds_the_checkout_then_runs_the_cli_restart_all(tmp_path):
    assert _make(tmp_path, "restart-all") == [
        "uv sync",
        "npm ci --silent",
        "npm run build --silent",
        "python -m github_orchestrator.cli restart-all"]


def test_a_second_restart_all_waits_for_the_first_to_restart_before_it_builds(tmp_path):
    lock = tmp_path / "restart-all.lock"
    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import fcntl, sys\n"
         f"lock = open({str(lock)!r}, 'w')\n"
         "fcntl.flock(lock, fcntl.LOCK_EX)\n"
         "print('held', flush=True)\n"
         "sys.stdin.readline()\n"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    assert holder.stdout is not None and holder.stdin is not None
    assert holder.stdout.readline() == "held\n"
    second = subprocess.Popen(
        ["make", "restart-all", f"FRONTEND_DIR={tmp_path / 'frontend'}",
         f"SERVED_APP={tmp_path / 'served'}", f"VENV_PYTHON={STUBS / 'python'}",
         f"RESTART_LOCK={lock}"],
        cwd=REPO_ROOT, env={**os.environ, "HOME": str(tmp_path),
                            "PATH": f"{STUBS}:{os.environ['PATH']}",
                            "STUB_LOG": str(tmp_path / "stub.log")},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (tmp_path / "frontend" / "dist").mkdir(parents=True)
    (tmp_path / "frontend" / "dist" / "index.html").write_text("built")
    try:
        second.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    assert second.returncode is None
    assert not (tmp_path / "stub.log").exists()

    holder.stdin.close()
    holder.wait(timeout=10)

    assert second.wait(timeout=60) == 0
    assert (tmp_path / "stub.log").read_text().splitlines()[0] == "uv sync"


def test_the_rebuild_serves_the_build_it_just_made(tmp_path):
    _make(tmp_path, "build_frontend")

    assert (tmp_path / "served" / "index.html").read_text() == "built"
