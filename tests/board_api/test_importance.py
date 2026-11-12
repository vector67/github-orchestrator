from github_orchestrator.board_api.interface import Importance, PrImportance
from github_orchestrator.wiring import RecordShelves
from tests.board_api.support import THE_PR, board_on, client_of, fake_threads
from tests.thread_records.support import disk_thread_records

IMPORTANCE = "/api/pull-request/importance"


def shelf_of(records):
    return RecordShelves(records).of(THE_PR)


def ranking_board(records):
    return client_of(board_on(fake_threads(), records=records))


def test_setting_importance_keeps_it_on_the_prs_shelf(tmp_path):
    records = disk_thread_records(tmp_path)

    answer = ranking_board(records).post(f"{IMPORTANCE}/operations:set",
                                         json={"importance": "important"})

    assert answer.status_code == 200
    assert answer.json() == {"importance": "important", "nudged_at": None}
    assert PrImportance.kept(shelf_of(records)) == PrImportance(Importance.IMPORTANT)


def test_changing_importance_keeps_when_you_last_nudged(tmp_path):
    records = disk_thread_records(tmp_path)
    PrImportance(Importance.IMPORTANT, "2026-11-10T09:00:00+00:00").keep(shelf_of(records))

    ranking_board(records).post(f"{IMPORTANCE}/operations:set", json={"importance": "someday"})

    assert PrImportance.kept(shelf_of(records)) == PrImportance(
        Importance.SOMEDAY, "2026-11-10T09:00:00+00:00")


def test_an_importance_the_board_does_not_know_is_refused(tmp_path):
    records = disk_thread_records(tmp_path)

    answer = ranking_board(records).post(f"{IMPORTANCE}/operations:set",
                                         json={"importance": "urgent"})

    assert answer.status_code == 400
    assert PrImportance.kept(shelf_of(records)) == PrImportance()


def test_saying_you_nudged_them_keeps_when_beside_the_importance(tmp_path):
    records = disk_thread_records(tmp_path)
    PrImportance(Importance.IMPORTANT).keep(shelf_of(records))

    answer = ranking_board(records).post(f"{IMPORTANCE}/operations:nudged")

    kept = PrImportance.kept(shelf_of(records))
    assert answer.status_code == 200
    assert answer.json() == {"importance": "important", "nudged_at": kept.nudged_at}
    assert kept.importance is Importance.IMPORTANT and kept.nudged_at is not None
