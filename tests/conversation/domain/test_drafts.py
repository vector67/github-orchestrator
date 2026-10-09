from github_orchestrator.conversation import (
    ConversationState,
    Denied,
    ErrorCode,
    OperationKind,
    OperationState,
    ReasonCode,
    Verdict,
)
from github_orchestrator.domain import Location, Side
from github_orchestrator.github import PullRequestState
from github_orchestrator.github.fake import FakeGitHub, GhError
from tests.builders import a_pr
from tests.conversation.support import PR, REPO, at, diff_over, drain, world

THE_PR = a_pr(PR, REPO)

NOW = "2026-09-23T10:00:00Z"

HEAD = "c0ffee0000000000000000000000000000000000"

BODY = "this name hides what it does"

FILE = "billing/invoice_writer.py"

HERE = Location(path=FILE, line=12, side=Side.AFTER)

THERE = Location(path=FILE, line=40, start_line=38, start_side=Side.BEFORE, side=Side.BEFORE)


class _RejectingGitHub(FakeGitHub):
    def post_review_comment(self, pr, head, location, body):
        raise GhError("HTTP 422: line not in the diff")


class Reviewing:
    def __init__(self, settings, github=None):
        github = github or FakeGitHub()
        github.add_pr(THE_PR)
        self.here = world(settings, github=github, clock=at(NOW))
        diff_over(self.here, FILE)
        self.threads = self.here.conversation_managers.of(THE_PR)

    def draft(self):
        return self.threads.open_draft(BODY, HERE, "op_created")

    def did(self, verb, key, *args):
        with self.threads.editing(key) as conversation:
            done = getattr(conversation, verb)(*args)
        assert not isinstance(done, Denied), done
        drain(self.threads)
        return self.threads.get(key)

    def on_github(self):
        return self.here.github.prs[THE_PR].threads


def test_a_new_draft_is_a_draft_with_nothing_on_github(settings):
    reviewing = Reviewing(settings)

    drafted = reviewing.draft()

    assert drafted.key.startswith("draft_")
    assert reviewing.threads.get(drafted.key) == drafted
    assert drafted.standing is ConversationState.DRAFT
    assert drafted.comment_type == "draft"
    assert drafted.github_node_id is None
    assert [(one.author, one.body) for one in drafted.comments] == [("octocat", BODY)]
    assert (drafted.path, drafted.line, drafted.start_line, drafted.side) == (
        FILE, 12, None, Side.AFTER)
    created = drafted.operations[-1]
    assert (created.id, created.kind, created.state, created.anchor) == (
        "op_created", OperationKind.CREATE_DRAFT, OperationState.APPLIED, HERE)
    assert reviewing.on_github() == []


def test_the_counts_hold_each_draft_the_reviewer_has_not_sent(settings):
    reviewing = Reviewing(settings)
    reviewing.draft()
    reviewing.threads.open_draft("and this one", THERE, "op_other")

    assert reviewing.threads.counts().drafts == 2


def test_an_edit_replaces_the_body_and_the_anchor_together(settings):
    reviewing = Reviewing(settings)
    key = reviewing.draft().key

    edited = reviewing.did("edit", key, "call it write_iso", THERE)

    assert edited.body == "call it write_iso"
    assert edited.comments[0].body == "call it write_iso"
    assert (edited.path, edited.line, edited.start_line, edited.side) == (
        FILE, 40, 38, Side.BEFORE)
    assert edited.standing is ConversationState.DRAFT


def test_consecutive_edits_collapse_into_one_operation(settings):
    reviewing = Reviewing(settings)
    key = reviewing.draft().key

    reviewing.did("edit", key, "first", HERE)
    twice = reviewing.did("edit", key, "second", THERE)

    assert [operation.kind for operation in twice.operations] == [
        OperationKind.CREATE_DRAFT, OperationKind.EDIT_DRAFT]
    edit = twice.operations[-1]
    assert (edit.text, edit.anchor) == ("second", THERE)


def test_an_edit_after_something_else_starts_a_new_entry(settings):
    reviewing = Reviewing(settings)
    key = reviewing.draft().key

    reviewing.did("edit", key, "first", HERE)
    reviewing.did("enrol", key)
    reviewing.did("withdraw", key)
    again = reviewing.did("edit", key, "second", HERE)

    assert [operation.kind for operation in again.operations] == [
        OperationKind.CREATE_DRAFT, OperationKind.EDIT_DRAFT, OperationKind.ENROL,
        OperationKind.WITHDRAW_FROM_REVIEW, OperationKind.EDIT_DRAFT]


def test_enrolling_and_withdrawing_move_the_draft_in_and_out_of_the_review(settings):
    reviewing = Reviewing(settings)
    key = reviewing.draft().key

    enrolled = reviewing.did("enrol", key)
    withdrawn = reviewing.did("withdraw", key)

    assert enrolled.standing is ConversationState.ENROLLED
    assert withdrawn.standing is ConversationState.DRAFT


def test_an_enrolled_draft_is_edited_in_place_and_stays_in_the_review(settings):
    reviewing = Reviewing(settings)
    key = reviewing.draft().key
    reviewing.did("enrol", key)

    edited = reviewing.did("edit", key, "call it write_iso", THERE)

    assert edited.body == "call it write_iso"
    assert (edited.path, edited.line, edited.start_line, edited.start_side, edited.side) == (
        FILE, 40, 38, Side.BEFORE, Side.BEFORE)
    assert edited.standing is ConversationState.ENROLLED


def test_an_enrolled_draft_moved_off_the_diff_is_refused_and_kept_as_it_was(settings):
    reviewing = Reviewing(settings)
    key = reviewing.draft().key
    reviewing.did("enrol", key)

    with reviewing.threads.editing(key) as editable:
        refused = editable.edit("no", Location(path="README", line=1,
                                side=Side.AFTER))
    drain(reviewing.threads)

    assert isinstance(refused, Denied)
    assert refused.code == ErrorCode.ANCHOR_NOT_IN_DIFF
    kept = reviewing.threads.get(key)
    assert (kept.body, kept.path, kept.line) == (BODY, FILE, 12)
    assert kept.standing is ConversationState.ENROLLED


def test_an_enrolled_draft_in_a_review_on_its_way_to_github_is_not_edited(settings):
    reviewing = Reviewing(settings)
    key = reviewing.draft().key
    reviewing.did("enrol", key)
    reviewing.threads.send_review(Verdict.COMMENT, "a few notes")

    with reviewing.threads.editing(key) as editable:
        refused = editable.edit("too late", HERE)

    assert isinstance(refused, Denied)
    assert refused.code == ErrorCode.REVIEW_IN_FLIGHT


def test_an_enrolled_draft_whose_anchor_stays_put_is_not_checked_again(settings):
    reviewing = Reviewing(settings)
    key = reviewing.draft().key
    reviewing.did("enrol", key)
    reviewing.here.polled(head_sha=HEAD, base_branch="main", is_author=False)

    with reviewing.threads.editing(key) as editable:
        moved = editable.edit("no", THERE)
    edited = reviewing.did("edit", key, "only the words", HERE)

    assert isinstance(moved, Denied)
    assert moved.code == ErrorCode.GIT_FAILED
    assert edited.body == "only the words"
    assert edited.standing is ConversationState.ENROLLED


def test_a_discarded_draft_is_done_and_unpark_brings_it_back(settings):
    reviewing = Reviewing(settings)
    key = reviewing.draft().key

    discarded = reviewing.did("discard", key)
    with reviewing.threads.editing(key) as editable:
        assert not isinstance(editable.unpark(), Denied)
    drain(reviewing.threads)
    back = reviewing.threads.get(key)

    assert discarded.standing is ConversationState.DONE
    assert back.standing is ConversationState.DRAFT
    assert back.body == BODY


def test_a_posted_draft_is_a_review_thread_under_the_same_key(settings):
    reviewing = Reviewing(settings)
    key = reviewing.draft().key

    thread = reviewing.did("post_now", key)

    [posted] = reviewing.on_github()
    [comment] = posted.comments
    assert comment.body == BODY
    assert (posted.path, posted.line) == (FILE, 12)
    assert thread.key == key
    assert thread.github_node_id == posted.key
    assert thread.comment_type == "review"
    assert thread.comment_id == comment.id
    assert [one.id for one in thread.comments] == [comment.id]
    assert thread.standing is ConversationState.WAITING
    operation = thread.operations[-1]
    assert (operation.kind, operation.state, operation.posted_comment) == (
        OperationKind.POST_NOW, OperationState.APPLIED, comment.id)


def test_the_posted_comment_is_the_boards_own_so_the_poller_passes_it_over(settings):
    reviewing = Reviewing(settings)
    key = reviewing.draft().key

    posted = reviewing.did("post_now", key)
    polled = reviewing.threads.poll(PullRequestState())

    assert posted.panel_reply_ids == (posted.comment_id,)
    assert polled.activity is None or not polled.activity.threads


def test_a_post_github_refused_leaves_the_draft_and_says_why(settings):
    reviewing = Reviewing(settings, _RejectingGitHub())
    key = reviewing.draft().key

    refused = reviewing.did("post_now", key)

    assert refused.standing is ConversationState.DRAFT
    operation = refused.operations[-1]
    assert (operation.kind, operation.state, operation.reason_code) == (
        OperationKind.POST_NOW, OperationState.REFUSED, ReasonCode.GITHUB_REJECTED)
    assert "line not in the diff" in (operation.reason or "")
    assert reviewing.on_github() == []


def test_a_posted_draft_has_a_fix_written_when_asked(settings):
    reviewing = Reviewing(settings)
    key = reviewing.draft().key
    reviewing.did("post_now", key)

    asked = reviewing.did("fix", key)

    assert asked.standing in (ConversationState.QUEUED, ConversationState.WORKING)
    operation = asked.operations[-1]
    assert (operation.kind, operation.state) in (
        (OperationKind.FIRST, OperationState.PENDING),
        (OperationKind.FIRST, OperationState.RUNNING))


def test_a_fix_is_not_asked_for_twice(settings):
    reviewing = Reviewing(settings)
    key = reviewing.draft().key
    reviewing.did("post_now", key)
    reviewing.did("fix", key)

    with reviewing.threads.editing(key) as editable:
        refused = editable.fix()

    assert isinstance(refused, Denied)
    assert refused.code == ErrorCode.OPERATION_OUTSTANDING


def test_a_draft_verb_on_a_github_thread_is_not_a_draft(settings):
    reviewing = Reviewing(settings)
    key = reviewing.draft().key
    reviewing.did("post_now", key)

    with reviewing.threads.editing(key) as editable:
        refused = editable.enrol()
    drain(reviewing.threads)

    assert refused.code == ErrorCode.NOT_A_DRAFT
    assert reviewing.threads.get(key).standing is ConversationState.WAITING


def test_a_draft_a_review_posted_is_a_review_thread_that_says_which_review(settings):
    reviewing = Reviewing(settings)
    key = reviewing.draft().key
    reviewing.did("enrol", key)

    sent = reviewing.threads.send_review(Verdict.COMMENT, "a few notes")
    drain(reviewing.threads)

    assert not isinstance(sent, Denied), sent
    posted = reviewing.threads.get(key)
    [thread] = [one for one in reviewing.on_github() if one.key.startswith("PRRT_")]
    [comment] = thread.comments
    assert comment.body == BODY
    assert (posted.key, posted.github_node_id, posted.comment_type) == (
        key, thread.key, "review")
    assert posted.standing is ConversationState.WAITING
    assert posted.panel_reply_ids == (comment.id,)
    operation = posted.operations[-1]
    assert (operation.kind, operation.state, operation.review,
            operation.posted_comment, operation.github_node_id,
            operation.settled_at) == (
        OperationKind.POSTED, OperationState.APPLIED, sent.id, comment.id, thread.key, NOW)


def test_only_an_enrolled_draft_is_posted_by_a_review(settings):
    reviewing = Reviewing(settings)
    enrolled = reviewing.draft().key
    reviewing.did("enrol", enrolled)
    kept = reviewing.threads.open_draft("and this one", THERE, "op_other").key

    reviewing.threads.send_review(Verdict.COMMENT, "a few notes")
    drain(reviewing.threads)

    posted = [comment.body for thread in reviewing.on_github()
              if thread.key.startswith("PRRT_") for comment in thread.comments]
    assert posted == [BODY]
    assert reviewing.threads.get(kept).standing is ConversationState.DRAFT


def test_a_draft_on_a_pr_with_no_worktree_is_not_enrolled_and_says_why(settings):
    github = FakeGitHub()
    github.add_pr(THE_PR)
    here = world(settings, github=github, clock=at(NOW))
    here.polled(head_sha=HEAD, is_author=False)
    threads = here.conversation_managers.of(THE_PR)
    draft = threads.open_draft(BODY, HERE, "op_created")

    with threads.editing(draft.key) as editable:
        refused = editable.enrol()

    assert isinstance(refused, Denied)
    assert refused.code == ErrorCode.GIT_FAILED
    assert "worktree is not known" in refused.reason
