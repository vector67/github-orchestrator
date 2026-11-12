from github_orchestrator.conversation import ConversationState
from tests.board_api.support import client_of
from tests.board_api.test_contract_writes import asked
from tests.board_api.test_thread_phases import KEY, reviewer_answered
from tests.conversation.support import drain


def _done(board, verb, **body):
    answer = asked(client_of(board), verb, key=KEY, **body)
    assert answer.status_code == 202, answer.json()
    assert answer.json()["operation"]["kind"] == "resolve"
    drain(board.threads)
    return board


def test_resolve_with_nothing_but_the_verb_resolves_the_thread_on_github():
    board = _done(reviewer_answered(), "resolve")

    assert board.threads.get(KEY).standing is ConversationState.DONE
    assert board.stage.github.thread(KEY).is_resolved


def test_mark_done_closes_the_thread_with_nothing_sent_to_github():
    board = reviewer_answered()
    comments = board.stage.github.thread(KEY).comments

    _done(board, "mark-done")

    assert board.threads.get(KEY).standing is ConversationState.DONE
    thread = board.stage.github.thread(KEY)
    assert not thread.is_resolved
    assert thread.comments == comments
    assert board.stage.github.thumbed_up() == []


def test_mark_done_with_a_reply_posts_the_reply_and_nothing_else():
    board = _done(reviewer_answered(), "mark-done", reply="Thanks, that reads better.")

    assert board.threads.get(KEY).standing is ConversationState.DONE
    thread = board.stage.github.thread(KEY)
    assert not thread.is_resolved
    assert thread.comments[-1].body == "Thanks, that reads better."
    assert board.stage.github.thumbed_up() == []
