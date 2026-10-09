import logging
import os
import signal

import pytest

from github_orchestrator.board_api.fake import FakeBoardApi
from github_orchestrator.pr_manager import Front
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.pr_manager.support import PR, REPO, manager_over, run_manager, seed_state
from tests.settings.support import disk_boards

THE_PR = a_pr(PR, REPO)


def test_the_browser_front_starts_its_board_at_start_up_and_wants_it_kept(settings, tmp_path):
    board = FakeBoardApi()
    run_manager(settings, is_author=True, worktree=tmp_path, board=board)
    assert board.starts == [{"pr": THE_PR, "port": disk_boards(settings.data_dir).board_port(THE_PR)}]
    assert disk_boards(settings.data_dir).board_wanted(THE_PR) is True


def test_the_browser_front_starts_its_board_once_a_poll_says_whose_pr_this_is(settings, tmp_path):
    board = FakeBoardApi()
    seen = []

    def poll_says() -> None:
        seen.append((len(board.starts), disk_boards(settings.data_dir).board_wanted(THE_PR)))
        seed_state(settings, is_author=False)

    run_manager(settings, None, poll_says, worktree=tmp_path, board=board)
    assert seen == [(0, False)]
    assert len(board.starts) == 1


def test_the_browser_front_keeps_trying_a_board_that_would_not_start(settings, tmp_path):
    board = FakeBoardApi(taken={disk_boards(settings.data_dir).board_port(THE_PR)})
    run_manager(settings, None, None, board.taken.clear, worktree=tmp_path, is_author=True,
                board=board)
    assert len(board.starts) == 1


def test_a_board_that_keeps_failing_is_logged_as_an_error_once(settings, tmp_path, caplog):
    board = FakeBoardApi(taken={disk_boards(settings.data_dir).board_port(THE_PR)})
    with caplog.at_level(logging.DEBUG):
        run_manager(settings, None, None, None, worktree=tmp_path, is_author=True,
                    board=board)
    assert len([record for record in caplog.records if record.levelno >= logging.ERROR]) == 1


def test_the_browser_fronts_board_comes_back_once_the_worktree_holds_its_branch_again(settings, tmp_path):
    seed_state(settings, branch="expected-branch")
    working_copies = FakeWorkingCopies()
    working_copies.add_worktree(tmp_path, "other-branch")
    board = FakeBoardApi()
    run_manager(settings, lambda: working_copies.add_worktree(tmp_path, "expected-branch"),
                is_author=True, worktree=tmp_path, board=board,
                working_copies=working_copies)
    assert len(board.starts) == 1
    assert board.running is True


def test_sigterm_inside_the_browser_fronts_session_raises_system_exit_and_the_handler_is_restored(
        settings, tmp_path):
    before = signal.getsignal(signal.SIGTERM)
    front = manager_over(settings, worktree=tmp_path).container.get(Front)
    with pytest.raises(SystemExit, match="terminated by signal 15"):
        with front.session():
            os.kill(os.getpid(), signal.SIGTERM)
    assert signal.getsignal(signal.SIGTERM) == before

