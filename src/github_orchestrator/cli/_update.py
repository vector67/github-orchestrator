import sys
import tempfile
from pathlib import Path

from github_orchestrator.cli._config import CliConfig, Run, Which
from github_orchestrator.cli._hub import HealthBody
from github_orchestrator.watcher import Releases

UPDATE = "github-orchestrator update"


def newer_release(config: CliConfig, answer: HealthBody | None, releases: Releases) -> str | None:
    if config.check_for_updates:
        newest = None if answer is None else answer.get("newest_release")
        if isinstance(newest, dict) and newest.get("newer") is True:
            return str(newest.get("version"))
        return None
    running = config.version if answer is None else answer.get("version")
    found = releases.look_up(None)
    if isinstance(found, str) or not found.newer_than(
            running if isinstance(running, str) else None):
        return None
    return found.version


TOOL_PYTHON = "3.12"


def update(config: CliConfig, run: Run, which: Which, releases: Releases, *,
           version: str | None, check: bool) -> None:
    found = releases.look_up(version)
    if isinstance(found, str):
        print(found, file=sys.stderr)
        sys.exit(1)
    installed = config.version or "(version unknown)"
    asked = "newest" if version is None else "asked for"
    print(f"Installed {installed}, {asked} {found.version}.")
    if version is None and not found.newer_than(config.version):
        print("Already up to date.")
        return
    if check:
        print(f"Run {UPDATE} to install {found.version}.")
        return
    uv = which("uv")
    if uv is None:
        print("uv is not on PATH; it installs the new version. "
              "curl -LsSf https://astral.sh/uv/install.sh | sh installs it.", file=sys.stderr)
        sys.exit(1)
    print(f"==> Installing {found.version}", flush=True)
    with tempfile.TemporaryDirectory() as folder:
        wheel = releases.download(found, Path(folder))
        if isinstance(wheel, str):
            print(wheel, file=sys.stderr)
            sys.exit(1)
        done = run([uv, "tool", "install", "--force", "--python", TOOL_PYTHON, str(wheel)],
                   capture_output=True, text=True)
    if done.returncode != 0:
        print(f"uv tool install failed, so {installed} stays installed: "
              f"{str(done.stderr).strip()}", file=sys.stderr)
        sys.exit(1)
    print("==> Restarting every instance on the new version", flush=True)
    restarted = run([config.python, "-m", "github_orchestrator.cli", "start", "--from-installer"])
    if restarted.returncode != 0:
        sys.exit(restarted.returncode)
    print(f"Updated to {found.version}.")
