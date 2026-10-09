import pytest

from github_orchestrator.agent_runs.fake import (
    FakeAgentRuns,
    FixingThread,
    Outcome,
)
from github_orchestrator.conversation import (
    ConversationState,
    OperationKind,
    OperationState,
)
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import fake_settings
from tests.builders import a_pr
from tests.conversation.support import (
    PR,
    REPO,
    WORKTREE,
    World,
    drain,
    hear,
    on_github,
    propose,
    repo_at,
    said,
    world,
)

THE_PR = a_pr(PR, REPO)

KEY = "PRRT_1"
TERMINATED = -15


def _heard(settings, agent_runs: FakeAgentRuns | None = None, *, pr_run_live: bool = False,
           keys: tuple[str, ...] = (KEY,)):
    here = world(settings, agent_runs=agent_runs)
    repo_at(here.working_copies, WORKTREE, {"src/foo.py": "old\n"})
    threads = here.threads(pr_run_live=pr_run_live)
    for number, key in enumerate(keys, start=1):
        on_github(here.github, key, said(number, "rename this"), path="src/foo.py", line=4)
    hear(threads)
    return here, threads


def _proposed(settings, *, pr_run_live: bool = False):
    here, threads = _heard(settings, pr_run_live=pr_run_live)
    propose(here, threads, KEY, {"src/foo.py": "new\n"})
    return here, threads


def _conversation(threads):
    return threads.get(KEY)


def _work(here: World):
    [started] = here.agent_runs.started
    return started.work


def _agent_runs(runs_class: type[FakeAgentRuns] = FakeAgentRuns) -> FakeAgentRuns:
    windows = FakePrProcesses()
    return runs_class(windows)


def _asked_last(threads, kind: OperationKind):
    last = _conversation(threads).operations[-1]
    assert last.kind is kind
    return last


def test_a_queued_thread_s_run_starts_in_the_fix_s_workspace(settings):
    here, threads = _heard(settings)
    here.agent_runs.script(Outcome(finishes=False))

    threads.tick(FakeNotifications(), on_hold=False)

    [started] = here.agent_runs.started
    assert started.worktree == here.working_copies.thread_checkout(THE_PR, KEY)
    assert isinstance(_work(here), FixingThread)
    assert len(threads.counts().live) == 1
    assert _conversation(threads).standing is ConversationState.WORKING


def test_a_thread_run_is_recorded_as_that_thread_s_run(settings):
    here, threads = _heard(settings)
    threads.tick(FakeNotifications(), on_hold=False)

    threads.tick(FakeNotifications(), on_hold=True)

    assert [entry["event"] for entry in here.agent_runs.ledger] == [
        f"thread-fix-{KEY}"]
    assert here.agent_runs.last_run(THE_PR) is None


def test_runs_are_kept_per_thread(settings):
    here, threads = _heard(settings, keys=(KEY, "PRRT_2"))
    here.agent_runs.script(Outcome(finishes=False), Outcome(finishes=False))

    threads.tick(FakeNotifications(), on_hold=False)

    copies = here.working_copies
    assert sorted(started.worktree for started in here.agent_runs.started) == sorted(
        copies.thread_checkout(THE_PR, key) for key in (KEY, "PRRT_2"))
    assert len(threads.counts().live) == 2


class _Refusing(FakeAgentRuns):
    def fix(self, fix):
        raise OSError("no such binary")


def test_a_run_that_will_not_start_leaves_no_live_run(settings):
    _, threads = _heard(settings, agent_runs=_agent_runs(_Refusing))

    threads.tick(FakeNotifications(), on_hold=False)

    assert len(threads.counts().live) == 0
    assert _conversation(threads).standing is not ConversationState.WORKING


def test_pumping_publishes_what_the_run_is_doing(settings):
    here, threads = _heard(settings)
    here.agent_runs.script(Outcome(events=({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Read", "input": {"file_path": "/wt/loop.py"}}]}},),
        finishes=False))
    threads.tick(FakeNotifications(), on_hold=False)

    threads.tick(FakeNotifications(), on_hold=False)

    assert threads.activity(_conversation(threads)).last_action == "● Read loop.py"
    assert len(threads.counts().live) == 1


@pytest.mark.parametrize(("elapsed", "live", "exit_codes"), [
    (5.0, 1, []),
    (12.5, 0, [TERMINATED]),
])
def test_a_run_is_timed_from_when_it_started(tmp_path, elapsed, live, exit_codes):
    now = [100.0]
    agent_runs = _agent_runs()
    agent_runs.clock = lambda: now[0]
    _, threads = _heard(fake_settings(tmp_path, agent_timeout=10), agent_runs=agent_runs)
    agent_runs.script(Outcome(finishes=False))
    threads.tick(FakeNotifications(), on_hold=False)
    now[0] += elapsed

    threads.tick(FakeNotifications(), on_hold=True)

    assert len(threads.counts().live) == live
    assert [entry["exit_code"] for entry in agent_runs.ledger] == exit_codes


def test_a_run_that_has_exited_leaves_the_live_count(settings):
    _, threads = _heard(settings)
    threads.tick(FakeNotifications(), on_hold=False)
    assert len(threads.counts().live) == 1

    threads.tick(FakeNotifications(), on_hold=True)

    assert len(threads.counts().live) == 0


def test_a_stop_intent_terminates_the_thread_s_run(settings):
    here, threads = _heard(settings)
    here.agent_runs.script(Outcome(finishes=False))
    threads.tick(FakeNotifications(), on_hold=False)
    with threads.editing(KEY) as editable:
        editable.stop()

    drain(threads)

    assert [entry["exit_code"] for entry in here.agent_runs.ledger] == [TERMINATED]
    assert len(threads.counts().live) == 0
    assert _conversation(threads).fix.has_failed


def test_stopping_a_thread_with_no_live_run_touches_no_run(settings):
    here, threads = _heard(settings)
    with threads.editing(KEY) as editable:
        editable.stop()

    drain(threads)

    assert here.agent_runs.ledger == []
    assert _conversation(threads).fix.has_failed
    assert not _asked_last(threads, OperationKind.STOP).in_flight


class _Unkillable(FakeAgentRuns):
    def fix(self, fix):
        run = super().fix(fix)

        def refuse():
            raise OSError("could not signal the run")

        run.terminate = refuse
        return run


def test_a_run_that_could_not_be_killed_is_still_a_live_run(settings):
    agent_runs = _agent_runs(_Unkillable)
    _, threads = _heard(settings, agent_runs=agent_runs)
    agent_runs.script(Outcome(finishes=False))
    threads.tick(FakeNotifications(), on_hold=False)
    with threads.editing(KEY) as editable:
        editable.stop()

    drain(threads)

    assert len(threads.counts().live) == 1
    assert agent_runs.ledger == []


@pytest.mark.parametrize(("alive", "kept"), [(True, True), (False, False)])
def test_an_approval_waits_while_the_manager_s_own_run_is_alive(settings, alive, kept):
    _, threads = _proposed(settings, pr_run_live=alive)
    with threads.editing(KEY) as editable:
        editable.approve()

    drain(threads)

    assert _conversation(threads).latest_approval.in_flight is kept


def test_a_session_intent_opens_a_session_in_the_fix_s_workspace(settings):
    here, threads = _proposed(settings)
    with threads.editing(KEY) as editable:
        editable.start_session(steer="Keep the old name.")

    drain(threads)

    [session] = here.pr_processes.sessions[THE_PR]
    assert session.worktree == here.working_copies.thread_checkout(THE_PR, KEY)
    [opened] = here.agent_runs.sessions
    assert (opened.fix.key, opened.steer) == (KEY, "Keep the old name.")


def test_a_session_opened_with_a_brief_carries_its_pointed_lines_and_included_replies(settings):
    here = world(settings)
    repo_at(here.working_copies, WORKTREE, {"src/foo.py": "old\n"})
    threads = here.threads()
    on_github(here.github, KEY, said(1, "rename this"), said(2, "and the test", author="carol"),
              said(3, "not this", author="dave"), path="src/foo.py", line=4)
    hear(threads)
    propose(here, threads, KEY, {"src/foo.py": "new\n"})
    with threads.editing(KEY) as editable:
        editable.start_session(steer="Keep the old name.",
                               pointed=[("src/foo.py", 1, "new")], include=["carol"])

    drain(threads)

    [opened] = here.agent_runs.sessions
    assert [(one.file, one.line, one.text) for one in opened.fix.pointed] == [
        ("src/foo.py", 1, "new")]
    assert [reply.body for reply in opened.fix.replies] == ["and the test"]


def test_a_session_that_will_not_start_opens_nothing_and_is_refused_with_its_reason(settings):
    here, threads = _proposed(settings)
    here.pr_processes.refusal = "[Errno 2] No such file or directory: 'claude'"
    with threads.editing(KEY) as editable:
        editable.start_session()

    drain(threads)

    assert here.pr_processes.sessions == {}
    refused = _asked_last(threads, OperationKind.START_SESSION)
    assert (refused.state, refused.reason) == (OperationState.REFUSED, "[Errno 2] No such file or directory: 'claude'")
