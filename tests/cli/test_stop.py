from github_orchestrator.pr_processes import ManagerPane
from tests.builders import a_pr
from tests.cli.scripted_system import Job

WATCHER = "com.github-orchestrator.watcher"
SECOND = "com.github-orchestrator.watcher.second"
IN_APP = a_pr(12, "acme/app")
IN_OTHER_APP = a_pr(13, "acme/app")
IN_SECOND = a_pr(22, "acme/gadgets")
FOREVER = ["zsh", "-l"]


def _launchctl(machine):
    return [call.cmd[1:] for call in machine.system.calls if call.cmd[0] == "launchctl"]


def _open_terminals(machine, *prs):
    return [machine.terminals.of(pr).start("/tmp/feature", FOREVER) for pr in prs]


def _still_open(machine):
    return [session for sessions in machine.terminals.held.values() for session in sessions.listed()]


def test_stop_unloads_the_watcher_and_then_stops_the_agent_managers(
        machine, run_cli, restartable, tmp_path):
    worktree = tmp_path / "feature-12"
    worktree.mkdir()
    machine.processes().open(IN_APP, worktree)

    ran = run_cli("stop")

    assert ran.code == 0, ran.out
    assert ran.out == (
        "==> Stopping the watcher\n"
        "Stopped the watcher daemon.\n"
        "==> Stopping the agent managers\n"
        "Stopped 1 agent manager(s): acme/app#12.\n"
        "==> Closing the terminal sessions\n"
        "No terminal sessions open.\n")
    assert _launchctl(machine) == [
        ["print", f"gui/501/{WATCHER}"],
        ["bootout", f"gui/501/{WATCHER}"]]
    assert machine.system.job is None
    assert machine.processes().manager(IN_APP) is ManagerPane.EXITED
    assert machine.prompts == []


def test_stop_says_so_when_the_watcher_was_not_running(machine, run_cli, restartable):
    machine.system.job = None

    ran = run_cli("stop")

    assert ran.code == 0, ran.out
    assert ran.under("Stopping the watcher") == "The watcher was not running.\n"
    assert ran.under("Stopping the agent managers") == "No agent manager processes running.\n"
    assert ["bootout", f"gui/501/{WATCHER}"] not in _launchctl(machine)


def test_stop_fails_when_launchd_refuses_to_unload_the_watcher(machine, run_cli, restartable):
    machine.system.bootout_exit = 5

    ran = run_cli("stop")

    assert ran.code == 1
    assert ran.out.endswith(f"launchctl bootout gui/501/{WATCHER} failed.\nBoot-out failed\n")


def test_stop_closes_the_terminal_sessions_when_asked_to(machine, run_cli, restartable):
    _open_terminals(machine, IN_APP, IN_OTHER_APP)
    machine.answers = ["y"]

    ran = run_cli("stop")

    assert ran.code == 0, ran.out
    assert machine.prompts == ["Close the 2 terminal session(s) still open? [y/N] "]
    assert ran.under("Closing the terminal sessions") == "Closed 2 terminal session(s).\n"
    assert _still_open(machine) == []


def test_stop_leaves_the_terminal_sessions_open_unless_told_to_close_them(
        machine, run_cli, restartable):
    _open_terminals(machine, IN_APP)
    machine.answers = [""]

    ran = run_cli("stop")

    assert ran.code == 0, ran.out
    assert ran.under("Closing the terminal sessions") == "Left 1 terminal session(s) open.\n"
    assert len(_still_open(machine)) == 1


def test_stop_leaves_the_terminal_sessions_open_when_nobody_can_answer(
        machine, run_cli, restartable):
    _open_terminals(machine, IN_APP)
    machine.answers = [EOFError]

    ran = run_cli("stop")

    assert ran.code == 0, ran.out
    assert ran.under("Closing the terminal sessions") == "Left 1 terminal session(s) open.\n"
    assert len(_still_open(machine)) == 1


def test_stop_force_closes_the_terminal_sessions_without_asking(machine, run_cli, restartable):
    _open_terminals(machine, IN_APP, IN_OTHER_APP)

    ran = run_cli("stop", "-f")

    assert ran.code == 0, ran.out
    assert machine.prompts == []
    assert ran.under("Closing the terminal sessions") == "Closed 2 terminal session(s).\n"
    assert _still_open(machine) == []


def test_stop_all_stops_every_other_instance_after_this_one(machine, run_cli, restartable, tmp_path):
    other = machine.another_instance("second")
    machine.system.jobs[SECOND] = Job()
    worktree = tmp_path / "feature-22"
    worktree.mkdir()
    other.processes().open(IN_SECOND, worktree)
    _open_terminals(other, IN_SECOND)

    ran = run_cli("stop", "--all", "--force")

    assert ran.code == 0, ran.out
    assert ran.out.endswith(
        "==> Stopping the watcher for second\n"
        "Stopped the watcher daemon.\n"
        "==> Stopping the agent managers for second\n"
        "Stopped 1 agent manager(s): acme/gadgets#22.\n"
        "==> Closing the terminal sessions for second\n"
        "Closed 1 terminal session(s).\n")
    assert machine.system.jobs[SECOND] is None
    assert other.processes().manager(IN_SECOND) is ManagerPane.EXITED
    assert _still_open(other) == []


def test_stop_leaves_the_other_instances_running_without_all(machine, run_cli, restartable):
    machine.another_instance("second")
    machine.system.jobs[SECOND] = Job()

    ran = run_cli("stop")

    assert ran.code == 0, ran.out
    assert "for second" not in ran.out
    assert machine.system.jobs[SECOND] == Job()
