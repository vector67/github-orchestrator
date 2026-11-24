import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STUBS = Path(__file__).parent / "stubs" / "warm_worktree"

needs_make = pytest.mark.skipif(shutil.which("make") is None, reason="needs make")
replays = pytest.mark.replays_while_unchanged(
    "Makefile", "tools/warm_worktree.sh", "tests/stubs/warm_worktree")


def _checkout(root, *, lockfile="{}"):
    frontend = root / "frontend"
    (frontend / "app").mkdir(parents=True)
    (frontend / "app" / "app.ts").write_text("export {};\n")
    (frontend / "package-lock.json").write_text(lockfile)
    return frontend


def _installed(frontend):
    record = frontend / "node_modules" / ".package-lock.json"
    record.parent.mkdir()
    record.write_text("{}")
    os.utime(frontend / "package-lock.json", (1_000, 1_000))
    (frontend / "node_modules" / "left-pad.js").write_text("module.exports = 1;\n")
    testem = frontend / "node_modules" / ".bin" / "testem"
    testem.parent.mkdir()
    testem.write_text("#!/bin/sh\n")
    testem.chmod(0o755)


def _make(tmp_path, target, frontend, main):
    log = tmp_path / "stub.log"
    log.touch()
    result = subprocess.run(
        ["make", target, f"FRONTEND_DIR={frontend}", f"MAIN_CHECKOUT={main}",
         f"SHARED_CACHE={tmp_path / 'shared'}"],
        cwd=REPO_ROOT,
        env={**os.environ, "PATH": f"{STUBS}:{os.environ['PATH']}", "STUB_LOG": str(log)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    calls = log.read_text().splitlines()
    log.write_text("")
    return calls


@needs_make
@replays
def test_a_fresh_worktree_clones_the_main_checkouts_packages_when_the_lockfiles_match(tmp_path):
    main = tmp_path / "main"
    _installed(_checkout(main))
    tree = _checkout(tmp_path / "tree")

    calls = _make(tmp_path, "frontend_deps", tree, main)

    assert "npm ci --silent" not in calls, (
        "the main checkout already installed this lockfile; a copy-on-write "
        "clone takes a second where npm ci takes a minute under load")
    assert (tree / "node_modules" / "left-pad.js").exists()


@needs_make
@replays
def test_cloned_packages_count_as_installed_on_the_next_run(tmp_path):
    main = tmp_path / "main"
    _installed(_checkout(main))
    os.utime(main / "frontend" / "node_modules" / ".package-lock.json", (2_000, 2_000))
    tree = _checkout(tmp_path / "tree")
    os.utime(tree / "package-lock.json", (3_000, 3_000))
    _make(tmp_path, "frontend_deps", tree, main)

    calls = _make(tmp_path, "frontend_deps", tree, main)

    assert "npm ci --silent" not in calls, (
        "a clone keeps the main checkout's install time, older than this "
        "worktree's freshly checked-out lockfile, so the next check reinstalls")


@needs_make
@replays
def test_a_fresh_worktree_installs_when_its_lockfile_differs_from_the_main_checkouts(tmp_path):
    main = tmp_path / "main"
    _installed(_checkout(main))
    tree = _checkout(tmp_path / "tree", lockfile='{"changed": true}')

    calls = _make(tmp_path, "frontend_deps", tree, main)

    assert "npm ci --silent" in calls, (
        "the main checkout's packages answer a different lockfile")


@needs_make
@replays
def test_a_test_build_of_the_same_sources_is_reused_by_the_next_worktree(tmp_path):
    first = _checkout(tmp_path / "first")
    _installed(first)
    second = _checkout(tmp_path / "second")
    _installed(second)
    _make(tmp_path, "test-frontend", first, tmp_path / "main")

    calls = _make(tmp_path, "test-frontend", second, tmp_path / "main")

    assert not any(call.startswith("npx vite build") for call in calls), (
        "another worktree already built these exact sources")
    assert (second / "dist-tests" / "index.html").read_text() == "built\n"


@needs_make
@replays
def test_a_test_build_of_other_sources_is_not_reused(tmp_path):
    first = _checkout(tmp_path / "first")
    _installed(first)
    second = _checkout(tmp_path / "second")
    _installed(second)
    (second / "app" / "app.ts").write_text("export const changed = true;\n")
    _make(tmp_path, "test-frontend", first, tmp_path / "main")

    calls = _make(tmp_path, "test-frontend", second, tmp_path / "main")

    assert any(call.startswith("npx vite build") for call in calls)


@replays
def test_a_worktree_without_test_durations_starts_from_the_main_checkouts(tmp_path):
    seconds = Path(".pytest_cache/v/forked_run/seconds")
    main, tree = tmp_path / "main", tmp_path / "tree"
    (main / seconds).parent.mkdir(parents=True)
    (main / seconds).write_text('{"tests/test_a.py::test_slow": 9.0}')
    tree.mkdir()

    subprocess.run(
        ["sh", str(REPO_ROOT / "tools/warm_worktree.sh"), "durations"],
        cwd=tree, env={**os.environ, "MAIN_CHECKOUT": str(main)}, check=True)

    assert (tree / seconds).read_text() == '{"tests/test_a.py::test_slow": 9.0}', (
        "the fork scheduler splits work by these durations; without them the "
        "first run's forks finish unevenly")


@replays
def test_a_worktree_keeps_its_own_test_durations(tmp_path):
    seconds = Path(".pytest_cache/v/forked_run/seconds")
    main, tree = tmp_path / "main", tmp_path / "tree"
    for checkout, durations in ((main, "{}"), (tree, '{"mine": 1.0}')):
        (checkout / seconds).parent.mkdir(parents=True)
        (checkout / seconds).write_text(durations)

    subprocess.run(
        ["sh", str(REPO_ROOT / "tools/warm_worktree.sh"), "durations"],
        cwd=tree, env={**os.environ, "MAIN_CHECKOUT": str(main)}, check=True)

    assert (tree / seconds).read_text() == '{"mine": 1.0}'
