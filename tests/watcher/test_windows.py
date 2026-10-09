from datetime import datetime, timezone
from pathlib import Path

import pytest

from github_orchestrator.desktop import Badge
from github_orchestrator.github import PullRequestState
from github_orchestrator.pr_processes import ManagerPane
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import fake_settings
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.change_detection.support import polled_on_disk, seen
from tests.disk_layout import board_port_file, dismissed_file
from tests.pr_event_queue.support import (
    ci_failed,
    closed,
    disk_event_queue,
    mergeable,
    pending_of,
    queue_of,
)
from tests.pr_processes.support import checked_out
from tests.settings.support import disk_dismissals
from tests.watcher.support import watcher_over, watching

REPO = "octocat/hello-world"
PR = 83
THE_PR = a_pr(PR, REPO)
OTHER_PR = 87
EXPECTED = "PROJ-30-add-archiving"
WANDERED = "PROJ-30-merge-archives"
GRACE = 3600
RUN_IDLE = 300
NOW = 100_000.0
RETRY_SECONDS = 20 * 60
BOARD_PORTS = range(8730, 8830)


@pytest.fixture
def settings(tmp_path):
    return fake_settings(tmp_path)


@pytest.fixture
def world():
    return FakePrProcesses()


@pytest.fixture
def copies(notifications):
    return FakeWorkingCopies(notifications=notifications, grace_seconds=GRACE,
                             run_idle_seconds=RUN_IDLE)


def _at_now():
    return datetime.fromtimestamp(NOW, timezone.utc)


def _github(settings, *numbers, branch=EXPECTED, author=True):
    github = watching(settings)
    for number in numbers or (PR,):
        github.add_pr(a_pr(number, REPO), PullRequestState(
            author=github.account if author else "alice", head_sha="sha1", branch=branch),
            review_requested=not author)
    return github


def _cycle(settings, world, copies, notifications, github=None):
    watcher_over(settings, github=github or _github(settings), notifications=notifications,
                 pr_processes=world, working_copies=copies, clock=_at_now).run_cycle()


def _window(world, copies, *, running=True, path="/wt/archiving", branch=EXPECTED, pr=PR):
    if branch is not None:
        copies.add_worktree(path, branch)
    world.open(a_pr(pr, REPO), Path(path))
    manager = world.managers[a_pr(pr, REPO)]
    manager.running = running
    return manager


def _flag(copies, *, since, run_output_at=None):
    copies.add_worktree("/wt/archiving", WANDERED)
    copies.report_branch(THE_PR, "/wt/archiving", EXPECTED, now=since,
                         run_output_at=run_output_at)


def _trouble(copies):
    return copies.verdict(THE_PR, None, expected=EXPECTED, window_open=True, now=NOW, manager_running=False)


def _detached(world):
    return world.manager(THE_PR) is ManagerPane.NO_WINDOW


def test_a_new_pr_gets_a_window_in_its_worktree(settings, world, copies, notifications, tmp_path):
    worktree = checked_out(copies, tmp_path / EXPECTED, EXPECTED)

    _cycle(settings, world, copies, notifications)

    assert world.manager_path(THE_PR) == str(worktree)


def test_a_new_window_is_given_its_board_port(settings, world, copies, notifications, tmp_path):
    checked_out(copies, tmp_path / EXPECTED, EXPECTED)

    _cycle(settings, world, copies, notifications)

    port = board_port_file(settings.board_dir, THE_PR).read_text().strip()
    assert int(port) in BOARD_PORTS


def test_a_pr_whose_worktree_cannot_be_cut_gets_no_window(settings, world, copies, notifications):
    _cycle(settings, world, copies, notifications)

    assert world.manager(THE_PR) is ManagerPane.NO_WINDOW
    assert not board_port_file(settings.board_dir, THE_PR).exists()


def test_a_pr_dismissed_until_its_next_event_stays_closed_while_nothing_waits(
        settings, world, copies, notifications, tmp_path):
    checked_out(copies, tmp_path / EXPECTED, EXPECTED)
    disk_dismissals(settings.data_dir).dismiss_until_next_event(THE_PR)

    _cycle(settings, world, copies, notifications)

    assert world.managers == {}
    assert dismissed_file(settings.dismissed_dir, THE_PR).exists()


def test_a_pr_dismissed_until_its_next_event_opens_again_when_one_waits(
        settings, world, copies, notifications, tmp_path):
    checked_out(copies, tmp_path / EXPECTED, EXPECTED)
    disk_dismissals(settings.data_dir).dismiss_until_next_event(THE_PR)
    disk_event_queue(settings.queues_dir).add(THE_PR, mergeable())

    _cycle(settings, world, copies, notifications)

    assert not dismissed_file(settings.dismissed_dir, THE_PR).exists()
    assert world.manager(THE_PR) is ManagerPane.RUNNING


def test_a_dead_manager_is_started_again_in_its_window(settings, world, copies, notifications):
    manager = _window(world, copies, running=False)

    _cycle(settings, world, copies, notifications)

    assert manager.running


def test_a_dead_manager_with_events_waiting_is_revived_once_its_role_is_known(
        settings, world, copies, notifications):
    manager = _window(world, copies, running=False)
    polled_on_disk(settings.state_dir, THE_PR, seen(settings.config.gh_account, is_author=False))
    disk_event_queue(settings.queues_dir).add(THE_PR, closed(merged=False))

    _cycle(settings, world, copies, notifications, _github(settings, 99))

    assert manager.running


def test_a_dead_manager_with_nothing_waiting_stays_down(settings, world, copies, notifications):
    manager = _window(world, copies, running=False)

    _cycle(settings, world, copies, notifications, _github(settings, 99))

    assert not manager.running


def test_an_event_a_dead_manager_had_in_hand_is_put_back_in_line(settings, world, copies, notifications):
    manager = _window(world, copies, running=False)
    polled_on_disk(settings.state_dir, THE_PR, seen(settings.config.gh_account))
    disk_event_queue(settings.queues_dir).add(THE_PR, ci_failed())
    disk_event_queue(settings.queues_dir).next(THE_PR, is_author=True, agents_enabled=True)

    _cycle(settings, world, copies, notifications, _github(settings, 99))

    assert [e.kind for e in pending_of(disk_event_queue(settings.queues_dir), THE_PR)] == ["ci-failed"]
    assert manager.running


def test_an_event_a_live_manager_has_in_hand_stays_with_it(settings, world, copies, notifications):
    manager = _window(world, copies)
    disk_event_queue(settings.queues_dir).add(THE_PR, ci_failed())
    disk_event_queue(settings.queues_dir).next(THE_PR, is_author=True, agents_enabled=True)

    _cycle(settings, world, copies, notifications, _github(settings, 99))

    assert len(queue_of(disk_event_queue(settings.queues_dir), THE_PR).in_flight) == 1
    assert manager.starts == 1


def test_a_live_manager_with_events_waiting_is_not_revived(settings, world, copies, notifications):
    manager = _window(world, copies)
    disk_event_queue(settings.queues_dir).add(THE_PR, ci_failed())

    _cycle(settings, world, copies, notifications, _github(settings, 99))

    assert manager.starts == 1


def test_pending_events_without_a_window_open_nothing(settings, world, copies, notifications):
    disk_event_queue(settings.queues_dir).add(THE_PR, ci_failed())

    _cycle(settings, world, copies, notifications, _github(settings, 99))

    assert world.manager(THE_PR) is ManagerPane.NO_WINDOW


def test_a_window_on_its_own_branch_is_left_alone(settings, world, copies, notifications):
    manager = _window(world, copies)

    _cycle(settings, world, copies, notifications)

    assert not _detached(world)
    assert manager.running
    assert _trouble(copies) is None


def test_the_watchers_own_evidence_starts_the_clock_without_detaching(settings, world, copies, notifications):
    _window(world, copies, branch=WANDERED)

    _cycle(settings, world, copies, notifications)

    verdict = _trouble(copies)
    assert (verdict.seconds_left, verdict.here, verdict.expected) == (GRACE, WANDERED, EXPECTED)
    assert not _detached(world)


def test_a_pane_directory_with_a_colon_is_read_whole(settings, world, copies, notifications):
    _window(world, copies, path="/wt/weird:name", branch=WANDERED)

    _cycle(settings, world, copies, notifications)

    assert _trouble(copies).worktree == "/wt/weird:name"


@pytest.mark.parametrize("since, grace, running, run_output_at, detached", [
    (NOW - 0, GRACE, True, None, False),
    (NOW - GRACE, GRACE, True, None, True),
    (NOW - GRACE, GRACE, False, NOW - 1, True),
], ids=[
    "just-flagged", "grace-spent", "dead-manager-with-a-stale-run",
])
def test_the_grace_period_decides_when_a_wandered_window_is_detached(
        settings, world, notifications, since, grace, running, run_output_at, detached):
    copies = FakeWorkingCopies(notifications=notifications, grace_seconds=grace,
                               run_idle_seconds=RUN_IDLE)
    _window(world, copies, running=running)
    _flag(copies, since=since, run_output_at=run_output_at)

    _cycle(settings, world, copies, notifications)

    assert _detached(world) is detached
    assert (_trouble(copies) is None) is detached


def test_a_requested_release_detaches_at_once(settings, world, copies, notifications):
    _window(world, copies)
    _flag(copies, since=NOW)
    copies.request_release(THE_PR)

    _cycle(settings, world, copies, notifications)

    assert _detached(world)


def test_a_detached_window_loses_its_manager_and_says_so(settings, world, copies, notifications):
    _window(world, copies)
    _flag(copies, since=NOW - GRACE)

    _cycle(settings, world, copies, notifications)

    assert _detached(world)
    assert [(n.badge, n.title, n.body) for n in notifications.posted] == [
        (Badge.FAILED, "PR #83 left on the wrong branch",
         "Window kept as hello-world/#83-defunct; building a fresh worktree")]


def test_a_dead_manager_in_a_foreign_directory_is_revived_not_detached(settings, world, copies, notifications):
    manager = _window(world, copies, running=False, branch="somewhere-else")

    _cycle(settings, world, copies, notifications)

    assert not _detached(world)
    assert manager.running
    assert _trouble(copies) is None


def test_a_pane_whose_branch_is_unknown_is_not_a_mismatch(settings, world, copies, notifications):
    _window(world, copies, branch=None)

    _cycle(settings, world, copies, notifications)

    assert not _detached(world)
    assert _trouble(copies) is None


def test_a_pr_whose_branch_is_unknown_is_not_a_mismatch(settings, world, copies, notifications):
    _window(world, copies, branch="anything")

    _cycle(settings, world, copies, notifications, _github(settings, branch=""))

    assert not _detached(world)
    assert _trouble(copies) is None


@pytest.fixture
def shared(settings, world, copies, tmp_path):
    path = checked_out(copies, tmp_path / "wt", EXPECTED)
    world.open(a_pr(OTHER_PR, REPO), path)
    return path


def _other_tracked(settings):
    return _github(settings, PR, OTHER_PR)


def test_no_window_opens_onto_another_prs_worktree(settings, world, copies, notifications, shared):
    _cycle(settings, world, copies, notifications, _other_tracked(settings))

    assert world.manager(THE_PR) is ManagerPane.NO_WINDOW
    assert not (shared / "agent-changes.md").exists()


def test_the_other_windows_directory_is_compared_resolved(settings, world, copies, notifications, tmp_path):
    path = checked_out(copies, tmp_path / "wt", EXPECTED)
    link = tmp_path / "link"
    link.symlink_to(path)
    world.open(a_pr(OTHER_PR, REPO), link)

    _cycle(settings, world, copies, notifications, _other_tracked(settings))

    assert world.manager(THE_PR) is ManagerPane.NO_WINDOW


def test_a_tracked_pr_without_a_window_does_not_hold_the_window(settings, world, copies, notifications, tmp_path):
    checked_out(copies, tmp_path / "wt", EXPECTED)

    _cycle(settings, world, copies, notifications, _other_tracked(settings))

    assert world.manager(THE_PR) is ManagerPane.RUNNING


def test_another_prs_window_elsewhere_does_not_hold_the_window(settings, world, copies, notifications, tmp_path):
    checked_out(copies, tmp_path / "wt", EXPECTED)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    world.open(a_pr(OTHER_PR, REPO), elsewhere)

    _cycle(settings, world, copies, notifications, _other_tracked(settings))

    assert world.manager(THE_PR) is ManagerPane.RUNNING
    assert copies.flags.conflicts.get(THE_PR) is None


def _seen_shared(copies, notifications, shared, now):
    copies.verdict(THE_PR, shared, window_open=False, now=now,
                   others={a_pr(OTHER_PR, REPO): str(shared)})
    notifications.posted.clear()


def test_the_conflict_is_recorded_and_said_once(settings, world, copies, notifications, shared):
    _cycle(settings, world, copies, notifications, _other_tracked(settings))

    flag = copies.flags.conflicts.get(THE_PR)
    assert (flag.since, flag.checks, flag.other_pr) == (NOW, 1, OTHER_PR)
    assert [(n.badge, n.title, n.body) for n in notifications.posted] == [
        (Badge.FAILED, "PR #83 shares a worktree",
         "wt is already PR #87's — not opening a window; press w on PR #87's screen "
         "to release it")]


def test_after_the_retry_budget_the_window_opens_there_anyway(settings, world, copies, notifications, shared):
    _seen_shared(copies, notifications, shared, NOW - RETRY_SECONDS)

    _cycle(settings, world, copies, notifications, _other_tracked(settings))

    assert world.manager_path(THE_PR) == str(shared)
    assert [(n.badge, n.title, n.body) for n in notifications.posted] == [
        (Badge.FAILED, "PR #83 worktree still shared",
         "wt is still PR #87's after 20 min — opening it anyway")]
    assert copies.flags.conflicts.get(THE_PR) is None
