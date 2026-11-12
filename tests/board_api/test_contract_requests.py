import pytest

from github_orchestrator.github.fake import FakeGitHub
from tests.board_api.support import (
    ACCOUNT,
    THE_PR,
    board_on,
    client_of,
    fake_threads,
    followed,
)

PATH = "f.py"

ASKED = "stop at the first match"


def _board(*, is_author=True):
    return board_on(fake_threads(FakeGitHub(account=ACCOUNT), agents_enabled=True),
                    is_author=is_author)


def _requested(client, **fields):
    return client.post("/api/operations:request-change",
                       json={"body": ASKED, "path": PATH, "line": 4, **fields})


@pytest.mark.parametrize(("visible", "kind"), [(False, "first"), (True, "start-session")])
def test_a_requested_change_is_a_thread_on_the_board_alone_and_starts_its_run(visible, kind):
    board = _board()
    client = client_of(board)

    answer = _requested(client, visible=visible)

    assert answer.status_code == 202
    started = answer.json()
    assert started["kind"] == kind
    assert followed(client, answer).json() == started
    requested = client.get(f"/api/conversations/{started['conversation']}").json()
    assert (requested["kind"], requested["github_node_id"]) == ("request", None)
    assert [one["author"] for one in requested["comments"]] == [ACCOUNT]
    assert board.stage.github.prs[THE_PR].threads == []


def test_a_change_is_requested_only_on_your_own_pull_request():
    answer = _requested(client_of(_board(is_author=False)), visible=False)

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "malformed-request"
