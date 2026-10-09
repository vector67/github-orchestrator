import errno
import socket

import pytest

from github_orchestrator.domain import Repo
from github_orchestrator.settings.fake import Dismissal
from tests.builders import a_pr
from tests.disk_layout import (
    board_flag_file,
    board_port_file,
    dismissed_file,
    on_hold_file,
)
from tests.settings.support import disk_switches

REPO = "acme/widgets"
FIRST_PORT = 8730
LAST_PORT = 8829


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
    assert switches.dismissals.is_hidden(a_pr(42, REPO), events_waiting=False) is True
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


def test_a_wanted_board_is_an_empty_flag_file(switches, tmp_path):
    switches.boards.want_board(a_pr(55, REPO), True)
    assert board_flag_file(tmp_path / "board", a_pr(55, REPO)).read_bytes() == b""


def test_the_first_board_port_is_the_first_free_one_in_the_range(switches):
    assert FIRST_PORT <= switches.boards.board_port(a_pr(55, REPO)) <= LAST_PORT


def test_the_board_port_is_written_where_the_next_process_reads_it(switches, tmp_path):
    port = switches.boards.board_port(a_pr(55, REPO))
    assert board_port_file(tmp_path / "board", a_pr(55, REPO)).read_text() == str(port)


def test_a_port_assigned_to_another_pr_is_not_handed_out_again(switches, tmp_path):
    _write(board_port_file(tmp_path / "board", a_pr(55, REPO)), str(FIRST_PORT))
    assert switches.boards.board_port(a_pr(56, REPO)) != FIRST_PORT


def test_a_port_something_else_is_listening_on_is_skipped(switches):
    with socket.socket() as held:
        try:
            held.bind(("127.0.0.1", FIRST_PORT))
            held.listen(1)
        except OSError as already_listening:
            if already_listening.errno != errno.EADDRINUSE:
                raise
        assert switches.boards.board_port(a_pr(55, REPO)) != FIRST_PORT


def test_an_unparsable_port_file_is_replaced(switches, tmp_path):
    _write(board_port_file(tmp_path / "board", a_pr(55, REPO)), "not a port")
    assert FIRST_PORT <= switches.boards.board_port(a_pr(55, REPO)) <= LAST_PORT


def test_a_port_outside_the_range_is_kept(switches, tmp_path):
    _write(board_port_file(tmp_path / "board", a_pr(55, REPO)), "41234")
    assert switches.boards.board_port(a_pr(55, REPO)) == 41234


def test_an_exhausted_range_raises(switches, tmp_path):
    for offset, port in enumerate(range(FIRST_PORT, LAST_PORT + 1)):
        _write(board_port_file(tmp_path / "board", a_pr(9000 + offset, REPO)), str(port))
    with pytest.raises(RuntimeError):
        switches.boards.board_port(a_pr(55, REPO))


def test_forgetting_a_pr_removes_its_four_files(switches, tmp_path):
    switches.holds.set_on_hold(a_pr(1, REPO), True)
    switches.dismissals.dismiss_forever(a_pr(1, REPO))
    switches.boards.want_board(a_pr(1, REPO), True)
    switches.boards.board_port(a_pr(1, REPO))

    switches.forget(a_pr(1, REPO))

    assert not on_hold_file(tmp_path / "on_hold", a_pr(1, REPO)).exists()
    assert not dismissed_file(tmp_path / "dismissed", a_pr(1, REPO)).exists()
    assert not board_flag_file(tmp_path / "board", a_pr(1, REPO)).exists()
    assert not board_port_file(tmp_path / "board", a_pr(1, REPO)).exists()


def test_a_flag_that_cannot_be_removed_fails_the_forget_and_the_rest_still_go(switches, tmp_path):
    dismissed_file(tmp_path / "dismissed", a_pr(1, REPO)).mkdir(parents=True)
    switches.holds.set_on_hold(a_pr(1, REPO), True)
    switches.boards.board_port(a_pr(1, REPO))

    assert switches.forget(a_pr(1, REPO)) is False

    assert switches.holds.on_hold(a_pr(1, REPO)) is False
    assert not board_port_file(tmp_path / "board", a_pr(1, REPO)).exists()


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


def test_archiving_leaves_dismissals_and_boards_in_place(switches, tmp_path):
    switches.dismissals.dismiss_forever(a_pr(2, "acme/other"))
    switches.boards.want_board(a_pr(2, "acme/other"), True)

    assert switches.holds.archive_other_repos({Repo.parse(REPO)}, tmp_path / "archive" / "on_hold") == []

    assert switches.dismissals.dismissal(a_pr(2, "acme/other")) is Dismissal.FOREVER
    assert switches.boards.board_wanted(a_pr(2, "acme/other")) is True


def _hold_a_free_board_port(held):
    for port in range(FIRST_PORT, LAST_PORT + 1):
        try:
            held.bind(("127.0.0.1", port))
        except OSError:
            continue
        held.listen(1)
        return
    raise AssertionError("every board port is taken")


def test_the_board_ports_in_use_are_counted_out_of_the_whole_range(switches):
    in_use, out_of = switches.boards.ports_in_use()

    with socket.socket() as held:
        _hold_a_free_board_port(held)
        assert switches.boards.ports_in_use() == (in_use + 1, LAST_PORT - FIRST_PORT + 1)
    assert out_of == 100
