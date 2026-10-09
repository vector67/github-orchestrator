import difflib
import enum
import os
import re
import shutil
import tempfile
import tomllib
import typing
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from github_orchestrator.agent_runs import Agent
from github_orchestrator.domain import Clone, HubState, Repo
from github_orchestrator.settings._renamed_keys import RENAMED_KEYS, doubled, renamed
from github_orchestrator.settings._switches import PORT_RANGE
from github_orchestrator.settings.interface import ConfigDescription, ConfigRow
from github_orchestrator.settings.interface import RepoEntry as RepoEntry


def resolve_data_dir(env: Mapping[str, str], home: Path) -> Path:
    override = env.get("GITHUB_ORCHESTRATOR_DATA_DIR")
    if override:
        return Path(override).expanduser()
    xdg = env.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg).expanduser() / "github-orchestrator"
    legacy = home / ".config" / "local" / "share" / "github-orchestrator"
    if legacy.exists():
        return legacy
    return home / ".local" / "share" / "github-orchestrator"


def child_environment(data_dir: Path, config_path: Path) -> dict[str, str]:
    return {
        "GITHUB_ORCHESTRATOR_DATA_DIR": str(data_dir),
        "GITHUB_ORCHESTRATOR_CONFIG": str(config_path),
    }


UNSET_PLACEHOLDERS = {
    "gh_account": "your-github-username",
}
UNSET_REPO = {"repo": "owner/repo", "local_path": "~/repositories/repo"}

UNSET_SOURCE = "unset"


class Tracker(enum.StrEnum):
    NONE = "none"
    GITHUB = "github"
    JIRA = "jira"


@dataclass(frozen=True)
class OrchestratorConfig:
    dashboard_refresh_interval: int = 1
    watcher_poll_interval: int = 60
    agent_timeout: int = 3600
    agents_enabled: bool = True
    agent: Agent = Agent.default()
    agent_command: str = Agent.default().default_command()
    agent_model: str = Agent.default().default_model
    summary_model: str = Agent.default().default_summary_model
    mismatch_grace_seconds: int = 3600
    mismatch_run_idle_seconds: int = 300
    max_thread_runs: int = 4
    pytest_workers: int = 2
    log_level: str = "INFO"
    gh_account: str = UNSET_PLACEHOLDERS["gh_account"]
    new_worktree_command: str = ""
    board_font_dir: str = ""
    not_fixed_opener: str = "Not fixed — "
    hub_port: int = 8720
    first_names_only: bool = False
    tracker: Tracker = Tracker.NONE
    tracker_project: str = ""
    check_for_updates: bool = True
    repos: tuple[RepoEntry, ...] = ()


_HINTS = typing.get_type_hints(OrchestratorConfig)


class ConfigError(Exception):
    def __init__(self, said: str, until_setup: str | None = None,
                 until_restart: str | None = None) -> None:
        super().__init__(said)
        self.until_setup = until_setup
        self.until_restart = until_restart

    def words(self, setup_command: str, restart_command: str) -> str:
        if self.until_setup is not None:
            return f"{self} — run `{setup_command}`, {self.until_setup}"
        if self.until_restart is not None:
            return f"{self} — run `{restart_command}`, {self.until_restart}"
        return str(self)


LEGACY_KEYS = ("pr_windows", "idle_threshold")
LEFT_BY_TMUX_MODE = ("tmux_window_ids", "glow_theme")


def _refuse_legacy_keys(config_path: Path, data: Mapping[str, object]) -> None:
    legacy = [key for key in LEGACY_KEYS if key in data]
    if legacy:
        raise ConfigError(
            f"{config_path}: {' and '.join(legacy)} {'is' if len(legacy) == 1 else 'are'} "
            "no longer read, now that the agent managers always run in the background",
            until_restart="which rewrites the config without them and keeps the old one beside it")


def _read(config_path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if config_path.exists():
        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"{config_path}: {e}") from e
        except (OSError, UnicodeDecodeError) as e:
            raise ConfigError(f"{config_path}: {e}") from e

    _refuse_legacy_keys(config_path, data)
    old = doubled(data)
    if old is not None:
        raise ConfigError(f"{config_path}: {old} is the old name of {RENAMED_KEYS[old]}; "
                          f"keep {RENAMED_KEYS[old]} and remove {old}")
    data = renamed(data)
    _read_repos(config_path, data)
    fields = OrchestratorConfig.__dataclass_fields__
    for key, value in data.items():
        if key == "repos":
            continue
        if key not in fields:
            near = difflib.get_close_matches(key, fields, n=1)
            hint = (f"did you mean {near[0]!r}?" if near
                    else f"(known keys: {', '.join(sorted(fields))})")
            raise ConfigError(f"{config_path}: unknown key {key!r} — {hint}")
        expected = _HINTS[key]
        if issubclass(expected, enum.Enum):
            data[key] = _choice(config_path, key, expected, value)
        elif type(value) is not expected:
            raise ConfigError(
                f"{config_path}: {key} must be {expected.__name__}, got "
                f"{type(value).__name__} ({value!r})"
            )
    hub_port = data.get("hub_port")
    if hub_port is not None and not _takes(hub_port):
        raise ConfigError(
            f"{config_path}: hub_port must be a port from 1 to 65535 outside the boards' "
            f"{PORT_RANGE.start}-{PORT_RANGE.stop - 1}, got {hub_port}"
        )
    _check_tracker(config_path, data.get("tracker", Tracker.NONE), data.get("tracker_project", ""))
    return data


_OLD_REPO_KEYS = {"watch_repo": "repo", "local_path": "local_path"}
_ENTRY_KEYS = ("repo", "local_path", "new_worktree_command")


def _old_repo_table(data: dict[str, Any]) -> dict[str, Any] | None:
    old = {new: data.pop(key) for key, new in _OLD_REPO_KEYS.items() if key in data}
    if not old:
        return None
    carried = {"new_worktree_command": data["new_worktree_command"]} if (
        "new_worktree_command" in data) else {}
    return {**UNSET_REPO, **old, **carried}


def _read_repos(config_path: Path, data: dict[str, Any]) -> None:
    if "repos" in data and any(key in data for key in _OLD_REPO_KEYS):
        raise ConfigError(
            f"{config_path}: watch_repo and local_path are the old way to write one "
            "[[repos]] entry; keep the [[repos]] tables and remove them")
    old = _old_repo_table(data)
    tables = [old] if old is not None else data.get("repos")
    if tables is None:
        return
    if not isinstance(tables, list) or not all(isinstance(table, dict) for table in tables):
        raise ConfigError(
            f"{config_path}: repos must be [[repos]] tables, each with repo and local_path")
    entries = tuple(_repo_entry(config_path, table) for table in tables)
    seen: set[Repo] = set()
    for entry in entries:
        if entry.repo in seen:
            raise ConfigError(f"{config_path}: {entry.repo} is watched twice in [[repos]]")
        seen.add(entry.repo)
    data["repos"] = entries


def _repo_entry(config_path: Path, table: Mapping[str, object]) -> RepoEntry:
    for key in table:
        if key not in _ENTRY_KEYS:
            near = difflib.get_close_matches(key, _ENTRY_KEYS, n=1)
            hint = f"did you mean {near[0]!r}?" if near else f"(known keys: {', '.join(_ENTRY_KEYS)})"
            raise ConfigError(f"{config_path}: unknown key {key!r} in [[repos]] — {hint}")
    strings: dict[str, str] = {}
    for key, value in table.items():
        if not isinstance(value, str):
            raise ConfigError(
                f"{config_path}: [[repos]] {key} must be str, got {type(value).__name__} "
                f"({value!r})")
        strings[key] = value
    for key in ("repo", "local_path"):
        if key not in strings:
            raise ConfigError(f"{config_path}: each [[repos]] entry needs {key}")
    try:
        repo = Repo.parse(strings["repo"])
    except ValueError as e:
        raise ConfigError(
            f"{config_path}: [[repos]] repo must be owner/name, got {strings['repo']!r}"
        ) from e
    return RepoEntry(repo, strings["local_path"], strings.get("new_worktree_command"))


def _repos_unset(entries: tuple[RepoEntry, ...]) -> bool:
    placeholder = Repo.parse(UNSET_REPO["repo"])
    return not entries or any(
        entry.repo == placeholder or entry.local_path == UNSET_REPO["local_path"]
        for entry in entries)


JIRA_PROJECT_KEY = re.compile(r"[A-Z][A-Z0-9_]+")


def _check_tracker(config_path: Path, tracker: Tracker, project: str) -> None:
    if tracker is not Tracker.JIRA and project:
        raise ConfigError(
            f'{config_path}: tracker_project names a Jira project, so it needs tracker = "jira"'
        )
    if tracker is Tracker.JIRA and not project:
        raise ConfigError(
            f'{config_path}: tracker = "jira" needs tracker_project, the Jira project '
            "tickets go to by default"
        )
    if project and not JIRA_PROJECT_KEY.fullmatch(project):
        raise ConfigError(
            f"{config_path}: tracker_project must be a Jira project key such as PROJ, "
            f"got {project!r}"
        )


def _choice(config_path: Path, key: str, choices: type[enum.Enum], value: object) -> enum.Enum:
    try:
        return choices(value)
    except ValueError:
        words = " or ".join(f'"{choice.value}"' for choice in choices)
        raise ConfigError(f"{config_path}: {key} must be {words}, got {value!r}") from None


def _unset_keys(data: Mapping[str, Any]) -> list[str]:
    unset = [key for key, placeholder in UNSET_PLACEHOLDERS.items()
             if data.get(key, placeholder) == placeholder]
    return [*unset, "repos"] if _repos_unset(data.get("repos", ())) else unset


def _parse(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise ConfigError(
            f"{config_path}: the config file does not exist",
            "which opens the board's setup page to write it",
        )
    data = _read(config_path)
    unset = _unset_keys(data)
    if unset:
        raise ConfigError(
            f"{config_path}: {', '.join(unset)} must be set to your own values",
            "which opens the board's setup page to ask for them",
        )
    return data


def _takes(hub_port: int) -> bool:
    return hub_port not in PORT_RANGE and 0 < hub_port < 65536


def _hub_port_of(config_path: Path) -> int:
    try:
        with open(config_path, "rb") as f:
            hub_port = tomllib.load(f).get("hub_port")
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return OrchestratorConfig.hub_port
    if type(hub_port) is int and _takes(hub_port):
        return hub_port
    return OrchestratorConfig.hub_port


def _with_agent_defaults(data: Mapping[str, Any]) -> dict[str, Any]:
    agent: Agent = data.get("agent", Agent.default())
    return {"agent_command": agent.default_command(), "agent_model": agent.default_model,
            "summary_model": agent.default_summary_model, **data}


def _agent_of(config_path: Path) -> Agent:
    try:
        with open(config_path, "rb") as f:
            return Agent(tomllib.load(f).get("agent", Agent.default()))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, ValueError):
        return Agent.default()


def read_config(config_path: Path) -> tuple[OrchestratorConfig, ConfigError | None]:
    try:
        return OrchestratorConfig(**_with_agent_defaults(_parse(config_path))), None
    except ConfigError as e:
        return OrchestratorConfig(**_with_agent_defaults(
            {"hub_port": _hub_port_of(config_path), "agent": _agent_of(config_path)})), e


def _hub_state(problem: ConfigError | None) -> HubState:
    if problem is None:
        return HubState.WATCHING
    return HubState.BROKEN if problem.until_setup is None else HubState.SETUP


_TOML_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r"}


def _toml_string(value: str) -> str:
    out = []
    for char in value:
        if char in _TOML_ESCAPES:
            out.append(_TOML_ESCAPES[char])
        elif char != "\t" and (char < " " or char == "\x7f"):
            out.append(f"\\u{ord(char):04x}")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return _toml_string(str(value))


def _rendered(top: Mapping[str, object], tables: Sequence[Mapping[str, object]]) -> str:
    lines = [f"{key} = {_toml_value(value)}" for key, value in top.items()]
    for table in tables:
        lines += ["", "[[repos]]", *(f"{key} = {_toml_value(value)}" for key, value in table.items())]
    return "\n".join(lines) + "\n"


def _writable(top: Mapping[str, object], tables: object) -> bool:
    def plain(values: Mapping[str, object]) -> bool:
        return all(isinstance(value, str | int) for value in values.values())
    return plain(top) and isinstance(tables, list) and all(
        isinstance(table, dict) and plain(table) for table in tables)


def _backup_of(path: Path) -> Path:
    backup = path.with_name(f"{path.name}.bak")
    taken = 0
    while backup.exists() or backup.is_symlink():
        taken += 1
        backup = path.with_name(f"{path.name}.bak.{taken}")
    return backup


def _migrated(path: Path) -> Path | None:
    try:
        original = path.read_bytes()
        data = tomllib.loads(original.decode())
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    if not any(key in data for key in (*LEGACY_KEYS, *_OLD_REPO_KEYS, *RENAMED_KEYS)):
        return None
    if doubled(data) is not None:
        return None
    data = renamed(data)
    for key in LEGACY_KEYS:
        data.pop(key, None)
    if "repos" not in data:
        table = _old_repo_table(data)
        if table is not None:
            data.pop("new_worktree_command", None)
            data["repos"] = [table]
    tables = data.pop("repos", [])
    if not _writable(data, tables):
        return None
    backup = _backup_of(path)
    backup.write_bytes(original)
    rewriting = path.with_name(f"{path.name}.migrating")
    rewriting.write_text(_rendered(data, tables))
    shutil.copymode(path, rewriting)
    os.replace(rewriting, path)
    return backup


def _legacy_in(path: Path) -> tuple[str, ...]:
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return ()
    return tuple(key for key in (*_OLD_REPO_KEYS, *LEGACY_KEYS, *RENAMED_KEYS) if key in data)


def _tidied(data_dir: Path) -> list[Path]:
    removed = []
    for name in LEFT_BY_TMUX_MODE:
        left = data_dir / name
        if left.is_dir() and not left.is_symlink():
            shutil.rmtree(left)
        elif left.exists() or left.is_symlink():
            left.unlink()
        else:
            continue
        removed.append(left)
    return removed


class TomlConfigFile:
    def __init__(self, path: Path, problem: ConfigError | None, setup_command: str,
                 restart_command: str, data_dir: Path) -> None:
        self._path = path
        self._problem = problem
        self._setup_command = setup_command
        self._restart_command = restart_command
        self._data_dir = data_dir

    def check(self) -> str | None:
        if self._problem is None:
            return None
        return self._problem.words(self._setup_command, self._restart_command)

    def state(self) -> HubState:
        _, problem = read_config(self._path)
        return _hub_state(problem)

    def location(self) -> str:
        return str(self._path)

    def describe(self) -> ConfigDescription:
        problem = None
        try:
            data = _read(self._path)
        except ConfigError as e:
            data, problem = {}, str(e)
        unset = set(_unset_keys(data))
        config = OrchestratorConfig(**_with_agent_defaults(data))
        shown = {"repos": ", ".join(str(entry) for entry in config.repos)}
        return ConfigDescription([
            ConfigRow(key, shown.get(key, getattr(config, key)),
                      UNSET_SOURCE if key in unset
                      else self._path.name if key in data else "default",
                      key in unset)
            for key in OrchestratorConfig.__dataclass_fields__
        ], problem, self._path.exists(), _legacy_in(self._path))

    def repos(self) -> tuple[RepoEntry, ...]:
        try:
            entries: tuple[RepoEntry, ...] = _read(self._path).get("repos", ())
        except ConfigError:
            return ()
        return entries

    def check_write(self, values: Mapping[str, str | int | bool], *,
                    repos: Mapping[Repo, Clone]) -> str | None:
        with tempfile.TemporaryDirectory() as trying:
            tried = Path(trying) / self._path.name
            tried.write_text(self._written(values, repos))
            try:
                _read(tried)
            except ConfigError as refused:
                return str(refused).replace(str(tried), str(self._path))
        return None

    def write(self, values: Mapping[str, str | int | bool], *,
              repos: Mapping[Repo, Clone]) -> None:
        rendered = self._written(values, repos)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        writing = self._path.with_name(f"{self._path.name}.writing")
        writing.write_text(rendered)
        os.replace(writing, self._path)

    def _written(self, values: Mapping[str, str | int | bool],
                 repos: Mapping[Repo, Clone]) -> str:
        kept = {key: value for key, value in _read(self._path).items() if key != "repos"}
        return _rendered({**kept, **values}, [
            {"repo": str(repo), "local_path": str(clone.path),
             **({"new_worktree_command": clone.new_worktree_command}
                if clone.new_worktree_command else {})}
            for repo, clone in repos.items()])

    def move_aside(self, now: datetime) -> str:
        moved = self._path.with_name(f"{self._path.name}.broken-{now:%Y%m%d-%H%M%S}")
        hub_port = _hub_port_of(self._path)
        os.replace(self._path, moved)
        if hub_port != OrchestratorConfig.hub_port:
            self._path.write_text(_rendered({"hub_port": hub_port}, []))
        return str(moved)

    def migrate(self) -> list[str]:
        said = []
        backup = _migrated(self._path)
        if backup is not None:
            said.append(f"Rewrote {self._path} for this release; the old one is {backup}")
            _, self._problem = read_config(self._path)
        said += [f"Removed {left}, which only tmux mode read" for left in _tidied(self._data_dir)]
        return said
