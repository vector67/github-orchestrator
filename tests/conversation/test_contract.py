from dataclasses import dataclass
from pathlib import Path

import pytest

from github_orchestrator.agent_runs.fake import FakeAgentRuns
from github_orchestrator.change_detection import Poll
from github_orchestrator.conversation import (
    Classification,
    ConversationState,
    Denied,
    ErrorCode,
    Verdict,
)
from github_orchestrator.desktop import Badge
from github_orchestrator.domain import Location, Pr, Side
from github_orchestrator.github import CommentKind, PullRequestState
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.notifications.fake import FakeNotifications, FixReady, Posted
from github_orchestrator.settings.fake import fake_settings
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.conversation.support import (
    THE_PR,
    WORKTREE,
    World,
    at,
    commit_fix,
    drain,
    fake_conversation_managers,
    hear,
    lost,
    on_github,
    propose,
    repo_at,
    said,
    start_run,
    world,
)
from tests.thread_records.support import disk_thread_records

NOW = "2026-09-26T10:00:00Z"
KEY = "PRRT_101"
BODY = "Please rename this helper."
TITLE = "Rename the helper"


@dataclass
class RealStage:
    here: World

    @property
    def github(self) -> FakeGitHub:
        return self.here.github

    @property
    def working_copies(self) -> FakeWorkingCopies:
        return self.here.working_copies

    @property
    def agent_runs(self) -> FakeAgentRuns:
        return self.here.agent_runs

    def of(self, pr: Pr):
        return self.here.conversation_managers.of(pr)

    def watch(self, pr: Pr, *, is_author: bool, title: str | None = None,
              base_branch: str = "main", head_sha: str | None = None,
              branch: str | None = None) -> None:
        author = self.github.account if is_author else f"not-{self.github.account}"
        self.github.add_pr(pr, PullRequestState(title=title, author=author,
                                                base_branch=base_branch, head_sha=head_sha,
                                                branch=branch))
        self.here.change_detection.advance(
            pr, Poll(state=self.github.pr_state(pr), polled_at=NOW), set())


@pytest.fixture(params=["fake", "real"])
def stage(request, tmp_path: Path):
    if request.param == "fake":
        return fake_conversation_managers(clock=at(NOW))
    settings = fake_settings(tmp_path / "data", agents_enabled=True)
    return RealStage(world(settings, thread_records=disk_thread_records(tmp_path / "threads"),
                           clock=at(NOW)))


def _pr(stage, *, is_author: bool = True):
    repo_at(stage.working_copies, WORKTREE, {"f": "old\n", "README": "hello"})
    head = stage.working_copies.commit(WORKTREE, {"f": "older\n"}, "change f")
    stage.watch(THE_PR, is_author=is_author, title=TITLE, head_sha=head)
    return stage.of(THE_PR)


def _commented(stage, *, is_author: bool = True, key: str = KEY):
    threads = _pr(stage, is_author=is_author)
    on_github(stage.github, key, said(101, BODY))
    hear(threads)
    return threads


def _standing(threads, key: str = KEY) -> ConversationState:
    return threads.get(key).standing


def _replies(stage, key: str = KEY) -> list[str]:
    return [comment.body for comment in stage.github.thread(key).comments[1:]]


def test_a_comment_heard_from_github_is_a_conversation_queued_for_a_fix(stage):
    threads = _pr(stage)
    on_github(stage.github, KEY, said(101, BODY))

    absorbed = hear(threads)

    assert [conversation.key for conversation in absorbed.created] == [KEY]
    conversation = threads.get(KEY)
    assert conversation.body == BODY
    assert conversation.standing is ConversationState.QUEUED
    assert [one.key for one in threads.all()] == [KEY]


def test_an_open_thread_already_in_the_cursor_without_a_record_is_a_conversation_on_the_next_poll(
        stage):
    threads = _pr(stage)
    on_github(stage.github, KEY, said(101, BODY))
    threads.poll(PullRequestState()).commit()

    absorbed = hear(threads)

    assert [conversation.key for conversation in absorbed.created] == [KEY]
    assert _standing(threads) is ConversationState.QUEUED


def test_a_thread_already_resolved_on_github_is_no_conversation(stage):
    threads = _pr(stage)
    on_github(stage.github, KEY, said(101, BODY), is_resolved=True)

    hear(threads)
    hear(threads)

    assert threads.all() == []


def test_a_pr_comment_already_there_when_the_pr_is_first_polled_is_no_conversation(stage):
    threads = _pr(stage)
    on_github(stage.github, "IC_101", said(101, BODY), kind=CommentKind.ISSUE, path=None,
              line=None)

    hear(threads)

    assert threads.all() == []


def test_a_recorded_thread_is_not_heard_again(stage):
    threads = _commented(stage)

    assert threads.poll(PullRequestState()).activity is None


def test_a_tick_starts_a_run_on_a_queued_conversation(stage):
    threads = _commented(stage)

    start_run(stage, threads, finishes=False)

    assert _standing(threads) is ConversationState.WORKING
    assert len(stage.agent_runs.started) == 1
    assert threads.counts().live == 1


def test_a_comment_deleted_on_github_is_found_removed_on_a_recheck(stage):
    threads = _commented(stage)
    stage.github.delete_comment(THE_PR, stage.github.thread(KEY).kind, 101)

    lost(threads, KEY)

    assert threads.get(KEY).is_removed


def test_an_agents_plan_and_its_steps_done_are_kept_on_the_fix(stage):
    threads = _commented(stage)
    start_run(stage, threads, finishes=False)

    with threads.editing(KEY) as editable:
        editable.plan([("rename the helper", "f"), ("update callers", None)])
    with threads.editing(KEY) as editable:
        editable.step_done([1])

    plan = threads.get(KEY).fix.plan
    assert [(step.text, step.file, step.done) for step in plan] == [
        ("rename the helper", "f", True), ("update callers", None, False)]


def test_a_fix_reported_ready_is_proposed_with_its_commit(stage):
    threads = _commented(stage)

    propose(stage, threads, KEY, summary="renamed it")

    conversation = threads.get(KEY)
    assert conversation.fix.is_proposed
    assert conversation.fix.summary == "renamed it"
    assert conversation.standing is ConversationState.READY
    assert threads.counts().proposed == 1


def test_a_declined_fix_keeps_its_classification_and_reason(stage):
    threads = _commented(stage)
    start_run(stage, threads, finishes=False)

    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.RISKY, "it wants a schema change")

    fix = threads.get(KEY).fix
    assert fix.is_declined
    assert (fix.classification, fix.reason) == (Classification.RISKY, "it wants a schema change")


def test_a_failed_attempt_is_queued_again_with_its_reason(stage):
    threads = _commented(stage)
    start_run(stage, threads, finishes=False)

    with threads.editing(KEY) as editable:
        editable.fail("the tests would not run")

    conversation = threads.get(KEY)
    assert conversation.standing is ConversationState.QUEUED
    assert conversation.fix.reason == "the tests would not run"


def test_a_fix_that_failed_every_attempt_can_be_retried(stage):
    threads = _commented(stage)
    for _ in range(threads.get(KEY).run_holder.attempts_allowed):
        start_run(stage, threads)
        with threads.editing(KEY) as editable:
            editable.fail("the tests would not run")
    assert threads.get(KEY).fix.has_failed

    with threads.editing(KEY) as editable:
        editable.retry()
    drain(threads)

    assert _standing(threads) in (ConversationState.QUEUED, ConversationState.WORKING)


def test_a_fix_proposed_when_its_run_ends_is_announced_as_ready(stage):
    threads = _commented(stage)
    start_run(stage, threads)
    sha = commit_fix(stage, KEY)
    with threads.editing(KEY) as editable:
        editable.ready(sha, summary="renamed it")
    news = FakeNotifications()

    threads.tick(news, on_hold=False)

    assert news.gathered == [FixReady(pr=THE_PR, key=KEY, gist=threads.get(KEY).gist,
                                      comments=(("reviewer", BODY),),
                                      fix_summary="renamed it")]


def test_a_fix_declined_when_its_run_ends_asks_for_your_call(stage):
    threads = _commented(stage)
    start_run(stage, threads)
    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.RISKY, "it wants a schema change")
    news = FakeNotifications()

    threads.tick(news, on_hold=False)

    assert news.posted == [Posted(THE_PR, Badge.NEEDS_YOU,
                                  f"Comment needs your call on {THE_PR.short}",
                                  "reviewer\nrisky: it wants a schema change")]


def test_a_fix_that_fails_its_last_attempt_is_announced_as_failed(stage):
    threads = _commented(stage)
    for _ in range(threads.get(KEY).run_holder.attempts_allowed):
        start_run(stage, threads)
        with threads.editing(KEY) as editable:
            editable.fail("the tests would not run")
    news = FakeNotifications()

    threads.tick(news, on_hold=False)

    assert news.posted == [Posted(THE_PR, Badge.FAILED, f"Fix failed on {THE_PR.short}",
                                  f"{threads.get(KEY).gist}: the tests would not run")]


def test_a_tick_with_no_run_ending_announces_nothing(stage):
    threads = _commented(stage)
    news = FakeNotifications()

    threads.tick(news, on_hold=False)

    assert (news.posted, news.gathered) == ([], [])


def test_a_report_on_a_thread_nobody_has_is_denied_not_found(stage):
    threads = _pr(stage)

    with threads.editing("PRRT_nobody") as editable:
        denied = editable.fail("no such thing")

    assert isinstance(denied, Denied)
    assert denied.code is ErrorCode.NOT_FOUND


def test_a_thread_opened_by_hand_answers_its_workspace(stage):
    threads = _pr(stage)
    on_github(stage.github, KEY, said(101, BODY))

    workspace = threads.open_thread(KEY, kind="review", path="f", line=1,
                                                comment_id=101, author="reviewer", body=BODY)

    assert workspace == stage.working_copies.thread_checkout(THE_PR, KEY)
    assert threads.get(KEY).body == BODY


def test_an_approved_fix_lands_and_its_reply_is_posted(stage):
    threads = _commented(stage)
    propose(stage, threads, KEY)

    with threads.editing(KEY) as editable:
        editable.approve(reply="Renamed it.")
    drain(threads)

    conversation = threads.get(KEY)
    assert conversation.standing is ConversationState.DONE
    assert stage.working_copies.commits[stage.working_copies.branches["main"]].tree["f"] == "new\n"
    [reply] = _replies(stage)
    assert reply.startswith("Renamed it.")


def test_a_rework_sends_the_proposal_back_to_the_agent(stage):
    threads = _commented(stage)
    propose(stage, threads, KEY)

    with threads.editing(KEY) as editable:
        editable.rework(note="also rename the test", pointed=[("f", 1, "old")])
    drain(threads)

    assert _standing(threads) is ConversationState.REWORK


def test_a_session_started_on_a_proposal_is_in_session(stage):
    threads = _commented(stage)
    propose(stage, threads, KEY)
    stage.agent_runs.pr_processes.open(THE_PR, Path(WORKTREE))

    with threads.editing(KEY) as editable:
        editable.start_session(steer="look at the callers")
    drain(threads)

    assert _standing(threads) is ConversationState.IN_SESSION
    [session] = stage.agent_runs.sessions
    assert session.steer == "look at the callers"


def test_a_stopped_run_leaves_the_fix_for_the_operator(stage):
    threads = _commented(stage)
    start_run(stage, threads, finishes=False)

    with threads.editing(KEY) as editable:
        editable.stop()
    drain(threads)

    assert _standing(threads) is ConversationState.READY


def test_a_resolved_conversation_is_done_and_resolved_on_github(stage):
    threads = _commented(stage)
    propose(stage, threads, KEY)

    with threads.editing(KEY) as editable:
        editable.resolve(reply="Handled elsewhere.")
    drain(threads)

    assert _standing(threads) is ConversationState.DONE
    assert _replies(stage) == ["Handled elsewhere."]


def test_an_authors_resolve_leaves_the_thread_open_on_github(stage):
    threads = _commented(stage)
    propose(stage, threads, KEY)

    with threads.editing(KEY) as editable:
        editable.resolve()
    drain(threads)

    assert _standing(threads) is ConversationState.DONE
    assert not stage.github.thread(KEY).is_resolved


def test_an_authors_resolve_on_github_marks_the_thread_resolved_there(stage):
    threads = _commented(stage)
    propose(stage, threads, KEY)

    with threads.editing(KEY) as editable:
        editable.resolve(resolve=True)
    drain(threads)

    assert _standing(threads) is ConversationState.DONE
    assert stage.github.thread(KEY).is_resolved is True
    assert _replies(stage) == []


def test_an_authors_resolve_on_github_posts_the_reply_before_resolving(stage):
    threads = _commented(stage)
    propose(stage, threads, KEY)

    with threads.editing(KEY) as editable:
        editable.resolve(reply="Handled elsewhere.", resolve=True)
    drain(threads)

    assert _standing(threads) is ConversationState.DONE
    assert stage.github.thread(KEY).is_resolved is True
    assert _replies(stage) == ["Handled elsewhere."]


def test_an_authors_resolve_on_github_puts_no_thumbs_up_on_the_thread(stage):
    threads = _commented(stage)
    propose(stage, threads, KEY)
    with threads.editing(KEY) as editable:
        editable.reply("I'll add that to the ticket.")
    drain(threads)

    with threads.editing(KEY) as editable:
        editable.resolve(resolve=True)
    drain(threads)

    assert stage.github.thread(KEY).is_resolved is True
    assert stage.github.reactions == {}


def test_an_authors_resolve_on_github_of_a_removed_comment_closes_it_on_the_board(stage):
    threads = _commented(stage)
    stage.github.delete_comment(THE_PR, stage.github.thread(KEY).kind, 101)
    lost(threads, KEY)

    with threads.editing(KEY) as editable:
        editable.resolve(resolve=True)
    drain(threads)

    assert _standing(threads) is ConversationState.DONE


def test_a_resolve_on_github_that_also_deletes_the_comment_is_denied(stage):
    threads = _commented(stage)
    propose(stage, threads, KEY)

    with threads.editing(KEY) as editable:
        denied = editable.resolve(delete_comment=True, resolve=True)

    assert isinstance(denied, Denied)
    assert denied.code is ErrorCode.MALFORMED_REQUEST


@pytest.mark.parametrize("stage", ["fake"], indirect=True)
def test_a_delete_of_a_comment_someone_else_wrote_is_denied(stage):
    threads = _commented(stage)
    propose(stage, threads, KEY)

    with threads.editing(KEY) as editable:
        denied = editable.reject(delete_comment=True)

    assert denied == Denied(ErrorCode.NOT_DELETABLE,
                            "reviewer wrote that comment, so it is not yours to delete")


def test_a_rejected_conversation_is_done(stage):
    threads = _commented(stage)
    propose(stage, threads, KEY)

    with threads.editing(KEY) as editable:
        editable.reject(reply="Not doing this.")
    drain(threads)

    assert _standing(threads) is ConversationState.DONE
    assert _replies(stage) == ["Not doing this."]


def test_a_deferred_conversation_waits_until_it_is_unparked(stage):
    threads = _commented(stage)
    propose(stage, threads, KEY)

    with threads.editing(KEY) as editable:
        editable.place(ConversationState.DEFERRED, note="after the release")
    drain(threads)
    assert _standing(threads) is ConversationState.DEFERRED
    assert threads.get(KEY).defer_note == "after the release"

    with threads.editing(KEY) as editable:
        editable.unpark()
    drain(threads)
    assert _standing(threads) is ConversationState.READY


def test_a_reply_is_posted_to_the_thread(stage):
    threads = _commented(stage)
    propose(stage, threads, KEY)

    with threads.editing(KEY) as editable:
        editable.reply("What did you mean?")
    drain(threads)

    assert _replies(stage) == ["What did you mean?"]
    assert threads.get(KEY).fix.is_proposed


def test_a_conversation_marked_seen_says_when(stage):
    threads = _commented(stage)

    with threads.editing(KEY) as editable:
        editable.mark_seen()

    assert threads.get(KEY).seen_at is not None


def _anchor() -> Location:
    return Location(path="f", line=1, side=Side.AFTER)


def test_a_draft_is_opened_edited_enrolled_and_withdrawn(stage):
    threads = _pr(stage, is_author=False)

    drafted = threads.open_draft("rename it", _anchor())
    assert drafted.standing is ConversationState.DRAFT
    with threads.editing(drafted.key) as editable:
        editable.edit("rename it, please", _anchor())
    drain(threads)
    with threads.editing(drafted.key) as editable:
        editable.enrol()
    drain(threads)
    enrolled = threads.get(drafted.key)
    assert (enrolled.body, enrolled.standing) == ("rename it, please", ConversationState.ENROLLED)

    with threads.editing(drafted.key) as editable:
        editable.withdraw()
    drain(threads)

    assert _standing(threads, drafted.key) is ConversationState.DRAFT


def test_a_discarded_draft_is_done(stage):
    threads = _pr(stage, is_author=False)
    drafted = threads.open_draft("rename it", _anchor())

    with threads.editing(drafted.key) as editable:
        editable.discard()
    drain(threads)

    assert _standing(threads, drafted.key) is ConversationState.DONE


def test_a_draft_posted_now_is_a_comment_on_github(stage):
    threads = _pr(stage, is_author=False)
    drafted = threads.open_draft("rename it", _anchor())

    with threads.editing(drafted.key) as editable:
        editable.post_now()
    drain(threads)

    assert [comment.body for thread in stage.github.threads(THE_PR)
            for comment in thread.comments] == ["rename it"]


def test_a_review_sent_carries_the_enrolled_drafts(stage):
    threads = _pr(stage, is_author=False)
    drafted = threads.open_draft("rename it", _anchor())
    with threads.editing(drafted.key) as editable:
        editable.enrol()
    drain(threads)

    sent = threads.send_review(Verdict.REQUEST_CHANGES, "a few things")
    drain(threads)

    assert not isinstance(sent, Denied), sent
    assert [review.verdict for review in threads.reviews()] == [Verdict.REQUEST_CHANGES]


def test_the_facts_say_whose_pr_it_is_and_its_title(stage):
    threads = _pr(stage, is_author=False)

    facts = threads.facts()

    assert (facts.is_author, facts.title, facts.base_branch) == (False, TITLE, "main")
    assert facts.head_sha == stage.working_copies.head_of(WORKTREE)
    assert facts.account == stage.github.account


def test_a_conversation_answers_its_comment_url_and_its_activity(stage):
    threads = _commented(stage)
    conversation = threads.get(KEY)

    assert threads.comment_url(conversation, 101) == stage.github.comment_url(
        THE_PR, stage.github.thread(KEY).kind, 101)
    assert threads.activity(conversation).last_action is None


def test_a_body_too_long_for_github_is_said_so(stage):
    threads = _pr(stage)

    assert threads.too_long("fine") is None
    assert threads.too_long("x" * 70000) is not None


def test_a_command_on_a_conversation_whose_edit_has_closed_is_refused(stage):
    threads = _commented(stage)
    with threads.editing(KEY) as conversation:
        pass

    with pytest.raises(RuntimeError, match="closed"):
        conversation.resolve()
    assert threads.get(KEY).standing is ConversationState.QUEUED
