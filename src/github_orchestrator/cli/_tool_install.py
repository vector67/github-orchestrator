import tomllib
from dataclasses import dataclass
from pathlib import Path

PACKAGE = "github-orchestrator"
INSTALLER = ("curl -LsSf https://github.com/vector67/github-orchestrator/releases/latest/download/"
             "install.sh | sh")


@dataclass(frozen=True)
class Install:
    venv: Path
    source: str | None
    reinstall: str
    editable: Path | None = None


@dataclass(frozen=True)
class ServicePython:
    python: str
    note: str | None


def checkout_of(venv: Path) -> Path | None:
    return venv.parent if (venv.parent / "pyproject.toml").exists() else None


def install_of(python: str) -> Install:
    venv = Path(python).parent.parent
    try:
        requirements = tomllib.loads((venv / "uv-receipt.toml").read_text())["tool"]["requirements"]
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError):
        checkout = checkout_of(venv)
        return Install(venv, None, INSTALLER if checkout is None
                       else f"uv tool install --force --editable {checkout}")
    ours = next((requirement for requirement in requirements
                 if isinstance(requirement, dict) and requirement.get("name") == PACKAGE), {})
    editable = ours.get("editable")
    if isinstance(editable, str):
        return Install(venv, f"{editable} (editable)",
                       f"uv tool install --force --editable {editable}", Path(editable))
    for key, prefix in (("directory", ""), ("path", ""), ("url", ""), ("git", "git+")):
        if isinstance(ours.get(key), str):
            reinstall = (INSTALLER if key == "path" and ours[key].endswith(".whl")
                         else f"uv tool install --force {prefix}{ours[key]}")
            return Install(venv, ours[key], reinstall)
    return Install(venv, "the package index", f"uv tool install --force {PACKAGE}")


def service_python(python: str, tool_dir: Path) -> ServicePython:
    checkout = checkout_of(Path(python).parent.parent)
    tool = install_of(str(tool_dir / PACKAGE / "bin" / "python"))
    if checkout is None or tool.source is None:
        return ServicePython(python, None)
    tool_python = tool.venv / "bin" / "python"
    if tool.editable is not None and tool.editable.resolve() == checkout.resolve():
        return ServicePython(str(tool_python),
                             f"The watcher runs on {tool_python}: the uv tool {PACKAGE} is an "
                             f"editable install of this checkout ({checkout}).")
    return ServicePython(python, f"The watcher runs on {python}: the uv tool {PACKAGE} in "
                                 f"{tool.venv} is installed from {tool.source}, not from this "
                                 f"checkout ({checkout}).")
