import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_makefile_checks import _logical_lines, _recipes
from tests.test_makefile_restart_all import STUBS

REPO_ROOT = Path(__file__).resolve().parents[1]

SERVED_APP = REPO_ROOT / "src/github_orchestrator/board_api/static/app"

needs_make = pytest.mark.skipif(shutil.which("make") is None, reason="needs make")


def _frontend(tmp_path, *, installed_after_lockfile):
    frontend = tmp_path / "frontend"
    (frontend / "dist").mkdir(parents=True)
    (frontend / "dist" / "index.html").write_text("built")
    lockfile = frontend / "package-lock.json"
    lockfile.write_text("{}")
    record = frontend / "node_modules" / ".package-lock.json"
    record.parent.mkdir()
    record.write_text("{}")
    os.utime(lockfile, (1_000, 1_000))
    installed = 2_000 if installed_after_lockfile else 500
    os.utime(record, (installed, installed))
    return frontend


def _npm_calls(tmp_path, target, frontend):
    log = tmp_path / "stub.log"
    log.touch()
    result = subprocess.run(
        ["make", target, f"FRONTEND_DIR={frontend}", f"SERVED_APP={tmp_path / 'served'}"],
        cwd=REPO_ROOT,
        env={**os.environ, "PATH": f"{STUBS}:{os.environ['PATH']}", "STUB_LOG": str(log)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return log.read_text().splitlines()


@needs_make
@pytest.mark.no_replay
@pytest.mark.parametrize("target", ["build_frontend", "frontend_deps"])
def test_an_install_as_new_as_the_lockfile_is_not_repeated(tmp_path, target):
    frontend = _frontend(tmp_path, installed_after_lockfile=True)

    assert "npm ci --silent" not in _npm_calls(tmp_path, target, frontend), (
        "npm ci deletes node_modules, so a needless one costs the install, "
        "the first-load scan of every native binary and the build's cache")


@needs_make
@pytest.mark.no_replay
@pytest.mark.parametrize("target", ["build_frontend", "frontend_deps"])
def test_a_lockfile_newer_than_the_install_installs_again(tmp_path, target):
    frontend = _frontend(tmp_path, installed_after_lockfile=False)

    assert "npm ci --silent" in _npm_calls(tmp_path, target, frontend), (
        "a merge that changes the lockfile has to reach node_modules before "
        "the next build, lint or test")


def test_building_the_frontend_refuses_a_machine_with_no_node():
    recipe = " ".join(_logical_lines(_recipes()["build_frontend"]))

    assert "command -v npm" in recipe, (
        "every recipe is shell and the machine may not have node; say so "
        "rather than failing inside npm")
