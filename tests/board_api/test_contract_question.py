import pytest

from github_orchestrator.agent_runs.fake import Outcome
from github_orchestrator.conversation import ConversationState
from tests.board_api.support import KEY, THE_PR, client_of, heard_on, proposed, running
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
                                "head": HEAD, "last_proposal": None}


def test_the_run_that_asked_has_settled(board):
    _asking(board)

    [run] = client_of(board).get(f"/api/conversations/{KEY}/operations").json()

    assert (run["kind"], run["state"]) == ("first", "applied")


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


def test_a_dropped_question_leaves_a_thread_no_agent_has_run_on(board):
    proposed(board)
    with board.threads.editing(KEY) as editable:
        editable.rework(note="stamp both bounds")
    _asking(board)
    asked(client_of(board), "drop-question")
    drained(board)

    question = client_of(board).get(f"/api/conversations/{KEY}").json()["question"]
    proposals = client_of(board).get(f"/api/conversations/{KEY}/proposals").json()
    written = asked(client_of(board), "fix")

    assert (question, proposals) == (None, [])
    assert written.status_code == 202, written.json()


def test_drop_question_refuses_a_thread_that_asks_nothing(ready):
    answer = asked(client_of(ready), "drop-question")

    assert answer.status_code == 409


def test_answering_a_question_opens_a_session(board):
    _asking(board)

    answering = settled_by(board, "start-session")

    assert answering.standing is ConversationState.IN_SESSION


def _asking_over_a_proposal(board):
    proposal = proposed(board)
    with board.threads.editing(KEY) as editable:
        editable.rework(note="use clock_timestamp() for both bounds")
    board.stage.agent_runs.script(Outcome(finishes=False))
    drain(board.threads)
    workspace = board.stage.working_copies.thread_checkout(THE_PR, KEY)
    board.stage.working_copies.commit(workspace, {"g": "committed since\n"}, "past it")
    board.stage.working_copies.edit(workspace, "f", "uncommitted\n")
    with board.threads.editing(KEY) as editable:
        editable.ask(QUESTION, CONTEXT, OPTIONS)
    return proposal


def test_a_question_asked_over_a_proposal_names_the_proposal_s_commits(board):
    proposal = _asking_over_a_proposal(board)

    question = client_of(board).get(f"/api/conversations/{KEY}").json()["question"]

    assert question["last_proposal"] == {"base": str(proposal.fix.base_sha),
                                         "head": str(proposal.fix.thread_sha)}


def test_a_first_run_s_question_names_no_proposal(board):
    _asking(board)

    assert client_of(board).get(f"/api/conversations/{KEY}").json()["question"][
        "last_proposal"] is None


def test_the_worktree_diff_holds_everything_past_the_last_proposal(board):
    proposal = _asking_over_a_proposal(board)

    diff = client_of(board).get(f"/api/conversations/{KEY}/worktree-diff").json()

    assert diff["base"] == str(proposal.fix.thread_sha)
    assert sorted(file["path"] for file in diff["files"]) == ["f", "g"]


def test_a_first_run_s_worktree_diff_holds_everything_it_changed(board):
    _asking(board)
    workspace = board.stage.working_copies.thread_checkout(THE_PR, KEY)
    board.stage.working_copies.edit(workspace, "f", "so far\n")

    diff = client_of(board).get(f"/api/conversations/{KEY}/worktree-diff").json()

    assert diff["base"] == str(board.threads.get(KEY).fix.base_sha)
    assert [file["path"] for file in diff["files"]] == ["f"]


def test_a_proposal_left_by_a_silent_run_carries_its_last_words(board):
    board.stage.agent_runs.script(Outcome(events=(
        {"type": "result", "subtype": "success", "is_error": False, "result": LAST_WORDS},)))
    drain(board.threads)
    commit_fix(board.stage, KEY, pr=THE_PR)
    drain(board.threads)

    [proposal] = client_of(board).get(f"/api/conversations/{KEY}/proposals").json()

    assert proposal["last_words"] == LAST_WORDS


ANSWER = "Widen the bound"


@pytest.mark.parametrize(("visible", "standing"), [(False, ConversationState.QUEUED),
                                                   (True, ConversationState.IN_SESSION)])
def test_answer_carries_the_agent_on_with_the_answer(board, visible, standing):
    _asking(board)

    answer = asked(client_of(board), "answer", text=ANSWER, visible=visible)

    assert answer.status_code == 202, answer.json()
    assert answer.json()["operation"]["kind"] == "answer"
    assert drained(board).standing is standing


def test_the_answer_stays_on_the_thread_s_operations(board):
    _asking(board)
    settled_by(board, "answer", text=ANSWER, visible=False)

    operations = client_of(board).get(f"/api/conversations/{KEY}/operations").json()

    assert (operations[-1]["kind"], operations[-1]["answer"]) == ("answer", ANSWER)


def test_answer_refuses_a_thread_that_asks_nothing(ready):
    answer = asked(client_of(ready), "answer", text=ANSWER, visible=False)

    assert answer.status_code == 409


def test_answer_refuses_an_answer_without_words(board):
    _asking(board)

    answer = asked(client_of(board), "answer", text="  ", visible=False)

    assert answer.status_code == 400
    assert answer.json()["errors"][0]["code"] == "empty-body"
