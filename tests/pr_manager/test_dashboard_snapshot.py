from github_orchestrator.board_api.fake import FakeBoardApi
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.pr_manager.polls import POLLED, REVIEWED, polled_pr, seed
from tests.pr_manager.support import run_manager, seed_state


def _drawn(settings, tmp_path, *script, is_author=True, **modules):
    board = modules.pop("board", None) or FakeBoardApi()
    run_manager(settings, *(script or (None,)), worktree=tmp_path, is_author=is_author,
                board=board, **modules)
    return board.panel.dashboard()


def test_the_dashboard_holds_the_pr_and_its_status_as_values(settings, tmp_path):
    seed(settings, POLLED)

    dashboard = _drawn(settings, tmp_path)

    assert (dashboard.title, dashboard.ticket, dashboard.branch, dashboard.url,
            dashboard.is_author) == (
        "Remove the changes field", "PROJ-34", "PROJ-34-remove-changes",
        "https://github.com/o/n/pull/1", True)
    assert (dashboard.ci, dashboard.mergeable, dashboard.review_decision) == (
        "failing", False, "changes-requested")
    assert (dashboard.detailed_reviewer, dashboard.is_detailed_reviewer) == ("carol", False)
    assert (dashboard.last_event_at, dashboard.review_ready_at) == (
        "2026-06-10T10:30:00+00:00", "2026-06-09T08:00:00Z")
    assert (dashboard.changes_requested_by, dashboard.failed_checks) == (
        ("bob",), ("unit-tests",))
    assert dashboard.since_commits is None


def test_the_dashboard_says_whether_the_branch_needs_a_rebase(settings, tmp_path):
    seed(settings, polled_pr(mergeable_state="dirty"))

    assert _drawn(settings, tmp_path).needs_rebase is True


def test_a_reviewers_dashboard_holds_their_review_and_what_happened_since(settings, tmp_path):
    seed(settings, REVIEWED)

    dashboard = _drawn(settings, tmp_path, is_author=False)

    assert dashboard.my_review == "approved"
    assert dashboard.is_detailed_reviewer is True
    assert dashboard.author == "alice"
    assert (dashboard.since_commits, dashboard.since_force_push, dashboard.since_reviews,
            dashboard.since_comments, dashboard.since_resolved) == (2, False, 1, 4, 1)


def test_the_dashboard_names_the_command_that_reverses_a_dismissal(settings, tmp_path):
    dashboard = _drawn(settings, tmp_path)

    assert dashboard.undismiss_command.endswith("undismiss --repo o/n 1")


def test_a_frozen_manager_still_publishes_its_dashboard_with_both_branches(settings, tmp_path):
    seed_state(settings, branch="expected-branch")
    working_copies = FakeWorkingCopies()
    working_copies.add_worktree(tmp_path, "expected-branch")

    dashboard = _drawn(settings, tmp_path,
                       lambda: working_copies.add_worktree(tmp_path, "other-branch"), None,
                       working_copies=working_copies)

    assert (dashboard.frozen_on, dashboard.expected_branch) == ("other-branch", "expected-branch")
    assert dashboard.worktree == str(tmp_path)
    assert dashboard.seconds_left is not None


def test_an_unfrozen_dashboard_names_no_branch_held_here(settings, tmp_path):
    seed(settings, POLLED)

    dashboard = _drawn(settings, tmp_path)

    assert (dashboard.frozen_on, dashboard.expected_branch, dashboard.seconds_left) == (
        None, None, None)
