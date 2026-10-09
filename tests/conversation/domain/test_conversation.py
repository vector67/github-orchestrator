from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from github_orchestrator.agent_runs.fake import (
    CommentAsked,
    FakeAgentRuns,
    HeldVerdicts,
    ThreadAsked,
    VerdictAsked,
)
from github_orchestrator.change_detection import Poll
from github_orchestrator.conversation import (
    Classification,
    ConversationState,
    Denied,
    ErrorCode,
    OperationKind,
    ReviewState,
)
from github_orchestrator.domain import AuthorKind, Side
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    ThreadComment,
)
from github_orchestrator.github import ReviewState as GitHubReviewState
from github_orchestrator.github.fake import FakeGitHub, GhError, ThreadAnchor
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.conversation.support import (
    THE_PR,
    WORKTREE,
    Moment,
    commit_fix,
    drain,
    hear,
    lost,
    on_github,
    propose,
    repo_at,
    start_run,
    without_runs,
    world,
)

KEY = "PRRT_one"
BODY = "rename this to _reference\n\nit reads better"
NOW = "2026-09-21T11:00:00Z"
CUTOFF = "2026-09-21T10:59:55Z"
EARLIER_NOW = "2026-09-21T09:00:00Z"
EARLIER_CUTOFF = "2026-09-21T08:59:55Z"
COMMENTED_AT = "2026-09-01T10:00:00Z"


@dataclass
class LaterSummaries(FakeAgentRuns):
    pending: list[Callable[[], None]] = field(default_factory=list)

    def summarize_comment(self, key, path, line, body, done, *, chars):
        self.pending.append(lambda: FakeAgentRuns.summarize_comment(
            self, key, path, line, body, done, chars=chars))

    def summarize_thread(self, key, path, line, comments, done, *, chars):
        self.pending.append(lambda: FakeAgentRuns.summarize_thread(
            self, key, path, line, comments, done, chars=chars))

    def settle(self) -> None:
        while self.pending:
            self.pending.pop(0)()

    def settle_newest_first(self) -> None:
        while self.pending:
            self.pending.pop()()


class ResolveRefused(FakeGitHub):
    def resolve_thread(self, key):
        raise GhError("gh: 403")

    def unresolve_thread(self, key):
        raise GhError("gh: 403")


class FirstReplyRefused(FakeGitHub):
    refused = False

    def reply_to_thread(self, key, body):
        if not self.refused:
            self.refused = True
            raise GhError("HTTP 403")
        return super().reply_to_thread(key, body)


def refusing_remote(github):
    copies = FakeWorkingCopies(github)
    copies.refuse_pushes("fatal: the remote hung up")
    return copies


def first_push_refused(github):
    copies = FakeWorkingCopies(github)
    copies.refuse_pushes("fatal: the remote hung up", times=1)
    return copies


def _comment(id=5001, author="reviewer", body="rename this to _reference",
             author_name="", review_state=None, created_at=COMMENTED_AT):
    return ThreadComment(id=id, author=author, body=body, created_at=created_at,
                         updated_at=created_at, author_name=author_name,
                         review_state=review_state)


ROOT = _comment(body=BODY)
REPLY = _comment(id=5002, author="anna", body="also worker.py")
BOT_NOTE = _comment(id=9999, author="octocat", body="\U0001F916 on it")
ANCHORED = ThreadAnchor(is_outdated=True, start_line=8, original_line=44,
                        original_start_line=42, original_commit="cafe1")
ANSWERED_THREAD = (_comment(author="reviewer"),
                   _comment(id=5002, author="jeffrey", body="fixed in a9296db"),
                   _comment(id=5003, author="reviewer", body="thanks"))


def _here(settings, *, github=None, agent_runs=None, remote=FakeWorkingCopies,
          clock=None):
    github = github or FakeGitHub()
    here = world(settings, github=github, agent_runs=agent_runs,
                 working_copies=remote(github), clock=clock or Moment(NOW))
    repo_at(here.working_copies, WORKTREE, {"f": "old\n", "README": "hello"})
    here.github.add_pr(THE_PR)
    return here


def _shows(here, *comments, kind=CommentKind.REVIEW, **fields):
    record = here.github.prs[THE_PR]
    record.threads = [one for one in record.threads if one.key != KEY]
    path, line = (None, None) if kind is CommentKind.ISSUE else ("src/app.py", 12)
    on_github(here.github, KEY, *comments, kind=kind, path=path, line=line, **fields)


def _adds(here, *comments):
    record = here.github.prs[THE_PR]
    thread = here.github.thread(KEY)
    record.threads = [one for one in record.threads if one.key != KEY]
    here.github.add_thread(THE_PR, replace(thread, comments=thread.comments + comments))


def _open(here, *comments, is_author=None, **fields):
    threads = here.threads(is_author=is_author)
    hear(threads)
    _shows(here, *(comments or (ROOT,)), **fields)
    hear(threads)
    return threads


def _held(threads):
    return threads.get(KEY)


def _reply_arrives(here, threads, *comments):
    _adds(here, *(comments or (REPLY,)))
    hear(threads)
    return _held(threads)


def _polled(here, threads, *comments, **fields):
    _shows(here, *(comments or (ROOT,)), *(() if "is_resolved" in fields else (BOT_NOTE,)),
           **fields)
    hear(threads)
    return _held(threads)


def _checked_out(here, fix):
    return bool(fix.base_sha) and here.working_copies.holds_thread(THE_PR, KEY)


def _said(conversation):
    return [(comment.id, comment.body) for comment in conversation.comments]


def _on_github(here):
    return here.github.thread(KEY)


def _asked(threads, verb, *args, **kwargs):
    with threads.editing(KEY) as conversation:
        asked = getattr(conversation, verb)(*args, **kwargs)
    if not isinstance(asked, Denied):
        drain(threads)
    return asked


def _working(here, threads):
    start_run(here, threads, finishes=False)


def _proposed(here, threads, **ready):
    propose(here, threads, KEY, **ready)


def _declined(here, threads):
    _working(here, threads)
    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.NEEDS_HUMAN, "a question, not a change")


def _failed(here, threads):
    for _ in range(_held(threads).run_holder.attempts_allowed):
        start_run(here, threads)
        with threads.editing(KEY) as editable:
            editable.fail("the tests would not run")


def _in_session(here, threads):
    _proposed(here, threads)
    here.pr_processes.open(THE_PR, Path(WORKTREE))
    _asked(threads, "start_session")


def _landed(here, threads):
    _proposed(here, threads)
    _asked(threads, "approve", reply="Renamed it.")


def _waiting(here, threads):
    _proposed(here, threads)
    _asked(threads, "reply", "which one?")


def _queued(here, threads):
    return None


def _requeued(here, threads):
    start_run(here, threads)
    with threads.editing(KEY) as editable:
        editable.fail("the tests would not run")


def _author(settings, reached=_queued, **built):
    here = _here(settings, **built)
    threads = _open(here)
    reached(here, threads)
    return here, threads


def _push_failed(settings):
    here, threads = _author(settings, _proposed, remote=refusing_remote)
    _asked(threads, "approve", reply="Renamed it.")
    return here, threads


def _reply_failed(settings):
    here, threads = _author(settings, _proposed, github=FirstReplyRefused())
    _asked(threads, "approve", reply="Renamed it.")
    return here, threads


def _reviewer(here, *comments):
    return _open(here, *(comments or (_comment(),)), is_author=False)


def test_a_new_conversation_is_open_and_wants_a_first_run(settings):
    here = _here(settings)

    threads = _open(here)
    conversation = _held(threads)
    drain(threads)

    assert conversation.key == KEY
    assert conversation.standing is ConversationState.QUEUED
    assert conversation.fix.run.kind is OperationKind.FIRST
    assert conversation.fix.attempts == 0
    assert len(here.agent_runs.started) == 1


def test_a_new_conversation_keeps_what_github_said_about_the_root(settings):
    conversation = _held(_open(_here(settings), anchor=ThreadAnchor(
        is_outdated=True, original_line=9, original_commit="abc1234")))

    assert conversation.comment_id == 5001
    assert conversation.comment_type == "review"
    assert conversation.author == "reviewer"
    assert conversation.path == "src/app.py"
    assert conversation.line == 12
    assert conversation.is_outdated is True
    assert conversation.original_line == 9
    assert conversation.original_commit == "abc1234"
    assert conversation.comment_created_at == COMMENTED_AT
    assert conversation.created_at == "2026-09-21T11:00:00.000000Z"


def test_a_new_conversation_takes_the_reviewer_and_the_review_off_the_root(settings):
    conversation = _held(_open(
        _here(settings),
        _comment(author="anna", author_name="Anna Example",
                 review_state=GitHubReviewState.CHANGES_REQUESTED),
        _comment(id=5002, author="bob", author_name="Bob Bobson",
                 review_state=GitHubReviewState.COMMENTED),
    ))

    assert conversation.reviewer_name == "Anna Example"
    assert conversation.review_state == ReviewState.CHANGES_REQUESTED


def test_a_new_conversation_with_nothing_said_on_it_names_no_reviewer(settings):
    conversation = _held(_open(_here(settings)))

    assert conversation.reviewer_name == ""
    assert conversation.review_state is None


def test_a_new_conversation_keeps_the_line_its_range_starts_on(settings):
    conversation = _held(_open(_here(settings), anchor=ThreadAnchor(
        start_line=8, original_line=9, original_start_line=5)))

    assert (conversation.start_line, conversation.line) == (8, 12)
    assert (conversation.original_start_line,
            conversation.original_line) == (5, 9)


def test_a_new_conversation_shows_the_first_line_and_asks_for_a_gist_of_the_root(settings):
    here = _here(settings)

    conversation = _held(_open(here))

    assert conversation.gist == "rename this to _reference"
    [asked] = here.agent_runs.asked
    assert isinstance(asked, CommentAsked)
    assert asked.body == BODY


def test_a_reviewer_conversation_whose_newest_comment_is_not_the_openers_is_open(settings):
    conversation = _held(_reviewer(_here(settings), _comment(author="reviewer"),
                                   _comment(id=5002, author="jeffrey", body="fixed in a9296db")))

    assert conversation.standing is ConversationState.READY


def test_a_reviewer_conversation_whose_newest_comment_is_the_openers_is_my_move_until_a_verdict(
        settings):
    conversation = _held(_reviewer(_here(settings), _comment(author="reviewer"),
                                   _comment(id=5002, author="reviewer", body="and the caller too")))

    assert (conversation.standing, conversation.unread) == (ConversationState.READY, True)


def test_a_reviewer_conversation_has_no_fix_to_run(settings):
    here = _here(settings)

    threads = _reviewer(here, _comment(author="reviewer"),
                        _comment(id=5002, author="jeffrey", body="have a look"))
    drain(threads)

    conversation = _held(threads)
    assert conversation.fix.base_sha is None
    assert not here.working_copies.holds_thread(THE_PR, KEY)
    assert here.agent_runs.started == []
    assert [type(asked) for asked in here.agent_runs.asked] == [CommentAsked, VerdictAsked]


def test_a_refresh_brings_the_record_back_in_step_and_decides_nothing(settings):
    here = _here(settings)
    threads = _open(here, ROOT, _comment(id=5002, body="agree"))
    before = _held(threads)

    refreshed = _polled(here, threads, ROOT, _comment(id=5002, body="agreed"),
                        anchor=ThreadAnchor(is_outdated=True, original_line=9,
                                            original_commit="abc1234"))

    assert _said(refreshed) == [(5001, BODY), (5002, "agreed"), (9999, BOT_NOTE.body)]
    assert refreshed.is_outdated is True
    assert refreshed.original_line == 9
    assert refreshed.original_commit == "abc1234"
    assert refreshed.fix == before.fix
    assert len(here.agent_runs.asked) == 1


def test_a_refresh_spends_no_attempt_moves_no_state_and_leaves_the_gist(settings):
    here, threads = _author(settings, _proposed)
    before = _held(threads)

    refreshed = _polled(here, threads)

    assert refreshed.fix.is_proposed
    assert refreshed.fix.attempts == before.fix.attempts
    assert refreshed.gist == before.gist


def test_the_first_run_a_reply_asks_for_starts_with_a_fresh_budget(settings):
    here, threads = _author(settings, _requeued)
    _proposed(here, threads)
    before = _held(threads)
    assert before.fix.attempts == 2

    fix = _reply_arrives(here, threads).fix

    assert _held(threads).standing is ConversationState.QUEUED
    assert fix.attempts == 0
    assert fix.started_at is None
    assert fix.run.kind is OperationKind.FIRST, (
        "the run the board asks for is a first, whatever ran before it")
    assert fix.base_sha == before.fix.base_sha


def test_a_reply_on_a_landed_fix_marks_it_reopened_and_asks_for_a_new_run(settings):
    here, threads = _author(settings, _landed)

    reopened = _reply_arrives(here, threads)

    assert reopened.reopened is True
    fix = reopened.fix
    assert reopened.standing is ConversationState.QUEUED
    assert fix.run.kind is OperationKind.FIRST, "a reply is new work, pushed or not"
    assert (fix.landed_base, fix.landed_sha) == (None, None)
    assert not (fix.picked or fix.pushed or fix.answered)


def _replied_while_the_push_failed(settings):
    here, threads = _author(settings, lambda here, threads: _proposed(here, threads, tests="passed"),
                            remote=first_push_refused)
    _asked(threads, "approve", reply="Renamed it.")
    assert _held(threads).fix.push_error
    _reply_arrives(here, threads)
    assert _held(threads).replied_during_run
    return here, threads


def test_a_first_run_after_a_failed_landing_has_landed_nothing(settings):
    here, threads = _replied_while_the_push_failed(settings)
    before = _held(threads).fix

    _asked(threads, "approve", reply="Renamed it.")

    fix = _held(threads).fix
    assert not (fix.picked or fix.pushed or fix.answered), (
        "the next fix has not been picked, pushed or answered")
    assert fix.landed_base is None
    assert fix.landed_sha is None
    assert fix.push_error is None
    assert fix.reply_error is None
    assert fix.decision_error is None
    assert fix.reply_note is None
    assert (fix.thread_sha, fix.tests) == (before.thread_sha, before.tests), (
        "what the agent last built and reported is still on the card")


def test_a_push_that_lands_after_a_reply_asks_for_a_first_run(settings):
    here, threads = _replied_while_the_push_failed(settings)

    _asked(threads, "approve", reply="Renamed it.")

    stored = _held(threads)
    assert stored.fix.run.kind is OperationKind.FIRST
    assert stored.standing in (ConversationState.QUEUED, ConversationState.WORKING)
    assert stored.fix.landed_sha is None
    assert _checked_out(here, stored.fix)
    assert stored.replied_during_run is False


@pytest.mark.parametrize("reached,standing", [
    (_requeued, ConversationState.QUEUED),
    (_working, ConversationState.WORKING),
], ids=["queued", "running"])
def test_a_reply_leaves_a_fix_that_is_already_being_worked_on_alone(settings, reached,
                                                                     standing):
    here, threads = _author(settings, reached)
    before = _held(threads).fix

    after = _reply_arrives(here, threads)

    assert after.standing is standing
    assert after.fix.attempts == before.attempts
    assert after.fix.started_at == before.started_at


def test_a_reply_opens_a_conversation_github_had_lost(settings):
    here, threads = _author(settings, _proposed)
    _adds(here, REPLY)
    here.github.delete_comment(THE_PR, CommentKind.REVIEW, 5001)
    lost(threads, KEY)
    assert _held(threads).is_removed

    assert not _reply_arrives(here, threads, _comment(id=5003, body="still there?")).is_removed


def _resolved(here, threads):
    _proposed(here, threads)
    _asked(threads, "resolve")


def _rejected(here, threads):
    _proposed(here, threads)
    _asked(threads, "reject")


def _deferred(here, threads):
    _proposed(here, threads)
    _asked(threads, "place", ConversationState.DEFERRED, until="ci", note="after the CI fix")


@pytest.mark.parametrize("reached", [_resolved, _rejected, _deferred],
                         ids=["resolved", "rejected", "deferred"])
def test_a_reply_opens_a_closed_or_deferred_conversation_for_a_new_run(settings, reached):
    here, threads = _author(settings, reached)

    reopened = _reply_arrives(here, threads)

    assert reopened.standing is ConversationState.QUEUED, (
        "a reply is new information: what was decided before it is history")
    assert reopened.fix.run.kind is OperationKind.FIRST


def test_a_reply_wakes_a_deferred_conversation_and_forgets_its_wake(settings):
    here, threads = _author(settings, _deferred)

    reopened = _reply_arrives(here, threads)

    assert (reopened.wake_on, reopened.defer_note) == (None, "")


def _closed_with(verb, **words):
    def reached(here, threads):
        _proposed(here, threads)
        _asked(threads, verb, **words)
    return reached


@pytest.mark.parametrize(("reached", "before"), [
    (_closed_with("reject", reply="not this one"), "rejected: not this one"),
    (_closed_with("reject"), "rejected"),
    (_closed_with("resolve", reply="done in abc1234"), "resolved: done in abc1234"),
    (_deferred, "deferred: after the CI fix"),
    (_landed, "pushed"),
    (_failed, "failed: the tests would not run"),
    (_declined, "declined: a question, not a change"),
    (_proposed, "proposed"),
], ids=["rejected with a reply", "rejected", "resolved with a reply", "deferred",
        "landed", "failed", "declined", "proposed"])
def test_a_reply_remembers_how_the_thread_had_ended_up(settings, reached, before):
    here, threads = _author(settings, reached)

    assert _reply_arrives(here, threads).before_reply == before


@pytest.mark.parametrize("reached,standing", [
    (lambda settings: _author(settings, _working), ConversationState.WORKING),
    (lambda settings: _author(settings, _in_session), ConversationState.IN_SESSION),
    (_push_failed, ConversationState.READY),
], ids=["running", "in session", "landing"])
def test_a_reply_during_work_under_way_asks_for_a_run_after_it(settings, reached, standing):
    here, threads = reached(settings)

    reopened = _reply_arrives(here, threads)

    assert reopened.replied_during_run is True
    assert reopened.standing is standing


def test_a_reply_to_a_queued_run_needs_no_second_one(settings):
    here, threads = _author(settings)

    assert _reply_arrives(here, threads).replied_during_run is False, (
        "the queued run has not read the thread yet")


def _on_the_last_attempt(here, threads):
    for _ in range(_held(threads).run_holder.attempts_allowed - 1):
        start_run(here, threads)
        with threads.editing(KEY) as editable:
            editable.fail("the tests would not run")
    _working(here, threads)
    _reply_arrives(here, threads)


def _reports_ready(here, threads):
    with threads.editing(KEY) as editable:
        return editable.ready(commit_fix(here, KEY))


def _reports_declined(here, threads):
    with threads.editing(KEY) as editable:
        return editable.not_a_fix(Classification.NEEDS_HUMAN, "a question")


def _reports_failed(here, threads):
    with threads.editing(KEY) as editable:
        return editable.fail("the tests would not run")


@pytest.mark.parametrize("report", [_reports_ready, _reports_declined, _reports_failed],
                         ids=["ready", "declined", "fail"])
def test_a_run_that_ends_after_a_reply_is_reworked_on_top(settings, report):
    here, threads = _author(settings, _on_the_last_attempt)
    before = _held(threads)
    assert before.replied_during_run

    outcome = report(here, threads)

    assert not isinstance(outcome, Denied)
    stored = _held(threads)
    fix = stored.fix
    assert stored.standing is ConversationState.REWORK
    assert fix.run.brief.include == ("anna",)
    assert fix.base_sha == before.fix.base_sha
    assert _checked_out(here, fix)
    assert stored.replied_during_run is False


def test_stopping_a_run_a_reply_arrived_during_starts_no_other(settings):
    here, threads = _author(settings, _working)
    _reply_arrives(here, threads)

    _asked(threads, "stop")

    stored = _held(threads)
    assert stored.fix.has_failed
    assert stored.replied_during_run is False


def test_a_reopen_takes_the_roots_current_wording_and_re_reads_the_thread(settings):
    here, threads = _author(settings, _proposed)
    _shows(here, _comment(body="rename this to _target instead"),
           _comment(id=5002, body="agreed"))

    hear(threads)

    assert _held(threads).body == "rename this to _target instead"
    asked = here.agent_runs.asked[-1]
    assert isinstance(asked, ThreadAsked)
    assert ("reviewer", "rename this to _target instead") in asked.comments
    assert ("reviewer", "agreed") in asked.comments


def _a_poll(here, threads, root, anchor=None):
    return _polled(here, threads, root, anchor=anchor or ThreadAnchor())


def _a_reply(here, threads, root, anchor=None):
    _shows(here, root, REPLY, anchor=anchor or ThreadAnchor())
    hear(threads)
    return _held(threads)


ARRIVALS = {"a poll": _a_poll, "a reply": _a_reply}


@pytest.mark.parametrize("arrival", sorted(ARRIVALS))
def test_a_display_name_github_changed_follows_on_the_next_poll(settings, arrival):
    here = _here(settings)
    threads = _open(here, _comment(author_name="Anna Kellar",
                                   review_state=GitHubReviewState.COMMENTED))
    _proposed(here, threads)

    followed = ARRIVALS[arrival](here, threads, _comment(
        author_name="Anna Example", review_state=GitHubReviewState.CHANGES_REQUESTED))

    assert followed.reviewer_name == "Anna Example"
    assert followed.review_state == ReviewState.CHANGES_REQUESTED


@pytest.mark.parametrize("arrival", sorted(ARRIVALS))
def test_a_range_github_moved_comes_back_in_step(settings, arrival):
    here = _here(settings)
    threads = _open(here, anchor=ThreadAnchor(start_line=8))
    _proposed(here, threads)

    moved = ARRIVALS[arrival](here, threads, ROOT, anchor=ThreadAnchor(
        is_outdated=True, original_line=40, original_start_line=36))

    assert moved.original_start_line == 36
    assert moved.start_line is None


@pytest.mark.parametrize("arrival", sorted(ARRIVALS))
def test_the_side_a_range_starts_on_comes_from_github(settings, arrival):
    here = _here(settings)
    threads = _open(here, anchor=ThreadAnchor(start_line=8, start_side=Side.AFTER,
                                              side=Side.AFTER))
    heard = threads.get(KEY).start_side
    _proposed(here, threads)

    moved = ARRIVALS[arrival](here, threads, ROOT, anchor=ThreadAnchor(
        start_line=8, start_side=Side.BEFORE, side=Side.AFTER))

    assert (heard, moved.start_side) == (Side.AFTER, Side.BEFORE)


@pytest.mark.parametrize("arrival", sorted(ARRIVALS))
def test_a_root_that_names_no_reviewer_leaves_the_one_known_alone(settings, arrival):
    here = _here(settings)
    threads = _open(here, _comment(author_name="Anna Example",
                                   review_state=GitHubReviewState.CHANGES_REQUESTED),
                    anchor=ANCHORED)
    _proposed(here, threads)

    kept = ARRIVALS[arrival](here, threads, _comment(), anchor=ANCHORED)

    assert kept.reviewer_name == "Anna Example"
    assert kept.review_state == ReviewState.CHANGES_REQUESTED


@pytest.mark.parametrize("arrival", sorted(ARRIVALS))
def test_a_caller_that_says_the_thread_has_no_anchor_clears_it(settings, arrival):
    here = _here(settings)
    threads = _open(here, anchor=ANCHORED)
    _proposed(here, threads)

    cleared = ARRIVALS[arrival](here, threads, _comment(), anchor=ThreadAnchor())

    assert (cleared.is_outdated, cleared.start_line) == (False, None)
    assert (cleared.original_line, cleared.original_start_line) == (None, None)
    assert cleared.original_commit is None


SPOKEN = {
    "a reply of your own": _waiting,
    "the reply that closed it": _closed_with("resolve", reply="done in abc1234"),
    "the reply that landed it": _landed,
}


@pytest.mark.parametrize("spoken", sorted(SPOKEN))
def test_a_reply_after_you_had_spoken_marks_the_conversation_reopened(settings, spoken):
    here, threads = _author(settings, SPOKEN[spoken])

    assert _reply_arrives(here, threads).reopened is True


@pytest.mark.parametrize("reached", [_push_failed, lambda settings: _author(settings, _landed)],
                         ids=["landing", "landed"])
def test_a_reply_on_a_fix_you_had_accepted_marks_it_reopened(settings, reached):
    here, threads = reached(settings)

    assert _reply_arrives(here, threads).reopened is True


def test_a_reply_on_a_conversation_you_turned_down_marks_it_reopened(settings):
    here, threads = _author(settings, _rejected)

    assert _reply_arrives(here, threads).reopened is True


@pytest.mark.parametrize("reached", [_queued, _working, _proposed, _declined, _failed,
                                     _in_session],
                         ids=["queued", "running", "proposed", "declined", "failed",
                              "in session"])
def test_a_reply_on_a_conversation_you_never_answered_leaves_it_unmarked(settings, reached):
    here, threads = _author(settings, reached)

    assert _reply_arrives(here, threads).reopened is False


def test_a_reply_on_a_reviewer_conversation_lands_it_answered_and_regenerates_the_gist(settings):
    here = _here(settings)
    threads = _reviewer(here)

    answered = _reply_arrives(here, threads,
                              _comment(id=5002, author="jeffrey", body="fixed in a9296db"))

    assert answered.standing is ConversationState.READY
    assert answered.fix.base_sha is None
    gists = [asked for asked in here.agent_runs.asked if not isinstance(asked, VerdictAsked)]
    assert len(gists) == 2
    assert ("jeffrey", "fixed in a9296db") in gists[-1].comments


def test_the_counts_name_your_threads_the_author_answered(settings):
    here = _here(settings, agent_runs=HeldVerdicts(FakePrProcesses()))
    threads = _reviewer(here, _comment(author=here.github.account))
    here.agent_runs.give("their-move")
    assert threads.counts().answered == ()

    _reply_arrives(here, threads, _comment(id=5002, author="jeffrey", body="fixed in a9296db"))

    assert threads.counts().answered == (KEY,)


def test_a_thread_another_reviewer_opened_is_not_counted_when_the_author_answers_it(settings):
    here = _here(settings)
    threads = _reviewer(here, _comment(author="frank"))

    _reply_arrives(here, threads, _comment(id=5002, author="heidi", body="fixed in a9296db"))

    assert threads.counts().answered == ()


def test_a_thread_of_yours_resolved_on_github_counts_as_answered(settings):
    here = _here(settings)
    mine = _comment(author=here.github.account)
    threads = _reviewer(here, mine)

    _polled(here, threads, mine, is_resolved=True)

    assert threads.counts().answered == (KEY,)


def test_a_proposed_fix_is_not_counted_as_answered(settings):
    here = _here(settings)
    threads = _open(here)
    propose(here, threads, KEY)

    counts = threads.counts()
    assert (counts.proposed, counts.answered) == (1, ())


@pytest.mark.parametrize("bot", ["claude", "Codex", "copilot[bot]"])
def test_a_thread_a_bot_opened_is_listed_as_a_bot_thread(settings, bot):
    here = _here(settings)
    threads = _open(here, _comment(author=bot))

    assert [row.author_kind for row in threads.counts().rows] == [AuthorKind.BOT]


def test_a_thread_you_opened_on_your_own_pr_is_listed_as_yours(settings):
    here = _here(settings)
    threads = _open(here, _comment(author=here.github.account))

    assert [row.author_kind for row in threads.counts().rows] == [AuthorKind.MINE]


def test_a_reply_by_the_opener_is_my_move_until_a_verdict_places_it(settings):
    here = _here(settings)
    threads = _reviewer(here, _comment(author="reviewer"),
                        _comment(id=5002, author="jeffrey", body="fixed in a9296db"))

    reopened = _reply_arrives(here, threads,
                              _comment(id=5003, author="reviewer", body="one more thing"))

    assert (reopened.standing, reopened.unread) == (ConversationState.READY, True)
    assert isinstance(here.agent_runs.asked[-1], VerdictAsked)


@pytest.mark.parametrize("opener,marked", [("octocat", True), ("reviewer", False)],
                         ids=["the viewer commented", "parked waiting by a verdict alone"])
def test_the_reopened_mark_is_set_only_when_the_reviewer_had_spoken(settings, opener, marked):
    here = _here(settings, agent_runs=HeldVerdicts(FakePrProcesses()))
    threads = _reviewer(here, _comment(author=opener))
    here.agent_runs.give("their-move")

    reopened = _reply_arrives(here, threads,
                              _comment(id=5002, author="jeffrey", body="have a look"))

    assert reopened.reopened is marked


def test_github_resolving_a_thread_moves_it_to_done(settings):
    here, threads = _author(settings)

    refreshed = _polled(here, threads, is_resolved=True)

    assert refreshed.standing is ConversationState.DONE
    assert refreshed.github_resolved is True
    assert refreshed.github_resolved_at == CUTOFF


UNRESOLVING = [
    ("a reviewer thread the author answered last", False,
     (_comment(author="reviewer"), _comment(id=5002, author="jeffrey",
                                            body="have a look")),
     ConversationState.READY),
    ("a reviewer thread its opener spoke last on", False,
     (_comment(author="reviewer"), _comment(id=5002, author="jeffrey"),
      _comment(id=5003, author="reviewer", body="still not it")),
     ConversationState.READY),
    ("an author thread", None, (_comment(author="reviewer"),), ConversationState.QUEUED),
]


@pytest.mark.parametrize("is_author,comments,standing",
                         [row[1:] for row in UNRESOLVING],
                         ids=[row[0] for row in UNRESOLVING])
def test_github_unresolving_a_thread_brings_it_back(settings, is_author, comments,
                                                    standing):
    clock = Moment(EARLIER_NOW)
    here = _here(settings, clock=clock)
    threads = _open(here, *comments, is_author=is_author)
    _polled(here, threads, *comments, is_resolved=True)
    assert _held(threads).standing is ConversationState.DONE
    clock.iso = NOW

    refreshed = _polled(here, threads, *comments, is_resolved=False)

    assert refreshed.standing is standing
    assert refreshed.github_resolved is False
    assert refreshed.github_resolved_at == CUTOFF


def test_a_stale_resolved_flag_cannot_undo_the_boards_own_resolve(settings):
    clock = Moment(EARLIER_NOW)
    here = _here(settings, clock=clock)
    threads = _reviewer(here, *ANSWERED_THREAD)
    _shows(here, *ANSWERED_THREAD, BOT_NOTE)
    in_flight = threads.poll(PullRequestState())
    in_flight.commit()
    clock.iso = NOW
    _asked(threads, "resolve", resolve=True)

    threads.absorb(in_flight.activity)

    refreshed = _held(threads)
    assert refreshed.standing is ConversationState.DONE, (
        "the poll was in flight while the board resolved the thread")
    assert refreshed.github_resolved is True
    assert refreshed.github_resolved_at == NOW


def test_replaying_an_older_poll_keeps_the_replies_posted_since(settings):
    clock = Moment(EARLIER_NOW)
    here = _here(settings, clock=clock)
    threads = here.threads()
    hear(threads)
    _shows(here, ROOT)
    replayed = threads.poll(PullRequestState())
    replayed.commit()
    threads.absorb(replayed.activity)
    clock.iso = NOW
    _reply_arrives(here, threads, _comment(id=5002, author="jeffrey", body="it limits the lookup",
                                           created_at="2026-09-21T10:00:00Z"))

    threads.absorb(replayed.activity)

    assert _said(_held(threads)) == [(5001, BODY), (5002, "it limits the lookup")]


def test_a_refresh_never_marks_a_conversation_reopened(settings):
    here, threads = _author(settings, _landed)

    assert _polled(here, threads).reopened is False


def _reopened_by_a_reply(here, threads):
    _waiting(here, threads)
    _reply_arrives(here, threads)


def test_a_refresh_never_clears_the_mark_a_reply_left(settings):
    here, threads = _author(settings, _reopened_by_a_reply)
    assert _held(threads).standing is ConversationState.QUEUED

    assert _polled(here, threads, ROOT, REPLY).reopened is True


def test_resolving_a_reviewer_thread_with_a_reply_posts_then_resolves(settings):
    here = _here(settings)
    threads = _reviewer(here, *ANSWERED_THREAD)

    _asked(threads, "resolve", reply="that's the one", resolve=True)

    on_github = _on_github(here)
    assert on_github.comments[-1].body == "that's the one"
    assert on_github.is_resolved is True
    settled = _held(threads)
    assert settled.standing is ConversationState.DONE
    assert settled.github_resolved is True
    assert settled.github_resolved_at == NOW
    assert here.github.reactions == {}, "a reply is the thanks"


def test_resolving_a_reviewer_thread_without_a_reply_resolves_then_thumbs_up_the_newest_other_comment(settings):
    here = _here(settings)
    threads = _reviewer(here, *ANSWERED_THREAD)

    _asked(threads, "resolve", resolve=True)

    assert _on_github(here).is_resolved is True
    assert here.github.reactions == {5002: ["+1"]}
    assert _held(threads).standing is ConversationState.DONE


def test_resolving_a_reviewer_thread_without_the_thumbs_up_resolves_and_reacts_to_nothing(settings):
    here = _here(settings)
    threads = _reviewer(here, *ANSWERED_THREAD)

    _asked(threads, "resolve", thumbs_up=False, resolve=True)

    assert _on_github(here).is_resolved is True
    assert here.github.reactions == {}
    assert _held(threads).standing is ConversationState.DONE


def test_a_thread_with_only_the_openers_comments_gets_no_reaction(settings):
    here = _here(settings)
    threads = _reviewer(here, _comment(author="reviewer"),
                        _comment(id=5002, author="reviewer", body="and the caller too"))

    _asked(threads, "resolve")

    assert _held(threads).standing is ConversationState.DONE
    assert here.github.reactions == {}


def test_a_reviewers_resolve_not_asked_onto_github_posts_the_reply_and_settles_here_only(settings):
    here = _here(settings)
    threads = _reviewer(here, *ANSWERED_THREAD)

    _asked(threads, "resolve", reply="sure, go ahead")

    on_github = _on_github(here)
    assert on_github.comments[-1].body == "sure, go ahead"
    assert not on_github.is_resolved
    assert _held(threads).standing is ConversationState.DONE


def test_reopening_a_reviewer_thread_the_board_resolved_on_github_unresolves_it_there(settings):
    here = _here(settings)
    threads = _reviewer(here, *ANSWERED_THREAD)
    _asked(threads, "resolve", reply="that's the one", resolve=True)

    _asked(threads, "unpark")

    assert not _on_github(here).is_resolved
    assert _held(threads).standing is ConversationState.READY


def test_reopening_a_reviewer_thread_resolved_here_only_leaves_github_alone(settings):
    here = _here(settings)
    threads = _reviewer(here, *ANSWERED_THREAD)
    _asked(threads, "resolve", reply="sure, go ahead")

    _asked(threads, "unpark")

    assert not _on_github(here).is_resolved
    assert _held(threads).standing is ConversationState.READY


def test_a_failed_resolve_hands_the_card_back_with_the_error(settings):
    here = _here(settings, github=ResolveRefused())
    threads = _reviewer(here, *ANSWERED_THREAD)

    outcome = _asked(threads, "resolve", reply="that's the one", resolve=True)

    assert not isinstance(outcome, Denied)
    assert _on_github(here).comments[-1].body == "that's the one"
    stored = _held(threads)
    assert stored.standing is not ConversationState.DONE, "not closed until GitHub says so"
    assert stored.fix.decision_error == "resolve failed: gh: 403"


def test_a_failed_reaction_is_a_note_and_the_thread_still_settles(settings):
    here = _here(settings)
    threads = _reviewer(here, *ANSWERED_THREAD)
    here.github.delete_comment(THE_PR, CommentKind.REVIEW, 5002)

    outcome = _asked(threads, "resolve", resolve=True)

    assert not isinstance(outcome, Denied)
    stored = _held(threads)
    assert stored.standing is ConversationState.DONE
    assert stored.fix.reply_note.startswith("thumbs-up failed: ")
    assert here.github.reactions == {}


def test_resolving_an_author_thread_silently_settles_it_here_only(settings):
    here, threads = _author(settings, _proposed)
    before = _held(threads)

    _asked(threads, "resolve")

    assert _held(threads).standing is ConversationState.DONE
    assert not _checked_out(here, before.fix)
    assert not _on_github(here).is_resolved
    assert len(_on_github(here).comments) == 1


def test_resolving_an_author_thread_with_a_reply_posts_it_and_settles(settings):
    here, threads = _author(settings, _proposed)
    before = _held(threads)

    _asked(threads, "resolve", reply="done, thanks")

    assert _on_github(here).comments[-1].body == "done, thanks"
    assert not _on_github(here).is_resolved
    assert _held(threads).standing is ConversationState.DONE
    assert not _checked_out(here, before.fix)


def _resolved_on_github(here, *comments, is_author=False):
    threads = _open(here, *comments, is_author=is_author)
    _polled(here, threads, *comments, is_resolved=True)
    assert _held(threads).github_resolved
    return threads


def test_reopening_a_resolved_reviewer_thread_unresolves_it_then_takes_its_state_from_the_comments(settings):
    here = _here(settings)
    threads = _resolved_on_github(here, *ANSWERED_THREAD[:2])

    _asked(threads, "unpark")

    assert not _on_github(here).is_resolved
    back = _held(threads)
    assert back.standing is ConversationState.READY
    assert back.github_resolved is False
    assert back.github_resolved_at == NOW


def test_a_failed_reopen_hands_the_card_back_with_the_error(settings):
    here = _here(settings, github=ResolveRefused())
    threads = _resolved_on_github(here, *ANSWERED_THREAD)

    outcome = _asked(threads, "unpark")

    assert not isinstance(outcome, Denied)
    stored = _held(threads)
    assert stored.standing is ConversationState.DONE
    assert stored.fix.decision_error == "reopen failed: gh: 403"


def test_a_reviewer_thread_a_conversation_comment_settles_without_a_github_resolve(settings):
    here = _here(settings)
    threads = _open(here, *ANSWERED_THREAD, is_author=False, kind=CommentKind.ISSUE)

    _asked(threads, "resolve")

    stored = _held(threads)
    assert stored.standing is ConversationState.DONE
    assert not stored.github_resolved


def _answering(settings):
    agent_runs = LaterSummaries(FakePrProcesses())
    return _here(settings, agent_runs=agent_runs), agent_runs


def test_a_written_gist_replaces_the_first_line(settings):
    here, agent_runs = _answering(settings)
    agent_runs.answer("rename the reference")
    threads = _open(here)

    agent_runs.settle()

    assert _held(threads).gist == "rename the reference"


def test_a_gist_written_against_wording_that_has_moved_on_is_dropped(settings):
    here, agent_runs = _answering(settings)
    agent_runs.answer("what it says now, gisted", "what it used to say, gisted")
    threads = _open(here)
    _shows(here, _comment(body="what the comment says now"))
    hear(threads)

    agent_runs.settle_newest_first()

    stored = _held(threads)
    assert stored.body == "what the comment says now"
    assert stored.gist == "what it says now, gisted"


@pytest.mark.parametrize("reached", [
    lambda settings: _author(settings),
    lambda settings: _author(settings, _proposed),
    lambda settings: _author(settings, _declined),
    lambda settings: _author(settings, _failed),
    lambda settings: _author(settings, _in_session),
    _push_failed,
], ids=["queued", "proposed", "declined", "failed", "in session", "landing picked"])
def test_a_root_github_has_lost_removes_an_unfinished_conversation(settings, reached):
    here, threads = reached(settings)
    before = _held(threads)
    here.github.delete_comment(THE_PR, CommentKind.REVIEW, 5001)

    lost(threads, KEY)

    gone = _held(threads)
    assert gone.is_removed
    assert gone.comment_deleted is True
    assert gone.deleted_by_board is False, "GitHub lost it; the board did not"
    assert gone.fix == before.fix, "the fix is whatever it was"


@pytest.mark.parametrize("reached", [
    lambda settings: _author(settings, _working),
    lambda settings: _author(settings, _landed),
    _reply_failed,
], ids=["running", "landed", "landing pushed"])
def test_a_root_github_has_lost_only_marks_a_conversation_it_cannot_remove(settings, reached):
    here, threads = reached(settings)
    here.github.delete_comment(THE_PR, CommentKind.REVIEW, 5001)

    lost(threads, KEY)

    gone = _held(threads)
    assert not gone.is_removed
    assert gone.comment_deleted is True


def test_a_root_github_has_lost_leaves_a_closed_conversation_closed(settings):
    here, threads = _author(settings, _resolved)
    here.github.delete_comment(THE_PR, CommentKind.REVIEW, 5001)

    lost(threads, KEY)

    gone = _held(threads)
    assert gone.standing is ConversationState.DONE
    assert not gone.is_removed
    assert gone.comment_deleted is True


def test_reject_drops_the_workspace_and_posts_nothing(settings):
    here, threads = _author(settings, _proposed)
    before = _held(threads)

    outcome = _asked(threads, "reject")

    assert not isinstance(outcome, Denied)
    stored = _held(threads)
    assert stored.standing is ConversationState.DONE
    assert stored.fix.thread_sha == before.fix.thread_sha
    assert not _checked_out(here, before.fix)
    assert len(_on_github(here).comments) == 1


@pytest.mark.parametrize("reached", [_failed, _declined], ids=["failed", "declined"])
def test_reject_turns_down_a_thread_the_agent_left_no_fix_on(settings, reached):
    _, threads = _author(settings, reached)

    outcome = _asked(threads, "reject")

    assert not isinstance(outcome, Denied)
    assert _held(threads).standing is ConversationState.DONE


def test_stop_halts_a_running_agent_and_hands_the_thread_back(settings):
    _, threads = _author(settings, _working)

    outcome = _asked(threads, "stop")

    assert not isinstance(outcome, Denied)
    assert _held(threads).fix.has_failed
    assert threads.counts().live == 0


def test_reject_refuses_a_run_still_in_flight(settings):
    _, threads = _author(settings, _working)

    outcome = _asked(threads, "reject")

    assert isinstance(outcome, Denied)
    assert outcome.code == ErrorCode.WORK_IN_FLIGHT
    assert _held(threads).fix.decision_error is None


def _proposed_then_lost(here, threads):
    _proposed(here, threads)
    here.github.delete_comment(THE_PR, CommentKind.REVIEW, 5001)
    lost(threads, KEY)
    assert _held(threads).comment_deleted


def test_rejecting_with_a_reply_refuses_when_the_comment_is_already_gone(settings):
    _, threads = _author(settings, _proposed_then_lost)

    outcome = _asked(threads, "reject", reply="not taking this")

    assert isinstance(outcome, Denied)
    assert outcome.code == ErrorCode.COMMENT_GONE


def test_rejecting_without_a_reply_still_settles_when_the_comment_is_gone(settings):
    _, threads = _author(settings, _proposed_then_lost)

    outcome = _asked(threads, "reject")

    assert not isinstance(outcome, Denied)
    assert _held(threads).standing is ConversationState.DONE


def test_reject_refuses_a_thread_no_agent_has_answered(settings):
    threads = _reviewer(_here(settings), _comment(author="reviewer"),
                        _comment(id=5002, author="jeffrey", body="have a look"))

    outcome = _asked(threads, "reject", reply="no")

    assert isinstance(outcome, Denied)
    assert outcome.code == ErrorCode.NO_PROPOSAL


def test_rejecting_by_deleting_the_comment_settles_into_rejected(settings):
    here = _here(settings)
    threads = _open(here, replace(ROOT, author=here.github.account))
    _proposed(here, threads)

    outcome = _asked(threads, "reject", delete_comment=True)

    assert not isinstance(outcome, Denied)
    assert _on_github(here) is None
    stored = _held(threads)
    assert stored.standing is ConversationState.DONE
    assert stored.comment_deleted is True
    assert stored.deleted_by_board is True
    assert stored.closing_into is None


def test_defer_parks_the_conversation_and_keeps_its_workspace(settings):
    here, threads = _author(settings, _proposed)
    before = _held(threads)

    outcome = _asked(threads, "place", ConversationState.DEFERRED, until="ci", note="after the rebase")

    assert not isinstance(outcome, Denied)
    stored = _held(threads)
    assert stored.standing is ConversationState.DEFERRED
    assert stored.wake_on == "ci"
    assert stored.defer_note == "after the rebase"
    assert stored.fix.base_sha == before.fix.base_sha
    assert _checked_out(here, stored.fix)


def test_defer_stops_a_running_agent_first(settings):
    _, threads = _author(settings, _working)

    outcome = _asked(threads, "place", ConversationState.DEFERRED)

    assert not isinstance(outcome, Denied)
    assert _held(threads).standing is ConversationState.DEFERRED
    assert threads.counts().live == 0


def test_defer_parks_a_conversation_that_was_waiting_on_the_other_party(settings):
    _, threads = _author(settings, _waiting)

    outcome = _asked(threads, "place", ConversationState.DEFERRED, until="ci")

    assert not isinstance(outcome, Denied)
    stored = _held(threads)
    assert stored.standing is ConversationState.DEFERRED
    assert stored.wake_on == "ci"


def _reworking_queued(here, threads):
    _proposed(here, threads)
    with threads.editing(KEY) as editable:
        editable.rework(note="narrow it")
    capped = world(without_runs(here.settings),
                   github=here.github, working_copies=here.working_copies,
                   agent_runs=here.agent_runs, thread_records=here.thread_records,
                   clock=here.clock, pr_processes=here.pr_processes).threads()
    drain(capped)
    assert capped.get(KEY).fix.started_at is None


@pytest.mark.parametrize("reached", [_reworking_queued], ids=["queued"])
@pytest.mark.parametrize(("verb", "args"), [("stop", ()),
                                            ("place", (ConversationState.DEFERRED,))])
def test_a_rework_run_accepts_every_decision_the_board_offers_it(settings, verb, args, reached):
    _, threads = _author(settings, reached)
    assert _held(threads).standing is ConversationState.REWORK

    assert not isinstance(_asked(threads, verb, *args), Denied)


def _pushed(here, head):
    record = here.github.prs[THE_PR]
    record.state = PullRequestState(author=here.github.account, base_branch="main",
                                    head_sha=head)
    here.change_detection.advance(
        THE_PR, Poll(state=here.github.pr_state(THE_PR), polled_at=NOW), set())


def test_waking_returns_a_deferred_conversation_to_open_with_a_reason(settings):
    here, threads = _author(settings, _proposed)
    _pushed(here, "a" * 40)
    _asked(threads, "place", ConversationState.DEFERRED, until="push")
    assert _held(threads).standing is ConversationState.DEFERRED

    _pushed(here, "b" * 40)
    drain(threads)

    stored = _held(threads)
    assert stored.standing is ConversationState.READY
    assert stored.wake_on is None
    assert stored.decidable_at == NOW
    assert stored.fix.reply_note == "woken: a new push landed"
    assert stored.reopened is False


def test_unparking_a_deferred_conversation_restores_its_proposal(settings):
    here, threads = _author(settings, _deferred)
    before = _held(threads)

    outcome = _asked(threads, "unpark")

    assert not isinstance(outcome, Denied)
    stored = _held(threads)
    assert stored.standing is ConversationState.READY
    assert stored.fix.is_proposed
    assert stored.fix.thread_sha == before.fix.thread_sha
    assert stored.wake_on is None
    assert stored.defer_note == ""
    assert stored.decidable_at == NOW
    assert len(here.agent_runs.asked) == 1


def test_unparking_a_waiting_on_reviewer_conversation_leaves_the_fix_alone(settings):
    _, threads = _author(settings, _waiting)
    before = _held(threads)

    outcome = _asked(threads, "unpark")

    assert not isinstance(outcome, Denied)
    stored = _held(threads)
    assert stored.standing is ConversationState.READY
    assert stored.fix.is_proposed
    assert stored.fix.thread_sha == before.fix.thread_sha


def _landed_and_resolved(here, threads):
    _proposed(here, threads)
    _asked(threads, "approve", reply="Renamed it.", resolve=True)


def test_unparking_a_resolved_conversation_leaves_the_fix_alone(settings):
    _, threads = _author(settings, _landed_and_resolved)
    before = _held(threads)
    assert before.github_resolved

    outcome = _asked(threads, "unpark")

    assert not isinstance(outcome, Denied)
    stored = _held(threads)
    assert stored.fix.pushed and stored.fix.answered
    assert stored.fix.commits == before.fix.commits
    assert stored.fix.thread_sha == before.fix.thread_sha


def test_replying_on_a_conversation_that_was_yours_parks_it_on_the_reviewer(settings):
    here, threads = _author(settings, _proposed)
    before = _held(threads)

    outcome = _asked(threads, "reply", "ok")

    assert not isinstance(outcome, Denied)
    assert _on_github(here).comments[-1].body == "ok"
    stored = _held(threads)
    assert stored.standing is ConversationState.WAITING
    assert stored.fix.is_proposed
    assert stored.fix.thread_sha == before.fix.thread_sha


def test_replying_on_a_conversation_that_was_not_yours_moves_nothing(settings):
    here, threads = _author(settings, _working)

    outcome = _asked(threads, "reply", "ok")

    assert not isinstance(outcome, Denied)
    assert _on_github(here).comments[-1].body == "ok"
    assert _held(threads).standing is ConversationState.WORKING


def test_a_reply_posted_on_a_deferred_thread_parks_it_on_the_other_party(settings):
    _, threads = _author(settings, _deferred)

    _asked(threads, "reply", "ok")

    stored = _held(threads)
    assert stored.standing is ConversationState.WAITING, (
        "you spoke last, which is what waiting means, and the wake condition "
        "no longer applies")
    assert (stored.wake_on, stored.defer_note) == (None, "")


def _removed_with_a_reply_left(here, threads):
    _proposed(here, threads)
    _adds(here, REPLY)
    here.github.delete_comment(THE_PR, CommentKind.REVIEW, 5001)
    lost(threads, KEY)


@pytest.mark.parametrize("reached,standing", [
    (_removed_with_a_reply_left, ConversationState.READY),
    (_waiting, ConversationState.WAITING),
], ids=["removed", "waiting on the reviewer"])
def test_no_reply_parks_a_conversation_that_is_no_longer_open(settings, reached, standing):
    _, threads = _author(settings, reached)
    before = _held(threads)

    outcome = _asked(threads, "reply", "ok")

    assert not isinstance(outcome, Denied)
    after = _held(threads)
    assert after.standing is standing
    assert after.is_removed == before.is_removed
