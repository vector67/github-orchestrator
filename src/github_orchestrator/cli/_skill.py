import shutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path
from typing import Literal

from github_orchestrator.cli._findings import Finding, ok, warn

SKILL = "rebase-on-main"

State = Literal["missing", "current", "different"]


def skill_folder(skills: Path) -> Path:
    return skills / SKILL


@contextmanager
def packaged_skill() -> Iterator[Path]:
    with as_file(files(__package__) / "skills" / SKILL) as source:
        yield source


def _contents(folder: Path) -> dict[Path, bytes]:
    return {path.relative_to(folder): path.read_bytes()
            for path in folder.rglob("*") if path.is_file()}


def skill_state(skills: Path) -> State:
    target = skill_folder(skills)
    if not (target.exists() or target.is_symlink()):
        return "missing"
    with packaged_skill() as source:
        if target.is_dir() and _contents(target) == _contents(source):
            return "current"
    return "different"


def _remove(target: Path) -> None:
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    else:
        target.unlink()


def install_skill(skills: Path, *, replace: bool) -> None:
    target = skill_folder(skills)
    state = skill_state(skills)
    if state == "current":
        print(f"The {SKILL} skill in {target} is already this version's.")
        return
    if state == "different":
        if not replace:
            print(f"The {SKILL} skill in {target} differs from this version's, so it was left "
                  "alone. github-orchestrator skill --replace puts this version's in its place.")
            sys.exit(1)
        _remove(target)
    with packaged_skill() as source:
        shutil.copytree(source, target)
    print(f"Installed the {SKILL} skill in {target}.")


def skill(skills: Path, *, status: bool, replace: bool) -> None:
    if status:
        print(skill_state(skills))
    else:
        install_skill(skills, replace=replace)


def skill_finding(skills: Path) -> Finding:
    if skill_state(skills) == "missing":
        return warn(f"the {SKILL} skill is not in {skills}, so the orchestrator's rebasing may not "
                    "work as you expect",
                    "github-orchestrator skill")
    return ok(f"the {SKILL} skill is in {skills}")
