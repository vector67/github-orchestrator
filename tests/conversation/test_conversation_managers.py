from datetime import datetime, timezone

from github_orchestrator.agent_runs.fake import Outcome as RunOutcome
from github_orchestrator.conversation import (
    Classification,
    ConversationState,
    Denied,
    ErrorCode,
    OperationKind,
)
from github_orchestrator.domain import Sha
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    ReviewState,
    Thread,
    ThreadComment,
)
from github_orchestrator.notifications.fake import FakeNotifications
from tests.builders import a_pr
from tests.conversation.support import (
    PR,
    REPO,
    WORKTREE,
    hear,
    on_github,
    repo_at,
    said,
    start_run,
    world,
)
from tests.disk_layout import thread_file
from tests.thread_records.support import disk_thread_records

THE_PR = a_pr(PR, REPO)

KEY = "PRRT_one"


def _heard(here):
    repo_at(here.working_copies, WORKTREE)
    threads = here.threads()
    on_github(here.github, KEY, said(101, "rename this"))
    hear(threads)
    return threads


def test_a_handle_keeps_the_runs_it_started_between_passes(settings):
    here = world(settings)
    threads = _heard(here)
    here.agent_runs.script(RunOutcome(finishes=False))

    threads.tick(FakeNotifications(), on_hold=False)
    threads.tick(FakeNotifications(), on_hold=False)

    assert len(here.agent_runs.started) == 1
    assert threads.counts().live == 1
    assert threads.counts().queued == 0
    assert threads.get(KEY).standing is ConversationState.WORKING


def test_each_handle_starts_with_no_runs_of_its_own(settings):
    here = world(settings)
    first = _heard(here)
    here.agent_runs.script(RunOutcome(finishes=False))
    first.tick(FakeNotifications(), on_hold=False)

    assert here.conversation_managers.of(THE_PR).counts().live == 0


def test_a_refusal_names_the_rule_a_command_breaks(settings):
    threads = world(settings).conversation_managers.of(THE_PR)

    with threads.editing(KEY) as editable:
        refused = editable.approve()

    assert isinstance(refused, Denied)
    assert refused.code in ErrorCode
    assert refused.reason


def test_a_command_the_rules_allow_is_queued_for_the_drain(settings):
    here = world(settings)
    threads = _heard(here)
    start_run(here, threads, finishes=False)
    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.NEEDS_HUMAN, "nothing to change")

    with threads.editing(KEY) as editable:
        asked = editable.resolve()

    assert not isinstance(asked, Denied), asked
    assert asked.operations[-1].kind is OperationKind.RESOLVE
    assert threads.get(KEY).operations[-1].in_flight


def test_a_refusal_queues_nothing(settings):
    threads = _heard(world(settings))
    before = threads.get(KEY).operations

    with threads.editing(KEY) as editable:
        refused = editable.approve()

    assert isinstance(refused, Denied)
    assert threads.get(KEY).operations == before


def test_an_opened_thread_has_a_workspace_cut_off_the_pr_worktree(settings, tmp_path):
    here = world(settings)
    pr_worktree = tmp_path / "widgets"
    here.working_copies.add_repo(pr_worktree, {"f": "1"}, "first")
    threads = here.threads(worktree=str(pr_worktree))

    checkout = threads.open_thread(KEY, kind="review", path="f", line=1, comment_id=101,
                                   author="reviewer", body="rename this")

    assert checkout == here.working_copies.thread_checkout(THE_PR, KEY)
    assert here.working_copies.holds_thread(THE_PR, KEY)
    assert here.load(KEY).fix.base_sha == Sha(here.working_copies.head_of(pr_worktree))


def test_a_poll_reports_a_new_thread_as_active(settings):
    here = world(settings)
    here.github.add_pr(THE_PR)
    here.github.add_thread(THE_PR, Thread(
        key=KEY, kind=CommentKind.REVIEW, path="f", line=1,
        comments=(ThreadComment(id=101, author="reviewer", body="rename this",
                                created_at="2025-12-01T00:00:00Z"),)))

    polled = here.conversation_managers.of(THE_PR).poll(PullRequestState())

    assert [thread.key for thread in polled.activity.threads] == [KEY]
    assert polled.unresolved_count == 1


def _said(comment_id, author, at):
    return ThreadComment(id=comment_id, author=author, body="words", created_at=at)


def test_a_poll_says_when_i_last_commented_and_how_many_others_did(settings):
    me = settings.config.gh_account
    here = world(settings)
    here.github.add_pr(THE_PR)
    here.github.add_thread(THE_PR, Thread(key=KEY, kind=CommentKind.REVIEW, path="f", line=1,
                                          comments=(_said(1, "alice", "2026-01-01T00:00:00Z"),
                                                    _said(2, me, "2026-01-02T00:00:00Z"),
                                                    _said(3, me, "2026-01-03T00:00:00Z"),
                                                    _said(4, "bob", "2026-01-04T00:00:00Z"))))

    polled = here.conversation_managers.of(THE_PR).poll(PullRequestState())

    assert (polled.my_last_comment_at, polled.comments_by_others) == ("2026-01-03T00:00:00Z", 2)


def test_a_review_summary_with_a_verdict_is_no_comment_but_a_commenting_one_is(settings):
    here = world(settings)
    here.github.add_pr(THE_PR)
    here.github.add_thread(THE_PR, Thread(key="PRR_one", kind=CommentKind.REVIEW_SUMMARY,
                                          state=ReviewState.CHANGES_REQUESTED,
                                          comments=(_said(1, "alice", "2026-01-01T00:00:00Z"),)))
    here.github.add_thread(THE_PR, Thread(key="PRR_two", kind=CommentKind.REVIEW_SUMMARY,
                                          state=ReviewState.COMMENTED,
                                          comments=(_said(2, "bob", "2026-01-02T00:00:00Z"),)))

    polled = here.conversation_managers.of(THE_PR).poll(PullRequestState())

    assert (polled.my_last_comment_at, polled.comments_by_others) == (None, 1)


def test_the_comment_cutoff_is_five_seconds_behind_the_clock(settings):
    here = world(settings, clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
    here.github.add_pr(THE_PR)

    assert here.conversation_managers.of(THE_PR).poll(PullRequestState()).polled_at == "2025-12-31T23:59:55Z"


def test_the_listing_holds_each_stored_thread_and_marks_a_corrupt_one_unreadable(settings):
    here = world(settings, thread_records=disk_thread_records(settings.threads_dir))
    _heard(here)
    corrupt = thread_file(settings.threads_dir, THE_PR, "PRRT_bad")
    corrupt.write_text("{")

    listed = here.conversation_managers.of(THE_PR).all()

    assert [(c.key, c.is_unreadable) for c in listed] == [(KEY, False), ("PRRT_bad", True)]
    assert listed[0].body == "rename this"
