import pytest

from tests.cli.support import SERVER_PID

HUB = "http://127.0.0.1:8720"
STOPPING = "Stopping the server"
BACK = "Confirming the server came back"


@pytest.fixture
def serving(machine, restartable):
    return machine


def test_restart_all_stops_the_server_before_it_restarts_the_watcher(serving, run_cli):
    running_when_the_watcher_restarted = []
    serving.system.on_kickstart = lambda: running_when_the_watcher_restarted.append(
        serving.server.pid)

    ran = run_cli("restart-all")

    assert ran.under(STOPPING) == f"Stopped the server, pid {SERVER_PID}.\n"
    assert running_when_the_watcher_restarted == [None]


def test_restart_all_waits_for_the_hub_to_answer_from_a_new_server(serving, run_cli):
    ran = run_cli("restart-all")

    assert ran.code == 0, ran.out
    assert ran.under(BACK) == f"The hub answers from the new server, pid {SERVER_PID + 1}.\n"


def test_restart_all_with_no_server_running_waits_for_the_one_the_watcher_starts(
        machine, run_cli, restartable):
    machine.server.kill(SERVER_PID, 15)
    machine.while_asleep.append(lambda: machine.server.start(SERVER_PID + 7))
    machine.hub_pid = SERVER_PID + 7

    ran = run_cli("restart-all")

    assert ran.code == 0, ran.out
    assert ran.under(STOPPING) == "No server running.\n"
    assert ran.under(BACK) == f"The hub answers from the new server, pid {SERVER_PID + 7}.\n"


def test_a_server_that_does_not_come_back_fails_the_restart_and_names_its_log(serving, run_cli):
    serving.server_comes_back = False

    ran = run_cli("restart-all")

    assert ran.code == 1
    assert "did not answer /api/health from a new server" in ran.under(BACK)
    assert str(serving.data_dir / "logs" / "server.log") in ran.under(BACK)
