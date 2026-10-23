from pathlib import Path

from github_orchestrator.agent_runs.fake import FakeAgentRuns, Outcome
from github_orchestrator.board_api.interface import Dashboards, ResetToOrigin, Shelves
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.working_copies.fake import FakeWorkingCopies
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
    manager = _manager(settings, tmp_path, copies)
    _queue(manager)

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
    manager = _manager(settings, tmp_path, copies,
                       lambda: ResetToOrigin.forget(manager.container.get(Shelves).of(THE_PR)))
    _queue(manager)

    manager.run()

    assert copies.head_of(tmp_path) == before
    assert _kept(manager) is None


def test_a_queued_reset_finding_uncommitted_changes_does_not_run_and_says_why(
        settings, tmp_path):
    seed(settings, POLLED)
    copies, _ = _diverged(tmp_path)
    before = copies.head_of(tmp_path)
    manager = _manager(settings, tmp_path, copies,
                       lambda: copies.edit(tmp_path, "f", "half done\n"))
    _queue(manager)

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
