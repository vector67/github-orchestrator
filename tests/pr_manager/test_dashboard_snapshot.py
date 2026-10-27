from dataclasses import replace

from github_orchestrator.conversation import Verdict
from github_orchestrator.github import ReviewState
from github_orchestrator.github.fake import FakeGitHub, Review
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.change_detection.support import ACCOUNT
from tests.pr_manager.polls import POLLED, REVIEWED, REVIEWED_AT, polled_pr, seed
from tests.pr_manager.support import ServerPanel, manager_over, run_manager, seed_state


def _drawn(settings, tmp_path, *script, is_author=True, **modules):
    board = modules.pop("board", None) or ServerPanel()
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
    assert dashboard.changes_requested_by == ("bob",)
    assert [check.name for check in dashboard.checks if check.failed] == ["unit-tests"]
    assert dashboard.since_commits is None


def test_the_dashboard_says_whether_the_branch_needs_a_rebase(settings, tmp_path):
    seed(settings, polled_pr(mergeable_state="dirty"))

    assert _drawn(settings, tmp_path).needs_rebase is True


def test_the_dashboard_names_the_branch_the_pr_merges_into(settings, tmp_path):
    seed(settings, polled_pr(base_branch="develop"))

    assert _drawn(settings, tmp_path).base_branch == "develop"


def test_the_dashboard_leaves_mergeable_unknown_before_the_first_poll(settings, tmp_path):
    assert _drawn(settings, tmp_path).mergeable is None


def test_the_dashboard_leaves_mergeable_unknown_while_github_is_still_deciding(settings, tmp_path):
    seed(settings, polled_pr(mergeable=False, mergeable_state="unknown"))

    assert _drawn(settings, tmp_path).mergeable is None


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


def _sent(settings, tmp_path, seen, verdict, body=None):
    seed(settings, seen)
    github = FakeGitHub()
    github.add_pr(a_pr())
    manager = manager_over(settings, None, worktree=tmp_path, is_author=False, github=github)
    manager.conversation_managers.of(a_pr()).send_review(verdict, body)
    manager.run()
    return manager.board.panel.dashboard()


def test_a_review_sent_since_the_last_poll_reads_as_given(settings, tmp_path):
    asked = polled_pr(author="alice", reviews=(), pending_reviewers=(ACCOUNT,))

    dashboard = _sent(settings, tmp_path, asked, Verdict.APPROVE)

    assert (dashboard.my_review, dashboard.my_review_at, dashboard.viewer_requested) == (
        "approved", "2026-09-24T12:00:00Z", False)


def test_a_comment_sent_after_an_approval_keeps_the_approval_and_ends_the_request(
        settings, tmp_path):
    approved = Review(ACCOUNT, ReviewState.APPROVED, REVIEWED_AT, "abc000")
    asked = polled_pr(author="alice", reviews=(approved,), pending_reviewers=(ACCOUNT,))

    dashboard = _sent(settings, tmp_path, asked, Verdict.COMMENT, "one more thing")

    assert (dashboard.my_review, dashboard.my_review_at, dashboard.viewer_requested) == (
        "approved", REVIEWED_AT, False)


def test_the_first_poll_after_a_sent_review_has_the_last_word(settings, tmp_path):
    asked_again = replace(polled_pr(author="alice", reviews=(), pending_reviewers=(ACCOUNT,))[0],
                          polled_at="2026-09-24T12:05:00Z")

    dashboard = _sent(settings, tmp_path, (asked_again,), Verdict.APPROVE)

    assert (dashboard.my_review, dashboard.viewer_requested) == (None, True)
