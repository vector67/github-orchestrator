import os
import secrets
import subprocess
import time

import pytest

from github_orchestrator.terminal_sessions import TerminalSessions
from github_orchestrator.terminal_sessions.fake import (
    FakeTerminals,
    FakeTerminalSessions,
)
from tests.builders import a_pr
from tests.terminal_sessions.support import real_terminal_sessions, real_terminals
from tests.waiting import until

FOREVER = ["sh", "-c", "while :; do sleep 0.1; done"]
SEVEN = a_pr(7, "octocat/hello-world")
EIGHT = a_pr(8, "octocat/hello-world")


def _everything(connection, seconds=10.0):
    heard = b""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        chunk = connection.read(0.1)
        if chunk is None:
            return heard
        heard += chunk
    raise AssertionError(f"the session never ended; it printed {heard!r}")


def _heard(connection, wanted, seconds=10.0):
    heard = b""
    deadline = time.monotonic() + seconds
    while wanted not in heard and time.monotonic() < deadline:
        chunk = connection.read(0.1)
        if chunk is None:
            break
        heard += chunk
    return heard


def _interrupted(sessions: TerminalSessions) -> bool:
    for session in sessions.listed():
        connection = sessions.attach(session.id)
        if connection is not None:
            connection.write(b"\x03")
            connection.close()
    return sessions.listed() == []


def _ended_everything(sessions: TerminalSessions) -> None:
    assert until(lambda: _interrupted(sessions))


def _working_in(marked: str) -> list[str]:
    listed = subprocess.Popen(["lsof", "-a", "-d", "cwd", "-F", "pn", "-u", str(os.getuid())],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    printed, _ = listed.communicate()
    found, pid = [], ""
    for line in printed.splitlines():
        if line.startswith("p"):
            pid = line[1:]
        elif line.startswith("n") and marked in line:
            found.append(f"{pid} in {line[1:]}")
    return found


@pytest.fixture(scope="module", autouse=True)
def worktree_name():
    name = f"feature-7-{secrets.token_hex(4)}"
    yield name
    assert until(lambda: _working_in(name) == [], seconds=3), _working_in(name)


@pytest.fixture
def real(settings):
    sessions = real_terminal_sessions(settings)
    yield sessions
    _ended_everything(sessions)


@pytest.fixture(params=["fake", "real"])
def any_sessions(request, settings):
    if request.param == "fake":
        yield FakeTerminalSessions()
        return
    sessions = real_terminal_sessions(settings)
    yield sessions
    _ended_everything(sessions)


@pytest.fixture(params=["fake", "real"])
def any_terminals(request, settings):
    if request.param == "fake":
        yield FakeTerminals()
        return
    terminals = real_terminals(settings)
    yield terminals
    for pr in (SEVEN, EIGHT):
        _ended_everything(terminals.of(pr))


@pytest.fixture
def worktree(tmp_path, worktree_name):
    path = tmp_path / worktree_name
    path.mkdir()
    return path


def test_a_started_session_is_listed_with_its_command_and_worktree(any_sessions, worktree):
    started = any_sessions.start(str(worktree), FOREVER)

    [listed] = any_sessions.listed()
    assert (listed.id, listed.argv, listed.worktree) == (started, tuple(FOREVER), str(worktree))


def test_sessions_are_listed_in_the_order_they_started(any_sessions, worktree):
    first = any_sessions.start(str(worktree), FOREVER)
    second = any_sessions.start(str(worktree), ["sh", "-c", "sleep 30"])

    assert [session.id for session in any_sessions.listed()] == [first, second]


def test_a_session_nobody_started_cannot_be_attached(any_sessions):
    assert any_sessions.attach("no-such-session") is None


def test_closing_the_last_connection_leaves_the_session_to_be_attached_again(any_sessions, worktree):
    started = any_sessions.start(str(worktree), FOREVER)
    one, other = any_sessions.attach(started), any_sessions.attach(started)

    one.close()
    other.close()
    if not isinstance(any_sessions, FakeTerminalSessions):
        time.sleep(0.1)

    assert [session.id for session in any_sessions.listed()] == [started]
    assert any_sessions.attach(started) is not None


def test_a_session_prints_what_its_command_prints_and_ends_with_its_exit_code(real, worktree):
    connection = real.attach(real.start(str(worktree), ["sh", "-c", "read go; printf hello; exit 3"]))

    connection.write(b"\r")

    assert b"hello" in _everything(connection)
    assert connection.exit_code() == 3
    assert real.listed() == []


def test_a_session_runs_in_its_worktree(real, worktree):
    connection = real.attach(real.start(str(worktree), ["sh", "-c", "read go; pwd"]))

    connection.write(b"\r")

    assert os.path.realpath(worktree).encode() in _everything(connection)


def test_what_the_page_types_reaches_the_command(real, worktree):
    connection = real.attach(real.start(str(worktree),
                                        ["sh", "-c", "read line; echo got:$line"]))

    connection.write(b"typed\r")

    assert b"got:typed" in _everything(connection)


def test_a_session_runs_on_a_terminal_sized_by_the_page(real, worktree):
    connection = real.attach(real.start(str(worktree),
                                        ["sh", "-c", "read go; stty size; tty -s && echo on-a-tty"]))

    connection.resize(100, 30)
    connection.write(b"\r")

    heard = _everything(connection)
    assert b"30 100" in heard
    assert b"on-a-tty" in heard


def test_the_terminal_owns_the_command_so_ctrl_c_interrupts_it(real, worktree):
    connection = real.attach(real.start(
        str(worktree), ["sh", "-c", "trap 'echo interrupted; exit 0' INT; echo ready; "
                                    "while :; do sleep 0.1; done"]))
    assert b"ready" in _heard(connection, b"ready")

    connection.write(b"\x03")

    assert b"interrupted" in _everything(connection)


def test_a_session_is_an_xterm_with_the_programs_environment(real, settings, worktree):
    connection = real.attach(real.start(
        str(worktree), ["sh", "-c", "echo term=$TERM; echo data=$GITHUB_ORCHESTRATOR_DATA_DIR; "
                                    "while :; do sleep 0.1; done"]))

    data = f"data={settings.data_dir}".encode()
    heard = _heard(connection, data)
    assert b"term=xterm-256color" in heard
    assert data in heard


def test_a_later_connection_is_shown_what_the_session_printed_before_it(real, worktree):
    started = real.start(str(worktree), ["sh", "-c", "echo early; while :; do sleep 0.1; done"])
    first = real.attach(started)
    assert b"early" in _heard(first, b"early")

    later = real.attach(started)

    assert b"early" in _heard(later, b"early")
    first.close()
    later.close()


def test_closing_the_last_connection_leaves_the_command_running(real, worktree, tmp_path):
    marker = tmp_path / "still-running"
    connection = real.attach(real.start(
        str(worktree), ["sh", "-c", f"while :; do touch {marker}; sleep 0.1; done"]))
    assert until(marker.exists)

    connection.close()
    time.sleep(0.1)
    marker.unlink()

    assert until(marker.exists)


def test_a_connection_resuming_after_what_it_saw_is_shown_only_what_came_after(
        real, worktree):
    started = real.start(str(worktree), ["sh", "-c", "echo first; read go; echo second; "
                                                     "while :; do sleep 0.1; done"])
    first = real.attach(started)
    seen = _heard(first, b"first")
    first.close()

    later = real.attach(started, after=len(seen))
    later.write(b"\r")

    heard = _heard(later, b"second")
    assert b"second" in heard
    assert b"first" not in heard
    later.close()


def test_a_reattached_connection_is_shown_what_the_session_printed_while_nobody_watched(
        real, worktree):
    started = real.start(str(worktree), ["sh", "-c", "read go; echo unwatched; "
                                                     "while :; do sleep 0.1; done"])
    first = real.attach(started)
    first.write(b"\r")
    first.close()

    later = real.attach(started)

    assert b"unwatched" in _heard(later, b"unwatched")
    later.close()


def test_a_session_no_page_connects_to_ends_after_the_wait(settings, worktree):
    sessions = real_terminal_sessions(settings, first_connection_seconds=0.05)
    started = sessions.start(str(worktree), FOREVER)

    assert until(lambda: sessions.listed() == [], seconds=5)
    assert sessions.attach(started) is None


def _parent_of(pid: int) -> int:
    listed = subprocess.Popen(["ps", "-o", "ppid=", "-p", str(pid)],
                              stdout=subprocess.PIPE, text=True)
    printed, _ = listed.communicate()
    return int(printed)


def test_a_session_started_elsewhere_is_listed_and_attached_with_what_it_printed(
        settings, worktree):
    elsewhere = real_terminal_sessions(settings)
    started = elsewhere.start(str(worktree), ["sh", "-c", "echo before; while :; do sleep 0.1; done"])
    assert b"before" in _heard(elsewhere.attach(started), b"before")

    here = real_terminal_sessions(settings)

    assert [session.id for session in here.listed()] == [started]
    assert b"before" in _heard(here.attach(started), b"before")
    _ended_everything(here)


def test_a_session_is_held_by_no_process_of_the_one_that_started_it(real, worktree):
    connection = real.attach(real.start(str(worktree), ["sh", "-c", "echo holder=$PPID; "
                                                                    "while :; do sleep 0.1; done"]))
    heard = _heard(connection, b"\n", seconds=10).decode()
    holder = int(heard.split("holder=")[1].split()[0])

    assert _parent_of(holder) == 1
    assert os.getpgid(holder) != os.getpgid(0)
    connection.close()


def test_a_session_in_a_missing_worktree_does_not_start(real, tmp_path):
    with pytest.raises(OSError):
        real.start(str(tmp_path / "gone"), ["pwd"])

    assert real.listed() == []


def test_hanging_up_ends_every_session_it_lists(any_sessions, worktree):
    first = any_sessions.start(str(worktree), FOREVER)
    any_sessions.start(str(worktree), FOREVER)

    any_sessions.hang_up()

    assert until(lambda: any_sessions.listed() == [])
    assert any_sessions.attach(first) is None


def test_each_pull_request_has_terminal_sessions_of_its_own(any_terminals, worktree):
    started = any_terminals.of(SEVEN).start(str(worktree), FOREVER)

    assert [session.id for session in any_terminals.of(SEVEN).listed()] == [started]
    assert any_terminals.of(EIGHT).listed() == []
    assert any_terminals.of(EIGHT).attach(started) is None


def test_everywhere_holds_the_terminal_sessions_of_every_pull_request(any_terminals, worktree):
    in_seven = any_terminals.of(SEVEN).start(str(worktree), FOREVER)
    in_eight = any_terminals.of(EIGHT).start(str(worktree), FOREVER)

    listed = {session.id for sessions in any_terminals.everywhere() for session in sessions.listed()}

    assert listed == {in_seven, in_eight}


def _running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _pid_of_command(sessions, worktree, pid_file, loop):
    sessions.start(str(worktree), ["sh", "-c", f"echo $$ > {pid_file}; {loop}"])
    assert until(lambda: pid_file.exists() and pid_file.read_text().strip() != "")
    return int(pid_file.read_text())


def test_hanging_up_ends_the_command_itself(real, worktree, tmp_path):
    command = _pid_of_command(real, worktree, tmp_path / "pid", "while :; do sleep 0.1; done")

    real.hang_up()

    assert until(lambda: not _running(command))


def _processes_carrying(marker: str) -> list[str]:
    listed = subprocess.Popen(["ps", "-Ao", "pid=,args="], stdout=subprocess.PIPE, text=True)
    printed, _ = listed.communicate()
    return [line for line in printed.splitlines() if marker in line]


def test_hanging_up_straight_after_starting_leaves_no_command_behind(real, worktree):
    marker = f"left-behind-{os.getpid()}-{time.monotonic_ns()}"
    for _ in range(5):
        real.start(str(worktree), ["sh", "-c", f"trap '' INT; while :; do sleep 0.1; done # {marker}"])

    real.hang_up()

    assert until(lambda: real.listed() == [])
    assert until(lambda: _processes_carrying(marker) == [], seconds=3), _processes_carrying(marker)


def test_hanging_up_ends_a_command_that_ignores_ctrl_c(real, worktree, tmp_path):
    command = _pid_of_command(real, worktree, tmp_path / "pid",
                              "trap '' INT; while :; do sleep 0.1; done")

    real.hang_up()

    assert until(lambda: not _running(command))
