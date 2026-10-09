from datetime import datetime, timezone

from github_orchestrator.agent_runs.fake import Outcome as RunOutcome
from github_orchestrator.github import PullRequestState
from github_orchestrator.notifications.fake import FakeNotifications
from tests.conversation.support import (
    WORKTREE,
    hear,
    on_github,
    repo_at,
    said,
    world,
)


class _Clock:
    def __init__(self, *moments):
        self.moments = list(moments)

    def __call__(self):
        return self.moments.pop(0) if len(self.moments) > 1 else self.moments[0]


def _created_at(settings, keys, *moments):
    clock = _Clock(datetime(2025, 12, 2, tzinfo=timezone.utc))
    here = world(settings, clock=clock)
    repo_at(here.working_copies, WORKTREE)
    for number, key in enumerate(keys, start=101):
        on_github(here.github, key, said(number, "rename this", created_at="2025-12-01T00:00:00Z"))
    threads = here.threads()
    polled = threads.poll(PullRequestState())
    polled.commit()
    clock.moments = list(moments)

    threads.absorb(polled.activity)

    return [threads.get(key).created_at for key in keys]


def test_stamps_bump_a_clock_that_has_not_moved_by_one_microsecond(settings):
    frozen = datetime(2026, 1, 2, 3, 4, 5, 6, tzinfo=timezone.utc)

    assert _created_at(settings, ["PRRT_a", "PRRT_b", "PRRT_c"], frozen) == [
        "2026-01-02T03:04:05.000006Z",
        "2026-01-02T03:04:05.000007Z",
        "2026-01-02T03:04:05.000008Z",
    ]


def test_stamps_follow_a_clock_that_does_move(settings):
    assert _created_at(settings, ["PRRT_a", "PRRT_b"],
                       datetime(2026, 1, 2, 3, 4, 5, 6, tzinfo=timezone.utc),
                       datetime(2026, 1, 2, 3, 4, 9, 8, tzinfo=timezone.utc)) == [
        "2026-01-02T03:04:05.000006Z",
        "2026-01-02T03:04:09.000008Z",
    ]


def test_the_run_start_stamp_is_the_second_precision_one_the_board_reads(settings):
    here = world(settings,
                 clock=lambda: datetime(2026, 1, 2, 3, 4, 5, 6, tzinfo=timezone.utc))
    repo_at(here.working_copies, WORKTREE)
    threads = here.threads()
    on_github(here.github, "PRRT_one", said(101, "rename this", created_at="2025-12-01T00:00:00Z"))
    hear(threads)
    here.agent_runs.script(RunOutcome(finishes=False))

    threads.tick(FakeNotifications(), on_hold=False)

    assert threads.get("PRRT_one").fix.started_at == "2026-01-02T03:04:05Z"
