from dataclasses import dataclass
from pathlib import Path

import dishka

from github_orchestrator.domain import Pr
from github_orchestrator.settings import (
    ConfigFile,
    Dismissals,
    Holds,
)
from github_orchestrator.settings.fake import (
    ConfigRow,
    FakeDismissals,
    FakeHolds,
    OrchestratorConfig,
    Settings,
    fake_settings,
)
from github_orchestrator.wiring import (
    load_settings,
    make_container,
    switches_wiring,
    wire,
)

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


@dataclass
class AllSwitches:
    holds: Holds
    dismissals: Dismissals

    def forget(self, pr: Pr) -> bool:
        return all([role.forget(pr) for role in (self.holds, self.dismissals)])

    def flagged(self) -> set[Pr]:
        return self.holds.on_hold_prs() | self.dismissals.dismissed_prs()


def disk_switches(data_dir: Path) -> AllSwitches:
    return AllSwitches(disk_holds(data_dir), disk_dismissals(data_dir))


def fake_switches() -> AllSwitches:
    return AllSwitches(FakeHolds(), FakeDismissals())


def _environment(config_path: Path, data_dir: Path | None) -> dict[str, str]:
    return {"GITHUB_ORCHESTRATOR_CONFIG": str(config_path),
            "GITHUB_ORCHESTRATOR_DATA_DIR": str(data_dir or config_path.parent / "data")}


def read_from(config_path: Path, data_dir: Path | None = None) -> dishka.Container:
    return make_container(_environment(config_path, data_dir), config_path.parent)


def settings_read_from(config_path: Path, data_dir: Path | None = None) -> Settings:
    return load_settings(_environment(config_path, data_dir), config_path.parent)


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
