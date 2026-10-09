from tests.board_api.support import KEY, board_on, client_of, fake_threads, heard_on


def _board():
    board = board_on(fake_threads())
    heard_on(board)
    return board


def test_opening_a_conversation_on_the_board_stamps_it_seen():
    board = _board()

    answer = client_of(board).post(f"/api/conversations/{KEY}/seen")

    assert answer.status_code == 204
    assert board.threads.get(KEY).seen_at is not None


def test_being_seen_leaves_the_conversation_etag_alone():
    client = client_of(_board())
    before = client.get(f"/api/conversations/{KEY}").json()["etag"]

    client.post(f"/api/conversations/{KEY}/seen")

    assert client.get(f"/api/conversations/{KEY}").json()["etag"] == before


def test_a_conversation_the_board_does_not_hold_cannot_be_seen():
    answer = client_of(_board()).post("/api/conversations/PRRT_nobody/seen")

    assert answer.status_code == 404
