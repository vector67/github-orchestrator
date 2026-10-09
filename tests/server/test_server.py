import fcntl
import json
import os
import signal
import socket
import subprocess
import sys
import urllib.error
import urllib.request

import pytest

from github_orchestrator.server.__main__ import main
from tests.waiting import until

STARTED_WITHIN_SECONDS = 60


@pytest.fixture
def instance(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text('gh_account = "octocat"\nserver_workers = 2\n\n[[repos]]\n'
                      f'repo = "acme/widgets"\nlocal_path = "{tmp_path / "widgets"}"\n')
    monkeypatch.setenv("GITHUB_ORCHESTRATOR_CONFIG", str(config))
    monkeypatch.setenv("GITHUB_ORCHESTRATOR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("GITHUB_ORCHESTRATOR_INSTANCE", raising=False)
    return tmp_path / "data"


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


def test_a_server_whose_port_is_taken_leaves_with_a_line_in_its_log(instance):
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]

        assert main(["--port", str(port)]) == 1

    assert f"port {port} is taken" in (instance / "logs" / "server.log").read_text()


def test_a_server_that_finds_the_lock_held_leaves_with_a_line_in_its_log(instance):
    instance.mkdir(parents=True)
    with open(instance / "server.lock", "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)

        assert main(["--port", str(_free_port())]) == 1

    assert "another server holds" in (instance / "logs" / "server.log").read_text()


def test_a_server_told_where_to_keep_its_own_files_leaves_none_in_the_data_directory(
        instance, tmp_path):
    own = tmp_path / "own"
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()

        assert main(["--port", str(taken.getsockname()[1]), "--files-in", str(own)]) == 1

    assert (own / "server.log").exists()
    assert not (instance / "logs" / "server.log").exists()
    assert not (instance / "server.lock").exists()


def test_the_server_answers_from_its_workers_and_stops_them_when_it_stops(instance, tmp_path):
    own, port = tmp_path / "own", _free_port()
    server = subprocess.Popen([sys.executable, "-m", "github_orchestrator.server",
                               "--port", str(port), "--files-in", str(own)],
                              env=os.environ.copy(), start_new_session=True)
    try:
        assert until(lambda: _health(port) is not None, STARTED_WITHIN_SECONDS)
        health = _health(port)
        workers = _children(server.pid)

        assert (health["serves"], health["pid"]) == ("hub", server.pid)
        assert (own / "server.pid").read_text().strip() == str(server.pid)
        assert server.pid not in workers and len(workers) >= 2
    finally:
        server.send_signal(signal.SIGTERM)
        exit_code = server.wait(timeout=30)

    assert exit_code == 0
    assert _health(port) is None
    assert not any(_alive(pid) for pid in workers)


def _children(pid):
    listing = subprocess.Popen(["pgrep", "-P", str(pid)], stdout=subprocess.PIPE, text=True)
    printed, _ = listing.communicate(timeout=10)
    return [int(child) for child in printed.split()]


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True
