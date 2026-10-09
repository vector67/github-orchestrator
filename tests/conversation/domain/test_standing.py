from dataclasses import replace

import pytest

from github_orchestrator.agent_runs.fake import Outcome
from github_orchestrator.conversation import Classification, ConversationState
from github_orchestrator.github.fake import FakeGitHub, GhError
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.conversation.support import (
    THE_PR,
    WORKTREE,
    World,
    at,
    drain,
    hear,
    lost,
    on_github,
    propose,
    repo_at,
    said,
    start_run,
    without_runs,
    world,
)

KEY = "PRRT_one"
BODY = "rename this"
NOW = "2026-09-21T11:00:00Z"
PUSH_FAILURE = ("To github.com:acme/widgets.git\n"
                " ! [rejected]        thread-x -> main (fetch first)\n"
                "error: failed to push some refs")


def refusing_remote(github: FakeGitHub) -> FakeWorkingCopies:
    copies = FakeWorkingCopies(github)
    copies.refuse_pushes(PUSH_FAILURE)
    return copies


class FirstReplyRefused(FakeGitHub):
    refused = False

    def reply_to_thread(self, key, body):
        if not self.refused:
            self.refused = True
            raise GhError("gh: Not Found (HTTP 404)")
        return super().reply_to_thread(key, body)


def _here(settings, *, github=None, working_copies=None) -> World:
    github = github or FakeGitHub()
    here = world(settings, github=github, working_copies=working_copies, clock=at(NOW))
    repo_at(here.working_copies, WORKTREE, {"f": "old\n", "README": "hello"})
    return here


def _heard(here, *comments, is_author=None):
    threads = here.threads(is_author=is_author)
    on_github(here.github, KEY, *(comments or (said(1, BODY),)))
    hear(threads)
    return threads


def _replied_on_github(here, *comments):
    record = here.github.prs[THE_PR]
    thread = here.github.thread(KEY)
    record.threads = [one for one in record.threads if one.key != KEY]
    here.github.add_thread(THE_PR, replace(thread, comments=thread.comments + comments))


def _capped(here):
    return world(without_runs(here.settings), github=here.github,
                 working_copies=here.working_copies, agent_runs=here.agent_runs,
                 thread_records=here.thread_records, clock=at(NOW),
                 pr_processes=here.pr_processes).threads()


def _standing(threads):
    return threads.get(KEY).standing


def queued(settings):
    here = _here(settings)
    return here, _heard(here)


def working(settings):
    here, threads = queued(settings)
    start_run(here, threads, finishes=False)
    return here, threads


def proposed(settings):
    here, threads = queued(settings)
    propose(here, threads, KEY)
    return here, threads


def declined(settings):
    here, threads = working(settings)
    with threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.NEEDS_HUMAN, "a question")
    return here, threads


def failed(settings):
    here, threads = queued(settings)
    for _ in range(threads.get(KEY).run_holder.attempts_allowed):
        start_run(here, threads)
        with threads.editing(KEY) as editable:
            editable.fail("the tests would not run")
    return here, threads


def reworking(settings):
    here, threads = proposed(settings)
    with threads.editing(KEY) as editable:
        editable.rework(note="narrow it")
    here.agent_runs.script(Outcome(finishes=False))
    drain(threads)
    return here, threads


def reworking_queued(settings):
    here, threads = proposed(settings)
    with threads.editing(KEY) as editable:
        editable.rework(note="narrow it")
    capped = _capped(here)
    drain(capped)
    return here, capped


def _approved_over_a_conflict(settings):
    here, threads = proposed(settings)
    here.working_copies.commit(WORKTREE, {"f": "moved on\n"}, "change f on main")
    with threads.editing(KEY) as editable:
        editable.approve(reply="Renamed it.")
    return here, threads


def rebasing(settings):
    here, threads = _approved_over_a_conflict(settings)
    here.agent_runs.script(Outcome(finishes=False))
    drain(threads)
    return here, threads


def rebasing_queued(settings):
    here, threads = _approved_over_a_conflict(settings)
    capped = _capped(here)
    drain(capped)
    return here, capped


def push_failed(settings):
    github = FakeGitHub()
    here = _here(settings, github=github, working_copies=refusing_remote(github))
    threads = _heard(here)
    propose(here, threads, KEY)
    with threads.editing(KEY) as editable:
        editable.approve(reply="Renamed it.")
    drain(threads)
    return here, threads


def reply_failed(settings):
    here = _here(settings, github=FirstReplyRefused())
    threads = _heard(here)
    propose(here, threads, KEY)
    with threads.editing(KEY) as editable:
        editable.approve(reply="Renamed it.")
    drain(threads)
    return here, threads


def queued_after_you_spoke(settings):
    here, threads = proposed(settings)
    with threads.editing(KEY) as editable:
        editable.reply("which one?")
    drain(threads)
    _replied_on_github(here, said(2, "the helper"))
    hear(threads)
    return here, threads


def working_after_you_spoke(settings):
    here, threads = queued_after_you_spoke(settings)
    start_run(here, threads, finishes=False)
    return here, threads


def ready_after_you_spoke(settings):
    here, threads = working_after_you_spoke(settings)
    here.working_copies.commit(here.working_copies.thread_checkout(THE_PR, KEY),
                               {"f": "newer\n"}, "rename the helper")
    with threads.editing(KEY) as editable:
        editable.ready(here.working_copies.head_of(
            here.working_copies.thread_checkout(THE_PR, KEY)))
    return here, threads


def _unparked_after_you_spoke(settings):
    here, threads = proposed(settings)
    with threads.editing(KEY) as editable:
        editable.reply("which one?")
    drain(threads)
    with threads.editing(KEY) as editable:
        editable.unpark()
    drain(threads)
    return here, threads


def reworking_after_you_spoke(settings):
    here, threads = _unparked_after_you_spoke(settings)
    with threads.editing(KEY) as editable:
        editable.rework(note="narrow it")
    here.agent_runs.script(Outcome(finishes=False))
    drain(threads)
    _replied_on_github(here, said(2, "the helper"))
    hear(threads)
    return here, threads


def rebasing_after_you_spoke(settings):
    here, threads = _unparked_after_you_spoke(settings)
    here.working_copies.commit(WORKTREE, {"f": "moved on\n"}, "change f on main")
    with threads.editing(KEY) as editable:
        editable.approve(reply="Renamed it.")
    here.agent_runs.script(Outcome(finishes=False))
    drain(threads)
    _replied_on_github(here, said(2, "the helper"))
    hear(threads)
    return here, threads


def a_reviewers_thread(settings):
    here = _here(settings)
    return here, _heard(here, said(1, BODY), said(2, "done", author="jeffrey"),
                        is_author=False)


YOURS_WHILE_OPEN = [
    (push_failed, True),
    (reply_failed, True),
    (reworking_queued, False),
    (reworking_after_you_spoke, False),
    (queued_after_you_spoke, True),
    (working_after_you_spoke, True),
    (a_reviewers_thread, True),
]


@pytest.mark.parametrize("reached,yours", YOURS_WHILE_OPEN,
                         ids=[reached.__name__ for reached, _ in YOURS_WHILE_OPEN])
def test_a_reply_parks_an_open_thread_only_when_it_was_yours_to_act_on(
    settings, reached, yours
):
    here, threads = reached(settings)

    with threads.editing(KEY) as editable:
        editable.reply("what did you mean?")
    drain(threads)

    assert here.github.thread(KEY).comments[-1].body == "what did you mean?"
    assert (_standing(threads) is ConversationState.WAITING) is yours


def test_a_thread_github_no_longer_has_is_still_yours_to_decide(settings):
    here, threads = queued(settings)
    here.github.delete_comment(THE_PR, here.github.thread(KEY).kind, 1)

    lost(threads, KEY)

    assert threads.get(KEY).is_removed
    assert _standing(threads) is ConversationState.READY


@pytest.mark.parametrize("reached", [a_reviewers_thread, proposed, declined, failed],
                         ids=lambda reached: reached.__name__)
def test_an_open_thread_is_ready_however_the_run_before_it_ended(settings, reached):
    _, threads = reached(settings)

    assert _standing(threads) is ConversationState.READY


def test_a_run_waiting_for_the_board_is_told_apart_from_one_underway(settings):
    assert _standing(queued(settings)[1]) is ConversationState.QUEUED
    assert _standing(working(settings)[1]) is ConversationState.WORKING


@pytest.mark.parametrize("reached", [rebasing_queued, rebasing],
                         ids=lambda reached: reached.__name__)
def test_a_rebase_run_is_landing_rather_than_queued_or_working(settings, reached):
    _, threads = reached(settings)

    assert _standing(threads) is ConversationState.LANDING


@pytest.mark.parametrize("reached", [reworking_queued, reworking],
                         ids=lambda reached: reached.__name__)
def test_a_run_on_a_brief_you_wrote_is_rework_before_and_after_pick_up(settings, reached):
    _, threads = reached(settings)

    assert _standing(threads) is ConversationState.REWORK


@pytest.mark.parametrize("reached", [push_failed, reply_failed],
                         ids=lambda reached: reached.__name__)
def test_a_landing_that_stalled_is_yours_again_rather_than_still_landing(settings, reached):
    _, threads = reached(settings)

    assert _standing(threads) is ConversationState.READY


@pytest.mark.parametrize("reached,expected", [
    (queued_after_you_spoke, ConversationState.QUEUED),
    (working_after_you_spoke, ConversationState.WORKING),
    (ready_after_you_spoke, ConversationState.READY),
    (rebasing_after_you_spoke, ConversationState.LANDING),
], ids=["queued", "working", "ready", "landing"])
def test_a_reply_that_came_back_after_you_spoke_leaves_the_state_alone(
    settings, reached, expected
):
    _, threads = reached(settings)

    spoken_on = threads.get(KEY)
    assert spoken_on.reopened
    assert spoken_on.standing is expected, (
        "reopened is a fact about the conversation and the state is a fact "
        "about the work; folding one into the other is what state_of exists "
        "to undo")
