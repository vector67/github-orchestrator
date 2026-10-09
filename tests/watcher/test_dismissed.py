from github_orchestrator.github import PullRequestState
from github_orchestrator.pr_processes import ManagerPane
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import Dismissal
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
    on_hold_file,
    thread_dir,
)
from tests.pr_event_queue.support import ci_failed, disk_event_queue
from tests.pr_processes.support import checked_out
from tests.settings.support import disk_dismissals
from tests.thread_records.support import disk_thread_records
from tests.watcher.support import the_clone, watcher_over, watching

REPO = "octocat/hello-world"
PR = 61
THE_PR = a_pr(PR, REPO)
BRANCH = "PROJ-1-thing"


def _open_on_github(settings, github):
    github.add_pr(THE_PR, PullRequestState(author=github.account, head_sha="sha1",
                                           branch=BRANCH))
    polled_on_disk(settings.state_dir, THE_PR,
                   seen(github.account, branch=BRANCH, head_sha="sha1"))


def _window(world, path, *, running=False):
    world.open(THE_PR, path)
    world.managers[THE_PR].running = running


def _flags(settings):
    for flag in (on_hold_file(settings.on_hold_dir, THE_PR),
                 board_flag_file(settings.board_dir, THE_PR)):
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text("")


def _threads(settings, github, copies):
    repo_at(copies, the_clone(settings), {"f": "1\n"}, pr=THE_PR)
    on_github(github, "PRRT_123", said(1, "rename this"), pr=THE_PR)
    hear(conversation_managers_over(settings, github=github, working_copies=copies,
                             thread_records=disk_thread_records(settings.threads_dir)
                             ).of(THE_PR))
    return copies.thread_checkout(THE_PR, "PRRT_123")


def _cycle(settings, github, world, copies):
    watcher_over(settings, github=github, working_copies=copies,
                 pr_processes=world).run_cycle()


def test_a_pr_dismissed_forever_is_torn_down_but_keeps_its_dismissal_and_snapshot(settings):
    github = watching(settings)
    world = FakePrProcesses()
    copies = FakeWorkingCopies(github, thread_worktrees_dir=settings.thread_worktrees_dir)
    _open_on_github(settings, github)
    worktree = checked_out(copies, the_clone(settings).parent / BRANCH, BRANCH)
    checkout = _threads(settings, github, copies)
    _window(world, worktree)
    disk_event_queue(settings.queues_dir).add(THE_PR, ci_failed())
    _flags(settings)
    disk_dismissals(settings.data_dir).dismiss_forever(THE_PR)

    _cycle(settings, github, world, copies)

    assert world.managers == {}
    assert copies.branch_at(worktree) is None
    assert copies.branch_at(checkout) is None
    assert not thread_dir(settings.threads_dir, THE_PR).exists()
    assert disk_event_queue(settings.queues_dir).queues() == []
    assert not on_hold_file(settings.on_hold_dir, THE_PR).exists()
    assert not board_flag_file(settings.board_dir, THE_PR).exists()
    assert disk_dismissals(settings.data_dir).dismissal(THE_PR) is Dismissal.FOREVER
    assert disk_change_detection(settings.state_dir).tracked() == [THE_PR]


def test_a_pr_dismissed_forever_whose_manager_still_runs_is_left_for_the_next_cycle(settings):
    github = watching(settings)
    world = FakePrProcesses()
    copies = FakeWorkingCopies(github)
    _open_on_github(settings, github)
    worktree = checked_out(copies, the_clone(settings).parent / BRANCH, BRANCH)
    _window(world, worktree, running=True)
    disk_dismissals(settings.data_dir).dismiss_forever(THE_PR)

    _cycle(settings, github, world, copies)

    assert list(world.managers) == [THE_PR]
    assert copies.branch_at(worktree) == BRANCH


def test_a_dismissed_pr_whose_worktree_will_not_go_keeps_its_window_for_a_retry(settings):
    github = watching(settings)
    world = FakePrProcesses()
    copies = FakeWorkingCopies(github)
    copies.fail_removals("fatal: the worktree is locked")
    _open_on_github(settings, github)
    worktree = checked_out(copies, the_clone(settings).parent / BRANCH, BRANCH)
    _window(world, worktree)
    disk_dismissals(settings.data_dir).dismiss_forever(THE_PR)

    _cycle(settings, github, world, copies)

    assert list(world.managers) == [THE_PR]


def test_a_pr_dismissed_until_its_next_event_has_its_window_closed_and_keeps_its_worktree(
        settings):
    github = watching(settings)
    world = FakePrProcesses()
    copies = FakeWorkingCopies(github)
    _open_on_github(settings, github)
    worktree = checked_out(copies, the_clone(settings).parent / BRANCH, BRANCH)
    _window(world, worktree)
    disk_dismissals(settings.data_dir).dismiss_until_next_event(THE_PR)

    _cycle(settings, github, world, copies)

    assert world.managers == {}
    assert copies.branch_at(worktree) == BRANCH
    assert disk_dismissals(settings.data_dir).dismissal(THE_PR) is Dismissal.UNTIL_NEXT_EVENT


def test_a_pr_dismissed_until_its_next_event_keeps_its_window_while_its_manager_runs(
        settings):
    github = watching(settings)
    world = FakePrProcesses()
    copies = FakeWorkingCopies(github)
    _open_on_github(settings, github)
    worktree = checked_out(copies, the_clone(settings).parent / BRANCH, BRANCH)
    _window(world, worktree, running=True)
    disk_dismissals(settings.data_dir).dismiss_until_next_event(THE_PR)

    _cycle(settings, github, world, copies)

    assert world.manager(THE_PR) is ManagerPane.RUNNING



def test_a_dismissed_pr_that_will_not_tear_down_keeps_its_window_though_events_wait(settings):
    github = watching(settings)
    world = FakePrProcesses()
    copies = FakeWorkingCopies(github)
    copies.fail_removals("fatal: the worktree is locked")
    _open_on_github(settings, github)
    worktree = checked_out(copies, the_clone(settings).parent / BRANCH, BRANCH)
    _window(world, worktree)
    disk_event_queue(settings.queues_dir).add(THE_PR, ci_failed())
    disk_dismissals(settings.data_dir).dismiss_forever(THE_PR)

    _cycle(settings, github, world, copies)

    assert list(world.managers) == [THE_PR]
