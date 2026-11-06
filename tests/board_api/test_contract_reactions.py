from dataclasses import replace

from github_orchestrator.github.fake import Reaction, ReactionContent
from tests.board_api.support import (
    BODY,
    COMMENT_ID,
    KEY,
    board_on,
    client_of,
    fake_threads,
    heard_on,
)
from tests.conversation.support import said


def _board(*reactions: Reaction):
    board = board_on(fake_threads())
    heard_on(board, KEY, replace(said(COMMENT_ID, BODY), node_id="PRRC_101",
                                 reactions=reactions))
    return board


def _react(client, content, *, mine=True, comment_id=COMMENT_ID):
    return client.post(f"/api/conversations/{KEY}/comments/{comment_id}:react",
                       json={"content": content, "mine": mine})


def test_a_comments_reactions_come_with_the_conversation_and_the_comment():
    client = client_of(_board(Reaction(ReactionContent.THUMBS_UP, 2, mine=True),
                              Reaction(ReactionContent.EYES, 1, mine=False)))
    expected = [{"content": "thumbs-up", "count": 2, "mine": True},
                {"content": "eyes", "count": 1, "mine": False}]

    summary = client.get(f"/api/conversations/{KEY}").json()["comments"][0]
    comment = client.get(f"/api/conversations/{KEY}/comments/{COMMENT_ID}").json()

    assert summary["reactions"] == expected
    assert comment["reactions"] == expected


def test_my_reaction_is_sent_and_the_conversation_comes_back_with_it_and_a_new_etag():
    board = _board()
    client = client_of(board)
    before = client.get(f"/api/conversations/{KEY}").json()["etag"]

    answer = _react(client, "hooray")

    assert answer.status_code == 200
    assert answer.json()["comments"][0]["reactions"] == [
        {"content": "hooray", "count": 1, "mine": True}]
    assert answer.json()["etag"] == client.get(f"/api/conversations/{KEY}").json()["etag"]
    assert answer.json()["etag"] != before
    assert board.stage.github.thread(KEY).comments[0].reactions == (
        Reaction(ReactionContent.HOORAY, 1, mine=True),)


def test_taking_my_reaction_back_leaves_the_others():
    client = client_of(_board(Reaction(ReactionContent.HEART, 3, mine=True)))

    answer = _react(client, "heart", mine=False)

    assert answer.json()["comments"][0]["reactions"] == [
        {"content": "heart", "count": 2, "mine": False}]


def test_a_reaction_github_refuses_is_a_refusal_naming_github():
    board = _board()
    board.stage.github.prs[next(iter(board.stage.github.prs))].threads = []

    answer = _react(client_of(board), "eyes")

    assert answer.status_code == 502
    assert answer.json()["errors"][0]["code"] == "github-rejected"


def test_a_reaction_on_a_comment_the_thread_does_not_hold_is_not_found():
    answer = _react(client_of(_board()), "eyes", comment_id=999)

    assert answer.status_code == 404


def test_a_reaction_github_has_no_word_for_is_refused_as_malformed():
    answer = _react(client_of(_board()), "party-parrot")

    assert answer.status_code == 400
    assert answer.json()["errors"][0]["code"] == "malformed-request"
