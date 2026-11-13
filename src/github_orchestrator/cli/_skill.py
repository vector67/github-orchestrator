import json
import shutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path
from typing import Literal

from github_orchestrator.cli._findings import Finding, ok, warn
from github_orchestrator.cli._setup import ReadLine
from github_orchestrator.settings import ConfigFile

State = Literal["missing", "current", "different"]

CREATE_PR = "create-pr"
PURPOSES = {
    "create-pr": "agents run it to open a new pull request, such as the one a split carries "
                 "code into; without it they open the pull request themselves",
    "rebase-on-main": "agents run it to rebase a pull request's branch when it stops merging",
}


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


def _record(config_file: ConfigFile, name: str, why: str) -> None:
    config_file.record_pr_skill(name)
    print(f"Recorded pr_skill = {json.dumps(name)} in {config_file.location()}: {why}")


def _put_back_create_pr(skills: Path, config_file: ConfigFile) -> None:
    if config_file.pr_skill() == "" and skill_state(skills, CREATE_PR) != "missing":
        _record(config_file, CREATE_PR, "agents open pull requests with it again.")


def leave_out(skills: Path, config_file: ConfigFile) -> None:
    if config_file.pr_skill() == CREATE_PR and skill_state(skills, CREATE_PR) == "missing":
        _record(config_file, "", "agents open pull requests themselves, and "
                "github-orchestrator skill installs the skills later.")


def install_skills(skills: Path, config_file: ConfigFile, *, replace: bool) -> None:
    installed = [_install(skills, name, replace=replace) for name in shipped_skills()]
    _put_back_create_pr(skills, config_file)
    if not all(installed):
        sys.exit(1)


def _wanted(skills: Path, missing: list[str], read_line: ReadLine) -> bool:
    print(f"The orchestrator's skills missing from {skills}:")
    for name in missing:
        print(f"  {name}: {PURPOSES[name]}")
    try:
        return read_line("Install them? [Y/n] ").strip().lower() not in ("n", "no")
    except EOFError:
        return False


def update_skills(skills: Path, config_file: ConfigFile, read_line: ReadLine | None) -> None:
    print("==> Updating the orchestrator's skills", flush=True)
    names = shipped_skills()
    missing = [name for name in names if skill_state(skills, name) == "missing"]
    left_out = bool(missing) and (config_file.pr_skill() == "" or (
        read_line is not None and not _wanted(skills, missing, read_line)))
    if left_out:
        print(f"Skills left out: {', '.join(missing)}. github-orchestrator skill installs "
              "them later.")
        leave_out(skills, config_file)
    for name in names:
        if not (left_out and name in missing):
            _install(skills, name, replace=False)


def skill(skills: Path, config_file: ConfigFile, *, status: bool, replace: bool,
          leaving_out: bool) -> None:
    if status:
        for name in shipped_skills():
            print(f"{name} {skill_state(skills, name)}")
    elif leaving_out:
        leave_out(skills, config_file)
    else:
        install_skills(skills, config_file, replace=replace)


def _skill_finding(skills: Path, name: str, pr_skill: str) -> Finding:
    if skill_state(skills, name) != "missing":
        return ok(f"the {name} skill is in {skills}")
    if name == CREATE_PR and pr_skill == "":
        return ok(f"the {name} skill was left out (pr_skill = \"\"), so agents open pull requests "
                  "themselves; github-orchestrator skill installs it")
    return warn(f"the {name} skill is not in {skills}, so the orchestrator's agents that run it "
                "may not work as you expect",
                "github-orchestrator skill")


def skill_findings(skills: Path, config_file: ConfigFile) -> list[Finding]:
    pr_skill = config_file.pr_skill()
    return [_skill_finding(skills, name, pr_skill) for name in shipped_skills()]
