import shutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path
from typing import Literal

from github_orchestrator.cli._findings import Finding, ok, warn

State = Literal["missing", "current", "different"]


def shipped_skills() -> list[str]:
    return sorted(entry.name for entry in (files(__package__) / "skills").iterdir()
                  if entry.is_dir())


@contextmanager
def packaged_skill(name: str) -> Iterator[Path]:
    with as_file(files(__package__) / "skills" / name) as source:
        yield source


def _contents(folder: Path) -> dict[Path, bytes]:
    return {path.relative_to(folder): path.read_bytes()
            for path in folder.rglob("*") if path.is_file()}


def skill_state(skills: Path, name: str) -> State:
    target = skills / name
    if not (target.exists() or target.is_symlink()):
        return "missing"
    with packaged_skill(name) as source:
        if target.is_dir() and _contents(target) == _contents(source):
            return "current"
    return "different"


def _remove(target: Path) -> None:
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    else:
        target.unlink()


def _install(skills: Path, name: str, *, replace: bool) -> bool:
    target = skills / name
    state = skill_state(skills, name)
    if state == "current":
        print(f"The {name} skill in {target} is already this version's.")
        return True
    if state == "different":
        if not replace:
            print(f"The {name} skill in {target} differs from this version's, so it was left "
                  "alone. github-orchestrator skill --replace puts this version's in its place.")
            return False
        _remove(target)
    with packaged_skill(name) as source:
        shutil.copytree(source, target)
    print(f"Installed the {name} skill in {target}.")
    return True


def install_skills(skills: Path, *, replace: bool) -> None:
    installed = [_install(skills, name, replace=replace) for name in shipped_skills()]
    if not all(installed):
        sys.exit(1)


def update_skills(skills: Path) -> None:
    print("==> Updating the orchestrator's skills", flush=True)
    names = shipped_skills()
    if all(skill_state(skills, name) == "missing" for name in names):
        print(f"Skills left out: {', '.join(names)}; github-orchestrator skill installs them "
              "later.")
        return
    for name in names:
        _install(skills, name, replace=False)


def skill(skills: Path, *, status: bool, replace: bool) -> None:
    if status:
        for name in shipped_skills():
            print(f"{name} {skill_state(skills, name)}")
    else:
        install_skills(skills, replace=replace)


def skill_findings(skills: Path) -> list[Finding]:
    return [warn(f"the {name} skill is not in {skills}, so the orchestrator's agents that run it "
                 "may not work as you expect",
                 "github-orchestrator skill")
            if skill_state(skills, name) == "missing" else ok(f"the {name} skill is in {skills}")
            for name in shipped_skills()]
