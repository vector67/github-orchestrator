import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from github_orchestrator.agent_runs.fake import FilingTicket, Outcome, RebasingFix
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
from github_orchestrator.github import CommentKind, ThreadComment
from github_orchestrator.github.fake import FakeGitHub, GhError
from github_orchestrator.working_copies.fake import FakeWorkingCopies
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
from tests.thread_records.support import disk_thread_records

KEY = "PRRT_101"
ISSUE_KEY = "IC_101"
COMMENT_ID = 101
BODY = "Please rename this helper."
WORDS = "Good catch — renamed it."
MESSAGE = "Rename the helper"
WAIT = 5
ME = FakeGitHub().account


def _replied(github: FakeGitHub, key: str, comment: ThreadComment) -> None:
    record = github.prs[THE_PR]
    record.threads = [replace(thread, comments=(*thread.comments, comment))
                      if thread.key == key else thread for thread in record.threads]


def _run_alive(here: World) -> None:
    here.agent_runs.script(Outcome(finishes=False))
    here.agent_runs.carry_on(WORKTREE, THE_PR)


@dataclass
class Scene:
    here: World
    threads: Any
    base: Sha
    key: str = KEY

    def propose(self, **ready) -> Sha:
        proposed = propose(self.here, self.threads, self.key, **{"tests": "passed", **ready})
        sha = proposed.fix.thread_sha
        assert sha is not None
        return sha

    def ask(self, **asked) -> Conversation | Denied:
        with self.threads.editing(self.key) as editable:
            answered: Conversation | Denied = editable.approve(**asked)
        return answered

    def approve(self, **asked) -> Conversation:
        approved = self.ask(**asked)
        assert not isinstance(approved, Denied), approved
        drain(self.threads)
        return self.stored()

    def stored(self) -> Conversation:
        found: Conversation | None = self.threads.get(self.key)
        assert found is not None
        return found

    def settled(self) -> bool:
        approval = self.stored().latest_approval
        assert approval is not None
        return approval.state in (OperationState.APPLIED, OperationState.REFUSED)

    def checkout(self) -> str:
        return self.here.working_copies.thread_checkout(THE_PR, self.key)

    def main(self) -> Sha:
        return Sha(self.here.working_copies.branches["main"])

    def pushed(self) -> Sha:
        return Sha(self.here.working_copies.origin["main"])

    def answers(self) -> tuple[ThreadComment, ...]:
        thread = self.here.github.thread(self.key)
        return () if thread is None else thread.comments[1:]

    def tree(self, sha: Sha) -> dict[str, str]:
        return self.here.working_copies.commits[str(sha)].tree

    def dropped(self) -> bool:
        return not self.here.working_copies.holds_thread(THE_PR, self.key)


def scene(settings, *, github=None, copies=None, thread_records=None, clock=None,
          key: str = KEY, kind: CommentKind = CommentKind.REVIEW,
          author: str = "reviewer") -> Scene:
    github = github or FakeGitHub()
    copies = copies or FakeWorkingCopies(github)
    here = world(settings, github=github, working_copies=copies,
                 thread_records=thread_records, clock=clock)
    base = repo_at(copies, WORKTREE, {"f": "old\n", "README": "hello"})
    review = kind is CommentKind.REVIEW
    threads = here.threads()
    first_poll(github, threads)
    on_github(github, key, said(COMMENT_ID, BODY, author=author), kind=kind,
              path="f" if review else None, line=1 if review else None)
    hear(threads)
    return Scene(here, threads, Sha(base), key)


def proposed(settings, **built) -> Scene:
    s = scene(settings, **built)
    s.propose()
    return s


def push_refused() -> FakeWorkingCopies:
    copies = FakeWorkingCopies()
    copies.refuse_pushes("failed to push some refs")
    return copies


def push_blows_up() -> FakeWorkingCopies:
    copies = FakeWorkingCopies()
    copies.fail_pushes(RuntimeError("git blew up"))
    return copies


class ReplyRefused(FakeGitHub):
    def __init__(self) -> None:
        super().__init__()
        self.refusing = True

    def reply_to_thread(self, key: str, body: str) -> ThreadComment | None:
        if self.refusing:
            raise GhError("gh api exploded")
        return super().reply_to_thread(key, body)


class ResolveForbidden(FakeGitHub):
    def __init__(self) -> None:
        super().__init__()
        self.refusing = True

    def resolve_thread(self, key: str) -> None:
        if self.refusing:
            raise GhError("gh: Forbidden (HTTP 403)")
        super().resolve_thread(key)


class DeleteForbidden(FakeGitHub):
    def delete_comment(self, pr, kind, comment_id: int) -> None:
        raise GhError("gh: Forbidden (HTTP 403)")


class AnsweredBeforeResolved(FakeGitHub):
    def __init__(self) -> None:
        super().__init__()
        self.answers_at_resolve: int | None = None

    def resolve_thread(self, key: str) -> None:
        thread = self.thread(key)
        assert thread is not None
        self.answers_at_resolve = len(thread.comments) - 1
        super().resolve_thread(key)


def test_an_approve_lands_the_fix_pushes_it_and_answers_the_comment(settings):
    s = proposed(settings)

    stored = s.approve()

    assert stored.standing is ConversationState.DONE
    assert (stored.fix.picked, stored.fix.pushed, stored.fix.answered) == (True, True, True)
    assert stored.fix.landed_base == s.base
    assert stored.fix.landed_sha == s.main() == s.pushed()
    assert s.tree(s.main())["f"] == "new\n"
    assert [f"/commit/{stored.fix.landed_sha}" in one.body for one in s.answers()] == [True]
    assert s.dropped()
    assert s.settled()


def test_an_approve_lands_while_claude_is_disabled(settings):
    s = proposed(settings)
    s.threads = s.here.claude(False).threads()

    stored = s.approve()

    assert stored.standing is ConversationState.DONE
    assert s.pushed() == stored.fix.landed_sha


def test_an_approve_in_the_operators_own_words_posts_them_and_remembers_them(settings):
    s = proposed(settings)

    stored = s.approve(reply=WORDS)

    [answer] = s.answers()
    assert answer.body.startswith(f"{WORDS}\n\n")
    assert f"/commit/{stored.fix.landed_sha}" in answer.body
    assert stored.approved_reply == WORDS
    assert stored.approved_reply_id == answer.id


def test_a_blank_approve_answers_with_the_commit_and_nothing_of_its_own(settings):
    s = proposed(settings)

    stored = s.approve()

    [answer] = s.answers()
    assert WORDS not in answer.body
    assert answer.body.endswith(f"/commit/{stored.fix.landed_sha})")
    assert stored.approved_reply == ""


def test_an_approve_answering_a_comment_with_no_thread_stays_off_the_next_poll(settings):
    s = proposed(settings, key=ISSUE_KEY, kind=CommentKind.ISSUE)

    stored = s.approve()

    posted = [thread.key for thread in s.here.github.threads(THE_PR)
              if thread.key != ISSUE_KEY]
    assert len(posted) == 1
    assert stored.posted_comment_keys == tuple(posted)
    hear(s.threads)
    assert [one.key for one in s.threads.all()] == [ISSUE_KEY]


def test_an_approve_with_no_commit_to_land_is_refused_and_leaves_the_card(settings):
    s = scene(settings)
    start_run(s.here, s.threads, finishes=False)
    with s.threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.NEEDS_HUMAN, "nothing to do")

    denied = s.ask()

    assert isinstance(denied, Denied)
    assert denied.code is ErrorCode.NO_PROPOSAL
    assert "nothing to land" in denied.reason
    assert s.main() == s.base
    assert s.answers() == ()
    assert s.stored().fix.is_declined


def _a_reply_proposed(settings, **built) -> Scene:
    s = scene(settings, **built)
    start_run(s.here, s.threads, finishes=False)
    with s.threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.QUESTION, "It runs once per poll.")
    return s


def test_accepting_a_reply_posts_the_edited_reply_and_neither_picks_nor_pushes(settings):
    s = _a_reply_proposed(settings)

    stored = s.approve(reply=WORDS)

    assert [answer.body for answer in s.answers()] == [WORDS]
    assert stored.standing is ConversationState.DONE
    assert (stored.fix.picked, stored.fix.pushed, stored.fix.answered) == (False, False, True)
    assert s.main() == s.base == s.pushed()
    assert stored.approved_reply == WORDS
    thread = s.here.github.thread(KEY)
    assert thread is not None and not thread.is_resolved
    assert s.settled()


def test_accepting_a_reply_ticked_to_resolve_resolves_after_answering(settings):
    github = AnsweredBeforeResolved()
    s = _a_reply_proposed(settings, github=github)

    stored = s.approve(reply=WORDS, resolve=True)

    assert github.answers_at_resolve == 1
    assert stored.github_resolved is True
    assert stored.standing is ConversationState.DONE


def test_accepting_a_reply_does_not_wait_on_a_claude_run_or_the_pr_worktree(settings):
    s = _a_reply_proposed(settings)
    _run_alive(s.here)

    stored = s.approve(reply=WORDS)

    assert stored.standing is ConversationState.DONE
    assert [answer.body for answer in s.answers()] == [WORDS]


def test_accepting_a_reply_with_nothing_to_say_is_refused(settings):
    s = _a_reply_proposed(settings)

    denied = s.ask(reply="  ")

    assert isinstance(denied, Denied)
    assert denied.code is ErrorCode.EMPTY_BODY
    assert s.answers() == ()
    assert s.stored().fix.is_proposed


TICKET_REPLY = "That is outside this PR; I've filed a ticket for it."
EDITED = {"ticket_project": "WEB", "ticket_title": "Share one model cache",
          "ticket_body": "Every export builds its own cache."}
FILED_URL = "https://example.atlassian.net/browse/WEB-12"


def _a_ticket_proposed(settings, **built) -> Scene:
    s = scene(settings, **built)
    start_run(s.here, s.threads)
    with s.threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.OUT_OF_SCOPE, "I've proposed a ticket for it.",
                           ticket_project="PROJ", ticket_title="Cache models",
                           ticket_body="Each export reads its model again.")
    return s


def _filings(s: Scene) -> list[FilingTicket]:
    return [started.work for started in s.here.agent_runs.started
            if isinstance(started.work, FilingTicket)]


def _filed(s: Scene, key: str = "WEB-12", url: str = FILED_URL) -> Conversation:
    with s.threads.editing(KEY) as editable:
        filed = editable.not_a_fix(Classification.OUT_OF_SCOPE, "", filed_key=key,
                                   filed_url=url)
    assert not isinstance(filed, Denied), filed
    drain(s.threads)
    return s.stored()


def test_accepting_a_ticket_starts_a_run_that_files_the_ticket_as_edited(settings):
    s = _a_ticket_proposed(settings)

    stored = s.approve(reply=TICKET_REPLY, **EDITED)

    [filing] = _filings(s)
    assert (filing.fix.ticket_project, filing.fix.ticket_title, filing.fix.ticket_body) == (
        "WEB", "Share one model cache", "Every export builds its own cache.")
    assert stored.standing is ConversationState.LANDING
    assert s.answers() == ()
    assert not s.settled()


def test_a_filed_ticket_is_answered_with_the_edited_reply_and_its_link_then_resolved(settings):
    github = AnsweredBeforeResolved()
    s = _a_ticket_proposed(settings, github=github)
    s.approve(reply=TICKET_REPLY, resolve=True, **EDITED)

    stored = _filed(s)

    assert [answer.body for answer in s.answers()] == [f"{TICKET_REPLY}\n\n{FILED_URL}"]
    assert github.answers_at_resolve == 1
    assert stored.github_resolved is True
    assert stored.standing is ConversationState.DONE
    assert (stored.fix.ticket_key, stored.fix.ticket_url) == ("WEB-12", FILED_URL)
    assert (stored.fix.filed, stored.fix.picked, stored.fix.pushed) == (True, False, False)
    assert s.main() == s.base == s.pushed()
    assert s.dropped()
    assert s.settled()


def _filing_reports_failure(s: Scene) -> None:
    with s.threads.editing(KEY) as editable:
        editable.fail("Jira refused the project key")


def _filing_exits_without_a_word(s: Scene) -> None:
    pass


@pytest.mark.parametrize("ends, reason", [
    (_filing_reports_failure, "Jira refused the project key"),
    (_filing_exits_without_a_word, "the filing run ended without reporting a filed ticket"),
])
def test_a_filing_that_files_nothing_keeps_the_ticket_and_posts_nothing(settings, ends, reason):
    s = _a_ticket_proposed(settings)
    s.approve(reply=TICKET_REPLY, resolve=True, **EDITED)
    ends(s)
    drain(s.threads)

    drain(s.threads)

    stored = s.stored()
    assert stored.standing is ConversationState.READY
    assert (stored.fix.file_error or "").startswith(reason)
    assert stored.proposal is not None and stored.proposal.kind == "ticket"
    assert stored.proposal.ticket.title == "Share one model cache"
    approval = stored.latest_approval
    assert (approval.state, approval.reason_code) == (OperationState.REFUSED,
                                                      ReasonCode.FILE_FAILED)
    assert s.answers() == ()
    thread = s.here.github.thread(KEY)
    assert thread is not None and not thread.is_resolved
    assert not s.dropped()


def test_accepting_again_after_a_failed_filing_files_it_again(settings):
    s = _a_ticket_proposed(settings)
    s.approve(reply=TICKET_REPLY, **EDITED)
    drain(s.threads)
    drain(s.threads)

    s.approve(reply="Filed it.", **{**EDITED, "ticket_title": "One model cache"})
    stored = _filed(s)

    assert [filing.fix.ticket_title for filing in _filings(s)] == [
        "Share one model cache", "One model cache"]
    assert [answer.body for answer in s.answers()] == [f"Filed it.\n\n{FILED_URL}"]
    assert stored.standing is ConversationState.DONE


def test_accepting_again_after_the_reply_failed_posts_it_without_filing_a_second_ticket(
        settings):
    github = ReplyRefused()
    s = _a_ticket_proposed(settings, github=github)
    s.approve(reply=TICKET_REPLY, **EDITED)
    failed = _filed(s)
    github.refusing = False

    stored = s.approve(reply=TICKET_REPLY, **EDITED)

    assert failed.fix.reply_error == "gh api exploded"
    assert len(_filings(s)) == 1
    assert [answer.body for answer in s.answers()] == [f"{TICKET_REPLY}\n\n{FILED_URL}"]
    assert stored.standing is ConversationState.DONE


def test_a_filed_ticket_whose_reply_failed_cannot_be_stopped_into_a_second_filing(settings):
    s = _a_ticket_proposed(settings, github=ReplyRefused())
    s.approve(reply=TICKET_REPLY, **EDITED)
    _filed(s)

    with s.threads.editing(KEY) as editable:
        denied = editable.stop()

    assert isinstance(denied, Denied)
    assert "already filed as WEB-12" in denied.reason


def test_accepting_a_ticket_while_claude_is_disabled_is_refused(settings):
    s = _a_ticket_proposed(settings)
    s.threads = s.here.claude(False).threads()

    denied = s.ask(reply=TICKET_REPLY, **EDITED)

    assert isinstance(denied, Denied)
    assert denied.code is ErrorCode.AGENTS_DISABLED
    assert _filings(s) == []


@pytest.mark.parametrize("edited", [
    {"reply": "  ", **EDITED},
    {"reply": TICKET_REPLY, **EDITED, "ticket_title": " "},
])
def test_accepting_a_ticket_with_an_empty_part_is_refused(settings, edited):
    s = _a_ticket_proposed(settings)

    denied = s.ask(**edited)

    assert isinstance(denied, Denied)
    assert denied.code is ErrorCode.EMPTY_BODY
    assert s.stored().fix.is_proposed


def test_a_reply_github_refuses_keeps_the_proposal_to_accept_again(settings):
    github = ReplyRefused()
    s = _a_reply_proposed(settings, github=github)
    s.approve(reply=WORDS)
    github.refusing = False

    stored = s.approve(reply=WORDS)

    assert [answer.body for answer in s.answers()] == [WORDS]
    assert stored.standing is ConversationState.DONE


def test_an_approve_waits_while_a_claude_run_is_alive(settings):
    s = proposed(settings)
    _run_alive(s.here)

    stored = s.approve()

    assert stored.fix.is_proposed
    assert not stored.fix.picked
    assert s.main() == s.base
    assert not s.settled()


def test_an_approve_waits_while_the_pr_worktree_is_dirty(settings):
    s = proposed(settings)
    s.here.working_copies.edit(WORKTREE, "README", "changed")

    stored = s.approve()

    assert stored.fix.is_proposed
    assert not stored.fix.picked
    assert s.main() == s.base
    assert not s.settled()


def test_a_pushed_commit_is_answered_without_being_pushed_again(settings):
    github = ReplyRefused()
    copies = FakeWorkingCopies(github)
    s = proposed(settings, github=github, copies=copies)
    landed = s.approve().fix.landed_sha
    github.refusing = False

    stored = s.approve()

    assert copies.pushes == 1
    assert s.pushed() == landed
    [answer] = s.answers()
    assert f"/commit/{landed}" in answer.body
    assert stored.standing is ConversationState.DONE
    assert stored.fix.reply_error is None


def test_a_push_that_fails_keeps_the_commit_local_and_answers_nobody(settings):
    copies = push_refused()
    s = proposed(settings, github=copies.github, copies=copies)

    stored = s.approve()

    assert stored.fix.push_error == "failed to push some refs"
    assert (stored.fix.picked, stored.fix.pushed, stored.fix.answered) == (True, False, False)
    assert stored.standing is ConversationState.READY
    assert stored.fix.landed_sha == s.main()
    assert s.pushed() == s.base
    assert s.answers() == ()
    assert s.settled()


def test_a_push_that_fails_hands_your_own_words_back_rather_than_losing_them(settings):
    copies = push_refused()
    s = proposed(settings, github=copies.github, copies=copies)

    assert s.approve(reply=WORDS).fix.pending_reply == WORDS


def test_a_refused_reply_hands_your_own_words_back(settings):
    s = proposed(settings, github=ReplyRefused())

    assert s.approve(reply=WORDS).fix.pending_reply == WORDS


def test_a_landed_approve_has_no_words_left_waiting_to_be_said(settings):
    s = proposed(settings)

    stored = s.approve(reply=WORDS)

    assert stored.approved_reply == WORDS
    assert stored.fix.pending_reply == ""


def test_an_approve_whose_reply_github_refuses_asks_to_be_retried(settings):
    s = proposed(settings, github=ReplyRefused())

    stored = s.approve()

    assert stored.fix.reply_error == "gh api exploded"
    assert (stored.fix.picked, stored.fix.pushed, stored.fix.answered) == (True, True, False)
    assert s.pushed() == stored.fix.landed_sha
    assert not s.dropped()
    assert s.settled()


def test_an_approve_with_a_message_of_its_own_lands_with_it(settings):
    s = proposed(settings)

    stored = s.approve(message="Rename the helper everywhere")

    assert stored.standing is ConversationState.DONE
    assert s.here.working_copies.commits[str(s.main())].message == "Rename the helper everywhere"


def test_an_approve_with_no_message_lands_with_the_agents(settings):
    s = proposed(settings)

    s.approve()

    assert s.here.working_copies.commits[str(s.main())].message == MESSAGE


def test_a_ticked_approve_resolves_the_thread_once_the_comment_is_answered(settings):
    github = AnsweredBeforeResolved()
    s = proposed(settings, github=github)

    stored = s.approve(resolve=True)

    assert github.answers_at_resolve == 1
    thread = github.thread(KEY)
    assert thread is not None and thread.is_resolved
    assert stored.standing is ConversationState.DONE
    assert stored.github_resolved is True
    assert (stored.fix.picked, stored.fix.pushed, stored.fix.answered) == (True, True, True)
    assert s.dropped()


def test_a_resolved_landing_is_stamped_with_the_clock_the_board_runs_on(settings):
    s = proposed(settings, clock=at("2026-09-07T12:00:00Z"))

    assert s.approve(resolve=True).state_changed_at == "2026-09-07T12:00:00Z"


def test_an_unticked_approve_leaves_the_thread_open(settings):
    s = proposed(settings)

    stored = s.approve()

    thread = s.here.github.thread(KEY)
    assert thread is not None and not thread.is_resolved
    assert stored.github_resolved is not True


def test_a_resolve_github_refuses_keeps_the_landing_open_to_be_retried(settings):
    s = proposed(settings, github=ResolveForbidden())

    stored = s.approve(resolve=True)

    assert stored.standing is ConversationState.READY
    assert (stored.fix.picked, stored.fix.pushed, stored.fix.answered) == (True, True, True)
    assert stored.fix.reply_error == "resolve failed: gh: Forbidden (HTTP 403)"
    assert not s.dropped()
    assert s.settled()


def test_approving_again_after_a_failed_resolve_only_resolves(settings):
    github = ResolveForbidden()
    s = proposed(settings, github=github)
    s.approve(resolve=True)
    github.refusing = False

    stored = s.approve()

    assert len(s.answers()) == 1
    thread = s.here.github.thread(KEY)
    assert thread is not None and thread.is_resolved
    assert stored.github_resolved is True
    assert stored.standing is ConversationState.DONE


def test_a_ticked_approve_on_a_comment_with_no_thread_is_refused(settings):
    s = proposed(settings, key=ISSUE_KEY, kind=CommentKind.ISSUE)

    denied = s.ask(resolve=True)

    assert s.main() == s.base
    assert isinstance(denied, Denied)
    assert denied.reason == "only a review thread can be marked resolved"


def test_a_ticked_approve_that_also_deletes_the_comment_is_refused(settings):
    s = proposed(settings)

    denied = s.ask(delete_comment=True, resolve=True)

    assert s.main() == s.base
    assert isinstance(denied, Denied)
    assert denied.reason == "a deleted comment leaves no thread to mark resolved"


def _conflicted(settings, **built) -> tuple[Scene, Sha]:
    s = proposed(settings, **built)
    head = Sha(s.here.working_copies.commit(WORKTREE, {"f": "theirs\n"}, "someone else"))
    return s, head


def test_a_conflicted_pick_queues_a_rebase_and_keeps_the_approve_waiting(settings):
    s, head = _conflicted(settings)

    stored = s.approve()

    assert stored.standing is ConversationState.LANDING
    assert stored.fix.run.kind == OperationKind.REBASE
    assert stored.fix.run.onto == head
    assert "Merge conflict in f" in (stored.fix.run.conflict or "")
    assert stored.fix.base_sha == head
    assert stored.fix.thread_sha is None
    assert [started.work.onto for started in s.here.agent_runs.started
            if isinstance(started.work, RebasingFix)] == [str(head)]
    assert not s.settled()


def test_a_failed_rebase_run_drops_the_approve_and_keeps_the_failure(settings):
    s, head = _conflicted(settings)
    s.approve()
    for _ in range(s.stored().run_holder.attempts_allowed + 1):
        drain(s.threads)

    stored = s.stored()
    assert stored.fix.has_failed
    assert stored.fix.reason == "run exited without rebasing"
    assert stored.fix.run.onto == head
    assert s.settled()


def test_a_ticked_approve_deletes_the_comment_instead_of_answering_it(settings):
    s = proposed(settings, author=ME)

    stored = s.approve(delete_comment=True)

    assert s.here.github.thread(KEY) is None
    assert stored.comment_deleted is True
    assert stored.deleted_by_board is True
    assert stored.standing is ConversationState.DONE
    assert s.settled()


def test_nothing_is_deleted_until_the_commit_is_pushed(settings):
    copies = push_refused()
    s = proposed(settings, github=copies.github, copies=copies, author=ME)

    stored = s.approve(delete_comment=True)

    assert s.here.github.thread(KEY) is not None
    assert stored.fix.push_error == "failed to push some refs"
    assert stored.comment_deleted is False


def test_a_retried_landing_that_asks_to_delete_someone_elses_comment_is_refused(settings):
    copies = push_refused()
    s = proposed(settings, github=copies.github, copies=copies)
    s.approve()

    denied = s.ask(delete_comment=True)

    assert denied == Denied(ErrorCode.NOT_DELETABLE,
                            "reviewer wrote that comment, so it is not yours to delete")


def test_a_delete_github_refuses_leaves_the_card_asking_to_be_retried(settings):
    s = proposed(settings, github=DeleteForbidden(), author=ME)

    stored = s.approve(delete_comment=True)

    assert (stored.fix.picked, stored.fix.pushed, stored.fix.answered) == (True, True, False)
    assert stored.fix.reply_error == "gh: Forbidden (HTTP 403)"
    assert stored.comment_deleted is False
    assert s.settled()


@pytest.mark.parametrize("blocker", ["run_alive", "dirty"])
def test_neither_a_live_run_nor_a_dirty_tree_blocks_a_push_that_is_owed(settings, blocker):
    copies = push_refused()
    s = proposed(settings, github=copies.github, copies=copies)
    landed = s.approve().fix.landed_sha
    copies.refuse_pushes(None)
    if blocker == "run_alive":
        _run_alive(s.here)
    else:
        s.here.working_copies.edit(WORKTREE, "README", "changed")

    stored = s.approve()

    assert s.pushed() == landed
    assert stored.standing is ConversationState.DONE


def test_the_landed_commit_is_on_the_record_before_the_push_is_tried(settings):
    s = proposed(settings, copies=push_blows_up())

    stored = s.approve()

    assert stored.standing is ConversationState.LANDING
    assert (stored.fix.picked, stored.fix.pushed) == (True, False)
    assert stored.fix.landed_sha == s.main()
    assert not s.settled()


def test_an_approve_says_nothing_when_github_has_already_lost_the_comment(settings):
    s = proposed(settings)
    s.here.github.delete_comment(THE_PR, CommentKind.REVIEW, COMMENT_ID)
    lost(s.threads, KEY)
    assert s.stored().comment_deleted

    stored = s.approve()

    assert s.answers() == ()
    assert (stored.fix.picked, stored.fix.pushed, stored.fix.answered) == (True, True, True)
    assert s.pushed() == stored.fix.landed_sha
    assert stored.fix.reply_note == "no reply: the comment was deleted"
    assert stored.deleted_by_board is False


def test_a_ticked_approve_on_a_card_that_has_landed_is_refused(settings):
    s = proposed(settings)
    landed = s.approve().fix.landed_sha

    denied = s.ask(delete_comment=True)

    assert isinstance(denied, Denied)
    assert s.here.github.thread(KEY) is not None
    assert s.main() == landed
    assert s.stored().comment_deleted is False


def test_a_new_run_after_a_failed_landing_picks_before_anything_is_dropped(settings):
    copies = push_refused()
    s = proposed(settings, github=copies.github, copies=copies)
    s.approve()
    copies.refuse_pushes(None)
    with s.threads.editing(KEY) as editable:
        editable.stop()
    drain(s.threads)
    _replied(s.here.github, KEY, said(202, "that is not quite it"))
    hear(s.threads)
    s.propose(files={"f": "newest\n"})

    stored = s.approve()

    assert stored.standing is ConversationState.DONE
    assert stored.fix.landed_sha == s.main() == s.pushed()
    assert s.tree(s.main())["f"] == "newest\n"
    [answer] = [one for one in s.answers() if one.id != 202]
    assert f"/commit/{stored.fix.landed_sha}" in answer.body
    assert s.dropped()


@dataclass
class HeldPick:
    copies: FakeWorkingCopies
    picking: threading.Event
    release: threading.Event

    def held(self) -> None:
        self.picking.set()
        assert self.release.wait(WAIT)


def held_pick(github: FakeGitHub) -> HeldPick:
    held = HeldPick(FakeWorkingCopies(github), threading.Event(), threading.Event())
    held.copies.on_pick = held.held
    return held


def test_the_conversation_stays_locked_while_its_effects_run(settings, tmp_path: Path):
    github = FakeGitHub()
    held = held_pick(github)
    copies = held.copies
    s = proposed(settings, github=github, copies=copies,
                 thread_records=disk_thread_records(tmp_path / "threads"))
    assert not isinstance(s.ask(), Denied)
    entered = threading.Event()

    def other_writer() -> None:
        with s.threads.editing(KEY) as editable:
            editable.mark_seen()
        entered.set()

    deciding = threading.Thread(target=drain, args=(s.threads,), daemon=True)
    deciding.start()
    assert held.picking.wait(WAIT)
    writer = threading.Thread(target=other_writer, daemon=True)
    writer.start()

    assert not entered.wait(0.05)
    held.release.set()
    deciding.join(WAIT)
    assert entered.wait(WAIT)
    landed = s.stored()
    assert landed.standing is ConversationState.DONE
    assert landed.seen_at is not None
