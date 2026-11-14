from datetime import UTC, datetime

import pytest

from github_orchestrator.agent_runs.fake import CarryingOn, FakeAgentRuns, Outcome
from github_orchestrator.board_api.interface import (
    Dashboards,
    HeldAgentSettings,
    ManagerRefusal,
    Notice,
    NoticeCode,
)
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.pr_event_queue.support import pending_of, review_requested
from tests.pr_manager.scripted_terminal import ManualClock
from tests.pr_manager.support import (
    THE_PR,
    ServerPanel,
    managed_in,
    manager_over,
    run_manager,
    seed_state,
)

CHANGED = {"CLAUDE.md": "Run the deploy check.", ".claude/settings.json": "{\"hooks\": {}}"}


def _changing(worktree, files=CHANGED):
    working_copies = FakeWorkingCopies()
    working_copies.change_agent_config(worktree, files)
    return working_copies


def _windows_at(worktree):
    pr_processes = FakePrProcesses()
    pr_processes.open(THE_PR, worktree)
    return pr_processes


def _shown(settings, worktree, working_copies, *, is_author):
    manager = manager_over(settings, None, worktree=worktree, is_author=is_author,
                           working_copies=working_copies, pr_processes=_windows_at(worktree))
    manager.run()
    return manager.container.get(Dashboards).dashboard(THE_PR)


def test_someone_elses_pull_request_that_changes_agent_files_is_held_on_them(settings, tmp_path):
    working_copies = _changing(tmp_path)

    shown = _shown(settings, tmp_path, working_copies, is_author=False)

    digest = working_copies.agent_config(THE_PR, str(tmp_path)).digest
    assert shown.agent_settings == HeldAgentSettings((".claude/settings.json", "CLAUDE.md"), digest)


def test_your_own_pull_request_is_never_held(settings, tmp_path):
    shown = _shown(settings, tmp_path, _changing(tmp_path), is_author=True)

    assert shown.agent_settings is None


def test_an_answer_lifts_the_hold_while_the_files_stay_the_same(settings, tmp_path):
    working_copies = _changing(tmp_path)
    digest = working_copies.agent_config(THE_PR, str(tmp_path)).digest
    working_copies.answer_agent_config(THE_PR, digest, allowed=False)

    shown = _shown(settings, tmp_path, working_copies, is_author=False)

    assert shown.agent_settings is None


def _answer(working_copies, worktree, *, allowed=False):
    digest = working_copies.agent_config(THE_PR, str(worktree)).digest
    working_copies.answer_agent_config(THE_PR, digest, allowed=allowed)


def test_a_review_asked_for_while_held_waits_and_starts_once_answered(settings, tmp_path):
    working_copies = _changing(tmp_path)
    runs = FakeAgentRuns(FakePrProcesses()).script(Outcome(finishes=False))
    waited = []
    manager = manager_over(settings, lambda: waited.append((len(runs.started), _kinds(manager))),
                           lambda: _answer(working_copies, tmp_path), None,
                           worktree=tmp_path, is_author=False,
                           working_copies=working_copies, agent_runs=runs)
    manager.event_queue.add(THE_PR, review_requested())

    manager.run()

    assert (waited, len(runs.started), _kinds(manager)) == ([(0, ["review-requested"])], 1, [])


def test_a_run_its_last_manager_was_interrupted_in_is_carried_on_once_answered(settings, tmp_path):
    working_copies = _changing(tmp_path)
    runs = FakeAgentRuns(FakePrProcesses()).script(Outcome(finishes=False), Outcome(finishes=False))
    runs.review("/wt", THE_PR, "review-requested", title="t", url="u", branch="b",
                additions=1, deletions=1).interrupt()
    runs = runs.restarted()
    waited = []
    manager = manager_over(settings, lambda: waited.append(_carried_on(runs)),
                           lambda: _answer(working_copies, tmp_path), None,
                           worktree=tmp_path, is_author=False,
                           working_copies=working_copies, agent_runs=runs)

    manager.run()

    assert (waited, len(_carried_on(runs))) == ([[]], 1)


ASKED_FOR = {
    "carry on": lambda board: board.panel.carry_on(),
    "start review": lambda board: board.panel.start_review(),
    "a question": lambda board: board.worktree.ask("Why this name?"),
    "a rebase session": lambda board: board.worktree.open_terminal("r"),
}


@pytest.mark.parametrize("asking", ASKED_FOR.values(), ids=ASKED_FOR.keys())
def test_an_agent_asked_for_while_held_is_refused_and_none_starts(settings, tmp_path, asking):
    processes = managed_in(tmp_path)
    runs = FakeAgentRuns(processes).script(Outcome(finishes=False))
    board = ServerPanel()
    answers = []
    run_manager(settings, lambda: answers.append(asking(board)), None, worktree=tmp_path,
                is_author=False, board=board, pr_processes=processes, agent_runs=runs,
                working_copies=_changing(tmp_path))

    assert (answers, runs.started, processes.sessions.get(THE_PR, [])) == (
        [ManagerRefusal.AGENT_SETTINGS_HELD], [], [])


def test_a_shell_in_the_terminal_still_opens_while_held(settings, tmp_path):
    processes = managed_in(tmp_path)
    board = ServerPanel()
    answers = []
    run_manager(settings, lambda: answers.append(board.worktree.open_terminal("new")), None,
                worktree=tmp_path, is_author=False, board=board, pr_processes=processes,
                working_copies=_changing(tmp_path))

    assert (answers, len(processes.sessions[THE_PR])) == ([None], 1)


def test_a_carry_on_drained_after_the_hold_began_is_refused_with_its_notice(settings, tmp_path):
    working_copies = FakeWorkingCopies()
    working_copies.change_agent_config(tmp_path, {})
    runs = FakeAgentRuns(FakePrProcesses()).script(Outcome(finishes=False))
    board = ServerPanel()
    seen = []

    def held_then_carried_on():
        board.panel.carry_on()
        working_copies.change_agent_config(tmp_path, CHANGED)

    run_manager(settings, held_then_carried_on, lambda: seen.append(board.panel.dashboard().notice),
                worktree=tmp_path, is_author=False, board=board, agent_runs=runs,
                working_copies=working_copies)

    assert (runs.started, seen) == ([], [Notice(NoticeCode.AGENT_SETTINGS_HELD)])


def test_an_answer_from_the_board_for_the_files_shown_lifts_the_hold(settings, tmp_path):
    working_copies = _changing(tmp_path)
    board = ServerPanel()
    shown, answered = [], []

    def answer():
        held = board.panel.dashboard().agent_settings
        shown.append(held.changed)
        answered.append(board.panel.answer_agent_settings("0ld", allowed=True))
        answered.append(board.panel.answer_agent_settings(held.digest, allowed=True))

    run_manager(settings, answer, lambda: shown.append(board.panel.dashboard().agent_settings),
                worktree=tmp_path, is_author=False, board=board,
                pr_processes=managed_in(tmp_path), working_copies=working_copies)

    assert (shown, answered) == ([(".claude/settings.json", "CLAUDE.md"), None], [False, True])
    assert working_copies.agent_config(THE_PR, str(tmp_path)).project_settings


def test_the_flags_say_when_the_hold_began(settings, tmp_path):
    working_copies = FakeWorkingCopies()
    working_copies.change_agent_config(tmp_path, {})
    clock = ManualClock(datetime(2026, 10, 8, 9, 0, tzinfo=UTC))
    manager = manager_over(settings, None, worktree=tmp_path, clock=clock, is_author=False,
                           pr_processes=_windows_at(tmp_path), working_copies=working_copies)
    dashboards = manager.container.get(Dashboards)

    first = dashboards.dashboard(THE_PR).flags_changed_at
    working_copies.change_agent_config(tmp_path, CHANGED)
    clock.advance(60)

    assert (first, dashboards.dashboard(THE_PR).flags_changed_at) == (
        "2026-10-08T09:00:00.000000Z", "2026-10-08T09:01:00.000000Z")


def test_a_run_whose_checkout_moves_to_unanswered_agent_files_is_stopped(settings, tmp_path):
    working_copies = FakeWorkingCopies()
    working_copies.change_agent_config(tmp_path, {})
    runs = FakeAgentRuns(FakePrProcesses()).script(Outcome(finishes=False))
    board = ServerPanel()
    seen = []
    run_manager(settings, lambda: board.panel.carry_on(), None,
                lambda: working_copies.change_agent_config(tmp_path, CHANGED), None,
                lambda: seen.append(board.panel.dashboard().working_on),
                worktree=tmp_path, is_author=False, board=board, agent_runs=runs,
                working_copies=working_copies)

    assert (len(runs.started), seen, runs.last_run(THE_PR).exit_code) == (1, [None], -15)


def test_a_push_seen_on_origin_holds_it_and_stops_the_run_before_the_worktree_moves(
        settings, tmp_path):
    seed_state(settings, is_author=False, branch="feature")
    working_copies = FakeWorkingCopies()
    working_copies.change_agent_config(tmp_path, {})
    processes = managed_in(tmp_path)
    runs = FakeAgentRuns(processes).script(Outcome(finishes=False))
    board = ServerPanel()
    seen = []
    run_manager(settings, lambda: board.panel.carry_on(), None,
                lambda: working_copies.fetch_agent_config(tmp_path, "feature", CHANGED),
                lambda: seen.append((board.panel.dashboard().working_on,
                                     board.panel.dashboard().agent_settings.changed)),
                worktree=tmp_path, is_author=False, board=board, agent_runs=runs,
                pr_processes=processes, working_copies=working_copies)

    assert (len(runs.started), seen, runs.last_run(THE_PR).exit_code) == (
        1, [(None, (".claude/settings.json", "CLAUDE.md"))], -15)
    assert working_copies.agent_config(THE_PR, str(tmp_path)).changed == ()


def _carried_on(runs):
    return [started for started in runs.started if isinstance(started.work, CarryingOn)]


def _kinds(manager):
    return [event.kind for event in pending_of(manager.event_queue, THE_PR)]


def test_a_push_that_changes_the_files_again_holds_it_again(settings, tmp_path):
    working_copies = _changing(tmp_path)
    digest = working_copies.agent_config(THE_PR, str(tmp_path)).digest
    working_copies.answer_agent_config(THE_PR, digest, allowed=True)
    working_copies.change_agent_config(tmp_path, {**CHANGED, "CLAUDE.md": "Run anything."})

    shown = _shown(settings, tmp_path, working_copies, is_author=False)

    assert shown.agent_settings is not None
