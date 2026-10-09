import dataclasses
import itertools
from dataclasses import field

import pytest

from github_orchestrator.agent_runs.fake import (
    FakeAgentRuns,
    FakeRun,
    FixingCheck,
    Outcome,
)
from github_orchestrator.board_api.fake import FakeBoardApi
from github_orchestrator.board_api.interface import Dashboards
from github_orchestrator.desktop import Badge
from github_orchestrator.github import PullRequestState
from github_orchestrator.notifications.fake import FakeNotifications, Posted
from github_orchestrator.pr_event_queue import Worklist
from github_orchestrator.pr_event_queue.fake import Queue
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.conversation.support import hear, on_github, propose, said
from tests.pr_event_queue.support import (
    EPOCH,
    ci_failed,
    ci_succeeded,
    closed,
    in_flight_of,
    pending_of,
    queue_of,
    unmergeable,
)
from tests.pr_manager.support import manager_over, seed_state
from tests.settings.support import disk_holds

WORKING = {"type": "assistant", "message": {"content": [{"type": "text", "text": "working"}]}}
TERMINATED = -15


@dataclasses.dataclass
class HeldRuns(FakeAgentRuns):
    runs: list[FakeRun] = field(default_factory=list)
    exploding: bool = False
    on_start: object = None

    def fix_check(self, worktree, pr, event_type, *, check, summary, push):
        return self._held(super().fix_check(worktree, pr, event_type, check=check,
                                            summary=summary, push=push))

    def carry_on(self, worktree, pr):
        return self._held(super().carry_on(worktree, pr))

    def rebase(self, worktree, pr, event_type, *, reason):
        return self._held(super().rebase(worktree, pr, event_type, reason=reason))

    def _held(self, run):
        if self.exploding:
            run.pump = _explode
        self.runs.append(run)
        if self.on_start is not None:
            self.on_start()
        return run


def _explode():
    raise RuntimeError("pipe exploded")


def _runs(*outcomes, **fields):
    return HeldRuns(FakePrProcesses(), **fields).script(*outcomes)


def _alive():
    return _runs(Outcome(events=(WORKING,), finishes=False))


CARRY_ON = "carry on from the board"


def _over(settings, *script, **modules):
    board = FakeBoardApi()
    script = tuple((lambda: board.panel.carry_on()) if item == CARRY_ON else item
                   for item in script)
    return manager_over(settings, *script, board=board, **modules)


def _shown(manager):
    return manager.board.panel.dashboard()


def _types(manager):
    return [event.kind for event in pending_of(manager.event_queue, a_pr(1, "o/n"))]


THE_PR = a_pr(1, "o/n")


COMMENT_IDS = itertools.count(1)


def _on_github(manager, *keys):
    for key in keys:
        on_github(manager.github, key, said(next(COMMENT_IDS), key, author="alice"), pr=THE_PR)


def _activity(manager, *keys):
    _on_github(manager, *keys)
    polled = manager.conversation_managers.of(THE_PR).poll(PullRequestState())
    polled.commit()
    manager.event_queue.add_thread_activity(THE_PR, polled.activity)


def _heard(manager, *keys):
    _on_github(manager, *keys)
    threads = manager.conversation_managers.of(THE_PR)
    hear(threads)
    return threads


def _stored_keys(manager):
    return [conversation.key
            for conversation in manager.conversation_managers.of(a_pr(1, "o/n")).all()]


def _with_config(settings, **config):
    return dataclasses.replace(settings, config=dataclasses.replace(settings.config, **config))


def _in_a_repo(tmp_path):
    working_copies = FakeWorkingCopies()
    working_copies.add_repo(tmp_path, {"README": "hello"}, "first")
    return working_copies


def test_an_idle_manager_carries_out_ci_failed_and_holds_it_in_flight_while_its_run_lives(settings, tmp_path):
    seed_state(settings, title="t", url="u")
    runs = _alive()
    manager = manager_over(settings, None, is_author=True, worktree=tmp_path, agent_runs=runs)
    manager.event_queue.add(a_pr(1, "o/n"), ci_failed('tests'))
    manager.run()
    [started] = runs.started
    assert started.work == FixingCheck("tests", None, True)
    assert _shown(manager).working_on == "ci-failed"
    assert in_flight_of(manager.event_queue, THE_PR) == [ci_failed('tests')]


def test_with_claude_disabled_ci_failed_is_drained_without_a_run(settings, tmp_path):
    runs = _runs()
    manager = manager_over(_with_config(settings, agents_enabled=False), is_author=True, worktree=tmp_path,
                           agent_runs=runs)
    manager.event_queue.add(a_pr(1, "o/n"), ci_failed('tests'))
    manager.run()
    assert runs.started == []
    assert "Agents are disabled" in manager.pr_processes.read(tmp_path)
    assert pending_of(manager.event_queue, a_pr(1, "o/n")) == []


def test_an_event_that_cannot_be_carried_out_is_marked_failed(settings, tmp_path):
    runs = _runs()
    reached = []
    manager = manager_over(settings, lambda: reached.append(True), is_author=True,
                           worktree=tmp_path / "gone", agent_runs=runs)
    manager.event_queue.add(a_pr(1, "o/n"), ci_failed('tests'))
    manager.run()
    assert runs.started == []
    assert queue_of(manager.event_queue, a_pr(1, "o/n")) == Queue(a_pr(1, "o/n"), ())
    assert [failed.event.kind for failed in manager.event_queue.failed_since(EPOCH)] == ["ci-failed"]
    assert reached == [True]


def test_a_run_started_is_kept_even_when_finishing_its_event_fails(settings, tmp_path):
    seed_state(settings, title="t", url="u")
    runs = _alive()
    manager = _over(settings, None, is_author=True, worktree=tmp_path, agent_runs=runs)
    manager.event_queue.add(a_pr(1, "o/n"), unmergeable())
    queue = next(settings.queues_dir.glob("*/*/*"))
    runs.on_start = lambda: queue.chmod(0o555)
    try:
        manager.run()
    finally:
        queue.chmod(0o755)
    assert _shown(manager).working_on == "became-unmergeable"
    assert [entry.event.kind for entry in queue_of(manager.event_queue, a_pr(1, "o/n")).in_flight] == ["became-unmergeable"]


def test_a_notice_is_carried_out_and_the_manager_keeps_going(settings, tmp_path):
    seed_state(settings, title="t", url="u")
    notifications = FakeNotifications()
    runs = _runs()
    reached = []
    manager = _over(settings, None, lambda: reached.append(True), is_author=True,
                    worktree=tmp_path, notifications=notifications, agent_runs=runs)
    manager.event_queue.add(a_pr(1, "o/n"), ci_succeeded('tests'))
    manager.run()
    assert notifications.posted == [
        Posted(a_pr(1, "o/n"), Badge.INFO, "CI passed — PR #1", "Checks passed: tests (success)"),
    ]
    assert runs.started == []
    assert _shown(manager).working_on is None
    assert reached == [True]
    assert not manager.event_queue.is_torn_down(a_pr(1, "o/n"))


def test_a_live_run_keeps_ci_failed_queued(settings, tmp_path):
    seed_state(settings, title="t", url="u")
    runs = _alive()
    manager = _over(settings, CARRY_ON, lambda: manager.event_queue.add(a_pr(1, "o/n"), ci_failed('tests')),
                           None, is_author=True, worktree=tmp_path, agent_runs=runs)
    manager.run()
    assert len(runs.started) == 1
    assert runs.runs[0].last_action == "working"
    assert _shown(manager).working_on == "manual-continue"
    assert _types(manager) == ["ci-failed"]
    assert queue_of(manager.event_queue, a_pr(1, "o/n")).in_flight == []


def test_a_live_run_lets_thread_activity_past_a_queued_ci_failed(settings, tmp_path):
    seed_state(settings, title="t", url="u")
    runs = _alive()

    def queue_both():
        manager.event_queue.add(a_pr(1, "o/n"), ci_failed('tests'))
        _activity(manager, "PRRT_one")

    manager = _over(settings, CARRY_ON, queue_both, is_author=True, worktree=tmp_path, agent_runs=runs,
                           working_copies=_in_a_repo(tmp_path))
    manager.run()
    assert _stored_keys(manager) == ["PRRT_one"]
    assert _types(manager) == ["ci-failed"]
    assert queue_of(manager.event_queue, a_pr(1, "o/n")).in_flight == []
    assert _shown(manager).working_on == "manual-continue"


@pytest.mark.parametrize("script", [(), (CARRY_ON,)], ids=["idle", "run alive"])
def test_thread_activity_events_are_carried_out_one_a_tick_in_order(settings, tmp_path, script):
    seed_state(settings, title="t", url="u")
    seen = []

    def queue_two():
        _activity(manager, "t1")
        _activity(manager, "t2")

    manager = _over(settings, *script, queue_two,
                           lambda: seen.append(_stored_keys(manager)),
                           lambda: seen.append(_stored_keys(manager)),
                           is_author=True, worktree=tmp_path, agent_runs=_alive(),
                           working_copies=_in_a_repo(tmp_path))
    manager.run()
    assert seen == [["t1"], ["t1", "t2"]]
    assert pending_of(manager.event_queue, a_pr(1, "o/n")) == []
    assert _shown(manager).working_on == ("manual-continue" if script else None)


def test_ci_failed_held_back_by_a_live_run_is_carried_out_once_it_ends(settings, tmp_path):
    runs = _runs(Outcome(finishes=False), Outcome(finishes=False))
    held = []
    manager = _over(settings, CARRY_ON,
                           lambda: manager.event_queue.add(a_pr(1, "o/n"), ci_failed('tests')),
                           lambda: held.append((len(runs.started), _types(manager))),
                           lambda: runs.runs[0].terminate(),
                           None, is_author=True, worktree=tmp_path, agent_runs=runs)
    manager.run()
    assert held == [(1, ["ci-failed"])]
    assert len(runs.started) == 2
    assert runs.started[1].work == FixingCheck("tests", None, True)
    assert pending_of(manager.event_queue, a_pr(1, "o/n")) == []


def test_a_ci_fix_that_fails_is_tried_again_and_says_why(settings, tmp_path):
    runs = _runs(Outcome(exit_code=143), Outcome(finishes=False))
    manager = manager_over(settings, None, None, is_author=True, worktree=tmp_path, agent_runs=runs)
    manager.event_queue.add(THE_PR, ci_failed('tests'))
    manager.run()
    assert [started.work for started in runs.started] == [FixingCheck("tests", None, True)] * 2
    assert "CI fix for tests failed (exit 143); retry 1 of 3" in manager.pr_processes.read(tmp_path)


def test_a_ci_fix_is_retried_three_times_and_then_given_up(settings, tmp_path):
    runs = _runs(*[Outcome(exit_code=1)] * 5)
    manager = manager_over(settings, *[None] * 6, is_author=True, worktree=tmp_path, agent_runs=runs)
    manager.event_queue.add(THE_PR, ci_failed('tests'))
    manager.run()
    changes = manager.pr_processes.read(tmp_path)
    assert len(runs.started) == 4
    assert [f"retry {n} of 3" in changes for n in (1, 2, 3)] == [True] * 3
    assert "CI fix for tests failed (exit 1) after 3 retries; giving up" in changes
    assert pending_of(manager.event_queue, THE_PR) == []


def test_a_ci_fix_that_succeeds_is_not_tried_again(settings, tmp_path):
    runs = _runs(Outcome(exit_code=0), Outcome(exit_code=0))
    manager = manager_over(settings, None, None, is_author=True, worktree=tmp_path, agent_runs=runs)
    manager.event_queue.add(THE_PR, ci_failed('tests'))
    manager.run()
    assert len(runs.started) == 1
    assert queue_of(manager.event_queue, THE_PR) == Queue(THE_PR, ())


def test_a_ci_fix_its_last_manager_stopped_in_is_retried_instead_of_carried_on(settings, tmp_path):
    runs = _runs(Outcome(finishes=False), Outcome(finishes=False))
    runs.fix_check("/wt", THE_PR, "ci-failed", check="tests", summary=None, push=True).interrupt()
    runs = runs.restarted()
    manager = manager_over(settings, None, is_author=True, worktree=tmp_path, agent_runs=runs)
    manager.event_queue.add(THE_PR, ci_failed('tests'))
    manager.container.get(Worklist).next(THE_PR, is_author=True, agents_enabled=True)
    manager.run()
    assert [started.work for started in runs.started] == [FixingCheck("tests", None, True)] * 2
    assert ("CI fix for tests failed (the agent manager stopped before the run ended); retry 1 of 3"
            in manager.pr_processes.read(tmp_path))


def test_on_hold_carries_out_nothing_even_with_a_live_run(settings, tmp_path):
    disk_holds(settings.data_dir).set_on_hold(a_pr(1, "o/n"), True)
    runs = _alive()
    manager = _over(settings, CARRY_ON, None, is_author=True, worktree=tmp_path, agent_runs=runs)
    manager.event_queue.add(a_pr(1, "o/n"), ci_failed('tests'))
    _activity(manager, "t1")
    manager.run()
    assert len(runs.started) == 1
    assert _types(manager) == ["ci-failed", "thread-activity"]


def test_a_live_run_leaves_pr_closed_behind_the_events_before_it(settings, tmp_path):
    runs = _alive()

    def queue_both():
        manager.event_queue.add(a_pr(1, "o/n"), ci_failed('tests'))
        manager.event_queue.add(a_pr(1, "o/n"), closed(merged=True))

    reached = []
    manager = _over(settings, CARRY_ON, queue_both, lambda: reached.append(True), is_author=True,
                    worktree=tmp_path, agent_runs=runs)
    manager.run()
    assert _types(manager) == ["ci-failed", "pr-closed"]
    assert not manager.event_queue.is_torn_down(a_pr(1, "o/n"))
    assert reached == [True]


@pytest.mark.parametrize("on_hold", [False, True], ids=["running", "on-hold"])
def test_pr_closed_terminates_a_live_run_and_ends_the_manager(settings, tmp_path, on_hold):
    if on_hold:
        disk_holds(settings.data_dir).set_on_hold(a_pr(1, "o/n"), True)
    runs = _alive()
    reached = []
    manager = _over(settings, CARRY_ON,
                    lambda: manager.event_queue.add(a_pr(1, "o/n"), closed(merged=False)),
                    lambda: reached.append(True), is_author=True, worktree=tmp_path,
                    agent_runs=runs)
    manager.run()
    assert manager.event_queue.is_torn_down(a_pr(1, "o/n"))
    assert runs.last_run(a_pr(1, "o/n")).exit_code == TERMINATED
    assert reached == []


def test_a_run_whose_pump_fails_is_terminated_and_kept_as_the_last_run(settings, tmp_path):
    seed_state(settings, title="t", url="u")
    runs = _runs(Outcome(finishes=False), exploding=True)
    manager = _over(settings, CARRY_ON, None, is_author=True, worktree=tmp_path, agent_runs=runs)
    manager.run()
    assert runs.runs[0].is_alive() is False
    shown = _shown(manager)
    assert shown.working_on is None
    assert (shown.last_run_event, shown.last_run_exit_code) == ("manual-continue", TERMINATED)


def test_a_thread_run_started_on_one_tick_is_not_started_again_on_the_next(settings, tmp_path):
    seed_state(settings, title="t", url="u")
    runs = _runs(Outcome(finishes=False))
    manager = manager_over(settings, None, None, is_author=True, worktree=tmp_path, agent_runs=runs,
                           working_copies=_in_a_repo(tmp_path))
    _heard(manager, "PRRT_queued")
    manager.run()
    assert len(runs.started) == 1
    shown = _shown(manager)
    assert (shown.threads_queued, len(shown.threads_live), shown.threads_proposed) == (0, 1, 0)


def test_thread_runs_are_started_up_to_max_thread_runs(settings, tmp_path):
    runs = _runs(*[Outcome(finishes=False)] * 4)
    manager = manager_over(_with_config(settings, max_thread_runs=3), is_author=True, worktree=tmp_path,
                           agent_runs=runs, working_copies=_in_a_repo(tmp_path))
    _heard(manager, "PRRT_one", "PRRT_two", "PRRT_three", "PRRT_four")
    manager.run()
    assert len(runs.started) == 3


def test_on_hold_starts_no_thread_runs(settings, tmp_path):
    seed_state(settings, title="t", url="u")
    disk_holds(settings.data_dir).set_on_hold(a_pr(1, "o/n"), True)
    runs = _runs()
    manager = manager_over(settings, None, is_author=True, worktree=tmp_path, agent_runs=runs,
                           working_copies=_in_a_repo(tmp_path))
    _heard(manager, "PRRT_queued")
    manager.run()
    assert runs.started == []
    shown = _shown(manager)
    assert (shown.threads_queued, len(shown.threads_live), shown.threads_proposed) == (1, 0, 0)


def test_frozen_on_the_wrong_branch_starts_no_thread_runs(settings, tmp_path):
    seed_state(settings, branch="expected-branch")
    working_copies = _in_a_repo(tmp_path)
    runs = _runs()
    manager = manager_over(settings, None, is_author=True, worktree=tmp_path, agent_runs=runs,
                           working_copies=working_copies)
    _heard(manager, "PRRT_queued")
    working_copies.check_out(tmp_path, "some-other-branch")
    manager.run()
    assert runs.started == []
    assert manager.container.get(Dashboards).dashboard(THE_PR).frozen_on == "some-other-branch"


def test_the_dashboard_counts_queued_working_and_ready_threads(settings, tmp_path):
    seed_state(settings, title="t", url="u")
    runs = _runs()
    manager = manager_over(settings, is_author=True, worktree=tmp_path, agent_runs=runs,
                           working_copies=_in_a_repo(tmp_path))
    for key in ("PRRT_ready", "PRRT_gone"):
        propose(manager, _heard(manager, key), key, pr=THE_PR)
    manager.github.resolve_thread("PRRT_gone")
    _heard(manager, "PRRT_queued")
    runs.script(Outcome(finishes=False))
    manager.run()
    shown = _shown(manager)
    assert (shown.threads_queued, len(shown.threads_live), shown.threads_proposed) == (1, 0, 1)
