import dataclasses

import pytest

from github_orchestrator.agent_runs.fake import CarryingOn, FakeAgentRuns, Outcome
from github_orchestrator.board_api.fake import FakeBoardApi
from github_orchestrator.pr_processes.fake import FakePrProcesses
from tests.builders import a_pr
from tests.pr_manager.support import manager_over, run_manager, seed_state

TERMINATED = -15


def _runs(*outcomes):
    return FakeAgentRuns(FakePrProcesses()).script(*outcomes)


def _without_claude(settings):
    return dataclasses.replace(settings, config=dataclasses.replace(settings.config,
                                                                    agents_enabled=False))


def _carry_on(board):
    return lambda: board.panel.carry_on()


def test_the_script_running_out_terminates_a_live_run(settings, tmp_path):
    runs = _runs(Outcome(finishes=False))
    board = FakeBoardApi()
    run_manager(settings, _carry_on(board), worktree=tmp_path, is_author=True, board=board,
                agent_runs=runs)
    assert runs.last_run(a_pr(1, "o/n")).exit_code == TERMINATED


def test_sigterm_terminates_a_live_run(settings, tmp_path):
    runs = _runs(Outcome(finishes=False))
    board = FakeBoardApi()
    manager = manager_over(settings, _carry_on(board), SystemExit("terminated by signal 15"),
                           worktree=tmp_path, is_author=True, board=board, agent_runs=runs)
    with pytest.raises(SystemExit):
        manager.run()
    assert runs.last_run(a_pr(1, "o/n")).exit_code == TERMINATED


def _after_an_interruption(runs):
    runs.rebase("/wt", a_pr(1, "o/n"), "became-unmergeable", reason="conflicts").interrupt()
    return runs.restarted()


def _carried_on(runs):
    return [started for started in runs.started if started.work == CarryingOn()]


def test_a_manager_carries_on_the_run_its_last_manager_was_interrupted_in(settings, tmp_path):
    seed_state(settings, title="t", url="u")
    runs = _after_an_interruption(_runs(Outcome(finishes=False), Outcome(finishes=False)))
    run_manager(settings, worktree=tmp_path, agent_runs=runs)
    [started] = _carried_on(runs)
    assert started.worktree == str(tmp_path)


def test_a_manager_carries_an_interrupted_run_on_only_once(settings, tmp_path):
    seed_state(settings, title="t", url="u")
    runs = _after_an_interruption(_runs(Outcome(finishes=False), Outcome()))
    run_manager(settings, None, None, worktree=tmp_path, agent_runs=runs)
    assert len(_carried_on(runs)) == 1


def test_a_manager_with_no_interrupted_run_carries_nothing_on(settings, tmp_path):
    seed_state(settings, title="t", url="u")
    runs = _runs()
    run_manager(settings, None, worktree=tmp_path, agent_runs=runs)
    assert runs.started == []


def test_a_manager_leaves_an_interrupted_run_alone_while_claude_is_disabled(settings, tmp_path):
    seed_state(settings, title="t", url="u")
    runs = _after_an_interruption(_runs(Outcome(finishes=False)))
    run_manager(_without_claude(settings), worktree=tmp_path, agent_runs=runs)
    assert _carried_on(runs) == []
    assert runs.restarted().interrupted(a_pr(1, "o/n")) == "became-unmergeable"


def test_sigterm_leaves_the_live_run_for_the_next_manager_to_carry_on(settings, tmp_path):
    runs = _runs(Outcome(finishes=False))
    board = FakeBoardApi()
    manager = manager_over(settings, _carry_on(board), SystemExit("terminated by signal 15"),
                           worktree=tmp_path, is_author=True, board=board, agent_runs=runs)
    with pytest.raises(SystemExit):
        manager.run()
    assert runs.restarted().interrupted(a_pr(1, "o/n")) == "manual-continue"


def test_dismissing_ends_the_live_run_for_good(settings, tmp_path):
    runs = _runs(Outcome(finishes=False))
    board = FakeBoardApi()
    run_manager(settings, _carry_on(board), lambda: board.panel.dismiss(False),
                worktree=tmp_path, is_author=True, board=board, agent_runs=runs)
    assert runs.restarted().interrupted(a_pr(1, "o/n")) is None
