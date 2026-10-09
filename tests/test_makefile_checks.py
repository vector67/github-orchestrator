import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STUBS = Path(__file__).parent / "stubs" / "lint_python"
MAKEFILE = REPO_ROOT / "Makefile"
TARGET = re.compile(r"^([A-Za-z0-9_.-]+):(?!=)")
CONDITIONALS = ("ifeq", "ifneq", "else", "endif")


def _recipes():
    blocks = {}
    current = None
    for line in MAKEFILE.read_text().splitlines():
        match = TARGET.match(line)
        if match:
            current = match.group(1)
            blocks[current] = []
            continue
        if line.startswith("\t") or line.split(" ")[0] in CONDITIONALS:
            if current is not None:
                blocks[current].append(line)
            continue
        current = None
    return blocks


def _logical_lines(recipe):
    lines, buffer = [], ""
    for line in recipe:
        buffer += line.strip()
        if buffer.endswith("\\"):
            buffer = buffer[:-1] + " "
            continue
        lines.append(buffer)
        buffer = ""
    if buffer:
        lines.append(buffer)
    return lines


def _recipe(name):
    return " ".join(_logical_lines(_recipes()[name]))


def test_every_frontend_target_goes_through_the_node_guard():
    for name in ("lint-frontend", "lint-frontend-fix"):
        assert "frontend_deps" in _recipe(name), (
            f"{name} needs node and node_modules; one guard holds that, and "
            "a target that skips it fails inside npm instead")


def test_the_node_guard_names_a_missing_node_and_installs_the_packages():
    recipe = _recipe("frontend_deps")

    assert "command -v npm" in recipe, (
        "every recipe is shell and the machine may not have node; say so "
        "rather than failing inside npm")
    assert "npm ci" in recipe, (
        "the checks have to work in a fresh checkout, where node_modules is "
        "not there yet")


@pytest.mark.no_replay
def test_lint_python_runs_mypy_even_when_ruff_fails(tmp_path):
    calls = tmp_path / "calls"
    env = {**os.environ, "PATH": f"{STUBS}:{os.environ['PATH']}", "STUB_CALLS": str(calls)}

    result = subprocess.run(
        ["make", "-f", str(MAKEFILE), "lint-python"], cwd=REPO_ROOT, env=env,
        capture_output=True, text=True)

    assert "run mypy" in calls.read_text(), (
        "a ruff failure must not hide mypy's errors, which are the list a "
        "refactor works through")
    assert result.returncode != 0
