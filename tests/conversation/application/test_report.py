import pytest

from github_orchestrator.conversation import (
    Classification,
    Conversation,
    ConversationState,
    Denied,
    ErrorCode,
)
from github_orchestrator.domain import Sha
from tests.conversation.support import (
    WORKTREE,
    commit_fix,
    hear,
    on_github,
    repo_at,
    said,
    start_run,
    world,
)

KEY = "PRRT_101"
BODY = "Please rename this helper."


def _commented(settings):
    here = world(settings)
    repo_at(here.working_copies, WORKTREE, {"f": "old\n"})
    threads = here.threads()
    on_github(here.github, KEY, said(101, BODY))
    hear(threads)
    return here, threads


def _running(settings):
    here, threads = _commented(settings)
    start_run(here, threads, finishes=False)
    return here, threads


def _plan(fix) -> list[tuple[str, str | None, bool]]:
    return [(step.text, step.file, step.done) for step in fix.plan]


def test_an_agent_that_declines_a_thread_records_what_it_found(settings):
    _, threads = _running(settings)

    with threads.editing(KEY) as editable:
        outcome = editable.not_a_fix(Classification.RISKY, "touches auth")

    assert isinstance(outcome, Conversation)
    fix = threads.get(KEY).fix
    assert fix.is_declined
    assert fix.classification == Classification.RISKY
    assert fix.reason == "touches auth"


@pytest.mark.parametrize("classification", [
    Classification.ALREADY_DONE, Classification.QUESTION, Classification.UNCLEAR,
    Classification.OUT_OF_SCOPE])
def test_an_agent_that_answers_without_code_proposes_its_reply(settings, classification):
    _, threads = _running(settings)

    with threads.editing(KEY) as editable:
        outcome = editable.not_a_fix(classification, "It runs once per poll, so no.")

    assert isinstance(outcome, Conversation)
    conversation = threads.get(KEY)
    assert conversation.standing is ConversationState.READY
    assert conversation.fix.is_proposed
    assert conversation.fix.classification is classification
    proposal = conversation.proposal
    assert (proposal.kind, proposal.reply, proposal.commits) == (
        "reply", "It runs once per poll, so no.", None)


def test_a_commit_the_agent_reports_is_a_commit_proposal(settings):
    here, threads = _running(settings)

    with threads.editing(KEY) as editable:
        editable.ready(commit_fix(here, KEY), tests="passed")

    proposal = threads.get(KEY).proposal
    assert (proposal.kind, proposal.reply) == ("commit", None)


def test_a_commit_reported_after_a_reply_replaces_it(settings):
    here, threads = _running(settings)
    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.QUESTION, "It runs once per poll.")

    with threads.editing(KEY) as editable:
        editable.ready(commit_fix(here, KEY), tests="passed")

    proposal = threads.get(KEY).proposal
    assert (proposal.kind, proposal.reply) == ("commit", None)
    assert proposal.commits is not None


def test_a_reply_reported_after_a_commit_replaces_it(settings):
    here, threads = _running(settings)
    with threads.editing(KEY) as editable:
        editable.ready(commit_fix(here, KEY), tests="passed", summary="renamed it")

    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.ALREADY_DONE, "The branch renames it already.")

    proposal = threads.get(KEY).proposal
    assert (proposal.kind, proposal.reply, proposal.commits) == (
        "reply", "The branch renames it already.", None)
    assert (proposal.summary, proposal.tests) == (None, None)


def test_an_agent_that_reports_a_commit_proposes_it_with_its_tests(settings):
    here, threads = _running(settings)
    sha = commit_fix(here, KEY)

    with threads.editing(KEY) as editable:
        outcome = editable.ready(sha, tests="passed", note="renamed the helper")

    assert isinstance(outcome, Conversation)
    fix = threads.get(KEY).fix
    assert fix.is_proposed
    assert fix.thread_sha == Sha(sha)
    assert fix.tests == "passed"
    assert fix.agent_note == "renamed the helper"


def test_a_report_the_fix_will_not_take_is_refused_and_writes_nothing(settings):
    _, threads = _running(settings)
    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.RISKY, "touches auth")
    declined = threads.get(KEY)

    with threads.editing(KEY) as editable:
        outcome = editable.ready("a" * 40)

    assert isinstance(outcome, Denied)
    assert threads.get(KEY) == declined


def test_a_report_on_a_conversation_nobody_opened_has_no_record_to_take_it(settings):
    threads = world(settings).threads()

    with threads.editing(KEY) as editable:
        refused = editable.ready("a" * 40)

    assert isinstance(refused, Denied)
    assert refused.code is ErrorCode.NOT_FOUND
    assert threads.get(KEY) is None


def test_a_failed_run_spends_an_attempt_until_the_budget_is_gone(settings):
    here, threads = _commented(settings)
    allowed = threads.get(KEY).run_holder.attempts_allowed

    for attempt in range(1, allowed + 1):
        start_run(here, threads)

        with threads.editing(KEY) as editable:
            outcome = editable.fail("tests failed")

        assert isinstance(outcome, Conversation)
        conversation = threads.get(KEY)
        assert conversation.fix.reason == "tests failed"
        assert conversation.fix.has_failed == (attempt == allowed), attempt
        if attempt < allowed:
            assert conversation.standing is ConversationState.QUEUED, attempt


def test_a_failure_on_a_fix_nobody_is_running_is_refused(settings):
    _, threads = _commented(settings)
    queued = threads.get(KEY)

    with threads.editing(KEY) as editable:
        outcome = editable.fail("boom")

    assert isinstance(outcome, Denied)
    assert threads.get(KEY) == queued


def test_a_plan_an_agent_declares_reaches_the_record_it_belongs_to(settings):
    _, threads = _running(settings)

    with threads.editing(KEY) as editable:
        outcome = editable.plan((
            ("Raise instead of continue", "billing/invoice_writer.py"),
            ("Test the raise", None),
        ))

    assert isinstance(outcome, Conversation)
    assert _plan(threads.get(KEY).fix) == [
        ("Raise instead of continue", "billing/invoice_writer.py", False),
        ("Test the raise", None, False),
    ]


def test_a_step_an_agent_finished_is_marked_on_the_plan(settings):
    _, threads = _running(settings)
    with threads.editing(KEY) as editable:
        editable.plan((("raise instead", None), ("test the raise", None)))

    with threads.editing(KEY) as editable:
        outcome = editable.step_done((1,))

    assert isinstance(outcome, Conversation)
    assert [done for _, _, done in _plan(threads.get(KEY).fix)] == [
        True, False]


def test_a_step_the_plan_does_not_have_is_refused_and_writes_nothing(settings):
    _, threads = _running(settings)
    with threads.editing(KEY) as editable:
        editable.plan((("raise instead", None),))
    planned = threads.get(KEY)

    with threads.editing(KEY) as editable:
        outcome = editable.step_done((2,))

    assert isinstance(outcome, Denied)
    assert threads.get(KEY) == planned
