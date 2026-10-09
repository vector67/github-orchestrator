import json
from dataclasses import replace
from datetime import datetime

from github_orchestrator.agent_runs.fake import Outcome as RunOutcome
from github_orchestrator.change_detection import Poll
from github_orchestrator.conversation import (
    Classification,
    Conversation,
    ConversationState,
    Denied,
    ErrorCode,
    OperationKind,
    OperationState,
    ReasonCode,
)
from github_orchestrator.github import ThreadComment
from github_orchestrator.github.fake import FakeGitHub, GhError
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.conversation.support import (
    PR,
    REPO,
    WORKTREE,
    World,
    at,
    commit_fix,
    drain,
    hear,
    on_github,
    propose,
    repo_at,
    said,
    start_run,
    world,
)

THE_PR = a_pr(PR, REPO)

KEY = "PRRT_one"

EARLIER = "2026-09-22T09:59:00Z"
OPENED_AT = "2026-09-22T10:00:00.000000Z"

NOW = "2026-09-22T10:00:00Z"

LATER = "2026-09-22T10:05:00Z"



def refusing_remote() -> FakeWorkingCopies:
    copies = FakeWorkingCopies()
    copies.refuse_pushes("the remote hung up")
    return copies


class RefusingGitHub(FakeGitHub):
    def reply_to_thread(self, key: str, body: str) -> ThreadComment | None:
        raise GhError("HTTP 502")

    def delete_comment(self, pr, kind: str, comment_id: int) -> None:
        raise GhError("HTTP 403")

    def resolve_thread(self, key: str) -> None:
        raise GhError("HTTP 403")

    def unresolve_thread(self, key: str) -> None:
        raise GhError("HTTP 403")


class Clock:
    def __init__(self, iso: str = NOW) -> None:
        self.iso = iso

    def __call__(self) -> datetime:
        return at(self.iso)()


def _world(settings, *, github=None, working_copies=None, clock=None) -> World:
    github = github or FakeGitHub()
    github.add_pr(THE_PR)
    here = world(settings, github=github,
                 working_copies=working_copies or FakeWorkingCopies(github),
                 clock=clock or Clock())
    repo_at(here.working_copies, WORKTREE, {"f.py": "old\n"})
    return here


def _heard(here: World, is_author=None, author: str = "reviewer", **handle) -> object:
    threads = here.threads(is_author=is_author, **handle)
    on_github(here.github, KEY, said(1, "rename this", author=author), path="f.py")
    hear(threads)
    return threads


def _conversation(threads) -> Conversation:
    found: Conversation = threads.get(KEY)
    return found


def _proposed(here: World, **handle):
    threads = _heard(here, **handle)
    propose(here, threads, KEY, {"f.py": "new\n"})
    return threads


def _running(here: World):
    threads = _heard(here)
    start_run(here, threads, finishes=False)
    return threads


def _asked(threads, verb) -> Conversation:
    with threads.editing(KEY) as conversation:
        asked = verb(conversation)
    assert not isinstance(asked, Denied), asked
    drain(threads)
    return _conversation(threads)


def _answers(here: World) -> list[str]:
    thread = here.github.thread(KEY)
    return [] if thread is None else [comment.body for comment in thread.comments[1:]]


def _only(conversation, kind):
    matching = [op for op in conversation.operations if op.kind == kind]
    assert len(matching) == 1, conversation.operations
    return matching[0]


def _opened(here: World, is_author=None) -> Conversation:
    threads = here.threads(is_author=is_author)
    threads.open_thread(KEY, kind="review", path="f.py", line=1, comment_id=1,
                                    author="reviewer", body="rename this")
    return _conversation(threads)


def _conflicting(here: World, **handle):
    threads = _proposed(here, **handle)
    here.working_copies.commit(WORKTREE, {"f.py": "theirs\n"}, "someone else")
    return threads


def test_a_thread_the_board_opens_is_born_with_its_first_run_pending(settings):
    here = _world(settings)

    [first] = _opened(here).operations

    assert (first.id, first.kind, first.state, first.requested_at) == (
        f"{KEY}.1", OperationKind.FIRST, OperationState.PENDING, OPENED_AT)


def test_a_reviewers_thread_is_born_with_nothing_to_run(settings):
    here = _world(settings)

    assert _opened(here, is_author=False).operations == ()


def test_a_verb_is_recorded_under_the_id_and_time_it_was_asked_with(settings):
    clock = Clock()
    here = _world(settings, clock=clock)
    threads = _proposed(here, agents_enabled=True)
    here.agent_runs.script(RunOutcome(finishes=False))
    clock.iso = EARLIER

    with threads.editing(KEY) as editable:
        answered = _only(editable.rework(note="the other way"), OperationKind.REWORK)
    clock.iso = LATER
    drain(threads)

    rework = _only(_conversation(threads), OperationKind.REWORK)
    assert rework.id == answered.id
    assert rework.requested_at == EARLIER
    assert rework.in_flight
    assert rework.brief.note == "the other way"


def test_a_run_moves_from_pending_to_running_to_applied_as_the_board_drives_it(settings):
    clock = Clock(EARLIER)
    here = _world(settings, clock=clock)
    threads = _proposed(here, agents_enabled=True)
    with threads.editing(KEY) as editable:
        pending = _only(editable.rework(note="the other way"), OperationKind.REWORK)

    clock.iso = NOW
    start_run(here, threads, finishes=False)
    running = _only(_conversation(threads), OperationKind.REWORK)
    clock.iso = LATER
    with threads.editing(KEY) as editable:
        editable.ready(commit_fix(here, KEY, {"f.py": "newer\n"}))

    assert pending.state == OperationState.PENDING
    assert running.state == OperationState.RUNNING
    settled = _only(_conversation(threads), OperationKind.REWORK)
    assert settled.state == OperationState.APPLIED
    assert settled.settled_at == LATER
    assert settled.attempts == 1


def test_a_second_run_leaves_the_first_where_a_client_holding_its_id_can_find_it(settings):
    here = _world(settings)
    threads = _proposed(here, agents_enabled=True)

    reworked = _asked(threads, lambda conversation: conversation.rework(note="the other way"))

    first, rework = reworked.operations
    assert (first.id, first.kind, first.state) == (
        f"{KEY}.1", OperationKind.FIRST, OperationState.APPLIED)
    assert rework.kind == OperationKind.REWORK


def test_a_run_put_back_by_the_board_is_requeued_and_picked_up_again_as_itself(settings):
    here = _world(settings)
    running = _conversation(_running(here))
    restarted = here.threads()

    restarted.tick(FakeNotifications(), on_hold=True)
    lost = _conversation(restarted)
    start_run(here, restarted, finishes=False)
    again = _conversation(restarted)

    assert lost.operations[0].state == OperationState.REQUEUED
    assert again.operations[0].state == OperationState.RUNNING
    assert again.operations[0].id == running.operations[0].id


def test_a_declined_run_settles_refused_with_the_agents_reason(settings):
    here = _world(settings)
    threads = _running(here)

    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.NEEDS_HUMAN, "which helper?")

    run = _conversation(threads).operations[0]
    assert run.state == OperationState.REFUSED
    assert run.reason_code == ReasonCode.AGENT_DECLINED
    assert run.reason == "which helper?"
    assert run.settled_at == NOW


def test_stop_names_the_run_it_halted_and_the_run_settles_withdrawn(settings):
    here = _world(settings)
    threads = _running(here)

    stopped = _asked(threads, lambda conversation: conversation.stop())

    run, stop = stopped.operations
    assert run.state == OperationState.REFUSED
    assert run.reason_code == ReasonCode.WITHDRAWN
    assert stop.kind == OperationKind.STOP
    assert stop.state == OperationState.APPLIED
    assert stop.stopped == run.id
    assert stop.settled_at == NOW


def test_a_verb_that_posts_settles_with_the_comment_github_made(settings):
    here = _world(settings)
    threads = _proposed(here)

    resolved = _asked(threads, lambda conversation: conversation.resolve(reply="thanks"))

    resolve = _only(resolved, OperationKind.RESOLVE)
    assert resolve.state == OperationState.APPLIED
    assert resolve.posted_comment == here.github.thread(KEY).comments[-1].id
    assert resolve.text == "thanks"
    assert resolve.settled_at == NOW


def test_a_verb_that_touches_nothing_outside_the_board_applies_at_once(settings):
    here = _world(settings)
    threads = _proposed(here)
    record = here.github.prs[THE_PR]
    record.state = replace(record.state, head_sha="abc1234")
    here.change_detection.advance(THE_PR, Poll(state=record.state, polled_at=NOW), set())

    deferred = _asked(threads, lambda conversation: conversation.place(ConversationState.DEFERRED, until="push", note="later"))

    defer = _only(deferred, OperationKind.DEFER)
    assert defer.state == OperationState.APPLIED
    assert defer.until == "push"
    assert defer.text == "later"


def test_a_second_verb_before_the_board_took_the_first_is_refused(settings):
    here = _world(settings)
    threads = _proposed(here)
    with threads.editing(KEY) as editable:
        editable.reply("a word")

    with threads.editing(KEY) as editable:
        outcome = editable.place(ConversationState.DEFERRED)

    assert isinstance(outcome, Denied)
    assert outcome.code == ErrorCode.OPERATION_OUTSTANDING


def test_a_verb_the_drain_finds_it_cannot_take_is_recorded_refused(settings):
    here = _world(settings)
    threads = _proposed(here)
    with threads.editing(KEY) as editable:
        asked = _only(editable.resolve(reply="one more thing"),
                                       OperationKind.RESOLVE)
    record = here.github.prs[THE_PR]
    record.threads = [replace(thread, comments=(*thread.comments, said(900, "wait")))
                      for thread in record.threads]
    hear(threads)

    drain(threads)

    refused = _conversation(threads)
    resolve = _only(refused, OperationKind.RESOLVE)
    assert resolve.id == asked.id
    assert resolve.state == OperationState.REFUSED
    assert resolve.reason
    assert resolve.reason == refused.fix.decision_error
    assert resolve.settled_at == NOW
    assert _answers(here) == ["wait"]


def test_an_approve_waiting_on_the_agent_stays_pending_under_its_own_id(settings):
    here = _world(settings)
    _proposed(here)
    threads = here.threads(pr_run_live=True)
    with threads.editing(KEY) as editable:
        asked = _only(editable.approve(), OperationKind.APPROVE)
    drain(threads)

    drain(threads)

    approve = _only(_conversation(threads), OperationKind.APPROVE)
    assert approve.id == asked.id
    assert approve.state == OperationState.PENDING


def test_a_push_github_refused_settles_the_approve_refused_as_push_failed(settings):
    here = _world(settings, working_copies=refusing_remote())
    threads = _proposed(here)

    failed = _asked(threads, lambda conversation: conversation.approve())

    approve = _only(failed, OperationKind.APPROVE)
    assert approve.state == OperationState.REFUSED
    assert approve.reason_code == ReasonCode.PUSH_FAILED
    assert approve.reason == "the remote hung up"


def test_an_answer_github_refused_settles_the_approve_refused_as_reply_failed(settings):
    here = _world(settings, github=RefusingGitHub())
    threads = _proposed(here)

    failed = _asked(threads, lambda conversation: conversation.approve(reply="renamed"))

    assert (failed.fix.picked, failed.fix.pushed, failed.fix.answered) == (True, True, False)
    assert _only(failed, OperationKind.APPROVE).reason_code == ReasonCode.REPLY_FAILED


def test_a_pick_git_refused_hands_the_proposal_back_and_settles_git_failed(settings):
    here = _world(settings)
    threads = _proposed(here)
    checkout = here.working_copies.thread_checkout(THE_PR, KEY)
    here.working_copies.commit(checkout, {"f.py": "newer\n"}, "changed after review")

    refused = _asked(threads, lambda conversation: conversation.approve())

    assert refused.fix.is_proposed
    approve = _only(refused, OperationKind.APPROVE)
    assert approve.state == OperationState.REFUSED
    assert approve.reason_code == ReasonCode.GIT_FAILED


def test_a_pick_that_conflicts_puts_the_approve_back_behind_a_rebase_run(settings):
    here = _world(settings)
    threads = _conflicting(here, agents_enabled=True)
    here.agent_runs.script(RunOutcome(finishes=False))

    rebasing = _asked(threads, lambda conversation: conversation.approve())

    approve, rebase = rebasing.operations[-2:]
    assert approve.kind == OperationKind.APPROVE and approve.state == OperationState.REQUEUED
    assert rebase.kind == OperationKind.REBASE and rebase.in_flight
    assert rebasing.standing is ConversationState.LANDING


def test_a_conflict_with_no_rebase_allowed_settles_the_approve_as_a_conflict(settings):
    here = _world(settings)
    _conflicting(here, agents_enabled=True)
    threads = here.threads(agents_enabled=False)

    handed_back = _asked(threads, lambda conversation: conversation.approve())

    assert handed_back.fix.is_proposed
    assert _only(handed_back, OperationKind.APPROVE).reason_code == ReasonCode.CONFLICT


def test_a_reply_github_refused_settles_refused_as_reply_failed(settings):
    here = _world(settings, github=RefusingGitHub())
    threads = _proposed(here)

    failed = _asked(threads, lambda conversation: conversation.reply("a word"))

    reply = _only(failed, OperationKind.REPLY)
    assert reply.state == OperationState.REFUSED
    assert reply.reason_code == ReasonCode.REPLY_FAILED


def test_a_closing_reply_github_refused_settles_refused_as_reply_failed(settings):
    here = _world(settings, github=RefusingGitHub())
    threads = _proposed(here)

    failed = _asked(threads, lambda conversation: conversation.resolve(reply="thanks"))

    assert _only(failed, OperationKind.RESOLVE).reason_code == ReasonCode.REPLY_FAILED


def test_a_delete_github_refused_settles_refused_as_github_rejected(settings):
    here = _world(settings, github=RefusingGitHub())
    threads = _proposed(here, author=here.github.account)

    failed = _asked(threads, lambda conversation: conversation.resolve(delete_comment=True))

    assert _only(failed, OperationKind.RESOLVE).reason_code == ReasonCode.GITHUB_REJECTED


def _my_thread(here: World):
    threads = here.threads(is_author=False)
    on_github(here.github, KEY, said(1, "rename this", author=here.github.account),
              said(2, "why?", author="someone-else"), path="f.py")
    hear(threads)
    return threads


def test_a_resolve_github_would_not_take_settles_refused_as_github_rejected(settings):
    here = _world(settings, github=RefusingGitHub())
    threads = _my_thread(here)

    failed = _asked(threads, lambda conversation: conversation.resolve(resolve=True))

    assert _only(failed, OperationKind.RESOLVE).reason_code == ReasonCode.GITHUB_REJECTED


def test_an_unresolve_github_would_not_take_settles_refused_as_github_rejected(settings):
    here = _world(settings, github=RefusingGitHub())
    threads = _my_thread(here)
    record = here.github.prs[THE_PR]
    record.threads = [replace(thread, is_resolved=True) for thread in record.threads]
    hear(threads)

    failed = _asked(threads, lambda conversation: conversation.unpark())

    assert _only(failed, OperationKind.UNPARK).reason_code == ReasonCode.GITHUB_REJECTED


def test_unparking_a_rejected_thread_records_the_unpark_and_the_run_it_asks_for(settings):
    here = _world(settings)
    threads = _proposed(here)
    _asked(threads, lambda conversation: conversation.reject())

    unparked = _asked(threads, lambda conversation: conversation.unpark())

    unpark, first = unparked.operations[-2:]
    assert (unpark.kind, unpark.state) == (OperationKind.UNPARK, OperationState.APPLIED)
    assert first.kind == OperationKind.FIRST and first.in_flight


def test_a_record_written_before_the_history_gives_its_fix_the_id_the_history_keeps(settings):
    here = _world(settings)
    threads = _heard(here)
    stored = here.thread_records.of(THE_PR)
    document = json.loads(stored.load("json", KEY))
    stored.save("json", KEY, json.dumps(
        {name: value for name, value in document.items() if name != "operations"}).encode())
    read = _conversation(threads).operations

    start_run(here, threads, finishes=False)

    [running] = _conversation(threads).operations
    assert [op.id for op in read] == [running.id] == [f"{KEY}.1"]
    assert (running.kind, running.state, running.attempts) == (
        OperationKind.FIRST, OperationState.RUNNING, 1)


def test_a_plan_step_ticked_off_does_not_touch_the_history(settings):
    here = _world(settings)
    threads = _running(here)
    with threads.editing(KEY) as editable:
        planned = editable.plan([("rename it", None)])

    with threads.editing(KEY) as editable:
        editable.step_done(indexes=(1,))

    ticked = _conversation(threads)
    assert ticked.fix.plan[0].done is True
    assert ticked.operations == planned.operations


def test_a_reply_posted_settles_the_reply_with_the_comment_it_made(settings):
    here = _world(settings)
    threads = _proposed(here)

    posted = _asked(threads, lambda conversation: conversation.reply("a word"))

    reply = _only(posted, OperationKind.REPLY)
    assert reply.state == OperationState.APPLIED
    assert reply.posted_comment == here.github.thread(KEY).comments[-1].id
    assert reply.text == "a word"
