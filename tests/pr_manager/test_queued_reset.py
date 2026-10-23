from pathlib import Path

from github_orchestrator.agent_runs.fake import FakeAgentRuns, Outcome
from github_orchestrator.board_api.interface import Dashboards, ResetToOrigin, Shelves
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.pr_event_queue.support import ci_failed, in_flight_of
from tests.pr_manager.polls import BRANCH, POLLED, seed
from tests.pr_manager.support import THE_PR, ServerPanel, manager_over

QUEUED_AT = "2026-10-23T09:00:00Z"


def _diverged(worktree):
    copies = FakeWorkingCopies()
    base = copies.add_repo(Path("/nonexistent/repo"), {"f": "one\n"}, "first")
    copies.publish(BRANCH, base, {"f": "two\n"}, "the pull request's work")
    copies.add_worktree(worktree, None)
    copies.check_out(worktree, BRANCH)
    copies.commit(worktree, {"f": "local\n"}, "local work")
    rewritten = copies.publish(BRANCH, base, {"f": "rewritten\n"}, "the work, rewritten")
    return copies, rewritten


def _manager(settings, worktree, copies, *script):
    board = ServerPanel()
    runs = FakeAgentRuns(FakePrProcesses()).script(Outcome(finishes=False))
    steps = [lambda: board.panel.carry_on(), None, *script,
             lambda: runs.pr_runs[THE_PR].terminate(), None]
    return manager_over(settings, *steps, board=board, is_author=True, worktree=worktree,
                        agent_runs=runs, working_copies=copies)


def _queue(manager):
    ResetToOrigin(queued_at=QUEUED_AT).keep(manager.container.get(Shelves).of(THE_PR))


def _kept(manager):
    return ResetToOrigin.kept(manager.container.get(Shelves).of(THE_PR))


def test_a_queued_reset_runs_when_the_agent_run_ends(settings, tmp_path):
    seed(settings, POLLED)
    copies, rewritten = _diverged(tmp_path)
    manager = _manager(settings, tmp_path, copies, lambda: _queue(manager))

    manager.run()

    assert copies.head_of(tmp_path) == rewritten
    kept = _kept(manager)
    assert kept is not None and kept.ran_at is not None
    assert (kept.queued_at, kept.refused) == (None, None)
    assert manager.container.get(Dashboards).dashboard(THE_PR).reset_to_origin == kept


def test_a_queued_reset_cancelled_before_the_run_ends_does_not_run(settings, tmp_path):
    seed(settings, POLLED)
    copies, _ = _diverged(tmp_path)
    before = copies.head_of(tmp_path)
    manager = _manager(settings, tmp_path, copies, lambda: _queue(manager),
                       lambda: ResetToOrigin.forget(manager.container.get(Shelves).of(THE_PR)))

    manager.run()

    assert copies.head_of(tmp_path) == before
    assert _kept(manager) is None


def test_a_queued_reset_finding_uncommitted_changes_does_not_run_and_says_why(
        settings, tmp_path):
    seed(settings, POLLED)
    copies, _ = _diverged(tmp_path)
    before = copies.head_of(tmp_path)
    manager = _manager(settings, tmp_path, copies, lambda: _queue(manager),
                       lambda: copies.edit(tmp_path, "f", "half done\n"))

    manager.run()

    assert copies.head_of(tmp_path) == before
    kept = _kept(manager)
    assert kept is not None and kept.ran_at is not None
    assert kept.refused is not None and "uncommitted changes" in kept.refused
    assert manager.container.get(Dashboards).dashboard(THE_PR).reset_to_origin == kept


def test_a_queued_reset_outlives_the_manager_it_was_queued_under(settings, tmp_path):
    seed(settings, POLLED)
    copies, rewritten = _diverged(tmp_path)
    _queue(_manager(settings, tmp_path, copies))

    _manager(settings, tmp_path, copies).run()

    assert copies.head_of(tmp_path) == rewritten


def test_a_queued_reset_cancelled_while_it_fetches_does_not_run(settings, tmp_path):
    seed(settings, POLLED)
    copies, _ = _diverged(tmp_path)
    before = copies.head_of(tmp_path)
    manager = _manager(settings, tmp_path, copies, lambda: _queue(manager))
    copies.on_fetch = lambda: ResetToOrigin.forget(manager.container.get(Shelves).of(THE_PR))

    manager.run()

    assert copies.head_of(tmp_path) == before
    assert _kept(manager) is None


def test_a_reset_queued_after_the_run_ended_runs_before_the_next_run_starts(settings, tmp_path):
    seed(settings, POLLED)
    copies, rewritten = _diverged(tmp_path)
    board = ServerPanel()
    runs = FakeAgentRuns(FakePrProcesses()).script(Outcome(finishes=False))
    next_run = []
    manager = manager_over(
        settings, lambda: _queue(manager), lambda: board.panel.carry_on(), None,
        lambda: next_run.append(copies.commit(tmp_path, {"g": "the fix\n"}, "the next run's fix")),
        lambda: runs.pr_runs[THE_PR].terminate(), None,
        board=board, is_author=True, worktree=tmp_path, agent_runs=runs, working_copies=copies)

    manager.run()

    assert next_run == [copies.head_of(tmp_path)]
    assert copies.commits[next_run[0]].parents == (rewritten,)


def test_a_queued_reset_whose_record_cannot_be_written_does_not_run_and_the_run_still_ends(
        settings, tmp_path):
    seed(settings, POLLED)
    copies, _ = _diverged(tmp_path)
    before = copies.head_of(tmp_path)
    shelf_dir = []

    def queued_onto_a_shelf_that_takes_no_more():
        _queue(manager)
        shelf_dir.append(next(settings.threads_dir.rglob("state.reset")).parent)
        shelf_dir[0].chmod(0o555)

    runs = FakeAgentRuns(FakePrProcesses()).script(Outcome())
    manager = manager_over(settings, queued_onto_a_shelf_that_takes_no_more, None,
                           is_author=True, worktree=tmp_path, agent_runs=runs,
                           working_copies=copies)
    manager.event_queue.add(THE_PR, ci_failed("tests"))

    try:
        manager.run()
    finally:
        shelf_dir[0].chmod(0o755)

    assert len(runs.started) == 1
    assert copies.head_of(tmp_path) == before
    assert in_flight_of(manager.event_queue, THE_PR) == []
