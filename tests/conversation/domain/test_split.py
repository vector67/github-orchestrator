import pytest

from github_orchestrator.conversation import (
    Classification,
    ConversationState,
    Denied,
    ErrorCode,
)
from github_orchestrator.domain import Sha
from github_orchestrator.settings.fake import fake_settings
from tests.conversation.support import (
    WORKTREE,
    commit_fix,
    drain,
    hear,
    on_github,
    repo_at,
    said,
    start_run,
    world,
)

KEY = "PRRT_split"
BRANCH = "split/cache-tax-rates"
REPLY = "This moved to its own PR."


@pytest.fixture
def here(tmp_path):
    built = world(fake_settings(tmp_path / "data"))
    repo_at(built.working_copies, WORKTREE, {"f": "old\n", "README": "hello"})
    return built


@pytest.fixture
def threads(here):
    threads = here.threads()
    on_github(here.github, KEY, said(101, "this isn't part of PROJ-12, can it go in a separate PR?"))
    hear(threads)
    start_run(here, threads, finishes=False)
    return threads


def _removed(here):
    sha = commit_fix(here, KEY, {"f": "removed\n"}, message="Take the cache out")
    here.working_copies.branches[BRANCH] = sha
    return sha


def _split(threads, sha, **fields):
    with threads.editing(KEY) as editable:
        return editable.split(sha, **{
            "branch": BRANCH, "base": "main", "base_reason": "the cache stands alone",
            "reply": REPLY, **fields})


def _asked(threads, verb, *args, **kwargs):
    with threads.editing(KEY) as editable:
        asked = getattr(editable, verb)(*args, **kwargs)
    if not isinstance(asked, Denied):
        drain(threads)
    return asked


def test_a_split_under_this_prs_ticket_is_proposed_with_every_part(here, threads):
    sha = _removed(here)

    outcome = _split(threads, sha)

    assert not isinstance(outcome, Denied), outcome
    stored = threads.get(KEY)
    fix = stored.fix
    assert stored.standing is ConversationState.READY
    assert fix.is_proposed
    assert (fix.kind, fix.thread_sha, fix.reply) == ("split", Sha(sha), REPLY)
    assert (fix.split.branch, fix.split.base, fix.split.base_reason, fix.split.ticket) == (
        BRANCH, "main", "the cache stands alone", None)


def test_a_split_under_a_new_ticket_carries_the_ticket_draft(here, threads):
    sha = _removed(here)

    _split(threads, sha, ticket_project="PROJ", ticket_title="Cache tax rates",
           ticket_body="Each export reads its model again.")

    ticket = threads.get(KEY).fix.split.ticket
    assert (ticket.project, ticket.title, ticket.body) == (
        "PROJ", "Cache tax rates", "Each export reads its model again.")


def test_a_split_onto_a_branch_the_worktree_does_not_have_is_refused(here, threads):
    sha = commit_fix(here, KEY, {"f": "removed\n"})

    outcome = _split(threads, sha)

    assert isinstance(outcome, Denied)
    assert BRANCH in outcome.reason
    assert threads.get(KEY).standing is ConversationState.WORKING


def test_a_split_whose_removal_is_not_on_the_threads_base_is_refused(here, threads):
    base = threads.get(KEY).fix.base_sha
    stray = here.working_copies.publish("elsewhere", None, {"g": "x\n"}, "unrelated")
    here.working_copies.branches[BRANCH] = stray

    outcome = _split(threads, stray)

    assert isinstance(outcome, Denied)
    assert f"{base} is not an ancestor of {stray}" in outcome.reason


def test_accepting_a_split_is_refused_until_a_later_step_and_says_so(here, threads):
    _split(threads, _removed(here))

    outcome = _asked(threads, "approve", reply=REPLY)

    assert isinstance(outcome, Denied)
    assert outcome.code is ErrorCode.NO_PROPOSAL
    assert "accepting a split arrives in a later step" in outcome.reason
    assert threads.get(KEY).standing is ConversationState.READY


def test_a_split_can_be_rejected_like_any_proposal(here, threads):
    _split(threads, _removed(here))

    outcome = _asked(threads, "reject")

    assert not isinstance(outcome, Denied), outcome
    assert threads.get(KEY).standing is ConversationState.DONE


def test_a_split_can_be_sent_back_for_rework_like_any_proposal(here, threads):
    _split(threads, _removed(here))

    outcome = _asked(threads, "rework", note="keep the rename here")

    assert not isinstance(outcome, Denied), outcome
    assert threads.get(KEY).fix.run.brief.note == "keep the rename here"


def test_a_reply_reported_after_a_split_leaves_no_split_behind(here, threads):
    _split(threads, _removed(here))

    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.QUESTION, "It runs once per poll.")

    fix = threads.get(KEY).fix
    assert (fix.kind, fix.split, fix.thread_sha) == ("reply", None, None)
