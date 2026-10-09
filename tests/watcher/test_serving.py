import sys
from dataclasses import dataclass, field

import pytest

from github_orchestrator import wiring
from github_orchestrator.wiring import Server, make_container

INSTANCE = "side"


@pytest.fixture
def side_instance(tmp_path):
    home = tmp_path / "home"
    config = home / ".config" / "github-orchestrator" / f"{INSTANCE}.toml"
    config.parent.mkdir(parents=True)
    config.write_text('gh_account = "octocat"\ncheck_for_updates = false\n')
    env = {"HOME": str(home), "XDG_DATA_HOME": str(tmp_path / "share"),
           "GITHUB_ORCHESTRATOR_INSTANCE": INSTANCE}
    return env, home, config, tmp_path / "share" / f"github-orchestrator-{INSTANCE}"


@dataclass
class Spawns:
    made: list[tuple[list[str], dict[str, str], object]] = field(default_factory=list)

    def __call__(self, argv, env, log_file):
        self.made.append((list(argv), dict(env), log_file))
        return self

    def poll(self):
        return None


def test_a_watcher_of_another_instance_starts_that_instances_server_on_its_config_and_data(
        side_instance, monkeypatch):
    env, home, config, data_dir = side_instance
    spawns = Spawns()
    monkeypatch.setattr(wiring, "detached", spawns)

    make_container(env, home).get(Server).keep_running()

    [(argv, environment, log_file)] = spawns.made
    assert argv == [sys.executable, "-m", "github_orchestrator.server"]
    assert environment["GITHUB_ORCHESTRATOR_CONFIG"] == str(config)
    assert environment["GITHUB_ORCHESTRATOR_DATA_DIR"] == str(data_dir)
    assert log_file == data_dir / "logs" / "server.log"
