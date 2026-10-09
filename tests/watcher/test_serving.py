import json
import os
import signal
import socket
import subprocess
import sys
import urllib.error
import urllib.request

import pytest

from tests.waiting import until

STARTED_WITHIN_SECONDS = 60
INSTANCE = "side"


def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _health(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as answer:
            return json.load(answer)
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        return None


@pytest.fixture
def side_instance(tmp_path):
    home, port = tmp_path / "home", _free_port()
    folder = home / ".config" / "github-orchestrator"
    folder.mkdir(parents=True)
    (folder / f"{INSTANCE}.toml").write_text(
        f'gh_account = "octocat"\nhub_port = {port}\nserver_workers = 1\n'
        "check_for_updates = false\n")
    env = {name: value for name, value in os.environ.items()
           if not name.startswith("GITHUB_ORCHESTRATOR_")}
    env.update(HOME=str(home), XDG_DATA_HOME=str(tmp_path / "share"),
               GITHUB_ORCHESTRATOR_INSTANCE=INSTANCE)
    return env, port, tmp_path / "share" / f"github-orchestrator-{INSTANCE}"


def _server_pid(data_dir):
    try:
        return int((data_dir / "server.pid").read_text())
    except (OSError, ValueError):
        return None


def _answers_from_its_pid_file(port, data_dir):
    health = _health(port)
    return health is not None and health["pid"] == _server_pid(data_dir)


def test_a_watcher_of_another_instance_starts_that_instances_server_and_leaves_it_running(
        side_instance):
    env, port, data_dir = side_instance
    watcher = subprocess.Popen([sys.executable, "-m", "github_orchestrator.watcher", "--loop"],
                               env=env, start_new_session=True, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    server = None
    try:
        assert until(lambda: _answers_from_its_pid_file(port, data_dir), STARTED_WITHIN_SECONDS)
        server = _server_pid(data_dir)
        watcher.send_signal(signal.SIGTERM)
        watcher.wait(timeout=30)

        assert server != watcher.pid
        assert _health(port)["pid"] == server
    finally:
        watcher.kill()
        watcher.wait()
        if server is not None:
            os.kill(server, signal.SIGTERM)
            assert until(lambda: _health(port) is None, 30)
