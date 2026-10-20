
import pytest

from github_orchestrator.domain import Repo
from github_orchestrator.settings.fake import Dismissal
from tests.builders import a_pr
from tests.disk_layout import (
    dismissed_file,
    on_hold_file,
)
from tests.settings.support import disk_switches

REPO = "acme/widgets"


@pytest.fixture
def switches(tmp_path):
    return disk_switches(tmp_path)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_a_hold_is_an_empty_flag_file_where_every_process_looks(switches, tmp_path):
    switches.holds.set_on_hold(a_pr(55, REPO), True)
    assert on_hold_file(tmp_path / "on_hold", a_pr(55, REPO)).read_bytes() == b""


def test_a_hold_another_process_set_is_seen(switches, tmp_path):
    _write(on_hold_file(tmp_path / "on_hold", a_pr(55, REPO)), "")
    assert switches.holds.on_hold(a_pr(55, REPO)) is True


def test_a_hold_set_by_one_instance_is_seen_and_lifted_by_another(tmp_path):
    cli, manager = disk_switches(tmp_path), disk_switches(tmp_path)
    cli.holds.set_on_hold(a_pr(55, REPO), True)
    assert manager.holds.on_hold(a_pr(55, REPO)) is True
    manager.holds.set_on_hold(a_pr(55, REPO), False)
    assert cli.holds.on_hold(a_pr(55, REPO)) is False


def test_a_dismissal_until_the_next_event_is_written_in_a_flag_file(switches, tmp_path):
    switches.dismissals.dismiss_until_next_event(a_pr(42, REPO))
    assert dismissed_file(tmp_path / "dismissed", a_pr(42, REPO)).read_bytes() == b"until-event"


def test_a_dismissal_forever_is_written_in_a_flag_file(switches, tmp_path):
    switches.dismissals.dismiss_forever(a_pr(42, REPO))
    assert dismissed_file(tmp_path / "dismissed", a_pr(42, REPO)).read_bytes() == b"forever"


def test_a_dismissal_until_the_next_event_written_before_still_reads(switches, tmp_path):
    _write(dismissed_file(tmp_path / "dismissed", a_pr(42, REPO)), "until-event")
    assert switches.dismissals.is_hidden(a_pr(42, REPO), events_waiting=False, draft=False) is True
    assert switches.dismissals.is_dismissed_forever(a_pr(42, REPO)) is False


def test_a_dismissal_another_process_wrote_is_read_with_its_whitespace_trimmed(switches, tmp_path):
    _write(dismissed_file(tmp_path / "dismissed", a_pr(42, REPO)), "forever\n")
    assert switches.dismissals.dismissal(a_pr(42, REPO)) is Dismissal.FOREVER


def test_a_flag_holding_no_known_mode_is_not_a_dismissal(switches, tmp_path):
    _write(dismissed_file(tmp_path / "dismissed", a_pr(42, REPO)), "bogus")
    assert switches.dismissals.dismissal(a_pr(42, REPO)) is None


def test_a_flag_holding_bytes_that_are_not_utf8_is_not_a_dismissal(switches, tmp_path):
    flag = dismissed_file(tmp_path / "dismissed", a_pr(42, REPO))
    flag.parent.mkdir(parents=True)
    flag.write_bytes(b"\xff\xfe forever")
    assert switches.dismissals.dismissal(a_pr(42, REPO)) is None


def test_a_directory_where_a_flag_belongs_is_not_a_dismissal(switches, tmp_path):
    dismissed_file(tmp_path / "dismissed", a_pr(42, REPO)).mkdir(parents=True)
    assert switches.dismissals.dismissal(a_pr(42, REPO)) is None


def test_forgetting_a_pr_removes_its_flag_files(switches, tmp_path):
    switches.holds.set_on_hold(a_pr(1, REPO), True)
    switches.dismissals.dismiss_forever(a_pr(1, REPO))

    switches.forget(a_pr(1, REPO))

    assert not on_hold_file(tmp_path / "on_hold", a_pr(1, REPO)).exists()
    assert not dismissed_file(tmp_path / "dismissed", a_pr(1, REPO)).exists()


def test_a_flag_that_cannot_be_removed_fails_the_forget_and_the_rest_still_go(switches, tmp_path):
    dismissed_file(tmp_path / "dismissed", a_pr(1, REPO)).mkdir(parents=True)
    switches.holds.set_on_hold(a_pr(1, REPO), True)

    assert switches.forget(a_pr(1, REPO)) is False

    assert switches.holds.on_hold(a_pr(1, REPO)) is False


def test_flagged_ignores_files_that_are_not_a_prs_flag(switches, tmp_path):
    _write(tmp_path / "on_hold" / "stray.flag", "")
    _write(tmp_path / "on_hold" / "acme" / "widgets" / "abc.flag", "")
    _write(tmp_path / "dismissed" / "acme" / "widgets" / "7.json", "")
    assert switches.flagged() == set()


def test_archiving_moves_the_repos_flag_directory_whole(switches, tmp_path):
    switches.holds.set_on_hold(a_pr(2, "acme/other"), True)
    into = tmp_path / "archive" / "on_hold"

    switches.holds.archive_other_repos({Repo.parse(REPO)}, into)

    assert on_hold_file(into, a_pr(2, "acme/other")).exists()
    assert not (tmp_path / "on_hold" / "acme" / "other").exists()


def test_archiving_leaves_dismissals_in_place(switches, tmp_path):
    switches.dismissals.dismiss_forever(a_pr(2, "acme/other"))

    assert switches.holds.archive_other_repos({Repo.parse(REPO)}, tmp_path / "archive" / "on_hold") == []

    assert switches.dismissals.dismissal(a_pr(2, "acme/other")) is Dismissal.FOREVER


