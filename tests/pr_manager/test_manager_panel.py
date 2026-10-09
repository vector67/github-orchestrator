import dataclasses
import threading

import pytest

from github_orchestrator.agent_runs import Agent
from github_orchestrator.agent_runs.fake import (
    CarryingOn,
    FakeAgentRuns,
    Outcome,
    Reviewing,
)
from github_orchestrator.board_api.fake import FakeBoardApi
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import Dismissal
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.pr_manager.support import PR, REPO, run_manager, seed_state
from tests.settings.support import disk_dismissals, disk_holds

THE_PR = a_pr(PR, REPO)
URL = "https://github.com/o/n/pull/1"


def _runs(*outcomes):
    return FakeAgentRuns(FakePrProcesses()).script(*outcomes)


def test_the_panel_answers_the_status_the_manager_last_drew(settings, tmp_path):
    seed_state(settings, title="t", url=URL)
    disk_holds(settings.data_dir).set_on_hold(THE_PR, True)
    board = FakeBoardApi()

    run_manager(settings, None, worktree=tmp_path, is_author=True, board=board)

    status = board.panel.dashboard()
    assert (status.agents_enabled, status.working_on, status.on_hold, status.queued_events,
            status.url, status.notice) == (True, None, True, 0, URL, None)
    assert (status.threads_queued, len(status.threads_live), status.threads_proposed) == (0, 0, 0)


def test_the_panel_names_the_agent_this_instance_runs(settings, tmp_path):
    seed_state(settings, title="t", url=URL)
    codex = dataclasses.replace(settings, config=dataclasses.replace(settings.config,
                                                                      agent=Agent.CODEX))
    board = FakeBoardApi()

    run_manager(codex, None, worktree=tmp_path, is_author=True, board=board)

    assert board.panel.dashboard().agent_name == "Codex"


def test_the_panel_answers_the_last_run_on_the_ledger(settings, tmp_path):
    seed_state(settings, title="t", url=URL)
    runs = _runs(Outcome(exit_code=-9))
    runs.fix_check("/wt", THE_PR, "ci-failed", check="tests", summary=None, push=True).pump()
    board = FakeBoardApi()

    run_manager(settings, None, worktree=tmp_path, is_author=True, board=board,
                agent_runs=runs)

    status = board.panel.dashboard()
    assert (status.last_run_event, status.last_run_exit_code) == ("ci-failed", -9)
    assert status.last_run_ended_at


def test_the_panel_answers_the_run_going(settings, tmp_path):
    seed_state(settings, title="t", url=URL)
    board = FakeBoardApi()

    run_manager(settings, lambda: board.panel.carry_on(), None, worktree=tmp_path,
                is_author=True, board=board, agent_runs=_runs(Outcome(finishes=False)))

    status = board.panel.dashboard()
    assert status.working_on == "manual-continue"
    assert status.elapsed_seconds is not None
    assert status.silent_seconds is not None


def _without_claude(settings):
    return dataclasses.replace(settings, config=dataclasses.replace(settings.config,
                                                                    agents_enabled=False))


def _on_the_browser_front(settings, tmp_path, *script, **modules):
    board = modules.pop("board", None) or FakeBoardApi()
    run_manager(settings, *script, worktree=tmp_path, is_author=True, board=board,
                **modules)
    return board


class CountingCopies(FakeWorkingCopies):
    def __init__(self):
        super().__init__()
        self.counted = 0

    def commits_since(self, worktree, sha):
        self.counted += 1
        return super().commits_since(worktree, sha)


def _one_commit_ahead(settings, tmp_path):
    copies = CountingCopies()
    pushed = copies.add_repo(tmp_path / "repo", {"a": "0"}, "init")
    copies.add_worktree(tmp_path, "PROJ-123-test")
    copies.branches["PROJ-123-test"] = pushed
    copies.commit(tmp_path, {"a": "1"}, "change")
    seed_state(settings, title="t", url=URL, head_sha=pushed)
    return copies


def test_unpushed_commits_go_uncounted_while_nobody_reads_the_board(settings, tmp_path):
    copies = _one_commit_ahead(settings, tmp_path)
    _on_the_browser_front(settings, tmp_path, None, None, None, working_copies=copies)
    assert copies.counted == 0


def test_a_board_read_counts_the_commits_made_since_the_last_tick(settings, tmp_path):
    copies = _one_commit_ahead(settings, tmp_path)
    board = _on_the_browser_front(settings, tmp_path, None, working_copies=copies)
    copies.commit(tmp_path, {"a": "2"}, "another")
    assert board.panel.dashboard().unpushed_commits == 2


def test_hold_from_the_board_holds_the_pr_and_the_next_status_says_so(settings, tmp_path):
    board = FakeBoardApi()
    seen = []
    _on_the_browser_front(settings, tmp_path, lambda: board.panel.set_on_hold(True),
              lambda: seen.append(board.panel.dashboard().on_hold), board=board)
    assert seen == [True]
    assert disk_holds(settings.data_dir).on_hold(THE_PR) is True


def test_a_command_from_the_boards_thread_waits_for_the_loop_to_carry_it_out(settings, tmp_path):
    board = FakeBoardApi()
    seen = []

    def from_the_boards_thread():
        sender = threading.Thread(target=lambda: board.panel.set_on_hold(True))
        sender.start()
        sender.join()
        seen.append(disk_holds(settings.data_dir).on_hold(THE_PR))

    _on_the_browser_front(settings, tmp_path, from_the_boards_thread,
                          lambda: seen.append(disk_holds(settings.data_dir).on_hold(THE_PR)),
                          board=board)
    assert seen == [False, True]


def test_hold_from_the_board_leaves_a_held_pr_on_hold(settings, tmp_path):
    disk_holds(settings.data_dir).set_on_hold(THE_PR, True)
    board = FakeBoardApi()
    _on_the_browser_front(settings, tmp_path, lambda: board.panel.set_on_hold(True), None, board=board)
    assert disk_holds(settings.data_dir).on_hold(THE_PR) is True


def test_resume_from_the_board_resumes_a_pr_on_hold(settings, tmp_path):
    disk_holds(settings.data_dir).set_on_hold(THE_PR, True)
    board = FakeBoardApi()
    seen = []
    _on_the_browser_front(settings, tmp_path, lambda: board.panel.set_on_hold(False),
              lambda: seen.append(board.panel.dashboard().on_hold), board=board)
    assert seen == [False]
    assert disk_holds(settings.data_dir).on_hold(THE_PR) is False


def test_carry_on_from_the_board_starts_claude_continue_as_r_does(settings, tmp_path):
    runs = _runs(Outcome(finishes=False))
    board = FakeBoardApi()
    seen = []
    _on_the_browser_front(settings, tmp_path, lambda: board.panel.carry_on(),
              lambda: seen.append(board.panel.dashboard().working_on), board=board,
              agent_runs=runs)
    [started] = runs.started
    assert started.work == CarryingOn()
    assert seen == ["manual-continue"]


def test_carry_on_from_the_board_is_refused_with_rs_notice_when_claude_is_disabled(
        settings, tmp_path):
    runs = _runs()
    board = FakeBoardApi()
    seen = []
    _on_the_browser_front(_without_claude(settings), tmp_path, lambda: board.panel.carry_on(),
              lambda: seen.append(board.panel.dashboard().notice), board=board, agent_runs=runs)
    assert runs.started == []
    assert seen == ["agents are disabled in config.toml"]


def _reviewer_of(settings, tmp_path, *script, **modules):
    seed_state(settings, title="Fix bug", url=URL, author="alice", branch="PROJ-123-fix",
               is_author=False)
    board = modules.pop("board", None) or FakeBoardApi()
    run_manager(settings, *script, worktree=tmp_path, is_author=False, board=board,
                **modules)
    return board


def test_start_review_from_the_board_starts_the_review_agent_a_review_request_would(
        settings, tmp_path):
    runs = _runs(Outcome(finishes=False))
    board = FakeBoardApi()
    seen = []
    _reviewer_of(settings, tmp_path, lambda: board.panel.start_review(), None,
                 lambda: seen.append(board.panel.dashboard().working_on), board=board,
                 agent_runs=runs)
    [started] = runs.started
    assert started.work == Reviewing("Fix bug", URL, "PROJ-123-fix", 0, 0)
    assert seen == ["review-requested"]


def test_start_review_from_the_board_is_refused_while_claude_is_running(settings, tmp_path):
    runs = _runs(Outcome(finishes=False))
    board = FakeBoardApi()
    seen = []
    _reviewer_of(settings, tmp_path, lambda: board.panel.carry_on(),
                 lambda: board.panel.start_review(), None,
                 lambda: seen.append(board.panel.dashboard().notice), board=board,
                 agent_runs=runs)
    assert [run.work for run in runs.started] == [CarryingOn()]
    assert seen == ["an agent is already running"]


def test_start_review_from_the_board_is_refused_when_claude_is_disabled(settings, tmp_path):
    runs = _runs()
    board = FakeBoardApi()
    seen = []
    _reviewer_of(_without_claude(settings), tmp_path, lambda: board.panel.start_review(), None,
                 lambda: seen.append(board.panel.dashboard().notice), board=board,
                 agent_runs=runs)
    assert runs.started == []
    assert seen == ["agents are disabled in config.toml"]


@pytest.mark.parametrize(("forever", "dismissal"), [
    (False, Dismissal.UNTIL_NEXT_EVENT),
    (True, Dismissal.FOREVER),
])
def test_dismiss_from_the_board_records_it_and_the_manager_exits(settings, tmp_path, forever,
                                                                  dismissal):
    board = FakeBoardApi()
    reached = []
    _on_the_browser_front(settings, tmp_path, lambda: board.panel.dismiss(forever),
              lambda: reached.append(True), board=board)
    assert disk_dismissals(settings.data_dir).dismissal(THE_PR) is dismissal
    assert reached == []


def test_close_from_the_board_closes_the_pr_on_github(settings, tmp_path):
    github = FakeGitHub()
    github.add_pr(THE_PR)
    board = FakeBoardApi()
    _on_the_browser_front(settings, tmp_path, lambda: board.panel.close(), None, board=board,
                          github=github)
    assert github.is_closed(THE_PR) is True


def test_a_close_github_refuses_says_why_in_the_notice(settings, tmp_path):
    board = FakeBoardApi()
    seen = []
    _on_the_browser_front(settings, tmp_path, lambda: board.panel.close(),
                          lambda: seen.append(board.panel.dashboard().notice), board=board)
    [notice] = seen
    assert notice is not None and "Not Found" in notice


def test_a_command_from_the_board_is_refused_while_the_worktree_holds_another_branch(
        settings, tmp_path):
    seed_state(settings, branch="expected-branch")
    working_copies = FakeWorkingCopies()
    working_copies.add_worktree(tmp_path, "expected-branch")
    board = FakeBoardApi()

    seen = []
    run_manager(settings, lambda: working_copies.add_worktree(tmp_path, "other-branch"),
                lambda: board.panel.set_on_hold(True),
                lambda: seen.append(board.panel.dashboard().notice), worktree=tmp_path,
                is_author=True, board=board, working_copies=working_copies)
    assert disk_holds(settings.data_dir).on_hold(THE_PR) is False
    assert seen == ["refused: the worktree holds another PR's branch"]


def test_a_command_queued_behind_a_dismiss_is_dropped(settings, tmp_path):
    board = FakeBoardApi()

    def dismiss_then_hold():
        board.panel.dismiss(False)
        board.panel.set_on_hold(True)

    _on_the_browser_front(settings, tmp_path, dismiss_then_hold, None, board=board)
    assert disk_dismissals(settings.data_dir).dismissal(THE_PR) is Dismissal.UNTIL_NEXT_EVENT
    assert disk_holds(settings.data_dir).on_hold(THE_PR) is False
