from tests.board_api.support import (
    board_on,
    branched_from_main,
    client_of,
    fake_threads,
)
from tests.thread_records.support import disk_thread_records

MARKS = "/api/pull-request/read-marks"


def marks_board(copies, records=None):
    serving = {} if records is None else {"records": records}
    return client_of(board_on(fake_threads(working_copies=copies), base_branch="main",
                              **serving))


def test_a_pull_request_nobody_has_read_has_no_read_marks():
    copies, _, _ = branched_from_main()

    answer = marks_board(copies).get(MARKS)

    assert answer.status_code == 200
    assert answer.json() == {"marks": []}
    assert answer.headers["ETag"]


def test_marking_a_commit_read_keeps_its_subject_beside_its_sha():
    copies, _, head = branched_from_main()
    board = marks_board(copies)

    answer = board.post(f"{MARKS}/operations:mark-read", json={"sha": head})

    marked = {"marks": [{"sha": head, "subject": "check first"}]}
    assert answer.status_code == 200
    assert answer.json() == marked
    assert board.get(MARKS).json() == marked


def test_marking_a_commit_unread_drops_its_mark():
    copies, _, head = branched_from_main()
    board = marks_board(copies)
    board.post(f"{MARKS}/operations:mark-read", json={"sha": head})

    answer = board.post(f"{MARKS}/operations:mark-unread", json={"sha": head})

    assert answer.status_code == 200
    assert answer.json() == {"marks": []}
    assert board.get(MARKS).json() == {"marks": []}


def test_read_marks_outlive_the_board_that_wrote_them(tmp_path):
    copies, _, head = branched_from_main()
    marks_board(copies, disk_thread_records(tmp_path)).post(
        f"{MARKS}/operations:mark-read", json={"sha": head})

    answer = marks_board(copies, disk_thread_records(tmp_path)).get(MARKS)

    assert answer.json() == {"marks": [{"sha": head, "subject": "check first"}]}


def test_a_commit_git_does_not_have_cannot_be_marked_read():
    copies, _, _ = branched_from_main()
    board = marks_board(copies)

    answer = board.post(f"{MARKS}/operations:mark-read", json={"sha": "0" * 40})

    assert answer.status_code == 404
    assert answer.json()["errors"][0]["code"] == "no-such-commit"
    assert board.get(MARKS).json() == {"marks": []}
