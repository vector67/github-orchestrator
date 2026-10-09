import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from github_orchestrator.agent_runs.fake import Outcome, Reworking
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
from github_orchestrator.domain import Sha
from github_orchestrator.github import CommentKind
from github_orchestrator.github.fake import FakeGitHub, GhError
from github_orchestrator.working_copies.fake import FakeWorkingCopies, ThreadGitError
from tests.conversation.support import (
    THE_PR,
    WORKTREE,
    World,
    at,
    drain,
    first_poll,
    hear,
    lost,
    on_github,
    propose,
    repo_at,
    said,
    start_run,
    world,
)
from tests.disk_layout import thread_file, thread_intent_file
from tests.thread_records.support import disk_thread_records

KEY = "PRRT_101"
OTHER = "PRRT_202"
ISSUE_KEY = "IC_101"
COMMENT_ID = 101
BODY = "Please rename this helper."
NOW = "2026-09-07T12:00:00Z"
MY_COMMENT = ((COMMENT_ID, FakeGitHub().account, BODY),)
REFUSAL = "[Errno 2] No such file or directory: 'claude'"


class WhileReplying(FakeGitHub):
    def __init__(self) -> None:
        super().__init__()
        self.meanwhile: Callable[[], None] = lambda: None

    def reply_to_thread(self, key, body):
        posted = super().reply_to_thread(key, body)
        self.meanwhile()
        return posted


class RepliesRefused(FakeGitHub):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error: Exception | None = error

    def reply_to_thread(self, key, body):
        if self.error is not None:
            raise self.error
        return super().reply_to_thread(key, body)


class DeleteRefused(FakeGitHub):
    def delete_comment(self, pr, kind, comment_id):
        raise GhError("gh: Forbidden (HTTP 403)")


def drop_refused(github):
    copies = FakeWorkingCopies(github)
    copies.fail_drops(ThreadGitError("git blew up"))
    return copies


@dataclass
class Scene:
    here: World
    threads: Any

    def stored(self, key: str = KEY) -> Conversation:
        found: Conversation | None = self.threads.get(key)
        assert found is not None
        return found

    def ask(self, verb: str, *args, key: str = KEY, **kwargs) -> Conversation:
        asked = self.answer(verb, *args, key=key, **kwargs)
        assert not isinstance(asked, Denied), asked
        return asked

    def answer(self, verb: str, *args, key: str = KEY, **kwargs) -> Conversation | Denied:
        with self.threads.editing(key) as conversation:
            answered: Conversation | Denied = getattr(conversation, verb)(*args, **kwargs)
        return answered

    def decide(self, verb: str, *args, key: str = KEY, **kwargs) -> Conversation:
        self.ask(verb, *args, key=key, **kwargs)
        drain(self.threads)
        return self.stored(key)

    def operation(self, asked: Conversation):
        wanted = asked.operations[-1].id
        [found] = [one for one in self.stored(asked.key).operations if one.id == wanted]
        return found

    def taken(self, asked: Conversation) -> bool:
        return self.operation(asked).state not in (OperationState.PENDING,
                                                   OperationState.REQUEUED)

    def replies(self, key: str = KEY) -> list[str]:
        thread = self.here.github.thread(key)
        assert thread is not None
        return [comment.body for comment in thread.comments[1:]]

    def still_cut(self, key: str = KEY) -> bool:
        return self.here.working_copies.holds_thread(THE_PR, key)

    def propose(self, key: str = KEY) -> Conversation:
        return propose(self.here, self.threads, key, tests="passed")

    def fail_every_attempt(self, *keys: str, reason: str = "tests failed") -> None:
        for _ in range(self.stored(keys[0]).run_holder.attempts_allowed):
            start_run(self.here, self.threads)
            for key in keys:
                with self.threads.editing(key) as editable:
                    editable.fail(reason)

    def sessions(self):
        return self.here.pr_processes.sessions.get(THE_PR, [])

    def refuse_sessions(self) -> None:
        self.here.pr_processes.refusal = REFUSAL

    def agents_disabled(self) -> Any:
        return self.here.claude(False).threads()


def scene(settings, *, github=None, working_copies=None, thread_records=None,
          comments=((COMMENT_ID, "reviewer", BODY),), is_author: bool | None = None,
          key: str = KEY, kind: CommentKind = CommentKind.REVIEW) -> Scene:
    github = github or FakeGitHub()
    here = world(settings, github=github,
                 working_copies=working_copies or FakeWorkingCopies(github),
                 thread_records=thread_records, clock=at(NOW))
    repo_at(here.working_copies, WORKTREE)
    review = kind is CommentKind.REVIEW
    threads = here.threads(is_author=is_author)
    first_poll(github, threads)
    on_github(github, key, *(said(id, body, author=author) for id, author, body in comments),
              kind=kind, path="f" if review else None, line=1 if review else None)
    hear(threads)
    return Scene(here, threads)


def proposed(settings, *, key: str = KEY, **built) -> Scene:
    s = scene(settings, key=key, **built)
    s.propose(key)
    return s


def _on_disk(settings, tmp_path, github=None) -> Scene:
    return proposed(settings, github=github,
                    thread_records=disk_thread_records(tmp_path / "threads"))


def test_a_reply_is_posted_in_the_operators_own_words(settings):
    s = proposed(settings)

    asked = s.ask("reply", "What did you mean by that?")
    drain(s.threads)

    assert s.replies() == ["What did you mean by that?"]
    stored = s.stored()
    assert stored.panel_reply_ids == (9001,)
    assert stored.comments[-1].body == "What did you mean by that?"
    assert s.taken(asked)


def test_a_reply_moves_no_decision(settings):
    s = proposed(settings)

    assert s.decide("reply", "just asking").fix.is_proposed


def test_a_second_reply_is_remembered_beside_the_first(settings):
    s = proposed(settings)
    s.decide("reply", "one")

    assert s.decide("reply", "two").panel_reply_ids == (9001, 9002)


def test_a_reply_github_refuses_settles_refused_with_its_words(settings):
    s = proposed(settings, github=RepliesRefused(GhError("gh api exploded")))

    asked = s.ask("reply", "please explain")
    drain(s.threads)

    assert s.stored().fix.reply_error == "gh api exploded"
    reply = s.operation(asked)
    assert (reply.kind, reply.state, reply.reason_code) == (
        OperationKind.REPLY, OperationState.REFUSED, ReasonCode.REPLY_FAILED)
    assert reply.text == "please explain"
    drain(s.threads)
    assert s.stored().fix.reply_error == "gh api exploded"
    assert [one.kind for one in s.stored().operations].count(OperationKind.REPLY) == 1, (
        "a refusal is where the reply settles, not a reason to post it "
        "again on every drain")


def test_a_reply_github_refuses_leaves_its_traceback_in_the_log(settings, caplog):
    s = proposed(settings, github=RepliesRefused(GhError("gh api exploded")))
    s.ask("reply", "please explain")

    with caplog.at_level(logging.WARNING):
        drain(s.threads)

    [failure] = [r for r in caplog.records if r.exc_info]
    assert KEY in failure.getMessage()
    assert "PostReply" in failure.getMessage()
    assert "gh api exploded" in caplog.text


def test_a_reply_the_gh_spawn_refuses_outright_is_recorded(settings):
    s = proposed(settings, github=RepliesRefused(OSError(7, "Argument list too long")))

    asked = s.ask("reply", "please explain")
    drain(s.threads)

    assert "Argument list too long" in s.stored().fix.reply_error
    assert s.operation(asked).state is OperationState.REFUSED


def test_a_reply_with_no_thread_to_land_on_is_kept_off_the_next_poll(settings):
    s = proposed(settings, key=ISSUE_KEY, kind=CommentKind.ISSUE)

    stored = s.decide("reply", "Versioned all four.", key=ISSUE_KEY)

    assert stored.posted_comment_keys == ("IC_9001",)
    assert stored.panel_reply_ids == (9001,)
    assert "Versioned all four." in s.here.github.thread("IC_9001").comments[0].body
    hear(s.threads)
    assert [one.key for one in s.threads.all()] == [ISSUE_KEY]


def test_a_decision_on_a_record_that_will_not_read_is_kept(settings, tmp_path):
    s = _on_disk(settings, tmp_path)
    record = thread_file(tmp_path / "threads", THE_PR, KEY)
    s.ask("resolve", reply="closing this")
    readable = record.read_bytes()
    record.write_text("[]")

    drain(s.threads)
    assert s.replies() == []
    record.write_bytes(readable)
    drain(s.threads)

    assert s.replies() == ["closing this"]
    assert s.stored().standing is ConversationState.DONE


def test_every_pending_reply_drains_in_the_order_it_was_written(settings):
    s = scene(settings)
    on_github(s.here.github, OTHER, said(202, "and this one"))
    hear(s.threads)
    s.propose()
    s.propose(OTHER)
    s.ask("reply", "second thread", key=OTHER)
    s.ask("reply", "first thread")

    drain(s.threads)

    assert s.stored(OTHER).panel_reply_ids == (9001,)
    assert s.stored().panel_reply_ids == (9002,)
    assert s.replies(OTHER) == ["second thread"]
    assert s.replies() == ["first thread"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads anything")
def test_a_decision_the_drain_cannot_open_is_kept_and_never_called_garbage(
    settings, tmp_path, caplog,
):
    s = _on_disk(settings, tmp_path)
    s.ask("approve", reply="ship it")
    path = thread_intent_file(tmp_path / "threads", THE_PR, KEY)
    path.chmod(0)
    try:
        with caplog.at_level(logging.WARNING):
            drain(s.threads)
        survived = path.exists()
    finally:
        if path.exists():
            path.chmod(0o600)

    assert survived, "a decision whose file would not open was deleted unread"
    assert "garbage" not in caplog.text


def test_a_composer_reply_github_took_is_never_dropped_by_a_write_that_fails(
    settings, tmp_path, monkeypatch,
):
    github = WhileReplying()
    s = _on_disk(settings, tmp_path, github)
    s.here.thread_records.of(THE_PR).save("reply", KEY, b"please also bump the lockfile")
    posted = []
    real_replace = Path.replace

    def replace_once_github_has_been_told(self, target):
        if posted:
            raise OSError(28, "No space left on device")
        return real_replace(self, target)

    github.meanwhile = lambda: posted.append(True)
    monkeypatch.setattr(Path, "replace", replace_once_github_has_been_told)

    drain(s.threads)

    assert posted, "the reply never reached GitHub; the test proved nothing"
    waiting = s.stored().operations[-1]
    assert (waiting.kind, waiting.state, waiting.text) == (
        OperationKind.REPLY, OperationState.PENDING, "please also bump the lockfile"), (
        "the reply is on GitHub, the inbox is empty and no record carries its id")


def test_a_decision_nobody_touched_is_cleared_when_it_is_done(settings, tmp_path):
    s = _on_disk(settings, tmp_path)

    asked = s.ask("resolve", reply="closing this")
    drain(s.threads)

    assert s.taken(asked)
    assert s.stored().standing is ConversationState.DONE


def test_a_session_verb_opens_one_in_the_fixs_workspace(settings):
    s = proposed(settings)
    base = s.stored().fix.base_sha

    asked = s.ask("start_session", steer="not what I meant")
    drain(s.threads)

    [pane] = s.sessions()
    assert pane.worktree == s.here.working_copies.thread_checkout(THE_PR, KEY)
    assert [session.steer for session in s.here.agent_runs.sessions] == ["not what I meant"]
    stored = s.stored()
    assert stored.standing is ConversationState.IN_SESSION
    assert stored.fix.base_sha == base
    assert s.taken(asked)


def test_a_session_on_a_skipped_fix_says_so_to_the_session(settings):
    s = scene(settings)
    start_run(s.here, s.threads, finishes=False)
    with s.threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.NEEDS_HUMAN, "two plausible readings")
    drain(s.threads)

    s.decide("start_session")

    [session] = s.here.agent_runs.sessions
    assert (session.fix.classification, session.fix.skipped_because) == (
        Classification.NEEDS_HUMAN, "two plausible readings")


def test_a_session_with_no_workspace_left_cuts_one_and_records_what_it_got(settings):
    s = proposed(settings)
    s.here.working_copies.lose_worktree(s.here.working_copies.thread_checkout(THE_PR, KEY))
    assert not s.still_cut()

    stored = s.decide("start_session")

    assert s.still_cut()
    assert stored.fix.base_sha == Sha(s.here.working_copies.branches["main"])
    [pane] = s.sessions()
    assert pane.worktree == s.here.working_copies.thread_checkout(THE_PR, KEY)


def test_a_session_that_will_not_start_is_refused_and_leaves_the_fix_as_it_was(settings):
    s = proposed(settings)
    s.refuse_sessions()

    asked = s.ask("start_session")
    drain(s.threads)

    stored = s.stored()
    assert stored.fix.is_proposed
    assert stored.fix.decision_error == REFUSAL
    assert s.operation(asked).state is OperationState.REFUSED
    assert s.here.agent_runs.sessions == []


def test_a_declined_fix_whose_session_is_refused_is_still_declined(settings):
    s = scene(settings)
    start_run(s.here, s.threads, finishes=False)
    with s.threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.NEEDS_HUMAN, "two plausible readings")
    drain(s.threads)
    s.refuse_sessions()

    s.ask("start_session")
    drain(s.threads)

    assert s.stored().fix.is_declined
    assert s.stored().fix.decision_error == REFUSAL


def test_no_session_starts_while_claude_is_disabled(settings):
    s = proposed(settings)
    asked = s.ask("start_session")

    drain(s.agents_disabled())

    stored = s.stored()
    assert stored.fix.is_proposed
    assert "agents_enabled=false" in stored.fix.decision_error
    assert s.sessions() == []
    assert s.taken(asked)


POINTED = ("billing/invoice_writer.py", 142, "    return sorted(line_items)")


def test_a_rework_verb_queues_a_rework_run_carrying_the_brief(settings):
    s = proposed(settings)
    base = s.stored().fix.base_sha
    runs = len(s.here.agent_runs.started)

    asked = s.ask("rework", note="use the enum instead", pointed=[POINTED], include=("anna",))
    drain(s.threads)

    stored = s.stored()
    assert stored.standing is ConversationState.REWORK
    run = stored.fix.run
    assert run.kind is OperationKind.REWORK
    assert run.brief is not None
    assert (run.brief.note, run.brief.include) == ("use the enum instead", ("anna",))
    assert [(line.file, line.line, line.text) for line in run.brief.pointed] == [POINTED]
    assert stored.fix.base_sha == base
    assert s.sessions() == []
    [started] = s.here.agent_runs.started[runs:]
    assert isinstance(started.work, Reworking)
    assert started.work.fix.note == "use the enum instead"
    assert s.taken(asked)


def test_nothing_is_sent_back_for_rework_while_claude_is_disabled(settings):
    s = proposed(settings)
    asked = s.ask("rework", note="again")

    drain(s.agents_disabled())

    stored = s.stored()
    assert stored.fix.is_proposed
    assert "agents_enabled=false" in stored.fix.decision_error
    assert s.taken(asked)


def _push_failed(s: Scene) -> None:
    s.here.working_copies.refuse_pushes("! [rejected] main")
    s.decide("approve")
    assert s.stored().fix.push_error


def test_a_session_the_fix_will_not_take_spawns_nothing(settings):
    s = proposed(settings)
    _push_failed(s)
    base = s.stored().fix.base_sha

    denied = s.answer("start_session")

    assert isinstance(denied, Denied)
    assert s.sessions() == []
    stored = s.stored()
    assert stored.fix.picked
    assert stored.fix.base_sha == base


def _branch() -> str:
    return f"orchestrator/thread/{THE_PR.number}/{KEY}"


def test_a_resolve_closes_the_card_and_drops_its_workspace(settings):
    s = proposed(settings)

    asked = s.ask("resolve")
    drain(s.threads)

    assert s.stored().standing is ConversationState.DONE
    assert s.replies() == []
    assert not s.still_cut()
    assert _branch() not in s.here.working_copies.branches
    assert s.taken(asked)


def test_a_resolve_says_the_operators_words_before_it_closes_the_card(settings):
    s = proposed(settings)

    stored = s.decide("resolve", reply="Out of scope here.")

    assert s.replies() == ["Out of scope here."]
    assert stored.standing is ConversationState.DONE
    assert stored.closing_reply == "Out of scope here."
    assert stored.closing_reply_id == 9001
    assert stored.comments[-1].id == 9001


REVIEWER_COMMENTS = ((COMMENT_ID, "vector67", BODY), (202, "jeffrey", "done"))


def _reviewing(settings, **built) -> Scene:
    return scene(settings, comments=REVIEWER_COMMENTS, is_author=False, **built)


def test_a_reviewer_resolve_tells_github_and_thumbs_up_the_last_word(settings):
    s = _reviewing(settings)

    stored = s.decide("resolve", resolve=True)

    assert s.here.github.thread(KEY).is_resolved is True
    assert s.here.github.reactions == {202: ["+1"]}
    assert [c.id for c in s.here.github.thread(KEY).comments] == [COMMENT_ID, 202]
    assert stored.standing is ConversationState.DONE
    assert stored.github_resolved is True
    assert stored.github_resolved_at == NOW


def test_a_closing_reply_github_refuses_holds_the_card_where_it_is(settings):
    s = proposed(settings, github=RepliesRefused(GhError("gh api exploded")))

    asked = s.ask("resolve", reply="Out of scope.")
    drain(s.threads)

    stored = s.stored()
    assert stored.standing is ConversationState.READY
    assert "gh api exploded" in stored.fix.decision_error
    assert s.still_cut()
    assert s.taken(asked)


def _gone(s: Scene) -> None:
    s.here.github.delete_comment(THE_PR, CommentKind.REVIEW, COMMENT_ID)
    lost(s.threads, KEY)
    assert s.stored().comment_deleted


def test_a_closing_verb_still_closes_its_card_while_claude_is_disabled(settings):
    s = proposed(settings)
    s.threads = s.agents_disabled()

    asked = s.ask("resolve", reply="No thanks.")
    drain(s.threads)

    assert s.replies() == ["No thanks."]
    assert s.stored().standing is ConversationState.DONE
    assert s.taken(asked)


def test_a_ticked_resolve_deletes_the_comment_and_closes_the_card(settings):
    s = proposed(settings, comments=MY_COMMENT)

    stored = s.decide("resolve", delete_comment=True)

    assert s.here.github.thread(KEY) is None
    assert stored.standing is ConversationState.DONE
    assert stored.comment_deleted is True
    assert stored.deleted_by_board is True
    assert not s.still_cut()


def test_a_delete_github_refuses_holds_the_resolved_card_where_it_is(settings):
    s = proposed(settings, github=DeleteRefused(), comments=MY_COMMENT)

    asked = s.ask("resolve", delete_comment=True)
    drain(s.threads)

    stored = s.stored()
    assert stored.standing is ConversationState.READY
    assert "HTTP 403" in stored.fix.decision_error
    assert stored.comment_deleted is False
    assert s.still_cut()
    assert s.taken(asked)


def test_a_reject_says_the_operators_words_before_it_closes_the_card(settings):
    s = proposed(settings)

    asked = s.ask("reject", reply="Not taking this.")
    drain(s.threads)

    assert s.replies() == ["Not taking this."]
    stored = s.stored()
    assert stored.standing is ConversationState.DONE
    assert stored.closing_reply == "Not taking this."
    assert stored.closing_reply_id == 9001
    assert stored.comment_deleted is False
    assert s.taken(asked)


def test_a_rejecting_reply_github_refuses_holds_the_card_where_it_is(settings):
    s = proposed(settings, github=RepliesRefused(GhError("gh api exploded")))

    asked = s.ask("reject", reply="Not taking this.")
    drain(s.threads)

    stored = s.stored()
    assert stored.standing is ConversationState.READY
    assert "gh api exploded" in stored.fix.decision_error
    assert s.taken(asked)


def test_a_resolve_after_a_failed_reject_closes_the_card(settings):
    github = RepliesRefused(GhError("gh api exploded"))
    s = proposed(settings, github=github)
    s.decide("reject", reply="Not taking this.")
    github.error = None

    stored = s.decide("resolve", reply="Fine.")

    assert stored.standing is ConversationState.DONE
    assert s.replies() == ["Fine."]


def test_a_reject_delete_github_refuses_holds_the_card_where_it_is(settings):
    s = proposed(settings, github=DeleteRefused(), comments=MY_COMMENT)

    asked = s.ask("reject", delete_comment=True)
    drain(s.threads)

    stored = s.stored()
    assert stored.standing is ConversationState.READY
    assert "HTTP 403" in stored.fix.decision_error
    assert stored.comment_deleted is False
    assert s.taken(asked)


def test_a_defer_with_no_modifier_wakes_by_hand(settings):
    s = proposed(settings)

    stored = s.decide("place", ConversationState.DEFERRED)

    assert (stored.standing, stored.wake_on) == (ConversationState.DEFERRED, "manual")


def test_an_empty_reply_is_refused(settings):
    s = scene(settings)

    denied = s.answer("reply", "  ")

    assert isinstance(denied, Denied)
    assert denied.code is ErrorCode.EMPTY_BODY
    assert s.replies() == []


def test_defer_until_push_records_the_head_it_was_deferred_at(settings):
    head = "a9296dba" + "0" * 32
    s = proposed(settings)
    s.here.polled(head_sha=head, is_author=True)

    stored = s.decide("place", ConversationState.DEFERRED, note="until they push again", until="push")

    assert (stored.standing, stored.wake_on, stored.defer_note) == (
        ConversationState.DEFERRED, f"push:{head}", "until they push again")


def test_deferring_until_a_push_with_no_head_to_wait_on_is_refused(settings):
    s = proposed(settings)

    stored = s.decide("place", ConversationState.DEFERRED, until="push")

    assert stored.standing is ConversationState.READY
    assert stored.fix.decision_error == "no head to wait on"


def test_unparking_a_rejected_conversation_requeues_the_agent(settings):
    s = proposed(settings)
    s.decide("reject")
    s.here.agent_runs.script(Outcome(finishes=False))

    asked = s.ask("unpark")
    drain(s.threads)

    stored = s.stored()
    assert stored.standing is ConversationState.WORKING
    assert stored.fix.thread_sha is None
    assert s.still_cut()
    assert s.taken(asked)


def test_a_decision_whose_contents_do_not_parse_is_cleared_and_the_rest_drain(
    settings, tmp_path,
):
    s = _on_disk(settings, tmp_path)
    garbage = thread_intent_file(tmp_path / "threads", THE_PR, "PRRT_999")
    garbage.parent.mkdir(parents=True, exist_ok=True)
    garbage.write_text("not a decision at all")

    asked = s.ask("resolve")
    drain(s.threads)

    assert not garbage.exists()
    assert s.taken(asked)
    assert s.stored().standing is ConversationState.DONE


def test_a_decision_for_a_conversation_with_no_record_is_refused(settings):
    s = scene(settings)
    main = s.here.working_copies.branches["main"]

    denied = s.answer("approve", key="PRRT_nobody")

    assert isinstance(denied, Denied)
    assert denied.code is ErrorCode.NOT_FOUND
    assert s.threads.get("PRRT_nobody") is None
    assert s.here.working_copies.branches["main"] == main


def _removed(s: Scene) -> None:
    _gone(s)


PARKING: dict[str, tuple[Callable[[Scene], Any], ConversationState]] = {
    "removed from github": (_removed, ConversationState.READY),
}


@pytest.mark.parametrize("standing", sorted(PARKING))
def test_a_reply_moves_the_state_the_table_says_it_moves(settings, standing):
    reach, after = PARKING[standing]
    s = scene(settings)
    reach(s)

    s.ask("reply", "this wants a rebase first")
    drain(s.threads)

    assert s.stored().standing is after


def test_a_resolve_closes_a_conversation_github_has_already_lost(settings):
    s = scene(settings)
    _gone(s)

    asked = s.ask("resolve")
    drain(s.threads)

    assert s.stored().standing is ConversationState.DONE
    assert s.taken(asked)


def test_one_conversation_that_will_not_decide_leaves_the_next_alone(settings):
    github = FakeGitHub()
    s = scene(settings, github=github, working_copies=drop_refused(github))
    on_github(github, OTHER, said(202, "and this one"))
    hear(s.threads)
    s.fail_every_attempt(KEY, OTHER)
    s.ask("resolve")
    s.ask("retry", key=OTHER)
    s.here.agent_runs.script(Outcome(finishes=False))

    drain(s.threads)

    assert s.stored(OTHER).standing is ConversationState.WORKING
    assert s.still_cut()
