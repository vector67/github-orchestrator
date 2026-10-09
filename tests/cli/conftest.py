import pytest

from tests.cli.scripted_system import Job
from tests.cli.support import Machine, Ran


@pytest.fixture
def status_dirs(settings):
    for directory in (settings.state_dir, settings.queues_dir, settings.logs_dir,
                      settings.on_hold_dir, settings.dismissed_dir):
        directory.mkdir()
    return settings


@pytest.fixture
def machine(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    made = Machine(data_dir=tmp_path, home=home)
    made.configure()
    return made


@pytest.fixture
def restartable(machine):
    agents = machine.home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    plist = agents / "com.github-orchestrator.watcher.plist"
    plist.write_text("<plist/>")
    machine.system.job = Job()
    machine.settings().watcher_heartbeat.write_text(machine.now.isoformat())
    return plist


@pytest.fixture
def run_cli(machine, capsys):
    def run(*argv: str) -> Ran:
        cli = machine.cli()
        capsys.readouterr()
        code = cli.main(list(argv))
        captured = capsys.readouterr()
        return Ran(code, captured.out, captured.err)

    return run
