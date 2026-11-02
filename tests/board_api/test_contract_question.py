from github_orchestrator.agent_runs.fake import Outcome
from github_orchestrator.conversation import ConversationState
from tests.board_api.support import KEY, THE_PR, client_of, heard_on, running
from tests.board_api.test_contract_writes import (
    asked,
    board,
    board_of,
    drained,
    ready,
    settled_by,
)
from tests.conversation.support import commit_fix, drain

__all__ = ["board", "ready"]

QUESTION = "Change production, or widen the bound?"
CONTEXT = "Every test in the file failed."
OPTIONS = ["Change production", "Widen the bound"]
LAST_WORDS = "Shall I change production, or widen the bound?"
HEAD = "8f73fe8" + "0" * 33


def _asking(board):
    running(board)
    with board.threads.editing(KEY) as editable:
        editable.ask(QUESTION, CONTEXT, OPTIONS)


def test_a_thread_whose_agent_asked_carries_the_question_and_the_head_it_was_asked_on():
    board = board_of(head_sha=HEAD)
    heard_on(board, KEY)
    _asking(board)

    read = client_of(board).get(f"/api/conversations/{KEY}").json()

    assert read["state"] == "ready"
    assert read["question"] == {"text": QUESTION, "context": CONTEXT, "options": OPTIONS,
                                "head": HEAD}


def test_a_thread_whose_agent_asked_nothing_carries_no_question(ready):
    assert client_of(ready).get(f"/api/conversations/{KEY}").json()["question"] is None


def test_drop_question_gives_up_the_question(board):
    _asking(board)

    answer = asked(client_of(board), "drop-question")

    assert answer.status_code == 202, answer.json()
    assert answer.json()["operation"]["kind"] == "drop-question"
    dropped = drained(board)
    assert dropped.standing is ConversationState.READY
    assert dropped.fix.question is None


def test_drop_question_refuses_a_thread_that_asks_nothing(ready):
    answer = asked(client_of(ready), "drop-question")

    assert answer.status_code == 409


def test_answering_a_question_opens_a_session(board):
    _asking(board)

    answering = settled_by(board, "start-session")

    assert answering.standing is ConversationState.IN_SESSION


def test_a_proposal_left_by_a_silent_run_carries_its_last_words(board):
    board.stage.agent_runs.script(Outcome(events=(
        {"type": "result", "subtype": "success", "is_error": False, "result": LAST_WORDS},)))
    drain(board.threads)
    commit_fix(board.stage, KEY, pr=THE_PR)
    drain(board.threads)

    [proposal] = client_of(board).get(f"/api/conversations/{KEY}/proposals").json()

    assert proposal["last_words"] == LAST_WORDS
