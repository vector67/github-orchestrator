import os
import plistlib
import shutil
from pathlib import Path

from github_orchestrator.cli._config import Run
from github_orchestrator.settings import ConfigFile

TMUX_SESSION = "prs"
TMUX_MANAGER = "github_orchestrator[.]pr_manager --repo"


def _stop_tmux_managers(run: Run) -> int:
    try:
        panes = run(["tmux", "list-panes", "-s", "-t", f"={TMUX_SESSION}", "-F", "#{pane_pid}"],
                    capture_output=True, text=True)
    except OSError:
        return 0
    if panes.returncode != 0:
        return 0
    stopped = 0
    for pane in panes.stdout.split():
        if pane.isdigit():
            killed = run(["pkill", "-TERM", "-P", pane, "-f", TMUX_MANAGER],
                         capture_output=True, text=True)
            stopped += killed.returncode == 0
    return stopped


def migrate(config_file: ConfigFile, run: Run, heading: str) -> None:
    said = config_file.migrate()
    stopped = _stop_tmux_managers(run)
    if stopped:
        said.append(f"Stopped {stopped} agent manager tmux mode left in the {TMUX_SESSION} "
                    "session; the watcher starts it again in the background."
                    if stopped == 1 else
                    f"Stopped {stopped} agent managers tmux mode left in the {TMUX_SESSION} "
                    "session; the watcher starts them again in the background.")
    if said:
        print(f"==> {heading}", flush=True)
        for line in said:
            print(line, flush=True)


OLD_CONFIG = "config.toml"
CRON_BEGIN = "# github-orchestrator begin"
CRON_END = "# github-orchestrator end"
PINNED = "GITHUB_ORCHESTRATOR_CONFIG"


def _named_by(arguments: list[str]) -> Path | None:
    for flag in ("--project", "--directory"):
        if flag in arguments[:-1]:
            return Path(arguments[arguments.index(flag) + 1]) / OLD_CONFIG
    program = Path(arguments[0]) if arguments else None
    if program is not None and program.parent.parent.name == ".venv":
        return program.parents[2] / OLD_CONFIG
    return None


def _from_plist(plist: Path) -> Path | None:
    try:
        data = plistlib.loads(plist.read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException):
        return None
    environment = data.get("EnvironmentVariables")
    pinned = environment.get(PINNED) if isinstance(environment, dict) else None
    if isinstance(pinned, str):
        return Path(pinned)
    arguments = data.get("ProgramArguments")
    return _named_by([str(argument) for argument in arguments]) if isinstance(
        arguments, list) else None


def _crontab(run: Run) -> str | None:
    try:
        listed = run(["crontab", "-l"], capture_output=True, text=True)
    except OSError:
        return None
    return str(listed.stdout) if listed.returncode == 0 else None


def _cron_block(text: str) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    block: list[str] = []
    inside = False
    for line in text.splitlines(keepends=True):
        if line.strip() == CRON_BEGIN:
            inside = True
        if inside or "github_orchestrator" in line:
            block.append(line)
        else:
            kept.append(line)
        if line.strip() == CRON_END:
            inside = False
    return kept, block


def _from_cron(block: list[str]) -> Path | None:
    for line in block:
        name, _, value = line.strip().partition("=")
        if name == PINNED:
            return Path(value)
    for line in block:
        found = _named_by(line.split())
        if found is not None:
            return found
    return None


def old_config(plist: Path, run: Run, *, linux: bool) -> Path | None:
    if linux:
        listed = _crontab(run)
        return None if listed is None else _from_cron(_cron_block(listed)[1])
    return _from_plist(plist) if plist.exists() else None


def move_old_config(old: Path | None, target: Path) -> tuple[bool, list[str]]:
    if old is None or old == target or not old.is_file():
        return False, []
    if target.exists():
        return False, [f"Left {old} where it is: {target} is already there."]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(old, target)
    os.replace(old, old.with_name(f"{old.name}.bak"))
    return True, [f"Moved {old} to {target}; a copy stays at {old}.bak."]


def drop_cron_block(run: Run, keep_in: Path) -> list[str]:
    listed = _crontab(run)
    if listed is None:
        return []
    kept, block = _cron_block(listed)
    if not block:
        return []
    keep_in.parent.mkdir(parents=True, exist_ok=True)
    keep_in.write_text(listed)
    run(["crontab", "-"], input="".join(kept), capture_output=True, text=True)
    return [f"Removed the watcher's cron lines; the old crontab is {keep_in}."]
