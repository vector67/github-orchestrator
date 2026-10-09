import contextlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from github_orchestrator.pr_processes import ManagerPane, PrProcesses
from github_orchestrator.terminal_sessions import Terminals
from github_orchestrator.terminal_sessions.fake import FakeTerminals
from github_orchestrator.wiring import make_container
from tests.builders import a_pr
from tests.disk_layout import manager_record_file
from tests.pr_processes.scripted_processes import ScriptedProcesses
from tests.pr_processes.support import background_pr_processes
from tests.waiting import until

REPO = "octocat/hello-world"
THE_PR = a_pr(7, REPO)
OTHER_PR = a_pr(8, REPO)
MANAGER = f"{sys.executable} -m github_orchestrator.pr_manager --repo {REPO} --pr 7"


@pytest.fixture
def processes():
    return ScriptedProcesses()


@pytest.fixture
def terminals():
    return FakeTerminals()


@pytest.fixture
def sessions(terminals):
    return terminals.of(THE_PR)


@pytest.fixture
def windows(settings, processes, terminals):
    return background_pr_processes(settings, processes, terminals)


@pytest.fixture
def worktree(tmp_path):
    path = tmp_path / "feature-7"
    path.mkdir()
    return path


@pytest.fixture
def record(settings):
    return manager_record_file(settings.pr_managers_dir, THE_PR)


def test_opening_starts_the_manager_detached_in_the_worktree(
        settings, windows, processes, worktree):
    windows.open(THE_PR, worktree)

    [started] = processes.spawned
    assert started.command == MANAGER
    assert started.cwd == str(worktree)
    assert started.own_session is True
    assert started.output == str(settings.logs_dir / "pr_managers" / "octocat" / "hello-world"
                                 / "7.log")
    assert settings.child_environment().items() <= started.env.items()


def test_a_manager_that_exits_by_itself_reads_exited(windows, processes, worktree):
    windows.open(THE_PR, worktree)

    processes.exit(processes.pid_of(MANAGER))

    assert windows.manager(THE_PR) is ManagerPane.EXITED
    assert windows.manager_path(THE_PR) == str(worktree)


@pytest.mark.parametrize("other_program", [
    "vim notes.md",
    MANAGER + "0",
])
def test_a_pid_reused_by_another_program_reads_exited_and_is_never_signalled(
        windows, processes, worktree, other_program):
    windows.open(THE_PR, worktree)
    pid = processes.pid_of(MANAGER)
    processes.exit(pid)
    processes.reuse(pid, other_program)

    assert windows.manager(THE_PR) is ManagerPane.EXITED
    assert windows.stop_managers() == []
    windows.close(THE_PR)
    assert processes.signalled == []
    assert processes.table[pid].command == other_program


def test_a_manager_started_with_the_old_headless_flag_is_still_found_and_stopped(
        windows, processes, worktree):
    windows.open(THE_PR, worktree)
    pid = processes.pid_of(MANAGER)
    processes.reuse(pid, f"{MANAGER} --headless")

    assert windows.manager(THE_PR) is ManagerPane.RUNNING
    assert windows.stop_managers() == [THE_PR]
    assert processes.signalled == [pid]


def test_reviving_a_live_manager_starts_no_second_one(windows, processes, worktree):
    windows.open(THE_PR, worktree)

    windows.revive(THE_PR)

    assert len(processes.spawned) == 1


def test_a_revived_manager_starts_again_in_the_recorded_worktree(windows, processes,
                                                                  worktree):
    windows.open(THE_PR, worktree)
    processes.exit(processes.pid_of(MANAGER))

    windows.revive(THE_PR)

    assert [started.cwd for started in processes.spawned] == [str(worktree), str(worktree)]
    assert windows.manager(THE_PR) is ManagerPane.RUNNING


@pytest.mark.parametrize("stop", [
    lambda windows: windows.close(THE_PR),
    lambda windows: windows.detach(THE_PR),
])
def test_closing_or_detaching_stops_the_running_manager(windows, processes, worktree, stop):
    windows.open(THE_PR, worktree)
    pid = processes.pid_of(MANAGER)

    stop(windows)

    assert processes.signalled == [pid]
    assert pid not in processes.table


@pytest.mark.parametrize("stop", [
    lambda windows: windows.close(THE_PR),
    lambda windows: windows.detach(THE_PR),
])
def test_closing_or_detaching_hangs_up_that_pull_requests_terminal_sessions(
        windows, terminals, worktree, stop):
    windows.open(THE_PR, worktree)
    windows.open(OTHER_PR, worktree)
    windows.split(THE_PR, str(worktree), ["git", "add", "-p"])
    windows.split(OTHER_PR, str(worktree), ["git", "commit"])

    stop(windows)

    assert terminals.of(THE_PR).listed() == []
    assert [session.argv for session in terminals.of(OTHER_PR).listed()] == [("git", "commit")]


@pytest.mark.parametrize("text", [
    "not json", "[]", '{"worktree": "/wt"}',
    '{"pid": 1, "worktree": "/wt"}', '{"pid": true, "worktree": "/wt"}',
    '{"pid": 4000, "worktree": 3}',
])
def test_a_record_that_cannot_be_read_is_unreadable_and_nothing_is_signalled(
        windows, processes, record, text):
    record.parent.mkdir(parents=True)
    record.write_text(text)

    assert windows.manager(THE_PR) is ManagerPane.UNREADABLE
    assert windows.manager_path(THE_PR) is None
    assert windows.stop_managers() == []
    windows.revive(THE_PR)
    assert processes.calls == []


def test_an_unreadable_record_is_removed_by_a_close(windows, record):
    record.parent.mkdir(parents=True)
    record.write_text("not json")

    assert windows.close(THE_PR) is True

    assert windows.manager(THE_PR) is ManagerPane.NO_WINDOW


def test_an_unreadable_record_is_detached_under_the_defunct_name(windows, record):
    record.parent.mkdir(parents=True)
    record.write_text("not json")

    assert windows.detach(THE_PR) == "hello-world/#7-defunct"

    assert windows.manager(THE_PR) is ManagerPane.NO_WINDOW


def test_a_split_starts_a_terminal_session_in_the_worktree_it_names(
        windows, sessions, processes, worktree, tmp_path):
    windows.open(THE_PR, worktree)
    thread_worktree = tmp_path / "thread-7"

    assert windows.split(THE_PR, str(worktree), ["git", "add", "-p"]) is None
    assert windows.split(THE_PR, str(thread_worktree), ["claude", "/rebase-on-main"]) is None

    assert sessions.started() == [(str(worktree), ("git", "add", "-p")),
                                  (str(thread_worktree), ("claude", "/rebase-on-main"))]
    assert len(processes.spawned) == 1


def test_a_split_whose_session_cannot_start_is_refused_with_the_reason(
        windows, sessions, worktree):
    sessions.refusal = "No such file or directory"

    refused = windows.split(THE_PR, str(worktree), ["git", "commit"])

    assert refused is not None and "No such file or directory" in refused


STAND_IN = Path(__file__).parents[1] / "stubs" / "background_manager" / "python"


def _recorded_pid(settings):
    return json.loads(manager_record_file(settings.pr_managers_dir, THE_PR).read_text())["pid"]


def _parent_of(pid):
    listed = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True)
    return int(listed.stdout) if listed.returncode == 0 else None


def _alive(pid):
    return subprocess.run(["ps", "-p", str(pid)], capture_output=True).returncode == 0


@pytest.mark.no_replay
def test_a_real_manager_process_is_detached_logged_stopped_revived_and_closed(
        settings, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "executable", str(STAND_IN))
    worktree = tmp_path / "feature-7"
    worktree.mkdir()
    output = settings.logs_dir / "pr_managers" / "octocat" / "hello-world" / "7.log"
    windows = background_pr_processes(settings, subprocess.run, FakeTerminals())
    started = []
    try:
        windows.open(THE_PR, worktree)
        started.append(_recorded_pid(settings))

        assert windows.manager(THE_PR) is ManagerPane.RUNNING
        assert _parent_of(started[0]) != os.getpid()
        assert until(lambda: "stdin=" in output.read_text())
        assert output.read_text().splitlines() == [
            f"cwd={os.path.realpath(worktree)}",
            f"data={settings.data_dir}",
            f"args=-m github_orchestrator.pr_manager --repo {REPO} --pr 7",
            "stdin=empty",
        ]

        assert windows.stop_managers() == [THE_PR]
        assert until(lambda: windows.manager(THE_PR) is ManagerPane.EXITED)
        assert not _alive(started[0])

        windows.revive(THE_PR)
        started.append(_recorded_pid(settings))
        assert windows.manager(THE_PR) is ManagerPane.RUNNING

        assert windows.close(THE_PR) is True
        assert windows.manager(THE_PR) is ManagerPane.NO_WINDOW
        assert until(lambda: not _alive(started[1]))
    finally:
        for pid in started:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)


def test_the_pr_processes_a_config_builds_open_their_sessions_in_the_terminal_tab(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('gh_account = "hubot"\n[[repos]]\n'
                      'repo = "hubot/robots"\nlocal_path = "~/repositories/robots"\n')
    container = make_container({"GITHUB_ORCHESTRATOR_CONFIG": str(config),
                                "GITHUB_ORCHESTRATOR_DATA_DIR": str(tmp_path / "data")},
                               tmp_path)

    assert container.get(PrProcesses).split(THE_PR, str(tmp_path), ["sleep", "30"]) is None

    sessions = container.get(Terminals).of(THE_PR)
    [session] = sessions.listed()
    sessions.hang_up()
    assert (session.argv, session.worktree) == (("sleep", "30"), str(tmp_path))
