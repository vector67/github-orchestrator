from dataclasses import replace
from pathlib import Path

import pytest

from github_orchestrator.conversation import (
    Classification,
    Conversation,
    ConversationState,
    Denied,
    ErrorCode,
)
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.conversation.support import (
    THE_PR,
    WORKTREE,
    drain,
    hear,
    lost,
    on_github,
    propose,
    repo_at,
    said,
    start_run,
    world,
)

KEY = "PRRT_one"
TWO_STEPS = (("Raise instead of continue", "billing/invoice_writer.py"),
             ("Test: export raises on missing tax rate",
              "tests/test_invoice_writer.py"))
THREE_STEPS = tuple((f"step {n}", f"{n}.py") for n in range(1, 4))


class Bench:
    def __init__(self, settings):
        self.world = world(settings, working_copies=FakeWorkingCopies())
        repo_at(self.world.working_copies, WORKTREE, {"f": "old\n"})
        self.threads = self.world.threads()
        on_github(self.world.github, KEY, said(1, "rename this"))
        hear(self.threads)

    def stored(self) -> Conversation:
        return self.threads.get(KEY)

    def plan(self, steps=TWO_STEPS):
        with self.threads.editing(KEY) as editable:
            return editable.plan(steps)

    def mark(self, *indexes):
        with self.threads.editing(KEY) as editable:
            return editable.step_done(indexes)


@pytest.fixture
def bench(settings):
    return Bench(settings)


def _queued(bench):
    pass


def _running(bench):
    start_run(bench.world, bench.threads, finishes=False)


def _proposed(bench):
    propose(bench.world, bench.threads, KEY)


def _in_session(bench):
    _proposed(bench)
    bench.world.pr_processes.open(THE_PR, Path(WORKTREE))
    with bench.threads.editing(KEY) as editable:
        editable.start_session()
    drain(bench.threads)


def _declined(bench):
    _running(bench)
    with bench.threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.RISKY, "it wants a schema change")


def _failed(bench):
    for _ in range(bench.stored().run_holder.attempts_allowed):
        start_run(bench.world, bench.threads)
        with bench.threads.editing(KEY) as editable:
            editable.fail("the tests would not run")


def _landing(bench):
    _proposed(bench)
    bench.world.working_copies.refuse_pushes("fatal: the remote hung up")
    with bench.threads.editing(KEY) as editable:
        editable.approve()
    drain(bench.threads)


def _landed(bench):
    _proposed(bench)
    with bench.threads.editing(KEY) as editable:
        editable.approve()
    drain(bench.threads)


def _resolved(bench):
    _proposed(bench)
    with bench.threads.editing(KEY) as editable:
        editable.resolve()
    drain(bench.threads)


def _removed(bench):
    bench.world.github.delete_comment(THE_PR, bench.world.github.thread(KEY).kind, 1)
    lost(bench.threads, KEY)


def _reached(bench, reach, expected):
    reach(bench)
    assert expected(bench.stored()), bench.stored()


REACHED = {
    "queued": (_queued, lambda c: c.standing is ConversationState.QUEUED),
    "running": (_running, lambda c: c.standing is ConversationState.WORKING),
    "in_session": (_in_session, lambda c: c.standing is ConversationState.IN_SESSION),
    "proposed": (_proposed, lambda c: c.fix.is_proposed),
    "declined": (_declined, lambda c: c.fix.is_declined),
    "failed": (_failed, lambda c: c.fix.has_failed),
    "landing": (_landing, lambda c: c.fix.picked and not c.fix.pushed),
    "landed": (_landed, lambda c: c.standing is ConversationState.DONE and c.fix.answered),
    "resolved": (_resolved, lambda c: c.standing is ConversationState.DONE and not c.fix.picked),
    "removed": (_removed, lambda c: c.is_removed),
}


def _put(bench, state):
    _reached(bench, *REACHED[state])


def _plan_of(bench):
    return [(step.text, step.file, step.done) for step in bench.stored().fix.plan]


def test_an_agent_writes_down_the_steps_it_means_to_take(bench):
    _running(bench)
    started = len(bench.world.agent_runs.started)

    outcome = bench.plan()

    assert not isinstance(outcome, Denied)
    assert _plan_of(bench) == [
        ("Raise instead of continue", "billing/invoice_writer.py", False),
        ("Test: export raises on missing tax rate", "tests/test_invoice_writer.py", False),
    ]
    assert len(bench.world.agent_runs.started) == started


def test_a_step_whose_file_is_unknown_names_none(bench):
    _running(bench)

    bench.plan((("Work out where this belongs", None),))

    assert _plan_of(bench) == [("Work out where this belongs", None, False)]


def test_a_new_plan_replaces_the_one_before_it_whole(bench):
    _running(bench)
    bench.plan((("the old way", "a.py"), ("and the rest of it", "b.py")))
    bench.mark(1)

    bench.plan()

    assert _plan_of(bench) == [(text, file, False) for text, file in TWO_STEPS]


@pytest.mark.parametrize("state", ["queued", "running", "in_session"])
def test_a_plan_is_declared_from_the_moment_the_fix_is_waiting_for_an_agent(
    bench, state,
):
    _put(bench, state)

    assert isinstance(bench.plan(), Conversation)


def test_a_plan_declared_before_the_run_started_survives_it_starting(bench):
    bench.plan()
    planned = _plan_of(bench)

    _running(bench)

    assert bench.stored().standing is ConversationState.WORKING
    assert _plan_of(bench) == planned


@pytest.mark.parametrize("state", ["proposed", "landed"])
def test_a_fix_nobody_is_working_on_takes_no_plan(bench, state):
    _put(bench, state)

    outcome = bench.plan()

    assert isinstance(outcome, Denied)
    assert _plan_of(bench) == []


@pytest.mark.parametrize("state", ["resolved"])
def test_a_conversation_that_is_no_longer_open_takes_no_plan(bench, state):
    _put(bench, state)

    assert isinstance(bench.plan(), Denied)
    assert _plan_of(bench) == []


def _planned(bench, state="running", done=()):
    bench.plan(THREE_STEPS)
    if done:
        bench.mark(*done)
    _put(bench, state)


def _marks(bench):
    return [done for _, _, done in _plan_of(bench)]


def test_an_agent_marks_the_step_it_has_finished(bench):
    _planned(bench)
    started = len(bench.world.agent_runs.started)

    outcome = bench.mark(1)

    assert not isinstance(outcome, Denied)
    assert _marks(bench) == [True, False, False]
    assert len(bench.world.agent_runs.started) == started


def test_several_steps_are_marked_at_once(bench):
    _planned(bench)

    bench.mark(1, 3)

    assert _marks(bench) == [True, False, True]


def test_a_step_already_marked_stays_marked(bench):
    _planned(bench, done=(1,))

    bench.mark(2)

    assert _marks(bench) == [True, True, False]


def test_an_agent_may_mark_the_last_step_as_it_reports_the_fix(bench):
    _planned(bench, state="proposed")

    outcome = bench.mark(3)

    assert not isinstance(outcome, Denied)
    assert _marks(bench)[2] is True


@pytest.mark.parametrize("index", [0, 4])
def test_a_step_outside_the_plan_is_refused(bench, index):
    _planned(bench)
    before = _plan_of(bench)

    outcome = bench.mark(index)

    assert isinstance(outcome, Denied)
    assert outcome.code == ErrorCode.INTERNAL_REFUSAL
    assert _plan_of(bench) == before


def test_one_step_outside_the_plan_marks_none_of_the_others(bench):
    _planned(bench)

    outcome = bench.mark(1, 9)

    assert isinstance(outcome, Denied)
    assert _marks(bench) == [False, False, False]


@pytest.mark.parametrize("state", ["queued", "running", "in_session", "proposed"])
def test_a_step_is_marked_from_the_moment_the_fix_is_waiting_for_an_agent(
    bench, state,
):
    _planned(bench, state=state)

    assert isinstance(bench.mark(1), Conversation)


@pytest.mark.parametrize("state", ["declined", "landed"])
def test_a_fix_nobody_is_working_on_marks_no_step(bench, state):
    _planned(bench, state=state)
    before = _plan_of(bench)

    assert isinstance(bench.mark(1), Denied)
    assert _plan_of(bench) == before


@pytest.mark.parametrize("state", ["resolved"])
def test_a_conversation_that_is_no_longer_open_marks_no_step(bench, state):
    _planned(bench, state=state)

    assert isinstance(bench.mark(1), Denied)


def test_a_settled_conversation_is_refused_in_the_words_of_what_it_refused(bench):
    _planned(bench, state="resolved")

    declaring = bench.plan()
    marking = bench.mark(1)

    assert declaring.reason == "a resolved conversation takes no plan"
    assert marking.reason == "a resolved conversation marks no step"


def test_a_reply_that_reopens_a_conversation_leaves_the_plan_where_it_is(bench):
    _planned(bench, state="proposed", done=(1, 2))
    before = _plan_of(bench)
    record = bench.world.github.prs[THE_PR]
    [thread] = [one for one in record.threads if one.key == KEY]
    record.threads.remove(thread)
    bench.world.github.add_thread(THE_PR, replace(
        thread, comments=(*thread.comments, said(2, "still wrong"))))

    hear(bench.threads)

    assert bench.stored().standing is ConversationState.QUEUED
    assert _plan_of(bench) == before
