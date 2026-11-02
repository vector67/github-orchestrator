from pathlib import Path

import pytest

from github_orchestrator.agent_runs.fake import FakeAgentRuns, Outcome
from github_orchestrator.conversation import Conversation, ConversationState, Denied
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import fake_settings
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.conversation.support import (
    THE_PR,
    WORKTREE,
    at,
    commit_fix,
    drain,
    hear,
    on_github,
    propose,
    repo_at,
    said,
    start_run,
    world,
)

KEY = "PRRT_one"
NOW = "2026-09-01T10:09:00Z"
QUESTION = "Stamp both bounds with clock_timestamp(), or keep now() for the lower one?"
CONTEXT = "Every test in the file failed: production stamps now() inside the test's transaction."
OPTIONS = ("Use clock_timestamp() in production too", "Keep now() and widen the lower bound")


class Bench:
    def __init__(self, settings):
        self.agent_runs = FakeAgentRuns(FakePrProcesses())
        self.world = world(settings, agent_runs=self.agent_runs, clock=at(NOW),
                           working_copies=FakeWorkingCopies(),
                           pr_processes=self.agent_runs.pr_processes)
        self.working_copies = self.world.working_copies
        repo_at(self.working_copies, WORKTREE, {"f": "old\n"})
        self.threads = self.world.threads()
        on_github(self.world.github, KEY, said(1, "use one helper for both bounds"))
        hear(self.threads)

    def stored(self) -> Conversation:
        return self.threads.get(KEY)

    def checkout(self) -> str:
        return self.working_copies.thread_checkout(THE_PR, KEY)

    def ask(self, question=QUESTION, context=CONTEXT, options=OPTIONS):
        with self.threads.editing(KEY) as editable:
            return editable.ask(question, context, options)

    def plan(self, *steps):
        with self.threads.editing(KEY) as editable:
            editable.plan([(step, None) for step in steps])

    def step_done(self, *indexes):
        with self.threads.editing(KEY) as editable:
            editable.step_done(indexes)


@pytest.fixture
def bench(tmp_path):
    return Bench(fake_settings(tmp_path))


def _running(bench):
    start_run(bench.world, bench.threads, finishes=False)


def _in_session(bench):
    propose(bench.world, bench.threads, KEY)
    bench.world.pr_processes.open(THE_PR, Path(WORKTREE))
    with bench.threads.editing(KEY) as editable:
        editable.start_session()
    drain(bench.threads)


@pytest.mark.parametrize("reach", [_running, _in_session])
def test_an_agent_that_asks_puts_its_question_before_you(bench, reach):
    reach(bench)

    outcome = bench.ask()

    assert not isinstance(outcome, Denied), outcome
    conversation = bench.stored()
    assert conversation.standing is ConversationState.READY
    assert conversation.fix.is_asking
    question = conversation.fix.question
    assert (question.text, question.context, question.options) == (QUESTION, CONTEXT, OPTIONS)


def test_a_question_is_no_proposal_to_approve(bench):
    _running(bench)

    bench.ask()

    assert bench.stored().proposal is None


def test_a_question_keeps_the_plan_as_it_stands(bench):
    _running(bench)
    bench.plan("stamp the upper bound", "stamp the lower bound")
    bench.step_done(1)

    bench.ask()

    assert [step.done for step in bench.stored().fix.plan] == [True, False]


def test_a_question_spends_no_attempt(bench):
    _running(bench)

    bench.ask()

    assert bench.stored().fix.attempts == 0


def test_a_run_that_asked_and_then_ended_still_asks(bench):
    start_run(bench.world, bench.threads)
    bench.ask()

    bench.threads.tick(FakeNotifications(), on_hold=False)

    assert bench.stored().fix.is_asking


@pytest.mark.parametrize("reach", [lambda bench: None,
                                   lambda bench: propose(bench.world, bench.threads, KEY)])
def test_a_fix_nobody_is_working_on_asks_nothing(bench, reach):
    reach(bench)
    before = bench.stored().fix

    outcome = bench.ask()

    assert isinstance(outcome, Denied)
    assert bench.stored().fix == before


def _asked(bench):
    _running(bench)
    bench.ask()
    bench.world.pr_processes.open(THE_PR, Path(WORKTREE))


def _answer(bench):
    with bench.threads.editing(KEY) as editable:
        outcome = editable.start_session()
    drain(bench.threads)
    return outcome


def test_answering_a_question_continues_the_agent_s_conversation_in_a_session(bench):
    _asked(bench)

    outcome = _answer(bench)

    assert not isinstance(outcome, Denied), outcome
    assert bench.stored().standing is ConversationState.IN_SESSION
    [answering] = bench.agent_runs.answering
    assert answering.key == KEY


def test_answering_a_question_starts_the_attempts_over(bench):
    start_run(bench.world, bench.threads)
    with bench.threads.editing(KEY) as editable:
        editable.fail("the first attempt broke")
    _asked(bench)
    assert bench.stored().fix.attempts == 1

    _answer(bench)

    assert bench.stored().fix.attempts == 0


def test_a_session_that_ends_without_reporting_leaves_the_same_question(bench):
    _asked(bench)
    _answer(bench)

    with bench.threads.editing(KEY) as editable:
        editable.session_gone()

    fix = bench.stored().fix
    assert fix.is_asking
    assert fix.question.text == QUESTION


def test_a_session_that_asks_again_replaces_the_question(bench):
    _asked(bench)
    _answer(bench)

    bench.ask("A second question?", "the answer opened another fork", ())

    assert bench.stored().fix.question.text == "A second question?"


def test_a_session_that_proposes_a_fix_leaves_no_question(bench):
    _asked(bench)
    _answer(bench)

    with bench.threads.editing(KEY) as editable:
        editable.ready(commit_fix(bench.world, KEY), tests="passed")

    fix = bench.stored().fix
    assert fix.is_proposed
    assert fix.question is None


def _asked_over_a_proposal(bench):
    proposed = propose(bench.world, bench.threads, KEY).fix.thread_sha
    with bench.threads.editing(KEY) as editable:
        editable.rework(note="use clock_timestamp() for both bounds")
    start_run(bench.world, bench.threads, finishes=False)
    commit_fix(bench.world, KEY, {"f": "half done\n"}, message="Stamp the upper bound")
    bench.working_copies.edit(bench.checkout(), "f", "uncommitted\n")
    bench.ask()
    return proposed


def _drop(bench):
    with bench.threads.editing(KEY) as editable:
        outcome = editable.drop_question()
    drain(bench.threads)
    return outcome


def test_dropping_a_question_goes_back_to_the_last_proposal(bench):
    proposed = _asked_over_a_proposal(bench)

    outcome = _drop(bench)

    assert not isinstance(outcome, Denied), outcome
    fix = bench.stored().fix
    assert fix.is_proposed
    assert fix.question is None
    assert fix.thread_sha == proposed
    assert bench.working_copies.head_of(bench.checkout()) == str(proposed)
    assert bench.working_copies.edits_at(bench.checkout()) == {}


def test_dropping_the_question_of_a_first_run_fails_it(bench):
    _running(bench)
    commit_fix(bench.world, KEY)
    bench.ask()

    _drop(bench)

    fix = bench.stored().fix
    assert fix.has_failed
    assert fix.reason == "question dropped"
    assert bench.working_copies.head_of(bench.checkout()) == str(fix.base_sha)


def test_only_a_question_can_be_dropped(bench):
    propose(bench.world, bench.threads, KEY)

    assert isinstance(_drop(bench), Denied)


def test_a_question_deferred_comes_back_when_it_wakes(bench):
    _asked(bench)
    with bench.threads.editing(KEY) as editable:
        editable.place(ConversationState.DEFERRED, note="ask the team")
    with bench.threads.editing(KEY) as editable:
        editable.unpark()

    fix = bench.stored().fix
    assert bench.stored().standing is ConversationState.READY
    assert fix.is_asking
    assert fix.question.text == QUESTION


def test_a_question_rejected_closes_the_thread_and_its_worktree(bench):
    _asked(bench)

    with bench.threads.editing(KEY) as editable:
        outcome = editable.reject()
    drain(bench.threads)

    assert not isinstance(outcome, Denied), outcome
    assert bench.stored().standing is ConversationState.DONE
    assert not bench.working_copies.holds_thread(THE_PR, KEY)


def test_a_question_cannot_be_approved_or_sent_back(bench):
    _asked(bench)

    with bench.threads.editing(KEY) as editable:
        assert isinstance(editable.approve(), Denied)
        assert isinstance(editable.rework(note="try again"), Denied)


LAST_WORDS = "Every test in the file now fails. Shall I change production, or widen the bound?"


def _silent_run(bench, *, words=LAST_WORDS):
    bench.agent_runs.script(Outcome(events=(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Looking."}]}},
        {"type": "result", "subtype": "success", "is_error": False, "result": words},
    )))
    drain(bench.threads)


def test_a_run_that_stops_without_reporting_proposes_its_commit_with_its_last_words(bench):
    _silent_run(bench)
    commit_fix(bench.world, KEY)

    drain(bench.threads)

    fix = bench.stored().fix
    assert fix.is_proposed
    assert fix.tests == "unverified"
    assert fix.last_words == LAST_WORDS


def test_a_run_that_stops_without_reporting_or_committing_says_what_it_last_said(bench):
    _silent_run(bench)

    drain(bench.threads)

    assert bench.stored().fix.reason == f"run exited without reporting: {LAST_WORDS}"


def test_a_codex_run_that_stops_without_reporting_keeps_its_last_message(bench):
    bench.agent_runs.script(Outcome(events=(
        {"type": "item.completed", "item": {"type": "agent_message", "text": LAST_WORDS}},
        {"type": "turn.completed"},
    )))
    drain(bench.threads)
    commit_fix(bench.world, KEY)

    drain(bench.threads)

    assert bench.stored().fix.last_words == LAST_WORDS


def test_a_run_that_asked_tells_you_its_question(bench):
    start_run(bench.world, bench.threads)
    bench.ask()
    news = FakeNotifications()

    bench.threads.tick(news, on_hold=False)

    assert [(posted.title, posted.body) for posted in news.posted] == [
        (f"Agent question on #{THE_PR.number}", QUESTION)]


def test_a_run_that_stopped_without_reporting_announces_its_commit_with_its_last_words(bench):
    _silent_run(bench)
    commit_fix(bench.world, KEY)
    news = FakeNotifications()

    bench.threads.tick(news, on_hold=False)

    [ready] = news.gathered
    assert ready.gist == LAST_WORDS


def test_a_run_that_reports_leaves_no_last_words_behind(bench):
    _silent_run(bench)
    commit_fix(bench.world, KEY)
    drain(bench.threads)
    with bench.threads.editing(KEY) as editable:
        editable.rework(note="widen the bound")
    start_run(bench.world, bench.threads, finishes=False)

    bench.ask()

    assert bench.stored().fix.last_words is None
