import shlex

import pytest

from github_orchestrator.agent_runs import FixComment, PointedAt, ThreadFix
from github_orchestrator.agent_runs.fake import FakeAgentRuns
from github_orchestrator.pr_processes.fake import FakePrProcesses
from tests.agent_runs.cli_flags import assert_the_cli_takes, invocations
from tests.agent_runs.pinned import assert_pinned
from tests.agent_runs.scripted_claude import ScriptedClaude
from tests.agent_runs.support import finish, real_agent_runs
from tests.builders import a_pr


@pytest.fixture
def world():
    return FakeAgentRuns(FakePrProcesses())


@pytest.fixture
def claude(world):
    stand_in = ScriptedClaude(world)
    yield stand_in
    stand_in.reap()


@pytest.fixture
def runs(world, claude, tmp_path):
    return real_agent_runs(world, claude, tmp_path)


def _asked(runs, claude):
    assert runs.drain_summaries(10)
    [asked] = claude.asked
    return asked.prompt


def test_the_gist_of_a_comment_on_a_line(runs, claude):
    runs.summarize_comment("PRRT_1", "src/foo.py", 4, "rename this", lambda gist: None,
                           chars=60)

    assert_pinned("gist-comment", _asked(runs, claude))


def test_the_gist_of_a_comment_on_the_pull_request(runs, claude):
    runs.summarize_comment("PRRT_1", None, None, "rename this", lambda gist: None, chars=60)

    assert_pinned("gist-comment-on-the-pr", _asked(runs, claude))


def test_the_gist_of_a_thread(runs, claude):
    runs.summarize_thread("PRRT_1", "src/foo.py", 4,
                          [("reviewer", "rename this"), ("me", "which one?")],
                          lambda gist: None, chars=60)

    assert_pinned("gist-thread", _asked(runs, claude))


def test_the_verdict_on_a_thread(runs, claude):
    runs.judge_thread(
        "PRRT_1",
        [("you", "octocat", "rename this"), ("PR author", "mei", "fixed in abc123"),
         ("bot", "claude", "looks fine")],
        viewer="octocat", pr_author="mei", spoke_last="bot", viewer_commented=True,
        mentions_viewer=False, kind="review thread on a line",
        answers={"my-move": "the viewer has to answer",
                 "their-move": "someone else has to answer"},
        done=lambda verdict: None)

    assert_pinned("verdict", _asked(runs, claude))


def test_the_summary_of_a_batch_of_fixes(runs, claude):
    runs.summarize_fixes([([("Ada", "please rename the helper"), ("octocat", "which one?")],
                           "renamed the helper"),
                          ([("Reviewer B", "add a test")], None)],
                         lambda summary: None, chars=100)

    assert_pinned("summary-fixes", _asked(runs, claude))


def test_the_gists_of_a_batch_of_comments(runs, claude):
    runs.summarize_comments(["the IN list could hit the 65k parameter limit",
                             "this still fails on staging\nsee the log"],
                            lambda gists: None, chars=60)

    assert_pinned("gists-comments", _asked(runs, claude))


PR_ON_O_N = a_pr(1, "o/n")


def _prompted(runs, claude, run):
    finish(run)
    [prompt] = claude.prompts
    return prompt


def test_the_review_of_a_pr(runs, claude, tmp_path):
    prompt = _prompted(runs, claude, runs.review(
        str(tmp_path), PR_ON_O_N, "review-requested", title="Fix bug",
        url="https://example.com/pr/1", branch="PROJ-123-fix", additions=100, deletions=50))

    assert_pinned("review", prompt)


def test_the_in_depth_review_of_a_large_pr(runs, claude, tmp_path):
    prompt = _prompted(runs, claude, runs.review(
        str(tmp_path), PR_ON_O_N, "review-requested", title="Rework the pipeline",
        url="https://example.com/pr/2", branch="PROJ-456-pr", additions=300, deletions=200))

    assert_pinned("review-in-depth", prompt)


def test_the_review_of_a_pr_nothing_is_known_about(runs, claude, tmp_path):
    prompt = _prompted(runs, claude, runs.review(
        str(tmp_path), PR_ON_O_N, "review-requested", title="PR #1", url="", branch="",
        additions=0, deletions=0))

    assert_pinned("review-untitled", prompt)


def test_the_re_review_of_a_pr_sets_out_the_last_review_the_commits_since_and_the_replies(
        runs, claude, tmp_path):
    prompt = _prompted(runs, claude, runs.rereview(
        str(tmp_path), PR_ON_O_N, "review-requested", title="Fix bug",
        url="https://example.com/pr/1", branch="PROJ-123-fix", verdict="changes-requested",
        said=FixComment("me", "Two things before this can go in:\nthe retry and the test.",
                        "2026-09-30T09:00:00Z"),
        since="1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
        commits=("c0ffee1 Add the missing test", "badf00d Retry the upload once"),
        replied=(("src/upload.py", 42, (
                     FixComment("me", "This retries forever.", "2026-09-30T09:00:00Z"),
                     FixComment("alice", "Now it retries once.", "2026-09-30T12:00:00Z"))),
                 (None, None, (
                     FixComment("me", "Where is the test?", "2026-09-30T09:00:00Z"),
                     FixComment("alice", "Added in the last commit.",
                                "2026-09-30T12:05:00Z"))))))

    assert_pinned("rereview", prompt)


def test_the_re_review_of_a_pr_whose_reviewed_commit_is_gone_says_so(runs, claude, tmp_path):
    prompt = _prompted(runs, claude, runs.rereview(
        str(tmp_path), PR_ON_O_N, "review-requested", title="Fix bug",
        url="https://example.com/pr/1", branch="PROJ-123-fix", verdict="commented", said=None,
        since="1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b", commits=None, replied=()))

    assert_pinned("rereview-force-pushed", prompt)


def test_the_re_review_of_a_pr_with_nothing_new_on_the_branch_says_so(runs, claude, tmp_path):
    prompt = _prompted(runs, claude, runs.rereview(
        str(tmp_path), PR_ON_O_N, "review-requested", title="Fix bug",
        url="https://example.com/pr/1", branch="PROJ-123-fix", verdict="approved", said=None,
        since="1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b", commits=(), replied=()))

    assert "No commits have landed since you last reviewed or commented" in prompt


def test_the_re_review_of_a_pr_with_no_reviewed_commit_on_record_reviews_the_whole_branch(
        runs, claude, tmp_path):
    prompt = _prompted(runs, claude, runs.rereview(
        str(tmp_path), PR_ON_O_N, "review-requested", title="Fix bug",
        url="https://example.com/pr/1", branch="PROJ-123-fix", verdict="approved", said=None,
        since=None, commits=None, replied=()))

    assert "Which commit you last reviewed is not on record" in prompt


def test_a_re_review_hands_findings_back_through_the_draft_command_the_cli_takes(
        runs, claude, tmp_path):
    prompt = _prompted(runs, claude, runs.rereview(
        str(tmp_path), PR_ON_O_N, "review-requested", title="t", url="u", branch="b",
        verdict="commented", said=None, since=None, commits=None, replied=()))

    [(verb, flags)] = invocations(prompt)
    assert verb == "draft"
    assert_the_cli_takes(verb, flags)


def test_the_fix_of_the_last_failing_check(runs, claude, tmp_path):
    prompt = _prompted(runs, claude, runs.fix_check(
        str(tmp_path), PR_ON_O_N, "ci-failed", check="tests", summary="3 failed", push=True))

    assert_pinned("fix-check-push", prompt)


def test_the_fix_of_a_failing_check_with_more_to_come(runs, claude, tmp_path):
    prompt = _prompted(runs, claude, runs.fix_check(
        str(tmp_path), PR_ON_O_N, "ci-failed", check="tests", summary=None, push=False))

    assert_pinned("fix-check-hold", prompt)


def test_the_rebase_of_a_pr_branch(runs, claude, tmp_path):
    prompt = _prompted(runs, claude, runs.rebase(
        str(tmp_path), PR_ON_O_N, "became-unmergeable", reason="conflicts"))

    assert_pinned("rebase", prompt)


@pytest.mark.parametrize("additions", [10, 500])
def test_a_review_hands_findings_back_through_the_draft_command_the_cli_takes(
        runs, claude, tmp_path, additions):
    prompt = _prompted(runs, claude, runs.review(
        str(tmp_path), PR_ON_O_N, "review-requested", title="t", url="u", branch="b",
        additions=additions, deletions=0))

    [(verb, flags)] = invocations(prompt)
    assert verb == "draft"
    assert_the_cli_takes(verb, flags)


ACME = a_pr(7, "acme/widgets")
ROOT_COMMENT = FixComment("reviewer", "rename this", "2026-08-28T10:00:00Z")


@pytest.fixture
def at_wt(tmp_path):
    worktree = tmp_path / "wt"
    worktree.mkdir()
    return worktree


def _pinned(name, text, worktree):
    assert_pinned(name, text.replace(str(worktree), "/tmp/wt"))


def _thread(worktree, **fields):
    return ThreadFix(**{
        "pr": ACME, "key": "PRRT_1", "worktree": str(worktree), "author": "reviewer",
        "path": "src/foo.py", "line": 4, "body": "rename this",
        "comments": (ROOT_COMMENT,), "confidence_levels": ("low", "medium", "high"),
        **fields})


def test_the_fix_of_a_thread(runs, claude, at_wt):
    prompt = _prompted(runs, claude, runs.fix(_thread(at_wt,
        comments=(ROOT_COMMENT, FixComment("octocat", "which one?", "2026-08-28T11:00:00Z",
                                           by_pr_author=True)),
        before_reply="proposed", withdraws_proposal=True)))

    _pinned("thread-fix", prompt, at_wt)


def test_the_fix_of_a_thread_on_no_line(runs, claude, at_wt):
    prompt = _prompted(runs, claude, runs.fix(_thread(at_wt,
        path=None, line=None, comments=(), body="Please tidy up.",
        before_reply="rejected: not this one")))

    _pinned("thread-fix-general", prompt, at_wt)


def test_the_rebase_of_a_fix(runs, claude, at_wt):
    prompt = _prompted(runs, claude, runs.rebase_fix(
        _thread(at_wt, conflict="error: could not apply 1234abc... thread change"), "b" * 40))

    _pinned("fix-rebase", prompt, at_wt)


def test_the_rebase_of_a_fix_with_no_conflict_recorded(runs, claude, at_wt):
    prompt = _prompted(runs, claude, runs.rebase_fix(_thread(at_wt), "b" * 40))

    _pinned("fix-rebase-without-conflict", prompt, at_wt)


def test_the_rework_of_a_briefed_fix(runs, claude, at_wt):
    prompt = _prompted(runs, claude, runs.rework(_thread(at_wt,
        note="Use the enum instead.",
        pointed=(PointedAt("billing/invoice_writer.py", 142, "    return sorted(line_items)"),
                 PointedAt("billing/reader.py", 7, "    cache = {}")),
        replies=(FixComment("mira", "and drop the cache while you are there",
                            author_name="Mira Sample"),))))

    _pinned("rework-briefed", prompt, at_wt)


def test_the_rework_of_a_skipped_fix(runs, claude, at_wt):
    prompt = _prompted(runs, claude, runs.rework(_thread(at_wt,
        classification="ambiguous", skipped_because="two plausible readings")))

    _pinned("rework-skipped", prompt, at_wt)


def _session(world, runs, fix, steer):
    runs.open_session(fix, steer)
    [session] = world.pr_processes.sessions[fix.pr]
    return shlex.join(session.argv)


def test_a_steered_session_on_a_skipped_fix(world, runs, at_wt):
    command = _session(world, runs, _thread(at_wt,
        classification="ambiguous", skipped_because="two plausible readings"),
        "Keep the old name.")

    _pinned("session-steered", command, at_wt)


def test_a_session_nobody_steered(world, runs, at_wt):
    _pinned("session", _session(world, runs, _thread(at_wt), None), at_wt)


def test_the_fix_of_a_thread_with_jira_tickets(runs, claude, at_wt):
    prompt = _prompted(runs, claude, runs.fix(_thread(at_wt,
        tracker="jira", tracker_project="PROJ", branch_ticket="PROJ-21")))

    _pinned("thread-fix-jira", prompt, at_wt)


def test_the_fix_of_a_thread_with_github_issues(runs, claude, at_wt):
    prompt = _prompted(runs, claude, runs.fix(_thread(at_wt, tracker="github")))

    _pinned("thread-fix-github-issues", prompt, at_wt)


def test_the_rework_of_a_proposed_ticket(runs, claude, at_wt):
    prompt = _prompted(runs, claude, runs.rework(_thread(at_wt,
        note="This belongs in WEB, not PROJ.", classification="out-of-scope",
        reply="That is outside this PR, so I've proposed a ticket for it.",
        ticket_project="PROJ", ticket_title="Cache tax rates across exports",
        ticket_body="Each export reads its tax rate again.",
        tracker="jira", tracker_project="PROJ", branch_ticket="PROJ-21")))

    _pinned("rework-ticket", prompt, at_wt)


TICKET = {"ticket_project": "WEB", "ticket_title": "Share one tax rate cache",
          "ticket_body": "Each export builds its own cache.\n\nRaised on the review of #7."}


def test_the_filing_of_a_jira_ticket(runs, claude, at_wt):
    prompt = _prompted(runs, claude, runs.file_ticket(_thread(at_wt,
        tracker="jira", tracker_project="PROJ", **TICKET)))

    _pinned("file-ticket-jira", prompt, at_wt)


def test_the_filing_of_a_github_issue(runs, claude, at_wt):
    prompt = _prompted(runs, claude, runs.file_ticket(_thread(at_wt,
        tracker="github", **{**TICKET, "ticket_project": "acme/widgets"})))

    _pinned("file-ticket-github-issue", prompt, at_wt)
