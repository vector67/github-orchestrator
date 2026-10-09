from dataclasses import replace
from pathlib import Path

import pytest

from github_orchestrator.agent_runs.fake import Outcome as RunOutcome
from github_orchestrator.conversation import (
    Classification,
    Conversation,
    ConversationState,
    Denied,
    ErrorCode,
    OperationKind,
)
from github_orchestrator.github import CommentKind
from github_orchestrator.github.fake import FakeGitHub, GhError
from github_orchestrator.settings.fake import fake_settings
from tests.builders import a_pr
from tests.conversation.support import (
    PR,
    REPO,
    WORKTREE,
    World,
    commit_fix,
    drain,
    hear,
    lost,
    on_github,
    repo_at,
    said,
    start_run,
    world,
)

THE_PR = a_pr(PR, REPO)

KEY = "PRRT_one"

ROOT = 101

POINTED = (("billing/invoice_writer.py", 142, "    return sorted(line_items)"),)


class _RefusingGitHub(FakeGitHub):
    refusing = False

    def reply_to_thread(self, key, body):
        if self.refusing:
            raise GhError("HTTP 403")
        return super().reply_to_thread(key, body)

    def comment_on_pr(self, pr, body):
        if self.refusing:
            raise GhError("HTTP 403")
        return super().comment_on_pr(pr, body)

    def delete_comment(self, pr, kind, comment_id):
        if self.refusing:
            raise GhError("HTTP 403")
        return super().delete_comment(pr, kind, comment_id)


class Here:
    def __init__(self, tmp_path: Path, github: FakeGitHub | None = None) -> None:
        self.world: World = world(fake_settings(tmp_path, agents_enabled=True),
                                  github=github or FakeGitHub())
        self.github = self.world.github
        self.github.add_pr(THE_PR)
        repo_at(self.world.working_copies, WORKTREE)
        self.threads = self.world.threads()
        hear(self.threads)

    def heard(self, key: str = KEY, kind: CommentKind = CommentKind.REVIEW,
              author: str = "reviewer") -> None:
        on_github(self.github, key, said(ROOT, "rename this", author=author), kind=kind,
                  path=None if kind is CommentKind.ISSUE else "f")
        hear(self.threads)

    def says_more(self, comment_id: int = 900) -> None:
        record = self.github.prs[THE_PR]
        record.threads = [replace(thread, comments=(*thread.comments,
                                                    said(comment_id, "one more thing")))
                          if thread.key == KEY else thread for thread in record.threads]
        hear(self.threads)

    def conversation(self, key: str = KEY) -> Conversation:
        found: Conversation = self.threads.get(key)
        return found

    def asked(self, verb, key: str = KEY) -> Conversation:
        with self.threads.editing(key) as conversation:
            asked = verb(conversation)
        assert not isinstance(asked, Denied), asked
        drain(self.threads)
        return self.conversation(key)


@pytest.fixture
def here(tmp_path):
    return Here(tmp_path)


def _refusing(tmp_path) -> tuple[Here, _RefusingGitHub]:
    github = _RefusingGitHub()
    return Here(tmp_path, github), github


def _propose(here: Here, key: str = KEY) -> None:
    start_run(here.world, here.threads)
    sha = commit_fix(here.world, key)
    with here.threads.editing(key) as editable:
        assert not isinstance(editable.ready(sha), Denied)
    drain(here.threads)


def _proposed(here: Here) -> None:
    here.heard()
    _propose(here)


def _declined(here: Here) -> None:
    here.heard()
    start_run(here.world, here.threads)
    with here.threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.RISKY, "touches the public API")


def _fail_every_attempt(here: Here) -> None:
    for _ in range(here.conversation().run_holder.attempts_allowed):
        start_run(here.world, here.threads)
        with here.threads.editing(KEY) as editable:
            editable.fail("run exited without reporting")


def _failed(here: Here) -> None:
    here.heard()
    _fail_every_attempt(here)


def _removed(here: Here) -> None:
    _proposed(here)
    here.github.delete_comment(THE_PR, here.github.thread(KEY).kind, ROOT)
    lost(here.threads, KEY)


def _reopened(here: Here) -> None:
    _proposed(here)
    here.asked(lambda conversation: conversation.reply("is this what you meant?"))
    here.says_more()
    assert here.conversation().reopened


def _reopened_proposal(here: Here) -> None:
    _reopened(here)
    _propose(here)


def _reopened_failure(here: Here) -> None:
    _reopened(here)
    _fail_every_attempt(here)


def _sessions(here: Here):
    return here.world.pr_processes.sessions.get(THE_PR, [])


def _held(here: Here) -> bool:
    copies = here.world.working_copies
    return (copies.holds_thread(THE_PR, KEY)
            or f"orchestrator/thread/{THE_PR.number}/{KEY}" in copies.branches)


def _replies(here: Here, key: str = KEY):
    thread = here.github.thread(key)
    return [] if thread is None else [c for c in thread.comments if c.id not in (ROOT, 900)]


def _refused_and_left(here: Here, verb) -> Denied:
    was = here.conversation()
    with here.threads.editing(KEY) as conversation:
        refused = verb(conversation)
    assert isinstance(refused, Denied), refused
    now = here.conversation()
    assert now.standing is was.standing
    assert now.fix == was.fix
    return refused


@pytest.mark.parametrize("before", [_proposed, _declined],
                         ids=["proposed", "declined"])
def test_a_fix_you_steer_yourself_opens_a_session_in_its_own_workspace(here, before):
    before(here)

    stored = here.asked(lambda conversation: conversation.start_session(
        steer="try it the other way round"))

    assert stored.standing is ConversationState.IN_SESSION
    assert stored.fix.decision_error is None
    [session] = _sessions(here)
    assert session.worktree == here.world.working_copies.thread_checkout(THE_PR, KEY)
    [opened] = here.world.agent_runs.sessions
    assert opened.steer == "try it the other way round"
    assert (opened.fix.skipped_because == "touches the public API") == (before is _declined)


def test_no_session_is_opened_when_claude_is_disabled(here):
    _proposed(here)
    here.threads = here.world.threads(agents_enabled=False)

    refused = _refused_and_left(here, lambda conversation: conversation.start_session())

    assert refused.code == ErrorCode.AGENTS_DISABLED
    assert here.conversation().fix.is_proposed
    assert _sessions(here) == []


@pytest.mark.parametrize("before", [_removed], ids=["removed"])
def test_a_conversation_that_is_no_longer_open_opens_no_session(here, before):
    before(here)

    _refused_and_left(here, lambda conversation: conversation.start_session())

    assert _sessions(here) == []


@pytest.mark.parametrize("before", [_proposed], ids=["proposed"])
def test_a_fix_sent_back_is_queued_for_a_rework_run_carrying_the_brief(here, before):
    before(here)
    here.world.agent_runs.script(RunOutcome(finishes=False))

    stored = here.asked(lambda conversation: conversation.rework(
        note="use the enum instead", pointed=POINTED))

    assert stored.standing is ConversationState.REWORK
    brief = stored.fix.run.brief
    assert brief.note == "use the enum instead"
    assert [(one.file, one.line, one.text) for one in brief.pointed] == list(POINTED)
    assert stored.fix.attempts == 1
    assert stored.fix.plan == ()
    assert stored.fix.decision_error is None
    assert stored.fix.base_sha is not None
    assert _held(here)


def test_a_rework_pointing_at_lines_needs_no_note(here):
    _proposed(here)

    stored = here.asked(lambda conversation: conversation.rework(pointed=POINTED))

    assert stored.standing is ConversationState.REWORK
    assert [(one.file, one.line, one.text) for one in stored.fix.run.brief.pointed] == list(
        POINTED)


def test_a_rework_with_neither_a_note_nor_a_pointed_line_is_refused(here):
    _proposed(here)

    refused = _refused_and_left(here, lambda conversation: conversation.rework())

    assert refused.reason == "an autonomous rework needs a note or a pointed line to work from"
    assert here.conversation().fix.is_proposed


def test_nothing_is_sent_back_for_rework_when_claude_is_disabled(here):
    _proposed(here)
    here.threads = here.world.threads(agents_enabled=False)

    refused = _refused_and_left(here, lambda conversation: conversation.rework(
        note="again please"))

    assert refused.code == ErrorCode.AGENTS_DISABLED
    assert here.conversation().fix.is_proposed


@pytest.mark.parametrize("before", [_removed], ids=["removed"])
def test_a_conversation_that_is_no_longer_open_sends_nothing_back(here, before):
    before(here)
    run = here.conversation().fix.run

    _refused_and_left(here, lambda conversation: conversation.rework(note="again please"))

    assert here.conversation().fix.run == run


def test_sending_a_reopened_conversation_back_clears_the_reopened_mark(here):
    _reopened_proposal(here)

    stored = here.asked(lambda conversation: conversation.rework(note="again please"))

    assert stored.reopened is False


def test_a_retried_fix_is_queued_again_with_a_fresh_budget(here):
    _failed(here)
    failed = here.conversation()
    assert failed.fix.attempts == failed.run_holder.attempts_allowed
    here.world.agent_runs.script(RunOutcome(finishes=False))

    stored = here.asked(lambda conversation: conversation.retry())

    assert stored.run_holder.kind == OperationKind.RETRY
    assert stored.standing is ConversationState.WORKING
    assert stored.fix.attempts == 1
    assert stored.fix.decision_error is None
    assert stored.fix.base_sha == failed.fix.base_sha
    assert _replies(here) == []


def _posted_on_the_pr(here: Here):
    return [thread for thread in here.github.prs[THE_PR].threads
            if thread.kind is CommentKind.ISSUE and thread.key != "IC_one"]


def test_a_closing_reply_on_a_pr_comment_records_the_key_it_was_posted_under(here):
    here.heard("IC_one", CommentKind.ISSUE)
    _propose(here, "IC_one")

    stored = here.asked(lambda conversation: conversation.resolve(reply="not doing this one"),
                        "IC_one")

    [posted] = _posted_on_the_pr(here)
    assert stored.standing is ConversationState.DONE
    assert stored.posted_comment_keys == (posted.key,)
    assert stored.closing_reply_id == posted.comments[0].id


def test_a_resolve_that_would_delete_a_root_github_has_lost_just_closes(here):
    here.heard(author=here.github.account)
    _propose(here)
    here.github.delete_comment(THE_PR, here.github.thread(KEY).kind, ROOT)
    lost(here.threads, KEY)

    stored = here.asked(lambda conversation: conversation.resolve(delete_comment=True))

    assert stored.standing is ConversationState.DONE
    assert stored.deleted_by_board is False
    assert not _held(here)


def test_a_closing_reply_on_a_root_github_has_lost_is_refused(here):
    _removed(here)

    refused = _refused_and_left(here, lambda conversation: conversation.resolve(
        reply="not doing this one"))

    assert refused.code == ErrorCode.COMMENT_GONE
    assert refused.reason == "no reply posted: the comment was deleted from GitHub"
    assert _replies(here) == []


def test_a_reply_from_the_composer_joins_the_transcript_and_never_reopens_the_card(tmp_path):
    here, github = _refusing(tmp_path)
    _proposed(here)
    github.refusing = True
    here.asked(lambda conversation: conversation.reply("first try"))
    assert here.conversation().fix.reply_error == "HTTP 403"
    github.refusing = False

    stored = here.asked(lambda conversation: conversation.reply("what about the other one?"))

    [reply] = _replies(here)
    assert "what about the other one?" in reply.body
    assert [comment.id for comment in stored.comments] == [ROOT, reply.id]
    assert stored.panel_reply_ids == (reply.id,)
    assert stored.fix.reply_error is None
    assert stored.fix.is_proposed


def test_a_reply_on_a_pr_comment_records_the_key_it_was_posted_under(here):
    here.heard("IC_one", CommentKind.ISSUE)

    stored = here.asked(lambda conversation: conversation.reply("what about the other one?"),
                        "IC_one")

    [posted] = _posted_on_the_pr(here)
    assert stored.posted_comment_keys == (posted.key,)


def test_a_reply_github_refused_says_why_and_keeps_the_words(tmp_path):
    here, github = _refusing(tmp_path)
    _proposed(here)
    github.refusing = True

    stored = here.asked(lambda conversation: conversation.reply("what about the other one?"))

    assert stored.fix.reply_error == "HTTP 403"


CLEARS_THE_MARK = {
    "approve": (_reopened_proposal, lambda conversation: conversation.approve()),
    "open a session": (_reopened_proposal, lambda conversation: conversation.start_session()),
    "resolve": (_reopened_proposal, lambda conversation: conversation.resolve()),
    "try again": (_reopened_failure, lambda conversation: conversation.retry()),
}


@pytest.mark.parametrize("verb", sorted(CLEARS_THE_MARK))
def test_acting_on_a_reopened_conversation_takes_its_mark_off(here, verb):
    before, act = CLEARS_THE_MARK[verb]
    before(here)
    assert here.conversation().reopened

    stored = here.asked(act)

    assert stored.fix.decision_error is None
    assert stored.reopened is False


def test_a_reply_of_your_own_takes_the_reopened_mark_off(here):
    _reopened_proposal(here)

    assert here.asked(lambda conversation: conversation.reply("ok")).reopened is False


def test_a_verb_the_conversation_refuses_leaves_its_mark_where_it_was(here):
    _reopened(here)
    start_run(here.world, here.threads, finishes=False)

    _refused_and_left(here, lambda conversation: conversation.resolve())

    assert here.conversation().reopened is True
