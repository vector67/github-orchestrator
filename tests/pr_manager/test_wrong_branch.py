import pytest

from github_orchestrator.agent_runs.fake import FakeAgentRuns, Outcome
from github_orchestrator.board_api.fake import FakeBoardApi
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.pr_event_queue.support import ci_failed, pending_of
from tests.pr_manager.scripted_terminal import NOW, ManualClock
from tests.pr_manager.support import PR, REPO, manager_over, run_manager, seed_state
from tests.settings.support import disk_boards

THE_PR = a_pr(PR, REPO)

EXPECTED = "PROJ-30-add-archiving"
HERE = "PROJ-30-merge-archives"
REFRESH = 1
WORKING = {"type": "assistant", "message": {"content": [{"type": "text", "text": "reading the diff"}]}}


def _checked_out(worktree, branch):
    working_copies = FakeWorkingCopies()
    working_copies.add_worktree(worktree, branch)
    return working_copies


def _check_out(working_copies, worktree, branch):
    return lambda: working_copies.add_worktree(worktree, branch)


def _trouble(working_copies, now=None):
    return working_copies.verdict(THE_PR, None, expected=EXPECTED, window_open=True, now=NOW.timestamp() if now is None else now,
        manager_running=True)


def _runs_on(clock):
    return FakeAgentRuns(FakePrProcesses(), clock=clock.monotonic)


def test_a_wrong_branch_writes_the_flag(settings, tmp_path):
    seed_state(settings, branch=EXPECTED)
    working_copies = _checked_out(tmp_path, HERE)
    run_manager(settings, worktree=tmp_path, working_copies=working_copies)

    verdict = _trouble(working_copies)
    assert (verdict.here, verdict.expected, verdict.worktree) == (HERE, EXPECTED, str(tmp_path))
    assert (verdict.hands_off, verdict.seconds_left, verdict.run_working) == (False, 3600, False)


def test_a_board_is_not_served_while_frozen(settings, tmp_path):
    seed_state(settings, branch=EXPECTED)
    board = FakeBoardApi()
    run_manager(settings, None, worktree=tmp_path, is_author=True, board=board,
                working_copies=_checked_out(tmp_path, HERE))
    assert board.starts == []
    assert not disk_boards(settings.data_dir).board_wanted(THE_PR)


def test_a_wrong_branch_leaves_the_queue_alone(settings, tmp_path):
    seed_state(settings, branch=EXPECTED)
    manager = manager_over(settings, None, worktree=tmp_path,
                           working_copies=_checked_out(tmp_path, HERE))
    manager.event_queue.add(THE_PR, ci_failed('tests', 'boom'))
    manager.run()
    assert len(pending_of(manager.event_queue, THE_PR)) == 1
    assert manager.agent_runs.started == []


def _write_a_snapshot_without_a_branch(settings):
    seed_state(settings, url="https://example/83")


def _write_the_expected_branch(settings):
    seed_state(settings, branch=EXPECTED)


@pytest.mark.parametrize(("snapshot", "branch_here"), [
    (_write_the_expected_branch, EXPECTED),
    (_write_the_expected_branch, None),
    (_write_a_snapshot_without_a_branch, HERE),
], ids=["matching branch", "unknown branch here", "snapshot without a branch"])
def test_runs_normally_unless_the_branch_is_known_to_differ(settings, tmp_path, snapshot, branch_here):
    snapshot(settings)
    working_copies = _checked_out(tmp_path, branch_here)
    manager = manager_over(settings, worktree=tmp_path, working_copies=working_copies)
    manager.event_queue.add(THE_PR, ci_failed('tests', 'boom'))
    manager.run()

    assert pending_of(manager.event_queue, THE_PR) == []
    assert len(manager.agent_runs.started) == 1
    assert _trouble(working_copies) is None


def test_the_right_branch_clears_a_stale_flag(settings, tmp_path):
    seed_state(settings, branch=EXPECTED)
    working_copies = _checked_out(tmp_path, "other")
    working_copies.report_branch(THE_PR, str(tmp_path), EXPECTED, now=1.0, run_output_at=None)
    working_copies.add_worktree(tmp_path, EXPECTED)
    run_manager(settings, worktree=tmp_path, working_copies=working_copies)

    assert _trouble(working_copies) is None


def test_a_live_run_keeps_going_while_frozen(settings, tmp_path):
    seed_state(settings, branch=EXPECTED)
    clock = ManualClock()
    working_copies = _checked_out(tmp_path, EXPECTED)
    agent_runs = _runs_on(clock).script(Outcome(events=(WORKING,), finishes=False))
    manager = manager_over(settings, _check_out(working_copies, tmp_path, HERE),
                           _check_out(working_copies, tmp_path, EXPECTED), None,
                           worktree=tmp_path, clock=clock, working_copies=working_copies,
                           agent_runs=agent_runs, is_author=True)
    manager.event_queue.add(THE_PR, ci_failed('tests', 'boom'))
    manager.run()

    assert manager.board.panel.dashboard().working_on == "ci-failed"


def test_a_live_run_is_recorded_on_the_flag(settings, tmp_path):
    seed_state(settings, branch=EXPECTED)
    clock = ManualClock()
    working_copies = _checked_out(tmp_path, EXPECTED)

    def check_out_the_wrong_branch_and_wait():
        working_copies.add_worktree(tmp_path, HERE)
        clock.advance(12)

    manager = manager_over(settings, check_out_the_wrong_branch_and_wait, worktree=tmp_path,
                           clock=clock, working_copies=working_copies,
                           agent_runs=_runs_on(clock).script(Outcome(finishes=False)))
    manager.event_queue.add(THE_PR, ci_failed('tests', 'boom'))
    manager.run()

    verdict = _trouble(working_copies, now=NOW.timestamp() + 12 + REFRESH)
    assert verdict.run_working is True
    assert verdict.seconds_left == 3600


def test_a_run_that_finishes_while_frozen_is_recorded_as_gone(settings, tmp_path):
    seed_state(settings, branch=EXPECTED)
    clock = ManualClock()
    working_copies = _checked_out(tmp_path, EXPECTED)
    agent_runs = _runs_on(clock).script(Outcome(finishes=True))
    manager = manager_over(settings, _check_out(working_copies, tmp_path, HERE),
                           worktree=tmp_path, clock=clock, working_copies=working_copies,
                           agent_runs=agent_runs)
    manager.event_queue.add(THE_PR, ci_failed('tests', 'boom'))
    manager.run()

    assert len(agent_runs.ledger) == 1
    assert _trouble(working_copies).run_working is False


def test_the_grace_countdown_runs_from_the_first_freeze(settings, tmp_path):
    seed_state(settings, branch=EXPECTED)
    clock = ManualClock()
    working_copies = _checked_out(tmp_path, HERE)
    run_manager(settings, lambda: clock.advance(1200), None, worktree=tmp_path,
                clock=clock, working_copies=working_copies)

    assert _trouble(working_copies).seconds_left == 3600


def test_an_older_flag_keeps_its_start_and_the_countdown_reaches_zero(settings, tmp_path):
    seed_state(settings, branch=EXPECTED)
    working_copies = _checked_out(tmp_path, HERE)
    working_copies.report_branch(THE_PR, str(tmp_path), EXPECTED, now=1000.0, run_output_at=None)
    run_manager(settings, None, None, worktree=tmp_path, working_copies=working_copies)

    assert _trouble(working_copies, now=1000.0).seconds_left == 3600
    assert _trouble(working_copies).seconds_left == 0


def test_a_repeated_freeze_logs_once(settings, tmp_path, caplog):
    seed_state(settings, branch=EXPECTED)
    with caplog.at_level("ERROR"):
        run_manager(settings, None, None, None, None, worktree=tmp_path,
                    working_copies=_checked_out(tmp_path, HERE))
    assert len([r for r in caplog.records if "freezing" in r.getMessage()]) == 1


def test_a_freeze_on_another_branch_logs_again(settings, tmp_path, caplog):
    seed_state(settings, branch=EXPECTED)
    working_copies = _checked_out(tmp_path, HERE)
    with caplog.at_level("ERROR"):
        run_manager(settings, None, _check_out(working_copies, tmp_path, "PROJ-30-archive-filter"),
                    worktree=tmp_path, working_copies=working_copies)
    assert len([r for r in caplog.records if "freezing" in r.getMessage()]) == 2


def test_a_release_request_shows_and_survives_the_next_tick(settings, tmp_path):
    seed_state(settings, branch=EXPECTED)
    working_copies = _checked_out(tmp_path, HERE)
    run_manager(settings, lambda: working_copies.request_release(THE_PR), None,
                worktree=tmp_path, working_copies=working_copies)

    assert _trouble(working_copies).release_requested is True


def test_the_right_branch_drops_a_release_request(settings, tmp_path):
    seed_state(settings, branch=EXPECTED)
    working_copies = _checked_out(tmp_path, HERE)
    run_manager(settings, lambda: working_copies.request_release(THE_PR),
                _check_out(working_copies, tmp_path, EXPECTED),
                worktree=tmp_path, working_copies=working_copies)

    assert _trouble(working_copies) is None


def test_git_from_the_board_while_frozen_is_refused_and_runs_nothing(settings, tmp_path):
    seed_state(settings, branch=EXPECTED)
    ran = []
    board = FakeBoardApi()
    answers = []
    working_copies = _checked_out(tmp_path, EXPECTED)
    run_manager(settings, _check_out(working_copies, tmp_path, HERE),
                lambda: answers.append(board.panel.run_git("p")), None,
                worktree=tmp_path, is_author=True, board=board,
                working_copies=working_copies, run=lambda argv, **kwargs: ran.append(argv))

    [(exit_code, lines, _)] = answers
    assert exit_code != 0
    assert lines == ["refused: the worktree holds another PR's branch"]
    assert ran == []


def test_a_terminal_from_the_board_while_frozen_is_refused_and_opens_nothing(settings, tmp_path):
    seed_state(settings, branch=EXPECTED)
    board = FakeBoardApi()
    windows = FakePrProcesses()
    answers = []
    working_copies = _checked_out(tmp_path, EXPECTED)
    run_manager(settings, _check_out(working_copies, tmp_path, HERE),
                lambda: answers.append(board.panel.open_terminal("a")), None,
                worktree=tmp_path, is_author=True, board=board,
                working_copies=working_copies, pr_processes=windows)

    assert answers == ["refused: the worktree holds another PR's branch"]
    assert windows.sessions == {}


def _interrupted_runs():
    runs = FakeAgentRuns(FakePrProcesses()).script(Outcome(finishes=False), Outcome(finishes=False))
    runs.rebase("/wt", THE_PR, "became-unmergeable", reason="conflicts").interrupt()
    return runs.restarted()


def test_an_interrupted_run_is_not_carried_on_into_a_wrong_branch(settings, tmp_path):
    seed_state(settings, branch=EXPECTED)
    runs = _interrupted_runs()
    run_manager(settings, None, worktree=tmp_path, working_copies=_checked_out(tmp_path, HERE),
                agent_runs=runs)
    assert len(runs.started) == 1


def test_an_interrupted_run_is_carried_on_once_the_branch_is_back(settings, tmp_path):
    seed_state(settings, branch=EXPECTED)
    working_copies = _checked_out(tmp_path, HERE)
    runs = _interrupted_runs()
    run_manager(settings, _check_out(working_copies, tmp_path, EXPECTED), None,
                worktree=tmp_path, working_copies=working_copies, agent_runs=runs)
    assert len(runs.started) == 2
