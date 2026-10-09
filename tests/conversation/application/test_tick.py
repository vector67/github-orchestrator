import logging

import pytest

from github_orchestrator.agent_runs.fake import (
    THREAD_EVENT_PREFIX,
    FakeAgentRuns,
    FixingThread,
    Outcome,
    RebasingFix,
)
from github_orchestrator.conversation import (
    ConversationState,
    OperationState,
)
from github_orchestrator.domain import Sha
from github_orchestrator.github.fake import Check, FakeGitHub
from github_orchestrator.notifications.fake import FakeNotifications, FixReady
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import fake_settings
from github_orchestrator.thread_records.fake import FakeThreadRecords
from tests.builders import a_pr
from tests.change_detection.support import failing, passing
from tests.conversation.support import (
    PR,
    REPO,
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
    world,
)
from tests.disk_layout import thread_file
from tests.thread_records.support import disk_thread_records

THE_PR = a_pr(PR, REPO)

KEY = "PRRT_1"
TERMINATED = -15
KEEPS_GOING = Outcome(finishes=False)
READ = {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Read", "input": {"file_path": "foo.py"}}]}}
BASH = {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Bash", "input": {"command": "uv run pytest"}}]}}


def _agent_runs(cls=FakeAgentRuns, **fields):
    return cls(FakePrProcesses(), **fields)


class FailsToLaunch(FakeAgentRuns):
    refused: frozenset[str] = frozenset()

    def fix(self, fix):
        if fix.key in self.refused:
            return "could not start claude: claude binary missing"
        return super().fix(fix)


class WatchesTheRecord(FakeAgentRuns):
    look = None
    seen: list = []

    def fix(self, fix):
        self.seen.append(self.look())
        return super().fix(fix)


def _pipe_gone():
    raise RuntimeError("pipe gone")


class PumpBreaks(FakeAgentRuns):
    broken: frozenset[str] = frozenset()

    def fix(self, fix):
        run = super().fix(fix)
        if fix.key in self.broken:
            run.pump = _pipe_gone
        return run


class CountingGitHub(FakeGitHub):
    def __init__(self):
        super().__init__()
        self.closed_asks = 0

    def is_closed(self, pr):
        self.closed_asks += 1
        return super().is_closed(pr)


def _world(settings, **fakes):
    here = world(settings, **fakes)
    repo_at(here.working_copies, WORKTREE, {"f": "base\n", "README": "hello"})
    return here


def _commented(here, threads, *keys: str) -> None:
    for number, key in enumerate(keys or (KEY,), start=1):
        on_github(here.github, key, said(100 + number, "rename this"))
    hear(threads)


def _ready_world(settings, *keys: str, **fakes):
    here = _world(settings, **fakes)
    threads = here.threads()
    _commented(here, threads, *keys)
    return here, threads


def _checkout(here, key: str = KEY) -> str:
    return here.working_copies.thread_checkout(THE_PR, key)


def _commit(here, key: str = KEY) -> str:
    return commit_fix(here, key, {"README": "fixed"})


def _read(threads, key: str = KEY):
    return threads.get(key)


def _exits(agent_runs, key: str = KEY):
    return [entry["exit_code"] for entry in agent_runs.ledger
            if entry["event"] == f"{THREAD_EVENT_PREFIX}{key}"]


def _started_in(agent_runs):
    return [started.worktree for started in agent_runs.started]


def _reported(here, threads, key: str = KEY) -> None:
    with threads.editing(key) as editable:
        reported = editable.ready(_commit(here, key))
    assert reported.fix.is_proposed, reported


def _rebasing(here, threads) -> Sha:
    propose(here, threads, KEY, {"f": "base\nfixed\n"})
    head = here.working_copies.commit(WORKTREE, {"f": "moved on\n"}, "moved")
    with threads.editing(KEY) as editable:
        editable.approve()
    drain(threads)
    return Sha(head)


def test_the_cap_holds_and_the_next_starts_when_a_slot_frees(tmp_path):
    agent_runs = _agent_runs().script(Outcome(), *[KEEPS_GOING] * 4)
    keys = [f"PRRT_{n}" for n in (1, 2, 3, 4, 5)]
    here, threads = _ready_world(fake_settings(tmp_path, max_thread_runs=4), *keys,
                                 agent_runs=agent_runs)

    threads.tick(FakeNotifications(), on_hold=False)

    assert threads.counts().live == 4
    assert threads.counts().queued == 1
    assert _started_in(agent_runs) == [_checkout(here, key) for key in keys[:4]]
    assert _read(threads, "PRRT_1").standing is ConversationState.WORKING
    assert _read(threads, "PRRT_5").standing is ConversationState.QUEUED

    _reported(here, threads, "PRRT_1")
    threads.tick(FakeNotifications(), on_hold=False)

    assert threads.counts().live == 4
    assert threads.counts().queued == 0
    assert _started_in(agent_runs)[-1] == _checkout(here, "PRRT_5")


def test_a_pass_that_may_not_schedule_pumps_but_starts_nothing(tmp_path):
    agent_runs = _agent_runs().script(Outcome(events=(READ,), finishes=False))
    here, threads = _ready_world(fake_settings(tmp_path, max_thread_runs=1),
                                 "PRRT_1", "PRRT_2", agent_runs=agent_runs)
    threads.tick(FakeNotifications(), on_hold=False)

    threads.tick(FakeNotifications(), on_hold=True)

    assert threads.activity(_read(threads, "PRRT_1")).last_action is not None
    assert len(agent_runs.started) == 1
    assert _read(threads, "PRRT_2").standing is ConversationState.QUEUED


def test_the_run_is_started_with_the_kind_the_fix_carries(settings):
    agent_runs = _agent_runs()
    here, threads = _ready_world(settings, agent_runs=agent_runs)

    head = _rebasing(here, threads)

    first, rebase = agent_runs.started
    assert isinstance(first.work, FixingThread)
    assert rebase.work == RebasingFix(rebase.work.fix, str(head))


def test_a_started_fix_carries_the_stamp_the_clock_gave_it(settings):
    here, threads = _ready_world(settings, clock=at("2026-09-07T12:00:00Z"))

    threads.tick(FakeNotifications(), on_hold=False)

    started = _read(threads).fix
    assert started.started_at == "2026-09-07T12:00:00Z"
    assert started.attempts == 1


def test_the_fix_is_running_on_the_record_before_the_run_is_launched(settings):
    agent_runs = _agent_runs(WatchesTheRecord)
    agent_runs.seen = []
    here, threads = _ready_world(settings, agent_runs=agent_runs)
    agent_runs.look = lambda: _read(threads).standing

    threads.tick(FakeNotifications(), on_hold=False)

    assert agent_runs.seen == [ConversationState.WORKING]


def test_a_launch_failure_retries_that_fix_and_starts_the_rest(settings):
    agent_runs = _agent_runs(FailsToLaunch).script(KEEPS_GOING)
    agent_runs.refused = frozenset({"PRRT_1"})
    here, threads = _ready_world(settings, "PRRT_1", "PRRT_2", agent_runs=agent_runs)

    threads.tick(FakeNotifications(), on_hold=False)

    failed = _read(threads, "PRRT_1")
    assert failed.standing is ConversationState.QUEUED
    assert failed.fix.reason == "failed to launch the agent run"
    assert _read(threads, "PRRT_2").standing is ConversationState.WORKING
    assert threads.counts().live == 1


def test_a_launch_failure_leaves_the_reason_in_the_log(settings, caplog):
    agent_runs = _agent_runs(FailsToLaunch).script(KEEPS_GOING)
    agent_runs.refused = frozenset({"PRRT_1"})
    _, threads = _ready_world(settings, agent_runs=agent_runs)

    with caplog.at_level(logging.WARNING):
        threads.tick(FakeNotifications(), on_hold=False)

    [failure] = [r for r in caplog.records if "claude binary missing" in r.getMessage()]
    assert "PRRT_1" in failure.getMessage()


def test_a_launch_failure_that_spends_the_budget_stamps_the_managers_clock(settings):
    agent_runs = _agent_runs(FailsToLaunch)
    agent_runs.refused = frozenset({"PRRT_1"})
    _, threads = _ready_world(settings, agent_runs=agent_runs,
                              clock=at("2026-09-12T08:30:00Z"))

    for _ in range(_read(threads).run_holder.attempts_allowed):
        threads.tick(FakeNotifications(), on_hold=False)

    settled = _read(threads)
    assert settled.fix.has_failed
    assert settled.decidable_at == "2026-09-12T08:30:00Z"


def test_nothing_is_spawned_while_claude_is_disabled(settings):
    agent_runs = _agent_runs()
    here = _world(settings, agent_runs=agent_runs)
    _commented(here, here.threads(agents_enabled=True), "PRRT_1", "PRRT_2")
    threads = here.threads(agents_enabled=False)

    threads.tick(FakeNotifications(), on_hold=False)

    assert agent_runs.started == []
    assert threads.counts().live == 0
    assert _read(threads, "PRRT_1").standing is ConversationState.QUEUED


def test_re_enabling_claude_starts_the_fixes_that_waited(settings):
    agent_runs = _agent_runs()
    here = _world(settings, agent_runs=agent_runs)
    _commented(here, here.threads(agents_enabled=True), "PRRT_1", "PRRT_2")
    here.threads(agents_enabled=False).tick(FakeNotifications(), on_hold=False)

    here.threads(agents_enabled=True).tick(FakeNotifications(), on_hold=False)

    assert sorted(_started_in(agent_runs)) == sorted(
        _checkout(here, key) for key in ("PRRT_1", "PRRT_2"))


def test_a_running_fix_with_no_live_run_is_requeued_then_scheduled(settings):
    agent_runs = _agent_runs().script(KEEPS_GOING)
    here, stranding = _ready_world(settings, agent_runs=agent_runs)
    stranding.tick(FakeNotifications(), on_hold=False)
    threads = here.threads()

    threads.tick(FakeNotifications(), on_hold=True)

    requeued = _read(threads)
    assert requeued.standing is ConversationState.QUEUED
    assert requeued.fix.started_at is None

    threads.tick(FakeNotifications(), on_hold=False)

    assert _read(threads).standing is ConversationState.WORKING
    assert _started_in(agent_runs) == [_checkout(here)] * 2
    assert isinstance(agent_runs.started[-1].work, FixingThread)


def _started(threads, key: str = KEY):
    threads.tick(FakeNotifications(), on_hold=False)
    return _read(threads, key)


def test_a_running_fix_with_a_live_run_is_left_alone(settings):
    agent_runs = _agent_runs().script(KEEPS_GOING)
    _, threads = _ready_world(settings, agent_runs=agent_runs)
    started = _started(threads)

    threads.tick(FakeNotifications(), on_hold=False)

    assert _read(threads) == started
    assert len(agent_runs.started) == 1
    assert _exits(agent_runs) == []
    assert threads.counts().live == 1


def test_a_run_that_exited_without_reporting_is_retried_before_it_is_failed(settings):
    _, threads = _ready_world(settings)
    _started(threads)

    threads.tick(FakeNotifications(), on_hold=False)

    settled = _read(threads)
    assert settled.standing is ConversationState.WORKING
    assert settled.fix.attempts == 2
    assert "without reporting" in settled.fix.reason


def test_the_last_attempt_settles_as_failed(settings):
    _, threads = _ready_world(settings)
    allowed = _read(threads).run_holder.attempts_allowed
    for _ in range(allowed):
        threads.tick(FakeNotifications(), on_hold=False)

    threads.tick(FakeNotifications(), on_hold=True)

    settled = _read(threads).fix
    assert settled.has_failed
    assert settled.attempts == allowed


def _timed(tmp_path, *outcomes, **fakes):
    now = [1000.0]
    agent_runs = _agent_runs(clock=lambda: now[0]).script(*(outcomes or (KEEPS_GOING,)))
    here, threads = _ready_world(fake_settings(tmp_path, agent_timeout=10),
                                 agent_runs=agent_runs, **fakes)
    return here, threads, agent_runs, now


def test_a_run_past_the_claude_timeout_is_terminated_and_retried(tmp_path):
    _, threads, agent_runs, now = _timed(tmp_path)
    _started(threads)
    now[0] += 11

    threads.tick(FakeNotifications(), on_hold=True)

    settled = _read(threads)
    assert settled.standing is ConversationState.QUEUED
    assert settled.fix.attempts == 1, "the attempt it timed out on stays spent"
    assert "agent_timeout" in settled.fix.reason
    assert _exits(agent_runs) == [TERMINATED]
    assert threads.counts().live == 0


def test_a_run_timed_out_for_good_stamps_the_managers_own_clock(tmp_path):
    _, threads, _, now = _timed(tmp_path, *[KEEPS_GOING] * 3,
                                clock=at("2026-09-12T08:30:00Z"))
    for _ in range(_read(threads).run_holder.attempts_allowed):
        _started(threads)
        now[0] += 11
        threads.tick(FakeNotifications(), on_hold=True)

    settled = _read(threads)
    assert settled.fix.has_failed
    assert settled.decidable_at == "2026-09-12T08:30:00Z"


def test_a_run_that_exited_leaving_a_commit_stamps_the_managers_own_clock(settings):
    here, threads = _ready_world(settings, clock=at("2026-09-12T08:30:00Z"))
    _started(threads)
    _commit(here)

    threads.tick(FakeNotifications(), on_hold=True)

    settled = _read(threads)
    assert settled.fix.is_proposed
    assert settled.decidable_at == "2026-09-12T08:30:00Z"


def test_a_run_past_the_timeout_is_stopped_even_after_the_agent_reported_ready(tmp_path):
    here, threads, agent_runs, now = _timed(tmp_path)
    _started(threads)
    _reported(here, threads)
    now[0] += 11

    threads.tick(FakeNotifications(), on_hold=True)

    assert _exits(agent_runs) == [TERMINATED]
    assert threads.counts().live == 0


def test_a_run_past_the_timeout_is_stopped_when_its_record_has_gone(tmp_path):
    here, threads, agent_runs, now = _timed(
        tmp_path, thread_records=disk_thread_records(tmp_path / "threads"))
    _started(threads)
    here.thread_records.forget(THE_PR)
    now[0] += 11

    threads.tick(FakeNotifications(), on_hold=True)

    assert _exits(agent_runs) == [TERMINATED]
    assert threads.counts().live == 0


def test_a_pass_that_falls_over_does_not_take_the_loop_down(settings):
    agent_runs = _agent_runs()
    records = FakeThreadRecords()
    _, threads = _ready_world(settings, agent_runs=agent_runs, thread_records=records)
    records.fail_lists(OSError("the store is gone"))

    threads.tick(FakeNotifications(), on_hold=False)

    assert agent_runs.started == []


def test_an_exception_settling_one_run_does_not_stop_the_others(settings):
    records = FakeThreadRecords()
    _, threads = _ready_world(settings, "PRRT_1", "PRRT_2", thread_records=records)
    threads.tick(FakeNotifications(), on_hold=False)
    records.refuse_lock("PRRT_1", RuntimeError("store exploded"))

    threads.tick(FakeNotifications(), on_hold=True)

    assert "without reporting" in _read(threads, "PRRT_2").fix.reason
    assert _read(threads, "PRRT_1").standing is ConversationState.WORKING
    assert threads.counts().live == 0


def test_an_exception_pumping_one_run_stops_that_run_and_no_other(settings):
    agent_runs = _agent_runs(PumpBreaks).script(KEEPS_GOING, KEEPS_GOING)
    agent_runs.broken = frozenset({"PRRT_1"})
    _, threads = _ready_world(settings, "PRRT_1", "PRRT_2", agent_runs=agent_runs)
    threads.tick(FakeNotifications(), on_hold=False)

    threads.tick(FakeNotifications(), on_hold=True)

    assert _exits(agent_runs, "PRRT_1") == [TERMINATED]
    assert _exits(agent_runs, "PRRT_2") == []
    assert threads.counts().live == 1


def test_the_runs_latest_action_is_published(settings):
    agent_runs = _agent_runs().script(Outcome(events=(READ, BASH), finishes=False))
    _, threads = _ready_world(settings, agent_runs=agent_runs)
    _started(threads)

    threads.tick(FakeNotifications(), on_hold=True)

    assert "uv run pytest" in threads.activity(_read(threads)).last_action


def test_an_action_that_will_not_be_written_does_not_cost_the_run(settings):
    agent_runs = _agent_runs().script(Outcome(events=(BASH,), finishes=False))
    records = FakeThreadRecords()
    _, threads = _ready_world(settings, agent_runs=agent_runs, thread_records=records)
    _started(threads)
    records.fail_saves(OSError("read-only store"))

    threads.tick(FakeNotifications(), on_hold=True)

    assert threads.activity(_read(threads)).last_action is None
    assert threads.counts().live == 1
    assert _read(threads).standing is ConversationState.WORKING


def test_a_stand_in_for_an_unreadable_record_never_stops_the_pr_scheduling(settings, tmp_path):
    agent_runs = _agent_runs()
    threads_dir = tmp_path / "threads"
    here, threads = _ready_world(settings, agent_runs=agent_runs,
                                 thread_records=disk_thread_records(threads_dir))
    thread_file(threads_dir, THE_PR, "PRRT_broken").write_text("[]")
    assert [c.key for c in threads.all() if c.is_unreadable] == [
        "PRRT_broken"]

    threads.tick(FakeNotifications(), on_hold=False)

    assert _started_in(agent_runs) == [_checkout(here)]


def test_a_queued_fix_of_a_conversation_that_is_not_open_is_never_started(settings):
    agent_runs = _agent_runs()
    here, threads = _ready_world(settings, "PRRT_1", "PRRT_2", agent_runs=agent_runs)
    here.github.resolve_thread("PRRT_1")
    hear(threads)
    here.github.delete_comment(THE_PR, here.github.thread("PRRT_2").kind, 102)
    lost(threads, "PRRT_2")
    assert _read(threads, "PRRT_1").standing is ConversationState.DONE
    assert _read(threads, "PRRT_2").is_removed

    threads.tick(FakeNotifications(), on_hold=False)

    assert agent_runs.started == []
    assert threads.counts().queued == 0


def test_an_absent_fix_is_never_scheduled(settings):
    agent_runs = _agent_runs()
    here = _world(settings, agent_runs=agent_runs)
    threads = here.threads(is_author=False)
    _commented(here, threads)

    threads.tick(FakeNotifications(), on_hold=False)

    assert agent_runs.started == []
    assert threads.counts().queued == 0


def _deferred(settings, until: str, *, before=None, **fakes):
    here, threads = _ready_world(settings, **fakes)
    propose(here, threads, KEY)
    if before is not None:
        before(here)
    with threads.editing(KEY) as editable:
        editable.place(ConversationState.DEFERRED, until=until)
    drain(threads)
    assert _read(threads).standing is ConversationState.DEFERRED
    return here, threads


def _pushed_at_a9296dba(here) -> None:
    here.polled(head_sha="a9296dba", is_author=True)


def _woken(threads):
    threads.tick(FakeNotifications(), on_hold=False)
    return _read(threads)


@pytest.mark.parametrize(("checks", "standing"), [
    ((passing(),), ConversationState.READY),
    ((failing(),), ConversationState.DEFERRED),
    ((Check("tests", "in_progress"),), ConversationState.DEFERRED),
], ids=["success", "failure", "pending"])
def test_a_ci_deferral_wakes_only_when_the_snapshot_says_ci_passed(settings, checks,
                                                                   standing):
    here, threads = _deferred(settings, "ci")
    here.polled(checks=checks, is_author=True)

    assert _woken(threads).standing is standing


def test_a_ci_deferral_with_no_snapshot_stays_parked(settings):
    _, threads = _deferred(settings, "ci")

    assert _woken(threads).standing is ConversationState.DEFERRED


@pytest.mark.parametrize("status", ["CLOSED", "MERGED"])
def test_a_pr_deferral_wakes_when_that_pr_closes(settings, status):
    now = [1000.0]
    here, threads = _deferred(settings, "pr:87", monotonic=lambda: now[0],
                              before=lambda here: here.github.add_pr(
                                  a_pr(87, REPO), status="OPEN"))
    here.github.add_pr(a_pr(87, REPO), status=status)
    now[0] += 60

    assert _woken(threads).standing is ConversationState.READY


def test_a_pr_deferral_sleeps_while_that_pr_is_open(settings):
    _, threads = _deferred(settings, "pr:87", before=lambda here: here.github.add_pr(
        a_pr(87, REPO), status="OPEN"))

    assert _woken(threads).standing is ConversationState.DEFERRED


def test_an_unknown_pr_closed_state_leaves_the_deferral_alone(settings):
    _, threads = _deferred(settings, "pr:87")

    assert _woken(threads).standing is ConversationState.DEFERRED


def test_a_deferral_wakes_when_the_head_moves(settings):
    here, threads = _deferred(settings, "push", before=_pushed_at_a9296dba)
    here.polled(head_sha="3f9c2a1b", is_author=True)

    stored = _woken(threads)
    assert stored.standing is ConversationState.READY
    assert stored.fix.reply_note == "woken: a new push landed"


def test_a_deferral_sleeps_while_the_head_stays(settings):
    here, threads = _deferred(settings, "push", before=_pushed_at_a9296dba)
    here.polled(head_sha="a9296dba", is_author=True)

    assert _woken(threads).standing is ConversationState.DEFERRED


def test_a_push_deferral_with_no_head_to_read_stays_parked(settings):
    here, threads = _deferred(settings, "push", before=_pushed_at_a9296dba)
    here.polled(branch="feature", is_author=True)

    assert _woken(threads).standing is ConversationState.DEFERRED


def test_a_pr_deferral_asks_github_once_a_poll_interval_not_once_a_pass(settings):
    github = CountingGitHub()
    github.add_pr(a_pr(87, REPO), status="OPEN")
    now = [1000.0]
    _, threads = _deferred(settings, "pr:87", github=github, monotonic=lambda: now[0])

    for _ in range(4):
        threads.tick(FakeNotifications(), on_hold=False)
    within_the_interval = github.closed_asks
    now[0] += 60
    threads.tick(FakeNotifications(), on_hold=False)

    assert within_the_interval == 1, (
        "the manager loop runs about once a second; asking GitHub every pass "
        "spends 3,600 REST calls an hour on one parked conversation")
    assert github.closed_asks == 2


def test_a_pass_with_nothing_deferred_never_asks_github_whether_a_pr_closed(settings):
    github = CountingGitHub()
    _, threads = _ready_world(settings, github=github)

    threads.tick(FakeNotifications(), on_hold=False)

    assert github.closed_asks == 0


def _ready_keys(threads) -> list[str]:
    news = FakeNotifications()
    threads.tick(news, on_hold=False)
    return [ready.key for ready in news.gathered if isinstance(ready, FixReady)]


def test_a_pass_announces_each_fix_whose_run_exited_with_a_commit_as_ready(settings):
    here, threads = _ready_world(settings)
    _started(threads)
    _commit(here)

    assert _ready_keys(threads) == [KEY]
    assert _read(threads).fix.is_proposed


def test_a_fix_the_agent_reported_before_exiting_is_announced_as_ready(settings):
    here, threads = _ready_world(settings)
    _started(threads)
    _reported(here, threads)

    assert _ready_keys(threads) == [KEY]


def test_a_pass_with_every_run_still_going_announces_nothing(settings):
    agent_runs = _agent_runs().script(KEEPS_GOING)
    _, threads = _ready_world(settings, agent_runs=agent_runs)
    _started(threads)

    assert _ready_keys(threads) == []


def test_pending_decisions_that_will_not_read_still_let_the_runs_move(settings, caplog):
    records = FakeThreadRecords()
    here, threads = _ready_world(settings, thread_records=records, agent_runs=_agent_runs())
    here.agent_runs.script(KEEPS_GOING)
    records.fail_lists(OSError("the board's pending decisions are on a disk that went away"),
                       times=1)

    with caplog.at_level(logging.ERROR):
        threads.tick(FakeNotifications(), on_hold=False)

    assert "the board's pending decisions could not be read" in caplog.text
    assert len(here.agent_runs.started) == 1


def test_an_on_hold_tick_leaves_the_decisions_waiting_and_starts_no_run(settings):
    here, threads = _ready_world(settings, agent_runs=_agent_runs())
    with threads.editing(KEY) as editable:
        editable.reply("on it")

    threads.tick(FakeNotifications(), on_hold=True)

    assert _read(threads).operations[-1].state is OperationState.PENDING
    assert here.github.thread(KEY).comments[1:] == ()
    assert here.agent_runs.started == []


def test_the_counts_say_what_is_queued_live_and_proposed(settings):
    here = _world(settings, agent_runs=_agent_runs())
    threads = here.threads()
    _commented(here, threads, "PRRT_c")
    propose(here, threads, "PRRT_c")
    here.agent_runs.script(KEEPS_GOING, KEEPS_GOING)
    on_github(here.github, "PRRT_a", said(201, "rename this"))
    on_github(here.github, "PRRT_b", said(202, "rename this"))
    hear(threads)

    before = threads.counts()
    threads.tick(FakeNotifications(), on_hold=False)

    assert (before.queued, before.live, before.proposed) == (2, 0, 1)
    assert (threads.counts().queued, threads.counts().live) == (0, 2)
