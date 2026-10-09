from datetime import datetime, timezone

import pytest

from github_orchestrator.agent_runs.fake import FakeAgentRuns, Outcome
from github_orchestrator.board_api.fake import FakeBoardApi
from github_orchestrator.conversation import Classification
from github_orchestrator.desktop import Badge
from github_orchestrator.notifications.fake import FakeNotifications, FixReady, Posted
from github_orchestrator.pr_processes.fake import FakePrProcesses
from tests.conversation.support import (
    commit_fix,
    fake_conversation_managers,
    hear,
    on_github,
    repo_at,
    said,
)
from tests.pr_manager.scripted_terminal import ManualClock
from tests.pr_manager.support import THE_PR, manager_over, seed_state

KEY = "PRRT_1"


@pytest.fixture(autouse=True)
def _pr_state(settings):
    seed_state(settings, title="Test PR", url="https://github.com/o/n/pull/1")


@pytest.fixture
def clock():
    return ManualClock(datetime.now(timezone.utc))


@pytest.fixture
def notifications():
    return FakeNotifications()


@pytest.fixture
def runs(settings):
    return FakeAgentRuns(FakePrProcesses())


@pytest.fixture
def threads(runs, tmp_path):
    fake = fake_conversation_managers(runs)
    repo_at(fake.working_copies, tmp_path, {"f": "old\n"}, pr=THE_PR)
    fake.watch(THE_PR, is_author=True)
    return fake


def _commented(threads, author, body):
    on_github(threads.github, KEY, said(1, body, author=author), pr=THE_PR)
    hear(threads.of(THE_PR))


def _gist(threads):
    return threads.of(THE_PR).get(KEY).gist


def _reported(threads, report):
    def reported():
        with threads.of(THE_PR).editing(KEY) as conversation:
            report(conversation)
    return reported


def _ready(threads, summary):
    def report():
        sha = commit_fix(threads, KEY, pr=THE_PR)
        with threads.of(THE_PR).editing(KEY) as editable:
            editable.ready(sha, summary=summary)
    return report


CARRY_ON = "carry on from the board"


def _run(settings, threads, tmp_path, clock, notifications, *script):
    board = FakeBoardApi()
    script = tuple((lambda: board.panel.carry_on()) if item == CARRY_ON else item
                   for item in script)
    return manager_over(settings, *script, worktree=tmp_path, clock=clock, board=board,
                        is_author=True, notifications=notifications,
                        agent_runs=threads.agent_runs, github=threads.github,
                        working_copies=threads.working_copies,
                        conversation_managers=threads).run()


def test_a_failed_run_is_posted_as_soon_as_it_ends(settings, tmp_path, clock, notifications,
                                                   runs, threads):
    runs.script(Outcome(exit_code=137))

    _run(settings, threads, tmp_path, clock, notifications, CARRY_ON, None)

    assert notifications.posted == [
        Posted(THE_PR, Badge.FAILED, "Run failed on n#1", "manual-continue exited 137"),
    ]


def test_a_run_that_succeeds_posts_nothing(settings, tmp_path, clock, notifications, runs,
                                           threads):
    runs.script(Outcome(exit_code=0))

    _run(settings, threads, tmp_path, clock, notifications, CARRY_ON, None)

    assert notifications.posted == []
    assert notifications.gathered == []


def test_a_proposed_fix_is_gathered_into_the_prs_fixes_ready(settings, tmp_path, clock,
                                                             notifications, threads):
    _commented(threads, "alice", "rename this helper")

    _run(settings, threads, tmp_path, clock, notifications,
         None, _ready(threads, "Renamed collapse to collapse_submission"), None)

    assert notifications.gathered == [
        FixReady(pr=THE_PR, key=KEY, gist=_gist(threads),
                 comments=(("alice", "rename this helper"),),
                 fix_summary="Renamed collapse to collapse_submission"),
    ]
    assert notifications.posted == []


def test_a_declined_comment_asks_for_your_call_at_once(settings, tmp_path, clock,
                                                        notifications, threads):
    _commented(threads, "carol", "looks great!")

    _run(settings, threads, tmp_path, clock, notifications, None,
         _reported(threads, lambda conversation: conversation.not_a_fix(
             Classification.ACKNOWLEDGEMENT, "praise, nothing to change")), None)

    assert notifications.posted == [
        Posted(THE_PR, Badge.NEEDS_YOU, "Comment needs your call on n#1",
               "carol\nacknowledgement: praise, nothing to change"),
    ]


def test_a_fix_that_failed_for_good_is_posted_at_once(settings, tmp_path, clock, notifications,
                                                      threads):
    _commented(threads, "alice", "rename the helper")
    attempts = threads.of(THE_PR).get(KEY).run_holder.attempts_allowed
    failing = _reported(threads, lambda conversation: conversation.fail(
        "run exited without reporting"))

    _run(settings, threads, tmp_path, clock, notifications,
         *[step for _ in range(attempts) for step in (None, failing)], None)

    assert threads.of(THE_PR).get(KEY).fix.has_failed
    assert notifications.posted == [
        Posted(THE_PR, Badge.FAILED, "Fix failed on n#1",
               f"{_gist(threads)}: run exited without reporting"),
    ]


def test_a_fix_sent_round_for_another_attempt_posts_nothing(settings, tmp_path, clock,
                                                            notifications, threads):
    _commented(threads, "alice", "rename it")
    threads.agent_runs.script(Outcome(), Outcome(finishes=False))

    _run(settings, threads, tmp_path, clock, notifications, None,
         _reported(threads, lambda conversation: conversation.fail("the tests would not run")), None)

    assert not threads.of(THE_PR).get(KEY).fix.has_failed
    assert notifications.posted == []
    assert notifications.gathered == []
