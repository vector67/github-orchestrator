import json
from dataclasses import replace

import pytest

from github_orchestrator.conversation import (
    Classification,
    ConversationState,
    OperationKind,
    ReviewState,
    Verdict,
)
from github_orchestrator.domain import Location, Sha, Side
from github_orchestrator.settings.fake import fake_settings
from tests.conversation.support import (
    THE_PR,
    WORKTREE,
    World,
    at,
    diff_over,
    drain,
    first_poll,
    hear,
    on_github,
    propose,
    repo_at,
    said,
    start_run,
    world,
)
from tests.disk_layout import thread_file
from tests.thread_records.support import disk_thread_records

NOW = "2026-09-26T10:00:00Z"
KEY = "PRRT_kwDO"


@pytest.fixture
def here(tmp_path) -> World:
    settings = fake_settings(tmp_path / "data")
    built = world(settings, thread_records=disk_thread_records(settings.threads_dir),
                  clock=at(NOW))
    repo_at(built.working_copies, WORKTREE, {"f": "old\n", "README": "hello"})
    return built


def _path(here: World, key: str = KEY):
    return thread_file(here.settings.threads_dir, THE_PR, key)


def _on_disk(here: World, key: str = KEY) -> dict:
    return json.loads(_path(here, key).read_text())


def _left(here: World, document, key: str = KEY) -> None:
    path = _path(here, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document if isinstance(document, str) else json.dumps(document))


def _read(here: World, document: dict):
    _left(here, document, document["thread_key"])
    return here.threads().get(document["thread_key"])


def _heard(here: World, *, author_name: str = ""):
    threads = here.threads()
    on_github(here.github, KEY, said(101, "please rename this", author_name=author_name))
    hear(threads)
    return threads


def _proposed_document(here: World) -> dict:
    threads = _heard(here, author_name="Mona Lisa Octocat")
    propose(here, threads, KEY)
    return _on_disk(here)


FIX_QUESTIONS = ("is_proposed", "is_declined", "has_failed", "picked", "pushed", "answered")


def _truths(conversation) -> set[str]:
    truths = {name for name in FIX_QUESTIONS if getattr(conversation.fix, name)}
    return truths | ({"is_removed"} if conversation.is_removed else set())


def _legacy(**fields):
    return {"thread_key": KEY, **fields}


@pytest.mark.parametrize("legacy,standing,truths", [
    ({"status": "queued"}, ConversationState.QUEUED, set()),
    ({"status": "working"}, ConversationState.WORKING, set()),
    ({"status": "ready"}, ConversationState.READY, {"is_proposed"}),
    ({"status": "skipped"}, ConversationState.READY, {"is_declined"}),
    ({"status": "failed"}, ConversationState.READY, {"has_failed"}),
    ({"status": "rejected"}, ConversationState.IN_SESSION, set()),
    ({"status": "committed"}, ConversationState.LANDING, {"picked"}),
    ({"status": "approved"}, ConversationState.LANDING, {"picked"}),
    ({"status": "approved", "pushed": True, "reply_error": "HTTP 404"},
     ConversationState.READY, {"picked", "pushed"}),
    ({"status": "approved", "pushed": True},
     ConversationState.DONE, {"picked", "pushed"}),
    ({"status": "approved", "pushed": True, "replied": True},
     ConversationState.DONE, {"picked", "pushed", "answered"}),
    ({"status": "dismissed"}, ConversationState.DONE, set()),
    ({"status": "removed"}, ConversationState.READY, {"is_removed"}),
    ({}, ConversationState.QUEUED, set()),
])
def test_a_record_written_before_the_port_reads_by_its_status(here, legacy, standing, truths):
    conversation = _read(here, _legacy(**legacy))

    assert conversation.standing is standing
    assert _truths(conversation) == truths


@pytest.mark.parametrize("legacy,standing,truths", [
    ({"status": "committed", "pushed": True}, ConversationState.LANDING, {"picked"}),
    ({"status": "dismissed", "pushed": True}, ConversationState.DONE, {"pushed"}),
    ({"status": "dismissed", "pushed": True, "replied": True},
     ConversationState.DONE, {"pushed", "answered"}),
    ({"status": "removed", "pushed": True, "replied": True},
     ConversationState.READY, {"is_removed", "pushed", "answered"}),
])
def test_a_record_written_before_the_port_keeps_what_it_already_did(
    here, legacy, standing, truths,
):
    conversation = _read(here, _legacy(**legacy))

    assert conversation.standing is standing
    assert _truths(conversation) == truths


def test_a_legacy_declined_dismissal_is_a_resolved_conversation_that_replied(here):
    conversation = _read(here, _legacy(status="dismissed", declined=True,
                                       declined_reply="Not needed: see #12.",
                                       declined_reply_id=51))

    assert conversation.standing is ConversationState.DONE
    assert conversation.closing_reply == "Not needed: see #12."
    assert conversation.closing_reply_id == 51


def test_a_legacy_dismissal_that_carried_both_replies_keeps_the_neutral_one(here):
    conversation = _read(here, _legacy(status="dismissed", declined=True,
                                       closing_reply="Tried it. Reverted.",
                                       closing_reply_id=60,
                                       declined_reply="Not needed: see #12.",
                                       declined_reply_id=51))

    assert conversation.closing_reply == "Tried it. Reverted."
    assert conversation.closing_reply_id == 60


def _v1(status, conversation_state="open", fix_state="queued", steps=(), **fields):
    document = {"version": 1, "thread_key": KEY, "status": status,
                "conversation_state": conversation_state,
                "fix_state": fix_state, "fix_steps": sorted(steps)}
    document.update(fields)
    return document


def _moved_by_old_code(new_status, **fields):
    return _v1(new_status, fix_state="running", attempts=1, **fields)


def test_a_v1_record_an_older_checkout_moved_reads_by_the_status_it_wrote(here):
    conversation = _read(here, _moved_by_old_code("ready", thread_sha="a" * 40,
                                                  tests="passed"))

    assert conversation.fix.is_proposed
    assert conversation.fix.thread_sha == Sha("a" * 40)


@pytest.mark.parametrize("status,truth", [
    ("skipped", "is_declined"),
    ("failed", "has_failed"),
])
def test_every_report_an_older_checkout_writes_is_honoured(here, status, truth):
    conversation = _read(here, _moved_by_old_code(status, reason="too risky"))

    assert _truths(conversation) == {truth}


def test_a_v1_record_whose_status_agrees_still_reads_by_its_states(here):
    conversation = _read(here, _v1("ready", fix_state="proposed", thread_sha="a" * 40))

    assert conversation.standing is ConversationState.READY
    assert _truths(conversation) == {"is_proposed"}
    assert conversation.fix.thread_sha == Sha("a" * 40)
    assert conversation.github_node_id == KEY


@pytest.mark.parametrize("word,standing,truths", [
    ("dismissed", ConversationState.DONE, {"is_proposed"}),
    ("removed", ConversationState.READY, {"is_proposed", "is_removed"}),
])
def test_a_v1_conversation_word_reads_as_the_state_that_carries_it_now(
    here, word, standing, truths,
):
    conversation = _read(here, _v1(word, conversation_state=word, fix_state="proposed",
                                   thread_sha="a" * 40))

    assert conversation.standing is standing
    assert _truths(conversation) == truths


def _v1_landing(steps, **fields):
    return _v1("approved" if "push" in steps else "committed",
               fix_state="landing", steps=steps, attempts=1, base_sha="ba5e0001",
               thread_sha="f1c50001", landed_base="ba5e0002", landed_sha="1a4d0001",
               pushed="push" in steps, replied="answer" in steps, **fields)


def test_a_reply_an_older_checkout_posted_is_never_posted_a_second_time(here):
    conversation = _read(here, dict(_v1_landing(("pick", "push")), replied=True))

    assert conversation.fix.answered


def test_a_v1_record_an_old_conversation_word_settled_keeps_its_fix(here):
    conversation = _read(here, dict(_v1_landing(("pick",)), status="removed",
                                    comment_deleted=True))

    assert _truths(conversation) == {"is_removed", "picked"}
    assert conversation.fix.landed_sha == Sha("1a4d0001")


@pytest.mark.parametrize("status", ["landed", 3])
def test_a_v1_record_whose_status_is_no_word_of_ours_is_unreadable(here, status):
    conversation = _read(here, dict(_v1_landing(("pick", "push", "answer")), status=status))

    assert conversation.is_unreadable


SPELLED_OUT_LISTS = {
    "comments-an-empty-mapping": {"comments": {}},
}


@pytest.mark.parametrize("shape", sorted(SPELLED_OUT_LISTS))
def test_a_list_a_document_spelled_out_is_unreadable_rather_than_iterated(here, shape):
    conversation = _read(here, dict(_v1_landing(("pick",)), **SPELLED_OUT_LISTS[shape]))

    assert conversation.is_unreadable


@pytest.mark.parametrize("status", ["dismissed"])
@pytest.mark.parametrize("fields,truths", [
    ({"thread_sha": "f1c50001"}, {"is_proposed"}),
    ({"classification": "risky"}, {"is_declined"}),
    ({"attempts": 3}, {"has_failed"}),
    ({}, set()),
])
def test_a_settled_record_keeps_the_fix_its_other_fields_imply(here, status, fields, truths):
    conversation = _read(here, _legacy(status=status, **fields))

    assert _truths(conversation) - {"is_removed"} == truths


@pytest.mark.parametrize("status", ["queued"])
def test_a_record_waiting_on_a_head_reads_as_a_rebase_run(here, status):
    conversation = _read(here, _legacy(status=status, rebase_onto="4ead0001",
                                       rebase_conflict="both modified: a.py"))

    assert conversation.fix.run.is_rebase
    assert conversation.fix.run.onto == Sha("4ead0001")
    assert conversation.fix.run.conflict == "both modified: a.py"


def test_a_record_with_no_head_to_rebase_onto_reads_as_a_first_run(here):
    conversation = _read(here, _legacy(status="queued"))

    assert not conversation.fix.run.is_rebase


def test_a_record_written_before_the_port_reads_back_the_same_once_saved(here):
    legacy = _legacy(
        status="approved",
        comment_id=42,
        comment_type="review",
        author="octocat",
        path="src/app.py",
        line=12,
        body="please rename this",
        comments=[{"id": 42, "author": "octocat", "body": "please rename this",
                   "created_at": "2026-01-01T00:00:00Z",
                   "updated_at": "2026-01-01T00:00:01Z"}],
        comment_created_at="2026-01-01T00:00:00Z",
        created_at="2026-01-01T00:00:00.000000Z",
        summary="rename the thing",
        is_outdated=True,
        original_line=9,
        original_commit="cafe1",
        comment_deleted=True,
        deleted_by_board=True,
        declined=True,
        closing_reply="not this time",
        closing_reply_id=51,
        declined_reply="it reads fine as it is",
        declined_reply_id=50,
        approved_reply="landed it",
        approved_reply_id=52,
        panel_reply_ids=[53, 54],
        posted_comment_keys=["IC_kwDO"],
        worktree="/wt/5/PRRT_kwDO",
        branch="orchestrator/thread/5/PRRT_kwDO",
        base_sha="ba5e0001",
        attempts=2,
        started_at="2026-01-03T00:00:00Z",
        thread_sha="f1c50001",
        tests="passed",
        tests_note="12 passed",
        agent_note="renamed the thing",
        classification="risky",
        reason="it conflicted",
        rebase_onto="4ead0001",
        rebase_conflict="both modified: a.py",
        landed_base="ba5e0002",
        landed_sha="1a4d0001",
        pushed=True,
        push_error="fatal: no upstream",
        replied=True,
        reply_note="no reply: the comment was deleted",
        reply_error=None,
        decision_error="retry on a ready card",
    )
    _left(here, legacy)

    threads = here.threads()
    before = threads.get(KEY)

    with threads.editing(KEY) as editable:
        editable.mark_seen()

    after = threads.get(KEY)
    assert replace(after, seen_at=None) == replace(before, seen_at=None)
    assert after.fix.commits == (Sha("ba5e0002"), Sha("1a4d0001"))
    assert after.closing_reply == "not this time"
    assert after.panel_reply_ids == (53, 54)


def test_a_review_state_written_in_githubs_words_reads_as_the_same_state(here):
    document = _proposed_document(here)
    document["review_state"] = "CHANGES_REQUESTED"
    document["comments"][0]["review_state"] = "COMMENTED"

    conversation = _read(here, document)

    assert conversation.review_state is ReviewState.CHANGES_REQUESTED
    assert conversation.comments[0].review_state is ReviewState.COMMENTED


def test_a_record_written_before_the_poller_asked_names_no_reviewer(here):
    document = _proposed_document(here)
    for gone in ("reviewer_name", "review_state", "start_line", "original_start_line"):
        document.pop(gone)
    for comment in document["comments"]:
        comment.pop("author_name")
        comment.pop("review_state")

    conversation = _read(here, document)

    assert conversation.reviewer_name == ""
    assert conversation.review_state is None
    assert conversation.start_line is None
    assert conversation.original_start_line is None
    assert [(c.author_name, c.review_state) for c in conversation.comments] == [("", None)]


def test_a_document_without_a_role_is_an_author_record_the_board_runs(here):
    _heard(here)
    document = _on_disk(here)
    document.pop("role")
    _left(here, document)
    threads = here.threads()

    start_run(here, threads, finishes=False)

    assert threads.get(KEY).standing is ConversationState.WORKING


@pytest.mark.parametrize("worktree, branch, base_sha", [
    ("/wt/5/PRRT_kwDO", "orchestrator/thread/5/PRRT_kwDO", "ba5e0001"),
    ("/wt/5/PRRT_kwDO", None, "ba5e0001"),
    ("", None, None),
    (None, None, None),
])
def test_a_record_that_stored_its_worktree_is_adopted_only_if_it_named_one(here, worktree,
                                                                           branch, base_sha):
    document = _proposed_document(here)
    document.update(worktree=worktree, branch=branch, base_sha="ba5e0001")

    assert _read(here, document).fix.base_sha == Sha.parse(base_sha)


def test_a_record_written_before_an_agent_planned_anything_has_no_plan(here):
    document = _proposed_document(here)
    for gone in ("plan", "fix_summary", "confidence", "confidence_note"):
        document.pop(gone)

    fix = _read(here, document).fix

    assert fix.plan == ()
    assert (fix.summary, fix.confidence, fix.confidence_note) == (None, None, None)


def test_a_record_written_before_proposals_had_a_kind_proposes_a_commit(here):
    document = _proposed_document(here)
    document.pop("proposal_kind")
    document.pop("proposed_reply")

    proposal = _read(here, document).proposal

    assert (proposal.kind, proposal.reply) == ("commit", None)
    assert proposal.commits is not None


def test_a_reply_the_agent_proposed_is_kept_on_disk(here):
    threads = _heard(here)
    start_run(here, threads, finishes=False)
    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.QUESTION, "It runs once per poll.")

    proposal = here.threads().get(KEY).proposal

    assert (proposal.kind, proposal.reply) == ("reply", "It runs once per poll.")


def test_a_ticket_the_agent_proposed_is_kept_on_disk(here):
    threads = _heard(here)
    start_run(here, threads, finishes=False)
    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.OUT_OF_SCOPE, "I've proposed a ticket for it.",
                           ticket_project="PROJ", ticket_title="Cache models",
                           ticket_body="Each export reads its model again.")

    proposal = here.threads().get(KEY).proposal

    assert (proposal.kind, proposal.reply) == ("ticket", "I've proposed a ticket for it.")
    assert (proposal.ticket.project, proposal.ticket.title, proposal.ticket.body) == (
        "PROJ", "Cache models", "Each export reads its model again.")


def test_a_ticket_being_filed_and_then_filed_is_kept_on_disk(here):
    threads = _heard(here)
    start_run(here, threads)
    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.OUT_OF_SCOPE, "I've proposed a ticket for it.",
                           ticket_project="PROJ", ticket_title="Cache models",
                           ticket_body="Each export reads its model again.")
    with threads.editing(KEY) as editable:
        editable.approve(reply="Filed it.", ticket_project="WEB", ticket_title="One cache",
                         ticket_body="Exports share it.")
    drain(threads)
    filing = here.threads().get(KEY).fix
    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.OUT_OF_SCOPE, "", filed_key="WEB-12",
                           filed_url="https://example.atlassian.net/browse/WEB-12")

    filed = here.threads().get(KEY).fix

    assert (filing.run.kind, filing.state) == ("file", "running")
    assert (filing.ticket.project, filing.ticket.title) == ("WEB", "One cache")
    assert (filed.filed, filed.ticket_key, filed.ticket_url) == (
        True, "WEB-12", "https://example.atlassian.net/browse/WEB-12")


def test_a_record_written_before_tickets_were_filed_has_filed_none(here):
    document = _proposed_document(here)
    for field in ("ticket_key", "ticket_url", "file_error"):
        document.pop(field)

    fix = _read(here, document).fix

    assert (fix.ticket_key, fix.ticket_url, fix.file_error) == (None, None, None)


def test_a_record_written_before_tickets_existed_proposes_no_ticket(here):
    document = _proposed_document(here)
    document.pop("proposed_ticket")

    assert _read(here, document).proposal.ticket is None


def test_a_proposal_of_a_kind_the_board_never_makes_is_unreadable(here):
    document = _proposed_document(here)
    document["proposal_kind"] = "poem"

    assert _read(here, document).is_unreadable


@pytest.mark.parametrize("classification", ["already-done", "question", "unclear",
                                            "out-of-scope"])
def test_a_record_declined_before_replies_existed_stays_declined(here, classification):
    document = _proposed_document(here)
    document.update(fix_state="declined", classification=classification,
                    reason="nothing to change", thread_sha=None)

    conversation = _read(here, document)

    assert conversation.fix.is_declined
    assert conversation.fix.classification == classification
    assert conversation.proposal is None


def test_a_record_written_before_the_history_reads_with_its_fix_as_its_only_work(here):
    document = _proposed_document(here)
    document.pop("operations")

    assert [(operation.id, operation.kind) for operation in _read(here, document).operations] == [
        (f"{KEY}.1", OperationKind.FIRST)]


def test_a_record_written_before_the_key_parted_from_the_node_id(here):
    document = _proposed_document(here)
    document.pop("github_node_id")
    document.pop("state_changed_at")

    conversation = _read(here, document)

    assert conversation.github_node_id == KEY
    assert conversation.state_changed_at is None


def test_a_thread_resolved_on_github_says_so_and_an_older_record_says_nothing(here):
    threads = here.threads()
    first_poll(here.github, threads)
    on_github(here.github, KEY, said(101, "please rename this"), is_resolved=True)
    hear(threads)
    assert threads.get(KEY).github_resolved is True

    document = _on_disk(here)
    document.pop("github_resolved")
    document.pop("github_resolved_at")

    assert _read(here, document).github_resolved is None, (
        "a record written before the flag existed says nothing about it")


@pytest.mark.parametrize(("word", "side"), [("LEFT", Side.BEFORE), ("RIGHT", Side.AFTER),
                                            ("before", Side.BEFORE), ("after", Side.AFTER)])
def test_a_record_reads_the_side_in_the_old_words_and_the_new(here, word, side):
    document = _proposed_document(here)
    document["side"] = word

    assert _read(here, document).side is side


UNREADABLE_HISTORIES = {
    "a-word": "first",
    "an-entry-that-is-a-word": ["first"],
    "an-entry-with-no-id": [{"kind": "first", "state": "pending"}],
    "a-kind-of-no-work-we-know": [{"id": "x", "kind": "tidy", "state": "pending"}],
    "a-state-no-work-is-in": [{"id": "x", "kind": "first", "state": "stuck"}],
}


@pytest.mark.parametrize("shape", sorted(UNREADABLE_HISTORIES))
def test_a_history_the_board_did_not_write_is_unreadable(here, shape):
    document = _proposed_document(here)
    document["operations"] = UNREADABLE_HISTORIES[shape]

    assert _read(here, document).is_unreadable


UNREADABLE_PLANS = {
    "a-word": "raise instead",
    "a-mapping": {"1": "raise instead"},
    "a-step-that-is-a-word": ["raise instead"],
    "a-step-with-no-text": [{"file": "a.py", "done": False}],
    "a-step-whose-text-is-a-number": [{"text": 3}],
    "a-step-whose-file-is-a-number": [{"text": "raise instead", "file": 3}],
    "a-step-whose-file-is-a-list": [{"text": "raise instead", "file": ["a.py"]}],
}


@pytest.mark.parametrize("shape", sorted(UNREADABLE_PLANS))
def test_a_plan_no_agent_of_ours_wrote_is_unreadable(here, shape):
    document = _proposed_document(here)
    document["plan"] = UNREADABLE_PLANS[shape]

    assert _read(here, document).is_unreadable


def test_the_brief_a_rework_carries_is_kept_on_its_run(here):
    threads = _heard(here)
    propose(here, threads, KEY)

    with threads.editing(KEY) as editable:
        editable.rework(note="use the enum instead",
                        pointed=[("f", 1, "old"), ("f", None, "  removed line")],
                        include=["anna"])
    drain(threads)

    brief = threads.get(KEY).fix.run.brief
    assert brief.note == "use the enum instead"
    assert [(line.file, line.line, line.text) for line in brief.pointed] == [
        ("f", 1, "old"), ("f", None, "  removed line")]
    assert brief.include == ("anna",)


@pytest.mark.parametrize("side", [Side.BEFORE, Side.AFTER])
def test_the_side_a_draft_hangs_on_is_kept(here, side):
    diff_over(here, "f")
    threads = here.threads(is_author=False)

    other = Side.AFTER if side is Side.BEFORE else Side.BEFORE
    drafted = threads.open_draft("call it write_iso",
                                  Location(path="f", line=40, start_line=38,
                                           start_side=other, side=side))

    read = threads.get(drafted.key)
    assert (read.side, read.start_side) == (side, other)


def test_a_conversation_nothing_ever_heard_is_nothing(here):
    assert here.threads().get(KEY) is None


def test_a_review_is_kept_beside_the_threads_and_is_not_one(here):
    diff_over(here, "f")
    threads = here.threads(is_author=False)
    drafted = threads.open_draft("call it write_iso", Location(path="f", line=1,
                                                                side=Side.AFTER))
    with threads.editing(drafted.key) as editable:
        editable.enrol()
    drain(threads)

    sent = threads.send_review(Verdict.COMMENT, "a few things")
    drain(threads)

    assert [review.id for review in threads.reviews()] == [sent.id]
    assert [conversation.key for conversation in threads.all()] == [
        drafted.key]
