import pytest

from github_orchestrator.domain import Repo
from github_orchestrator.settings.fake import Dismissal
from tests.builders import a_pr
from tests.settings.support import disk_switches, fake_switches

REPO = "acme/widgets"


@pytest.fixture(params=["fake", "disk"])
def switches(request, tmp_path):
    if request.param == "fake":
        return fake_switches()
    return disk_switches(tmp_path)


def test_setting_a_pr_on_hold_holds_it_and_setting_it_off_hold_resumes_it(switches):
    switches.holds.set_on_hold(a_pr(55, REPO), True)
    assert switches.holds.on_hold(a_pr(55, REPO)) is True
    switches.holds.set_on_hold(a_pr(55, REPO), False)
    assert switches.holds.on_hold(a_pr(55, REPO)) is False


def test_setting_a_pr_the_way_it_already_is_leaves_it_so(switches):
    switches.holds.set_on_hold(a_pr(55, REPO), True)
    switches.holds.set_on_hold(a_pr(55, REPO), True)
    assert switches.holds.on_hold(a_pr(55, REPO)) is True
    switches.holds.set_on_hold(a_pr(56, REPO), False)
    assert switches.holds.on_hold(a_pr(56, REPO)) is False


def test_holding_one_pr_leaves_the_others_running(switches):
    switches.holds.set_on_hold(a_pr(1, REPO), True)
    assert switches.holds.on_hold(a_pr(2, REPO)) is False
    assert switches.holds.on_hold(a_pr(1, "acme/other")) is False


def test_a_pr_is_not_dismissed_until_someone_dismisses_it(switches):
    assert switches.dismissals.dismissal(a_pr(42, REPO)) is None
    assert switches.dismissals.is_dismissed_forever(a_pr(42, REPO)) is False
    assert switches.dismissals.is_hidden(a_pr(42, REPO), events_waiting=False) is False


def test_a_pr_dismissed_forever_stays_hidden_whatever_is_waiting(switches):
    switches.dismissals.dismiss_forever(a_pr(42, REPO))
    assert switches.dismissals.dismissal(a_pr(42, REPO)) is Dismissal.FOREVER
    assert switches.dismissals.is_dismissed_forever(a_pr(42, REPO)) is True
    assert switches.dismissals.is_hidden(a_pr(42, REPO), events_waiting=True) is True
    assert switches.dismissals.is_dismissed_forever(a_pr(42, REPO)) is True


def test_a_pr_dismissed_until_the_next_event_is_hidden_while_nothing_waits(switches):
    switches.dismissals.dismiss_until_next_event(a_pr(42, REPO))
    assert switches.dismissals.is_hidden(a_pr(42, REPO), events_waiting=False) is True
    assert switches.dismissals.dismissal(a_pr(42, REPO)) is Dismissal.UNTIL_NEXT_EVENT
    assert switches.dismissals.is_dismissed_forever(a_pr(42, REPO)) is False


def test_an_event_waiting_ends_a_dismissal_until_the_next_event(switches):
    switches.dismissals.dismiss_until_next_event(a_pr(42, REPO))
    assert switches.dismissals.is_hidden(a_pr(42, REPO), events_waiting=True) is False
    assert switches.dismissals.dismissal(a_pr(42, REPO)) is None
    assert switches.dismissals.is_hidden(a_pr(42, REPO), events_waiting=False) is False


def test_a_second_dismissal_replaces_the_first(switches):
    switches.dismissals.dismiss_until_next_event(a_pr(42, REPO))
    switches.dismissals.dismiss_forever(a_pr(42, REPO))
    assert switches.dismissals.dismissal(a_pr(42, REPO)) is Dismissal.FOREVER


def test_undismissing_says_whether_there_was_a_dismissal(switches):
    switches.dismissals.dismiss_forever(a_pr(42, REPO))
    assert switches.dismissals.undismiss(a_pr(42, REPO)) is True
    assert switches.dismissals.dismissal(a_pr(42, REPO)) is None
    assert switches.dismissals.undismiss(a_pr(42, REPO)) is False


def test_dismissing_one_pr_leaves_the_others_shown(switches):
    switches.dismissals.dismiss_forever(a_pr(1, REPO))
    assert switches.dismissals.dismissal(a_pr(2, REPO)) is None
    assert switches.dismissals.is_hidden(a_pr(2, REPO), events_waiting=False) is False


def test_a_wanted_board_stays_wanted_until_it_is_let_go(switches):
    switches.boards.want_board(a_pr(55, REPO), True)
    assert switches.boards.board_wanted(a_pr(55, REPO)) is True
    switches.boards.want_board(a_pr(55, REPO), False)
    assert switches.boards.board_wanted(a_pr(55, REPO)) is False


def test_letting_go_of_a_board_nobody_wanted_is_harmless(switches):
    switches.boards.want_board(a_pr(55, REPO), False)
    assert switches.boards.board_wanted(a_pr(55, REPO)) is False


def test_a_pr_keeps_the_board_port_it_was_first_given(switches):
    assert switches.boards.board_port(a_pr(55, REPO)) == switches.boards.board_port(a_pr(55, REPO))


def test_each_pr_gets_a_board_port_of_its_own(switches):
    ports = {switches.boards.board_port(a_pr(pr, REPO)) for pr in (1, 2, 3)}
    assert len(ports) == 3


def test_nothing_is_flagged_when_no_pr_is_on_hold_or_dismissed(switches):
    switches.boards.want_board(a_pr(1, REPO), True)
    assert switches.flagged() == set()


def test_flagged_names_every_on_hold_or_dismissed_pr_once(switches):
    switches.holds.set_on_hold(a_pr(1, REPO), True)
    switches.dismissals.dismiss_forever(a_pr(2, REPO))
    switches.holds.set_on_hold(a_pr(3, "acme/other"), True)
    switches.dismissals.dismiss_until_next_event(a_pr(3, "acme/other"))
    assert switches.flagged() == {(a_pr(1, REPO)), (a_pr(2, REPO)), (a_pr(3, "acme/other"))}


def test_a_forgotten_pr_has_no_switch_left_on(switches):
    switches.holds.set_on_hold(a_pr(1, REPO), True)
    switches.dismissals.dismiss_forever(a_pr(1, REPO))
    switches.boards.want_board(a_pr(1, REPO), True)
    switches.boards.board_port(a_pr(1, REPO))

    assert switches.forget(a_pr(1, REPO)) is True

    assert switches.holds.on_hold(a_pr(1, REPO)) is False
    assert switches.dismissals.dismissal(a_pr(1, REPO)) is None
    assert switches.boards.board_wanted(a_pr(1, REPO)) is False
    assert switches.flagged() == set()


def test_forgetting_a_pr_with_no_switches_succeeds(switches):
    assert switches.forget(a_pr(1, REPO)) is True


def test_forgetting_one_pr_keeps_the_others_switches(switches):
    switches.holds.set_on_hold(a_pr(1, REPO), True)
    switches.holds.set_on_hold(a_pr(2, REPO), True)
    port = switches.boards.board_port(a_pr(2, REPO))

    switches.forget(a_pr(1, REPO))

    assert switches.holds.on_hold(a_pr(2, REPO)) is True
    assert switches.boards.board_port(a_pr(2, REPO)) == port


def test_archiving_moves_every_unwatched_repos_holds_and_keeps_every_watched_one(
        switches, tmp_path):
    switches.holds.set_on_hold(a_pr(1, REPO), True)
    switches.holds.set_on_hold(a_pr(2, "acme/other"), True)
    switches.holds.set_on_hold(a_pr(3, "octocat/third"), True)
    switches.holds.set_on_hold(a_pr(4, "acme/fourth"), True)
    into = tmp_path / "archive" / "on_hold"

    archived = switches.holds.archive_other_repos(
        {Repo.parse(REPO), Repo.parse("acme/fourth")}, into)

    assert sorted(archived) == [into / "acme" / "other", into / "octocat" / "third"]
    assert switches.holds.on_hold(a_pr(1, REPO)) is True
    assert switches.holds.on_hold(a_pr(2, "acme/other")) is False
    assert switches.flagged() == {a_pr(1, REPO), a_pr(4, "acme/fourth")}


def test_archiving_when_only_the_named_repo_is_on_hold_moves_nothing(switches, tmp_path):
    switches.holds.set_on_hold(a_pr(1, REPO), True)

    assert switches.holds.archive_other_repos({Repo.parse(REPO)}, tmp_path / "archive" / "on_hold") == []
    assert switches.holds.on_hold(a_pr(1, REPO)) is True


def test_a_new_pr_never_gets_a_port_a_remaining_pr_still_holds(switches):
    switches.boards.board_port(a_pr(1, REPO))
    kept = switches.boards.board_port(a_pr(2, REPO))
    switches.forget(a_pr(1, REPO))

    assert switches.boards.board_port(a_pr(3, REPO)) != kept
