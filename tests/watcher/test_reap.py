from pathlib import Path

import pytest

from github_orchestrator.domain import Repo
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import RepoEntry, fake_settings
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.change_detection.support import disk_change_detection, polled_on_disk, seen
from tests.conversation.support import (
    conversation_managers_over,
    hear,
    on_github,
    repo_at,
    said,
)
from tests.disk_layout import (
    board_flag_file,
    board_port_file,
    dismissed_file,
    on_hold_file,
    thread_dir,
)
from tests.pr_event_queue.support import closed, disk_event_queue
from tests.pr_processes.support import checked_out
from tests.thread_records.support import disk_thread_records
from tests.watcher.support import the_clone, watcher_over, watching

REPO = "acme/widgets"


@pytest.fixture
def settings(tmp_path):
    return fake_settings(tmp_path, repos=(
        RepoEntry(Repo.parse(REPO), str(tmp_path / "widgets" / "clone")),))


PR = 62
THE_PR = a_pr(PR, REPO)
BRANCH = "PROJ-33-foo"


def _closing(settings):
    polled_on_disk(settings.state_dir, THE_PR, seen(settings.config.gh_account, branch=BRANCH))
    disk_change_detection(settings.state_dir).close(THE_PR)


def _tracked(settings):
    return THE_PR in disk_change_detection(settings.state_dir).tracked()


def _world(settings):
    return FakePrProcesses()


def _window(world, *, running=True):
    world.open(THE_PR, Path("/wt"))
    world.managers[THE_PR].running = running


def _torn_down(settings):
    event_queue = disk_event_queue(settings.queues_dir)
    event_queue.add(THE_PR, closed(merged=False))
    event_queue.next(THE_PR, is_author=True, agents_enabled=True).done()


def _cycle(settings, world, copies):
    watcher_over(settings, github=watching(settings), pr_processes=world,
                 working_copies=copies).run_cycle()


def _threads(settings, copies):
    github = watching(settings)
    repo_at(copies, the_clone(settings), {"f": "1\n"}, pr=THE_PR)
    for comment_id, key in enumerate(("PRRT_123", "PRRT_456"), 1):
        on_github(github, key, said(comment_id, "rename this"), pr=THE_PR)
    hear(conversation_managers_over(settings, github=github, working_copies=copies,
                             thread_records=disk_thread_records(settings.threads_dir)
                             ).of(THE_PR))
    checkout = copies.thread_checkout(THE_PR, "PRRT_123")
    branch = copies.branch_at(checkout)
    assert branch in copies.branches
    return checkout, branch


def test_a_closing_pr_whose_manager_is_still_tearing_down_is_left_for_the_next_cycle(settings, capsys):
    world = _world(settings)
    copies = FakeWorkingCopies()
    worktree = checked_out(copies, the_clone(settings).parent / BRANCH, BRANCH)
    _closing(settings)
    _window(world)
    disk_event_queue(settings.queues_dir).add(THE_PR, closed(merged=False))

    _cycle(settings, world, copies)

    assert "0 torn down" in capsys.readouterr().out
    assert list(world.managers) == [THE_PR]
    assert _tracked(settings)
    assert disk_event_queue(settings.queues_dir).queues() != []
    assert copies.branch_at(worktree) == BRANCH


def test_a_closing_pr_whose_manager_has_exited_is_reaped(settings, capsys):
    world = _world(settings)
    _closing(settings)
    _window(world, running=False)
    disk_event_queue(settings.queues_dir).add(THE_PR, closed(merged=False))

    _cycle(settings, world, FakeWorkingCopies())

    assert "1 torn down" in capsys.readouterr().out
    assert world.managers == {}
    assert disk_event_queue(settings.queues_dir).queues() == []


def test_a_reaped_pr_leaves_nothing_behind(settings, capsys):
    world = _world(settings)
    copies = FakeWorkingCopies()
    worktree = checked_out(copies, the_clone(settings).parent / BRANCH, BRANCH)
    _closing(settings)
    _window(world)
    _torn_down(settings)
    for flag in (on_hold_file(settings.on_hold_dir, THE_PR),
                 dismissed_file(settings.dismissed_dir, THE_PR),
                 board_flag_file(settings.board_dir, THE_PR),
                 board_port_file(settings.board_dir, THE_PR)):
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text("")

    _cycle(settings, world, copies)

    assert "1 torn down" in capsys.readouterr().out
    assert world.managers == {}
    assert disk_event_queue(settings.queues_dir).queues() == []
    assert copies.branch_at(worktree) is None
    assert not _tracked(settings)
    assert not on_hold_file(settings.on_hold_dir, THE_PR).exists()
    assert not dismissed_file(settings.dismissed_dir, THE_PR).exists()
    assert not board_port_file(settings.board_dir, THE_PR).exists()
    assert not board_flag_file(settings.board_dir, THE_PR).exists()


def test_a_closing_pr_without_a_window_is_reaped(settings, capsys):
    world = _world(settings)
    _closing(settings)
    disk_event_queue(settings.queues_dir).add(THE_PR, closed(merged=False))

    _cycle(settings, world, FakeWorkingCopies())

    assert "1 torn down" in capsys.readouterr().out
    assert not _tracked(settings)
    assert disk_event_queue(settings.queues_dir).queues() == []


def test_a_reaped_pr_drops_each_threads_workspace_its_branch_and_the_records(settings, capsys):
    world = _world(settings)
    copies = FakeWorkingCopies(thread_worktrees_dir=settings.thread_worktrees_dir)
    _closing(settings)
    _torn_down(settings)
    checkout, branch = _threads(settings, copies)

    _cycle(settings, world, copies)

    assert "1 torn down" in capsys.readouterr().out
    assert copies.branch_at(checkout) is None
    assert branch not in copies.branches
    assert not thread_dir(settings.threads_dir, THE_PR).exists()
    assert not _tracked(settings)


def test_a_thread_branch_that_will_not_go_keeps_the_state_and_the_records(settings, capsys):
    world = _world(settings)
    copies = FakeWorkingCopies(thread_worktrees_dir=settings.thread_worktrees_dir)
    _closing(settings)
    _torn_down(settings)
    checkout, branch = _threads(settings, copies)
    copies.lose_worktree(checkout)
    copies.check_out(the_clone(settings), branch)

    _cycle(settings, world, copies)

    assert "0 torn down" in capsys.readouterr().out
    assert _tracked(settings)
    assert (thread_dir(settings.threads_dir, THE_PR) / "PRRT_123.json").exists()


def test_a_worktree_that_will_not_go_keeps_the_state_for_a_retry(settings, capsys):
    world = _world(settings)
    copies = FakeWorkingCopies()
    copies.fail_removals("fatal: 'wt' contains modified or untracked files")
    checked_out(copies, the_clone(settings).parent / BRANCH, BRANCH)
    _closing(settings)
    _torn_down(settings)

    _cycle(settings, world, copies)

    assert "0 torn down" in capsys.readouterr().out
    assert _tracked(settings)

