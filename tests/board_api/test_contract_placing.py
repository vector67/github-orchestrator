from tests.board_api.support import client_of
from tests.board_api.test_contract_writes import asked
from tests.board_api.test_thread_phases import (
    KEY,
    reviewer_assumed_done,
    reviewer_not_mine,
)
from tests.conversation.support import drain


def _read(board):
    drain(board.threads)
    return client_of(board).get(f"/api/conversations/{KEY}").json()


def test_confirm_answers_its_operation_and_the_thread_reads_done_confirmed():
    board = reviewer_assumed_done()

    answer = asked(client_of(board), "confirm", key=KEY)

    assert answer.status_code == 202, answer.json()
    assert answer.json()["operation"]["kind"] == "confirm"
    served = _read(board)
    assert (served["state"], served["record_state"]) == ("done", "confirmed")


def test_place_moves_the_thread_to_the_state_it_names():
    board = reviewer_not_mine()

    answer = asked(client_of(board), "place", key=KEY, to="waiting")

    assert answer.status_code == 202, answer.json()
    assert answer.json()["operation"]["kind"] == "place"
    assert _read(board)["state"] == "waiting"


def test_place_takes_only_a_state_an_outcome_lands_a_thread_in():
    board = reviewer_not_mine()

    answer = asked(client_of(board), "place", key=KEY, to="landing")

    assert answer.status_code == 400
    assert answer.json()["errors"][0]["code"] == "malformed-request"


def test_confirm_refuses_a_thread_no_agent_assumed_done():
    board = reviewer_not_mine()

    answer = asked(client_of(board), "confirm", key=KEY)

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "not-parked"
