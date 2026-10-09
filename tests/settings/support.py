from dataclasses import dataclass
from pathlib import Path

import dishka

from github_orchestrator.domain import Pr
from github_orchestrator.settings import (
    Boards,
    ConfigFile,
    Dismissals,
    Holds,
)
from github_orchestrator.settings.fake import (
    ConfigRow,
    FakeBoards,
    FakeDismissals,
    FakeHolds,
    OrchestratorConfig,
    Settings,
    fake_settings,
)
from github_orchestrator.wiring import make_container, switches_wiring, wire

REPO_ROOT = Path(__file__).resolve().parents[2]


def _switches(data_dir: Path) -> dishka.Container:
    settings = fake_settings(data_dir)
    return wire(switches_wiring(settings))


def disk_holds(data_dir: Path) -> Holds:
    holds: Holds = _switches(data_dir).get(Holds)
    return holds


def disk_dismissals(data_dir: Path) -> Dismissals:
    dismissals: Dismissals = _switches(data_dir).get(Dismissals)
    return dismissals


def disk_boards(data_dir: Path) -> Boards:
    boards: Boards = _switches(data_dir).get(Boards)
    return boards


@dataclass
class AllSwitches:
    holds: Holds
    dismissals: Dismissals
    boards: Boards

    def forget(self, pr: Pr) -> bool:
        return all([role.forget(pr) for role in (self.holds, self.dismissals, self.boards)])

    def flagged(self) -> set[Pr]:
        return self.holds.on_hold_prs() | self.dismissals.dismissed_prs()


def disk_switches(data_dir: Path) -> AllSwitches:
    return AllSwitches(disk_holds(data_dir), disk_dismissals(data_dir), disk_boards(data_dir))


def fake_switches() -> AllSwitches:
    return AllSwitches(FakeHolds(), FakeDismissals(), FakeBoards())


def read_from(config_path: Path, data_dir: Path | None = None) -> dishka.Container:
    env = {"GITHUB_ORCHESTRATOR_CONFIG": str(config_path),
           "GITHUB_ORCHESTRATOR_DATA_DIR": str(data_dir or config_path.parent / "data")}
    return make_container(env, config_path.parent)


def settings_read_from(config_path: Path, data_dir: Path | None = None) -> Settings:
    settings: Settings = read_from(config_path, data_dir).get(Settings)
    return settings


class ConfigProblem(Exception):
    pass


def load_config(config_path: Path) -> OrchestratorConfig:
    container = read_from(config_path)
    problem = container.get(ConfigFile).check()
    if problem is not None:
        raise ConfigProblem(problem)
    settings: Settings = container.get(Settings)
    return settings.config


def describe_config(config_path: Path) -> list[ConfigRow]:
    config_file: ConfigFile = read_from(config_path).get(ConfigFile)
    described = config_file.describe()
    if described.problem is not None:
        raise ConfigProblem(described.problem)
    return described.rows


def example_config() -> str:
    return (REPO_ROOT / "src" / "github_orchestrator" / "settings" / "config.toml.example").read_text()
