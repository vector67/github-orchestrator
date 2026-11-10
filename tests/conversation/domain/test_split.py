import pytest

from github_orchestrator.agent_runs.fake import FilingTicket
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
    start_run(here, threads)
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


TICKET = {"ticket_project": "PROJ", "ticket_title": "Cache tax rates",
          "ticket_body": "Each export reads its model again."}
FILED_URL = "https://example.atlassian.net/browse/PROJ-12"


def _split_with_a_ticket(here, threads):
    sha = _removed(here)
    _split(threads, sha, **TICKET)
    return sha


def _filed(threads):
    with threads.editing(KEY) as editable:
        filed = editable.not_a_fix(Classification.OUT_OF_SCOPE, "", filed_key="PROJ-12",
                                   filed_url=FILED_URL)
    assert not isinstance(filed, Denied), filed
    drain(threads)


def _accepted(threads, part):
    outcome = _asked(threads, "approve", part=part)
    assert not isinstance(outcome, Denied), outcome
    if part == "ticket":
        _filed(threads)
    return threads.get(KEY)


def _states(conversation):
    return {view.part: view.state for view in conversation.proposal.parts}


def _filings(here):
    return [started.work for started in here.agent_runs.started
            if isinstance(started.work, FilingTicket)]


def test_accepting_the_changes_pushes_the_removal_and_keeps_the_rest_proposed(here, threads):
    sha = _split_with_a_ticket(here, threads)

    stored = _accepted(threads, "changes")

    assert here.working_copies.commits[here.working_copies.origin["main"]].tree["f"] == (
        "removed\n")
    assert (stored.fix.picked, stored.fix.pushed) == (True, True)
    assert stored.standing is ConversationState.READY
    assert _states(stored) == {"ticket": "proposed", "changes": "run", "new-pr": "proposed",
                               "reply": "proposed"}
    assert stored.latest_approval.state == "applied"
    assert stored.fix.thread_sha == Sha(sha)


def test_accepting_the_ticket_files_the_splits_ticket_and_keeps_the_rest_proposed(here,
                                                                                  threads):
    _split_with_a_ticket(here, threads)

    _asked(threads, "approve", part="ticket")
    filing = threads.get(KEY)
    _filed(threads)

    [filed] = _filings(here)
    assert (filed.fix.ticket_project, filed.fix.ticket_title) == ("PROJ", "Cache tax rates")
    assert _states(filing)["ticket"] == "running"
    stored = threads.get(KEY)
    assert stored.standing is ConversationState.READY
    assert (stored.fix.ticket_key, stored.fix.ticket_url) == ("PROJ-12", FILED_URL)
    assert _states(stored) == {"ticket": "run", "changes": "proposed", "new-pr": "proposed",
                               "reply": "proposed"}
    assert here.github.thread(KEY).comments[1:] == ()


def test_accepting_the_reply_queues_it_waiting_for_the_new_pr(here, threads):
    _split(threads, _removed(here))

    stored = _accepted(threads, "reply")

    [reply] = [view for view in stored.proposal.parts if view.part == "reply"]
    assert (reply.state, reply.waits_for) == ("queued", "new-pr")
    assert stored.standing is ConversationState.READY
    assert here.github.thread(KEY).comments[1:] == ()


@pytest.mark.parametrize("order", [
    ("ticket", "changes", "reply"), ("ticket", "reply", "changes"),
    ("changes", "ticket", "reply"), ("changes", "reply", "ticket"),
    ("reply", "ticket", "changes"), ("reply", "changes", "ticket"),
])
def test_every_order_of_accepting_the_three_parts_runs_two_and_queues_the_reply(here, threads,
                                                                                order):
    _split_with_a_ticket(here, threads)

    for part in order:
        stored = _accepted(threads, part)

    assert _states(stored) == {"ticket": "run", "changes": "run", "new-pr": "proposed",
                               "reply": "queued"}
    assert stored.standing is ConversationState.READY
    assert len(_filings(here)) == 1
    assert here.github.thread(KEY).comments[1:] == ()


def test_a_split_under_this_prs_ticket_has_no_ticket_to_accept(here, threads):
    _split(threads, _removed(here))

    outcome = _asked(threads, "approve", part="ticket")

    assert isinstance(outcome, Denied)
    assert "files no ticket" in outcome.reason
    assert [view.part for view in threads.get(KEY).proposal.parts] == [
        "changes", "new-pr", "reply"]


@pytest.mark.parametrize("part", ["new-pr", None])
def test_accepting_the_new_pr_is_refused_until_a_later_step_and_says_so(here, threads, part):
    _split(threads, _removed(here))

    outcome = _asked(threads, "approve", part=part)

    assert isinstance(outcome, Denied)
    assert outcome.code is ErrorCode.NO_PROPOSAL
    assert "opening the new PR arrives in a later step" in outcome.reason
    assert threads.get(KEY).standing is ConversationState.READY


def test_a_part_that_has_run_is_locked(here, threads):
    _split(threads, _removed(here))
    _accepted(threads, "changes")

    outcome = _asked(threads, "approve", part="changes")

    assert isinstance(outcome, Denied)
    assert "locked" in outcome.reason


def test_a_split_is_no_longer_rejected_once_a_part_has_run(here, threads):
    _split(threads, _removed(here))
    _accepted(threads, "changes")

    outcome = _asked(threads, "reject")

    assert isinstance(outcome, Denied)
    assert threads.get(KEY).standing is ConversationState.READY


def test_a_split_with_only_a_queued_part_can_still_be_rejected(here, threads):
    _split(threads, _removed(here))
    _accepted(threads, "reply")

    outcome = _asked(threads, "reject")

    assert not isinstance(outcome, Denied), outcome


def test_a_failed_filing_leaves_the_ticket_to_accept_again(here, threads):
    _split_with_a_ticket(here, threads)
    _asked(threads, "approve", part="ticket")
    with threads.editing(KEY) as editable:
        editable.fail("Jira refused the project key")
    drain(threads)
    drain(threads)
    failed = threads.get(KEY)

    stored = _accepted(threads, "ticket")

    assert failed.standing is ConversationState.READY
    assert _states(failed)["ticket"] == "proposed"
    assert (failed.latest_approval.state, failed.latest_approval.reason_code) == (
        "refused", "file-failed")
    assert len(_filings(here)) == 2
    assert _states(stored)["ticket"] == "run"


def test_a_failed_push_leaves_the_changes_to_accept_again_without_picking_twice(here,
                                                                               threads):
    _split(threads, _removed(here))
    here.working_copies.refuse_pushes("failed to push some refs", times=1)

    failed = _accepted(threads, "changes")
    picked = failed.fix.landed_sha
    stored = _accepted(threads, "changes")

    assert _states(failed)["changes"] == "proposed"
    assert (failed.latest_approval.state, failed.latest_approval.reason_code) == (
        "refused", "push-failed")
    assert failed.standing is ConversationState.READY
    assert _states(stored)["changes"] == "run"
    assert stored.fix.landed_sha == picked
    assert here.working_copies.origin["main"] == str(picked)


def test_a_part_named_on_a_proposal_that_is_no_split_is_refused(here, threads):
    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.QUESTION, "It runs once per poll.")

    outcome = _asked(threads, "approve", reply="It runs once per poll.", part="changes")

    assert isinstance(outcome, Denied)
    assert outcome.code is ErrorCode.MALFORMED_REQUEST


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
