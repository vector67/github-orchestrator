import re
from collections.abc import Mapping
from pathlib import Path

from github_orchestrator.settings._config import (
    child_environment,
    read_config,
    resolve_data_dir,
)
from github_orchestrator.settings._settings import Settings

INSTANCES_FOLDER = Path(".config") / "github-orchestrator"
DEFAULT_CONFIG = "config.toml"
CHECKOUT_CONFIG = Path(__file__).resolve().parents[3] / DEFAULT_CONFIG


INSTANCE = "GITHUB_ORCHESTRATOR_INSTANCE"
PLAIN_NAME = re.compile(r"[A-Za-z0-9_-]+")


def with_instance(env: Mapping[str, str], name: str | None) -> dict[str, str]:
    return {**env} if name is None else {**env, INSTANCE: name}


def instance_refused(env: Mapping[str, str]) -> str | None:
    name = env.get(INSTANCE)
    if name is None:
        return None
    if name == Path(DEFAULT_CONFIG).stem:
        return (f"The instance name {name} is reserved: {DEFAULT_CONFIG} is the default "
                "instance's config. Leave --instance out for the default instance.")
    if not PLAIN_NAME.fullmatch(name):
        return (f"The instance name {name!r} must be letters, digits, '-' and '_' only, "
                "since it names a file and a folder.")
    return None


def _config_path(env: Mapping[str, str], home: Path) -> Path:
    override = env.get("GITHUB_ORCHESTRATOR_CONFIG")
    if override:
        return Path(override).expanduser()
    instance = env.get(INSTANCE)
    if instance:
        return home / INSTANCES_FOLDER / f"{instance}.toml"
    default = home / INSTANCES_FOLDER / DEFAULT_CONFIG
    if not default.exists() and CHECKOUT_CONFIG.exists():
        return CHECKOUT_CONFIG
    return default


def _data_dir(env: Mapping[str, str], home: Path) -> Path:
    instance = env.get(INSTANCE)
    if instance and not env.get("GITHUB_ORCHESTRATOR_DATA_DIR"):
        return resolve_data_dir(env, home).with_name(f"github-orchestrator-{instance}")
    return resolve_data_dir(env, home)


def instance_name(config_path: Path, home: Path) -> str | None:
    if config_path.parent != home / INSTANCES_FOLDER or config_path.name == DEFAULT_CONFIG:
        return None
    return config_path.stem


def other_instances(env: Mapping[str, str], home: Path) -> dict[str | None, dict[str, str]]:
    beside = {name: value for name, value in env.items()
              if name not in ("GITHUB_ORCHESTRATOR_DATA_DIR", "GITHUB_ORCHESTRATOR_CONFIG",
                              INSTANCE)}
    default_data_dir = resolve_data_dir(beside, home)
    this = instance_name(_config_path(env, home), home)
    default: dict[str | None, dict[str, str]] = {
        None: child_environment(default_data_dir, _config_path(beside, home))} if this is not None else {}
    return default | {
        config.stem: child_environment(
            default_data_dir.with_name(f"github-orchestrator-{config.stem}"), config)
        for config in sorted((home / INSTANCES_FOLDER).glob("*.toml"))
        if config.name != DEFAULT_CONFIG and config.stem != this
    }


def load_settings(env: Mapping[str, str], home: Path) -> Settings:
    config_path = _config_path(env, home)
    config, problem = read_config(config_path)
    return Settings(
        data_dir=_data_dir(env, home),
        config_path=config_path,
        config=config,
        problem=problem,
    )
