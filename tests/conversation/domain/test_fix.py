from pathlib import Path

import pytest

from github_orchestrator.agent_runs.fake import FakeAgentRuns, FixingThread, RebasingFix
from github_orchestrator.agent_runs.fake import Outcome as RunOutcome
from github_orchestrator.conversation import (
    Classification,
    ConfidenceLevel,
    Conversation,
    ConversationState,
    Denied,
    ErrorCode,
    OperationKind,
)
from github_orchestrator.domain import Sha
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
    lost,
    on_github,
    propose,
    repo_at,
    said,
    start_run,
    world,
)

KEY = "PRRT_one"
NOW = "2026-09-01T10:09:00Z"
TIMEOUT = 60
TERMINATED = -15


class Bench:
    def __init__(self, settings):
        self.ticks = [0.0]
        self.agent_runs = FakeAgentRuns(FakePrProcesses(), clock=self.monotonic)
        self.world = world(settings, agent_runs=self.agent_runs, clock=at(NOW),
                           monotonic=self.monotonic, working_copies=FakeWorkingCopies(),
                           pr_processes=self.agent_runs.pr_processes)
        self.working_copies = self.world.working_copies
        self.base = repo_at(self.working_copies, WORKTREE, {"f": "old\n"})
        self.checkout = self.working_copies.thread_checkout(THE_PR, KEY)
        self.threads = self.world.threads()
        on_github(self.world.github, KEY, said(1, "rename this"))
        hear(self.threads)

    def monotonic(self):
        return self.ticks[0]

    def stored(self) -> Conversation:
        return self.threads.get(KEY)

    def later(self, seconds):
        self.ticks[0] += seconds

    def tick(self, *, on_hold=False):
        self.threads.tick(FakeNotifications(), on_hold=on_hold)

    def ready(self, sha=None, **reported):
        with self.threads.editing(KEY) as editable:
            return editable.ready(sha or commit_fix(self.world, KEY), **reported)

    def fail(self, reason="boom"):
        with self.threads.editing(KEY) as editable:
            return editable.fail(reason)

    def decline(self, classification=Classification.RISKY, reason="it wants a schema change"):
        with self.threads.editing(KEY) as editable:
            return editable.not_a_fix(classification, reason)

    def started(self):
        return len(self.agent_runs.started)


@pytest.fixture
def bench(tmp_path):
    return Bench(fake_settings(tmp_path, agent_timeout=TIMEOUT))


def _attempts(bench):
    return bench.stored().run_holder.attempts_allowed


def _spend(bench, attempts):
    for _ in range(attempts):
        start_run(bench.world, bench.threads)
        bench.fail("the tests would not run")


def _queued(bench):
    pass


def _running(bench):
    start_run(bench.world, bench.threads, finishes=False)


def _proposed(bench, **ready):
    propose(bench.world, bench.threads, KEY, **ready)


def _in_session(bench, **ready):
    _proposed(bench, **ready)
    bench.world.pr_processes.open(THE_PR, Path(WORKTREE))
    with bench.threads.editing(KEY) as editable:
        editable.start_session()
    drain(bench.threads)


def _declined(bench):
    _running(bench)
    bench.decline()


def _failed(bench):
    _spend(bench, _attempts(bench))


def _landing(bench):
    _proposed(bench)
    bench.working_copies.refuse_pushes("fatal: the remote hung up")
    with bench.threads.editing(KEY) as editable:
        editable.approve()
    drain(bench.threads)


def _landed(bench):
    _proposed(bench)
    with bench.threads.editing(KEY) as editable:
        editable.approve()
    drain(bench.threads)


def _resolved(bench):
    with bench.threads.editing(KEY) as editable:
        editable.resolve()
    drain(bench.threads)


def _removed(bench):
    bench.world.github.delete_comment(THE_PR, bench.world.github.thread(KEY).kind, 1)
    lost(bench.threads, KEY)


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
    reach, expected = REACHED[state]
    reach(bench)
    assert expected(bench.stored()), bench.stored()


def _shape(bench):
    conversation = bench.stored()
    fix = conversation.fix
    return (conversation.standing, fix.is_proposed, fix.is_declined, fix.has_failed,
            fix.picked, fix.pushed, fix.answered, fix.commits, fix.reason)


def _conflicting(bench):
    _proposed(bench)
    head = bench.working_copies.commit(WORKTREE, {"f": "theirs\n"}, "someone else")
    with bench.threads.editing(KEY) as editable:
        editable.approve()
    return head


def _rebasing(bench, *, finishes=False):
    head = _conflicting(bench)
    bench.agent_runs.script(RunOutcome(finishes=finishes))
    drain(bench.threads)
    assert bench.stored().fix.run.kind is OperationKind.REBASE
    return head


def test_a_started_run_stamps_the_fix_and_spends_an_attempt(bench):
    _spend(bench, 1)

    _running(bench)

    fix = bench.stored().fix
    assert bench.stored().standing is ConversationState.WORKING
    assert bench.stored().run_holder.attempts == 2
    assert fix.started_at == NOW
    started = bench.agent_runs.started[-1]
    assert started.worktree == bench.checkout
    assert isinstance(started.work, FixingThread)


def test_a_started_rebase_run_carries_the_head_it_must_land_on(bench):
    head = _rebasing(bench)

    started = bench.agent_runs.started[-1]
    assert started.worktree == bench.checkout
    assert started.work == RebasingFix(started.work.fix, head)


@pytest.mark.parametrize("state", ["running", "landed"])
def test_no_run_starts_on_a_fix_that_is_not_queued(bench, state):
    _put(bench, state)
    before, started = _shape(bench), bench.started()

    bench.tick()

    assert _shape(bench) == before
    assert bench.started() == started


def test_no_run_starts_on_a_conversation_that_is_no_longer_open(bench):
    _put(bench, "removed")

    bench.tick()

    assert bench.agent_runs.started == []


@pytest.mark.parametrize("state", ["running", "in_session", "proposed"])
def test_an_agent_proposes_a_commit_from_a_fix_it_is_working_on(bench, state):
    _spend(bench, 1)
    _put(bench, state)
    started = bench.started()

    outcome = bench.ready(tests="passed", tests_note="42 passed", note="renamed the helper")

    assert not isinstance(outcome, Denied), outcome
    fix = bench.stored().fix
    assert fix.is_proposed
    assert fix.commits[1] == Sha(bench.working_copies.head_of(bench.checkout))
    assert fix.tests == "passed"
    assert fix.tests_note == "42 passed"
    assert fix.agent_note == "renamed the helper"
    assert fix.reason is None, "the attempt that failed is not this one"
    assert bench.started() == started


def test_a_proposed_fix_may_re_report_a_corrected_sha(bench):
    _proposed(bench)

    bench.ready(tests="passed")

    assert bench.stored().fix.commits[1] == Sha(bench.working_copies.head_of(bench.checkout))


@pytest.mark.parametrize("state", ["queued", "landed"])
def test_a_fix_nobody_is_working_on_proposes_nothing(bench, state):
    _put(bench, state)
    before = _shape(bench)

    outcome = bench.ready("abc1234", tests="passed")

    assert isinstance(outcome, Denied)
    assert _shape(bench) == before


@pytest.mark.parametrize("state", ["resolved"])
def test_a_conversation_that_is_no_longer_open_takes_no_report(bench, state):
    _proposed(bench)
    _put(bench, state)

    assert isinstance(bench.ready("abc1234", tests="passed"), Denied)


@pytest.mark.parametrize("state", ["queued", "running"])
def test_an_agent_declines_a_conversation_it_judged_unsafe_to_fix(bench, state):
    _put(bench, state)
    started = bench.started()

    bench.decline()

    fix = bench.stored().fix
    assert fix.is_declined
    assert fix.classification is Classification.RISKY
    assert fix.reason == "it wants a schema change"
    assert bench.started() == started


def test_a_session_the_operator_gives_up_on_settles_declined(bench):
    _in_session(bench)

    outcome = bench.decline(Classification.NEEDS_HUMAN, "not worth it")

    assert not isinstance(outcome, Denied), outcome
    assert bench.stored().fix.is_declined


@pytest.mark.parametrize("state", ["proposed", "landed"])
def test_only_a_fix_an_agent_holds_can_be_declined(bench, state):
    _put(bench, state)
    before = _shape(bench)

    outcome = bench.decline(reason="no")

    assert isinstance(outcome, Denied)
    assert _shape(bench) == before


def test_a_failed_attempt_with_budget_left_is_queued_again_as_it_was(bench):
    head = _rebasing(bench)
    attempts = bench.stored().run_holder.attempts

    bench.fail("run exited without rebasing")

    conversation = bench.stored()
    fix = conversation.fix
    assert conversation.standing is ConversationState.LANDING
    assert fix.reason == "run exited without rebasing"
    assert conversation.run_holder.attempts == attempts
    assert fix.started_at is None
    assert (fix.run.kind, fix.run.onto) == (OperationKind.REBASE, Sha(head))


def test_a_failed_attempt_that_spends_the_budget_settles_failed(bench):
    _spend(bench, _attempts(bench) - 1)
    start_run(bench.world, bench.threads)

    bench.fail("boom")

    fix = bench.stored().fix
    assert fix.has_failed
    assert fix.reason == "boom"


@pytest.mark.parametrize("state", ["queued", "landed"])
def test_a_fix_with_no_run_of_its_own_fails_nothing(bench, state):
    _put(bench, state)
    before = _shape(bench)

    outcome = bench.fail()

    assert isinstance(outcome, Denied)
    assert _shape(bench) == before


def test_a_run_killed_for_its_timeout_is_stopped_and_fails_or_retries(bench):
    _spend(bench, _attempts(bench) - 1)
    _running(bench)

    bench.later(TIMEOUT + 1)
    bench.tick()

    fix = bench.stored().fix
    assert fix.has_failed
    assert fix.reason.startswith("run exceeded agent_timeout")
    assert bench.threads.counts().live == 0
    assert bench.agent_runs.ledger[-1]["exit_code"] == TERMINATED


def test_a_run_inside_its_timeout_is_left_running(bench):
    _running(bench)

    bench.later(TIMEOUT - 1)
    bench.tick()

    assert bench.stored().standing is ConversationState.WORKING
    assert bench.threads.counts().live == 1


def test_a_run_that_exited_leaving_a_commit_proposes_it_unverified(bench):
    start_run(bench.world, bench.threads)
    committed = commit_fix(bench.world, KEY)

    bench.tick(on_hold=True)

    fix = bench.stored().fix
    assert fix.is_proposed
    assert fix.commits[1] == Sha(committed)
    assert fix.tests == "unverified"
    assert fix.tests_note == ("run exited without reporting; commit found in "
                              "worktree")


def _rebased_onto(bench, head):
    working_copies = bench.working_copies
    working_copies.branches[working_copies.branch_at(bench.checkout)] = head


def test_a_rebase_run_that_landed_on_the_head_proposes_its_commit(bench):
    head = _rebasing(bench, finishes=True)
    _rebased_onto(bench, head)
    committed = commit_fix(bench.world, KEY)

    bench.tick(on_hold=True)

    fix = bench.stored().fix
    assert fix.is_proposed
    assert fix.commits[1] == Sha(committed)
    assert fix.tests == "unverified"
    assert fix.tests_note == ("run exited without reporting; rebased commit "
                              "found in worktree")


@pytest.mark.parametrize("scenario", ["head off the target", "head is the target",
                                      "no head at all"])
def test_a_rebase_run_that_did_not_rebase_fails_or_retries(bench, scenario):
    head = _rebasing(bench, finishes=True)
    if scenario == "head off the target":
        commit_fix(bench.world, KEY)
    if scenario == "head is the target":
        _rebased_onto(bench, head)
    if scenario == "no head at all":
        bench.working_copies.lose_worktree(bench.checkout)

    bench.tick(on_hold=True)

    assert bench.stored().standing is ConversationState.LANDING
    assert bench.stored().fix.reason == "run exited without rebasing"


@pytest.mark.parametrize("state", ["queued", "proposed"])
def test_a_run_that_exited_settles_nothing_on_a_fix_that_was_not_running(bench, state):
    start_run(bench.world, bench.threads)
    if state == "queued":
        bench.fail("the tests would not run")
    else:
        bench.ready(tests="passed")
    before = _shape(bench)

    bench.tick(on_hold=True)

    assert bench.threads.counts().live == 0
    assert _shape(bench) == before


def test_a_running_fix_whose_run_is_gone_is_queued_again(bench):
    head = _rebasing(bench)
    attempts = bench.stored().run_holder.attempts
    started = bench.started()
    restarted = bench.world.threads()

    restarted.tick(FakeNotifications(), on_hold=True)

    conversation = restarted.get(KEY)
    fix = conversation.fix
    assert conversation.standing is ConversationState.LANDING
    assert conversation.run_holder.attempts == attempts, (
        "the attempt was spent even though nothing came back")
    assert fix.started_at is None
    assert (fix.run.kind, fix.run.onto) == (OperationKind.REBASE, Sha(head))
    assert bench.started() == started


@pytest.mark.parametrize("state", ["queued", "landing"])
def test_a_fix_that_was_not_running_is_not_requeued_by_a_lost_run(bench, state):
    _put(bench, state)
    before = _shape(bench)
    restarted = bench.world.threads()

    restarted.tick(FakeNotifications(), on_hold=True)

    assert _shape(bench) == before


def _ready(bench):
    _proposed(bench)


def _declined_by_the_agent(bench):
    _declined(bench)


def _timed_out_for_good(bench):
    _spend(bench, _attempts(bench) - 1)
    _running(bench)
    bench.later(TIMEOUT + 1)
    bench.tick()


def _exited_leaving_a_commit(bench):
    start_run(bench.world, bench.threads)
    commit_fix(bench.world, KEY)
    bench.tick(on_hold=True)


def _exited_with_nothing_left(bench):
    _spend(bench, _attempts(bench) - 1)
    start_run(bench.world, bench.threads)
    bench.tick(on_hold=True)


DECIDABLE = {
    "reported ready": _ready,
    "declined by the agent": _declined_by_the_agent,
    "out of attempts": _failed,
    "timed out for good": _timed_out_for_good,
    "exited leaving a commit": _exited_leaving_a_commit,
    "exited with nothing left": _exited_with_nothing_left,
}


@pytest.mark.parametrize("moment", sorted(DECIDABLE))
def test_a_fix_that_becomes_yours_to_decide_stamps_the_moment(bench, moment):
    assert bench.stored().decidable_at is None

    DECIDABLE[moment](bench)

    assert bench.stored().standing is ConversationState.READY
    assert bench.stored().decidable_at == NOW


def _failed_with_budget_left(bench):
    _spend(bench, 1)


def _timed_out_with_budget_left(bench):
    _running(bench)
    bench.later(TIMEOUT + 1)
    bench.tick(on_hold=True)


def _exited_with_budget_left(bench):
    start_run(bench.world, bench.threads)
    bench.tick(on_hold=True)


REQUEUED = {
    "failed with budget left": _failed_with_budget_left,
    "timed out with budget left": _timed_out_with_budget_left,
    "exited with budget left": _exited_with_budget_left,
}


@pytest.mark.parametrize("moment", sorted(REQUEUED))
def test_a_fix_going_back_to_the_agent_stamps_nothing(bench, moment):
    REQUEUED[moment](bench)

    requeued = bench.stored()
    assert requeued.standing is ConversationState.QUEUED
    assert requeued.decidable_at is None


def test_a_started_run_stamps_nothing_the_operator_could_decide_on(bench):
    _running(bench)

    assert bench.stored().standing is ConversationState.WORKING
    assert bench.stored().decidable_at is None


def test_an_agent_says_what_its_fix_does_and_how_sure_it_is_of_it(bench):
    _running(bench)

    bench.ready(tests="passed", summary="Raise MissingTaxRate instead of skipping.",
                confidence="medium",
                confidence_note="Callers in cli/billing.py may rely on the silent skip.")

    fix = bench.stored().fix
    assert fix.summary == "Raise MissingTaxRate instead of skipping."
    assert fix.confidence is ConfidenceLevel.MEDIUM
    assert fix.confidence_note == (
        "Callers in cli/billing.py may rely on the silent skip.")


@pytest.mark.parametrize("level", ["low", "medium", "high"])
def test_every_level_this_board_knows_is_taken(bench, level):
    _running(bench)

    outcome = bench.ready(confidence=level)

    assert not isinstance(outcome, Denied), outcome
    assert bench.stored().fix.confidence is ConfidenceLevel(level)


@pytest.mark.parametrize("level", ["certain", ""])
def test_a_confidence_that_is_no_level_of_ours_is_refused(bench, level):
    _running(bench)

    outcome = bench.ready(confidence=level)

    assert isinstance(outcome, Denied)
    assert outcome.code == ErrorCode.INTERNAL_REFUSAL
    assert bench.stored().standing is ConversationState.WORKING
    assert bench.stored().fix.commits is None


def test_a_session_that_reports_without_a_summary_is_not_made_to_invent_one(bench):
    _in_session(bench)

    outcome = bench.ready(tests="passed")

    assert not isinstance(outcome, Denied), outcome
    fix = bench.stored().fix
    assert fix.is_proposed
    assert (fix.summary, fix.confidence, fix.confidence_note) == (None, None, None)


def test_a_declined_conversation_carries_nothing_a_fix_would_have_said(bench):
    with bench.threads.editing(KEY) as editable:
        editable.plan([("raise instead", "a.py")])
    _in_session(bench, summary="Raise instead of skipping.", confidence="high",
                confidence_note="Nothing else reads it.")
    said_before = bench.stored().fix
    assert said_before.plan and said_before.summary and said_before.confidence

    bench.decline()

    fix = bench.stored().fix
    assert fix.is_declined
    assert fix.plan == ()
    assert (fix.summary, fix.confidence, fix.confidence_note) == (None, None, None)
