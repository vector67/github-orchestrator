from datetime import datetime, timezone
from pathlib import Path

import pytest

from github_orchestrator.board_api.fake import FakeHoldings
from github_orchestrator.board_api.interface import Holdings, SetupDesk, Told
from github_orchestrator.domain import HubState
from github_orchestrator.github import PullRequestState
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import fake_settings
from github_orchestrator.watcher import Watcher
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.change_detection.support import polled_on_disk, seen
from tests.settings.support import disk_boards, disk_dismissals, disk_holds
from tests.watcher.support import (
    ServerSpawns,
    health,
    watcher_container,
    watcher_over,
    watching,
)

REPO = "octocat/hello-world"
MINE = a_pr(83, REPO)
THEIRS = a_pr(87, REPO)
NOBODYS = a_pr(9999, REPO)
EXPECTED = "PROJ-30-add-archiving"
WANDERED = "PROJ-30-merge-archives"
NOW = 100_000.0
RESTS_PER_CYCLE = 30


def _at_now():
    return datetime.fromtimestamp(NOW, timezone.utc)


@pytest.fixture
def settings(tmp_path):
    return fake_settings(tmp_path)


def _github(settings):
    github = watching(settings)
    github.add_pr(MINE, PullRequestState(author=github.account, head_sha="sha1", branch=EXPECTED,
                                         title="Add archiving"))
    github.add_pr(THEIRS, PullRequestState(author="alice", head_sha="sha2", branch="tidy"),
                  review_requested=True)
    return github


class Naps:
    def __init__(self, cycles, between=None):
        self.left = cycles * RESTS_PER_CYCLE
        self.between = between
        self.taken = 0

    def __call__(self, seconds):
        self.taken += 1
        self.left -= 1
        if self.left <= 0:
            raise KeyboardInterrupt
        if self.between is not None and self.taken == RESTS_PER_CYCLE:
            self.between()


def _resident(settings, server=None, *, cycles=1, between=None, dry_run=False, **modules):
    watcher = watcher_over(settings, github=_github(settings), server=server or ServerSpawns(),
                           clock=_at_now, sleep=Naps(cycles, between), dry_run=dry_run, **modules)
    with pytest.raises(KeyboardInterrupt):
        watcher.run_forever()


def test_the_resident_watcher_keeps_the_server_running_on_every_cycle(settings):
    server = ServerSpawns()

    _resident(settings, server, cycles=3)

    assert server.made == 3
    assert set(_told(settings).held().managers) == {MINE, THEIRS}


def test_a_one_shot_cycle_starts_no_server(settings):
    server = ServerSpawns()

    watcher_over(settings, github=_github(settings), server=server).run_cycle()

    assert server.made == 0


def test_a_resident_dry_run_starts_no_server_and_tells_it_nothing(settings):
    server = ServerSpawns()

    _resident(settings, server, dry_run=True)

    told = _told(settings)
    assert (server.made, told.held().told, told.state()) == (0, False, None)


def test_a_watcher_waiting_in_setup_keeps_the_server_running_on_every_wait(settings):
    server = ServerSpawns()
    states = iter([HubState.SETUP] * 3 + [HubState.WATCHING])

    watcher_over(settings, server=server, sleep=lambda seconds: None).wait_in(
        HubState.SETUP, lambda: next(states))

    assert server.made == 3


def test_a_pr_dismissed_forever_is_not_told_to_the_hub(settings):
    disk_dismissals(settings.data_dir).dismiss_forever(THEIRS)

    _resident(settings)

    assert list(_told(settings).held().managers) == [MINE]


def test_a_pr_i_reviewed_that_left_the_search_is_still_told_to_the_hub(settings):
    reviewed = a_pr(198, REPO)
    polled_on_disk(settings.state_dir, reviewed,
                   seen(settings.config.gh_account, is_author=False, author="bob"))
    github = _github(settings)
    github.add_pr(reviewed, PullRequestState(author="bob", head_sha="sha3", branch="unify"),
                  viewer_reviewed=True)
    watcher = watcher_over(settings, github=github, clock=_at_now, sleep=Naps(1))

    with pytest.raises(KeyboardInterrupt):
        watcher.run_forever()

    assert set(_told(settings).held().managers) == {MINE, THEIRS, reviewed}


def _told(settings):
    return watcher_container(settings).get(Told)


def test_after_a_cycle_the_watcher_tells_the_hub_each_pr_it_holds_and_its_managers_state(
        settings):
    windows = FakePrProcesses()
    windows.open(MINE, Path("/wt/archiving"))

    _resident(settings, pr_processes=windows)

    held = _told(settings).held()
    assert held.told is True
    assert held.managers == {MINE: "running", THEIRS: "no-window"}


def test_a_watcher_starting_tells_the_hub_it_holds_nothing_yet_and_its_state(settings):
    _resident(settings)
    states = iter([HubState.SETUP, HubState.WATCHING])

    watcher_over(settings, sleep=lambda seconds: None).wait_in(HubState.SETUP,
                                                               lambda: next(states))

    told = _told(settings)
    assert (told.held().told, told.held().managers, told.state()) == (False, {},
                                                                       HubState.SETUP)


def test_a_resident_watcher_tells_the_hub_it_is_watching(settings):
    _resident(settings)

    assert _told(settings).state() is HubState.WATCHING


def test_the_hub_is_told_nothing_before_any_watcher_has_run(settings):
    told = _told(settings)

    assert (told.held().told, told.held().managers, told.state()) == (False, {}, None)


def _holdings(settings, **modules):
    _resident(settings, **modules)
    return watcher_container(settings, **modules).get(Holdings)


def test_a_board_has_a_port_to_link_to_only_while_it_is_wanted(settings):
    holdings = _holdings(settings)
    boards = disk_boards(settings.data_dir)

    unwanted = holdings.board_port(MINE)
    boards.want_board(MINE, True)

    assert unwanted is None
    assert holdings.board_port(MINE) == boards.board_port(MINE)


def test_hold_and_resume_from_the_hub_set_the_hold_switch_every_process_reads(settings):
    holdings = _holdings(settings)

    holdings.hold(MINE)
    on_hold = disk_holds(settings.data_dir).on_hold(MINE)
    holdings.resume(MINE)

    assert on_hold is True
    assert disk_holds(settings.data_dir).on_hold(MINE) is False


def test_a_pr_frozen_on_the_wrong_branch_can_be_released_from_the_hub(settings):
    copies = FakeWorkingCopies()
    holdings = _holdings(settings, working_copies=copies)
    copies.add_worktree("/wt/archiving", WANDERED)
    copies.report_branch(MINE, "/wt/archiving", EXPECTED, now=NOW, run_output_at=None)

    released = holdings.release(MINE)

    assert released is True
    assert copies.wrong_branch(MINE, now=NOW).release_requested is True


@pytest.fixture(params=["fake", "watcher"])
def holdings(request, settings):
    return FakeHoldings() if request.param == "fake" else _holdings(settings)


def test_a_pr_that_is_not_frozen_has_nothing_to_release(holdings):
    assert holdings.release(NOBODYS) is False


def test_a_pr_nothing_has_described_has_no_board_to_reach(holdings):
    assert holdings.board_port(NOBODYS) is None


def test_a_hub_waiting_in_setup_drops_the_error_of_cycles_it_no_longer_runs(settings):
    settings.watcher_failures.write_text('{"consecutive": 3, "last_error": "gh exploded"}')
    states = iter([HubState.SETUP, HubState.WATCHING])

    watcher_over(settings, sleep=lambda seconds: None).wait_in(HubState.SETUP,
                                                               lambda: next(states))

    assert health(settings).last_error is None


def test_a_resident_watcher_returns_once_setup_moves_the_config(settings):
    settings.config_path.write_text("gh_account = \n")
    server = ServerSpawns()
    container = watcher_container(settings, github=_github(settings), server=server,
                                  clock=_at_now,
                                  sleep=lambda seconds: container.get(SetupDesk).move_aside())

    container.get(Watcher).run_forever()

    assert server.made == 1


def test_a_hub_waiting_in_setup_returns_once_setup_moves_the_config_though_its_state_reads_on(
        settings):
    settings.config_path.write_text("gh_account = \n")
    moved = []
    container = watcher_container(
        settings, sleep=lambda seconds: moved.append(container.get(SetupDesk).move_aside()))

    container.get(Watcher).wait_in(HubState.BROKEN, lambda: HubState.BROKEN)

    assert len(moved) == 1
