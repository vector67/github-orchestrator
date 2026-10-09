import shutil
import sys
from pathlib import Path

from github_orchestrator.cli._config import CliConfig, Run, Which
from github_orchestrator.cli._restart_all import Instance
from github_orchestrator.cli._setup import ReadLine
from github_orchestrator.cli._skill import SKILL, skill_folder, skill_state
from github_orchestrator.cli._stop import agreed, stop

PACKAGE = "github-orchestrator"
NOTIFIER_APPS = "GHO *.app"
UNINSTALL = f"uv tool uninstall {PACKAGE}"


def _named(instances: list[Instance]) -> str:
    names = ["the default instance" if instance.name is None else instance.name
             for instance in instances]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _kept(config: CliConfig, instances: list[Instance]) -> list[Path]:
    folder = config.config_folder
    apps = sorted((config.home / "Applications").glob(NOTIFIER_APPS))
    return [path for path in (folder, *(instance.data_dir for instance in instances), *apps)
            if path.exists()]


def _removed(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()
    print(f"Removed {path}.")


def uninstall(config: CliConfig, run: Run, which: Which, read_line: ReadLine,
              instances: list[Instance], *, yes: bool) -> None:
    kind = "LaunchAgents" if config.platform == "darwin" else "systemd units"
    kept = _kept(config, instances)
    print("This stops every instance and removes:")
    print(f"  the {kind} for {_named(instances)}")
    print(f"  the {PACKAGE} command (uv tool uninstall)")
    if kept:
        print("It keeps, unless you say otherwise:")
        for path in kept:
            print(f"  {path}")
    skills = config.agent.skill_folder(config.home)
    skill = skill_folder(skills)
    if skill_state(skills) != "missing":
        print(f"It leaves the {SKILL} skill in {skill}, which {config.agent.described} uses without the "
              f"orchestrator too; rm -rf {skill} removes it.")
    print("Your clones are never touched.", flush=True)
    everything = yes or (bool(kept) and agreed(read_line, "Remove the config and data too? [y/N] "))
    for instance in instances:
        stop(read_line, [instance], force=True)
        instance.service.remove()
    if everything:
        for path in kept:
            _removed(path)
    uv = which("uv")
    if uv is None:
        print(f"uv is not on PATH, so the {PACKAGE} command is still there; remove it with "
              f"{UNINSTALL} once uv is on PATH.")
        sys.exit(1)
    done = run([uv, "tool", "uninstall", PACKAGE], capture_output=True, text=True)
    if done.returncode != 0:
        print(f"{UNINSTALL} failed: {str(done.stderr).strip()}")
        sys.exit(1)
    print(f"Uninstalled {PACKAGE}. uv, gh and {config.agent_program} stay installed.")
