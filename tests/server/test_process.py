import fcntl
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field

import pytest

from github_orchestrator.wiring import (
    LogsWiring,
    Server,
    ServerConfig,
    ServerControl,
    ServerWiring,
    detached,
    wire,
)
from tests.conftest import clocks_of
from tests.waiting import until

PYTHON = "/opt/python/bin/python3.14"
INSTANCE = {"GITHUB_ORCHESTRATOR_DATA_DIR": "/srv/side-data",
            "GITHUB_ORCHESTRATOR_CONFIG": "/srv/side.toml"}


@dataclass
class Started:
    argv: list[str]
    env: dict[str, str]
    exit_code: int | None = None

    def poll(self):
        return self.exit_code


@dataclass
class Spawns:
    made: list[Started] = field(default_factory=list)

    def __call__(self, argv, env, log_file):
        started = Started(list(argv), dict(env))
        self.made.append(started)
        return started


@pytest.fixture
def files(tmp_path):
    return tmp_path / "data"


def _container(files, spawns=None):
    config = ServerConfig(host="127.0.0.1", port=18799, workers=2, lock=files / "server.lock",
                          pid=files / "server.pid")
    return wire(clocks_of(sleep=lambda seconds: time.sleep(0.01)),
                LogsWiring(files / "logs", "INFO"),
                ServerWiring(config, python=PYTHON, environment=INSTANCE,
                             spawn=spawns or Spawns()))


def _held(lock):
    lock.parent.mkdir(parents=True, exist_ok=True)
    holder = open(lock, "a")
    fcntl.flock(holder, fcntl.LOCK_EX)
    return holder


def test_a_free_lock_starts_the_server_with_this_python_for_this_instance(files):
    spawns = Spawns()

    _container(files, spawns).get(Server).keep_running()

    [started] = spawns.made
    assert started.argv == [PYTHON, "-m", "github_orchestrator.server"]
    assert {name: started.env[name] for name in INSTANCE} == INSTANCE


def test_a_server_holding_the_lock_is_left_alone(files):
    spawns = Spawns()
    with _held(files / "server.lock"):
        _container(files, spawns).get(Server).keep_running()

    assert spawns.made == []


def test_a_server_still_starting_is_not_started_again(files):
    spawns = Spawns()
    server = _container(files, spawns).get(Server)

    server.keep_running()
    server.keep_running()

    assert len(spawns.made) == 1


def test_a_server_that_left_is_started_again(files):
    spawns = Spawns()
    server = _container(files, spawns).get(Server)
    server.keep_running()
    spawns.made[0].exit_code = 1

    server.keep_running()

    assert len(spawns.made) == 2


def _a_server_in(files):
    files.mkdir(parents=True, exist_ok=True)
    holder = subprocess.Popen([sys.executable, "-c", (
        "import fcntl, os, sys, time\n"
        "lock = open(sys.argv[1], 'a')\n"
        "fcntl.flock(lock, fcntl.LOCK_EX)\n"
        "open(sys.argv[2] + '.writing', 'w').write(f'{os.getpid()}\\n')\n"
        "os.replace(sys.argv[2] + '.writing', sys.argv[2])\n"
        "time.sleep(60)\n"), str(files / "server.lock"), str(files / "server.pid")])
    assert until(lambda: (files / "server.pid").exists())
    return holder


def test_the_running_servers_pid_is_the_one_it_wrote(files):
    holder = _a_server_in(files)
    try:
        assert _container(files).get(ServerControl).pid() == holder.pid
    finally:
        holder.kill()
        holder.wait()


def test_a_pid_file_no_server_holds_names_no_server(files):
    files.mkdir(parents=True)
    (files / "server.pid").write_text(f"{os.getpid()}\n")

    assert _container(files).get(ServerControl).pid() is None


def test_stopping_the_server_ends_it_and_names_its_pid(files):
    holder = _a_server_in(files)
    try:
        stopped = _container(files).get(ServerControl).stop()

        assert stopped == holder.pid
        assert holder.wait(timeout=10) == -signal.SIGTERM
    finally:
        holder.kill()
        holder.wait()


def test_stopping_with_no_server_running_signals_nothing(files):
    files.mkdir(parents=True)
    bystander = subprocess.Popen(["sleep", "60"])
    (files / "server.pid").write_text(f"{bystander.pid}\n")
    try:
        assert _container(files).get(ServerControl).stop() is None
        assert bystander.poll() is None
    finally:
        bystander.kill()
        bystander.wait()


def test_a_started_server_runs_in_a_session_of_its_own_so_it_outlives_the_watchers(tmp_path):
    log_file = tmp_path / "logs" / "server.log"
    started = detached([sys.executable, "-c", "print('serving', flush=True)\n"
                        "import time\ntime.sleep(60)"], {}, log_file)
    try:
        assert os.getsid(started.pid) == started.pid != os.getsid(0)
        assert until(lambda: log_file.read_text() == "serving\n")
    finally:
        started.kill()
        started.wait()
