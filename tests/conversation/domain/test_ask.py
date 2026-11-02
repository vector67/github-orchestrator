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
