import copy

from github_orchestrator.conversation import (
    Classification,
    ConversationState,
    Denied,
    ErrorCode,
    OperationKind,
    OperationState,
)
from github_orchestrator.notifications.fake import FakeNotifications
from tests.conversation.support import (
    WORKTREE,
    drain,
    hear,
    on_github,
    repo_at,
    said,
    start_run,
    world,
)
from tests.conversation.test_verdicts import (
    ME,
    THE_PR,
    Board,
    _one_review_thread,
    _review_thread,
    _said,
)

KEY = "PRRT_mine"


def _confirmed(board, key="PRRT_one"):
    with board.manager.editing(key) as editable:
        asked = editable.place(ConversationState.DONE)
    board.manager.tick(FakeNotifications(), on_hold=False)
    return asked


def test_confirm_moves_an_assumed_done_thread_to_done_and_touches_nothing_on_github(settings):
    board = _one_review_thread(settings)
    board.agent_runs.give("assumed-done")
    on_github = copy.deepcopy((board.here.github.prs[THE_PR], board.here.github.reactions))

    _confirmed(board)

    held = board.get("PRRT_one")
    assert (held.standing, held.state) == (ConversationState.DONE, "confirmed")
    assert (board.here.github.prs[THE_PR], board.here.github.reactions) == on_github


def test_only_an_assumed_done_thread_can_be_confirmed(settings):
    refused = {}
    for word in ("my-move", "their-move", "not-mine"):
        board = _one_review_thread(settings)
        board.agent_runs.give(word)
        asked = _confirmed(board)
        refused[word] = asked.code if isinstance(asked, Denied) else asked

    assert refused == {"my-move": ErrorCode.NOT_PARKED, "their-move": ErrorCode.NOT_PARKED,
                       "not-mine": ErrorCode.NOT_PARKED}


def _placed(board, to, key="PRRT_one"):
    with board.manager.editing(key) as editable:
        asked = editable.place(to)
    board.manager.tick(FakeNotifications(), on_hold=False)
    return asked


def test_a_reviewer_places_an_assumed_done_or_not_mine_thread_in_each_outcome_by_hand(settings):
    placed = {}
    for word in ("assumed-done", "not-mine"):
        for to in (ConversationState.READY, ConversationState.WAITING,
                   ConversationState.NOT_MINE):
            board = _one_review_thread(settings)
            board.agent_runs.give(word)
            on_github = copy.deepcopy((board.here.github.prs[THE_PR],
                                       board.here.github.reactions))
            _placed(board, to)
            held = board.get("PRRT_one")
            placed[word, to] = (held.standing, held.unread,
                                len(board.agent_runs.verdicts_asked()))
            assert (board.here.github.prs[THE_PR], board.here.github.reactions) == on_github

    assert placed == {
        ("assumed-done", ConversationState.READY): (ConversationState.READY, False, 1),
        ("assumed-done", ConversationState.WAITING): (ConversationState.WAITING, False, 1),
        ("assumed-done", ConversationState.NOT_MINE): (ConversationState.NOT_MINE, False, 1),
        ("not-mine", ConversationState.READY): (ConversationState.READY, False, 1),
        ("not-mine", ConversationState.WAITING): (ConversationState.WAITING, False, 1),
        ("not-mine", ConversationState.NOT_MINE): (ConversationState.NOT_MINE, False, 1),
    }


def _code(asked):
    return asked.code if isinstance(asked, Denied) else asked


def test_only_an_assumed_done_or_not_mine_thread_can_be_placed_by_hand(settings):
    refused = {}
    for word in ("my-move", "their-move"):
        board = _one_review_thread(settings)
        board.agent_runs.give(word)
        refused[word] = _code(_placed(board, ConversationState.NOT_MINE))

    assert refused == {"my-move": ErrorCode.NOT_PARKED, "their-move": ErrorCode.NOT_PARKED}


def test_a_reviewer_cannot_place_a_thread_where_no_outcome_of_theirs_lands_it(settings):
    refused = {}
    for to in (ConversationState.QUEUED, ConversationState.ASSUMED_DONE,
               ConversationState.LANDING):
        board = _one_review_thread(settings)
        board.agent_runs.give("not-mine")
        refused[to] = _code(_placed(board, to))

    assert refused == {ConversationState.QUEUED: ErrorCode.MALFORMED_REQUEST,
                       ConversationState.ASSUMED_DONE: ErrorCode.MALFORMED_REQUEST,
                       ConversationState.LANDING: ErrorCode.MALFORMED_REQUEST}


def _declined_on_my_pr(settings, classification):
    here = world(settings)
    repo_at(here.working_copies, WORKTREE)
    threads = here.threads()
    on_github(here.github, KEY, said(101, "thanks, looks good"))
    hear(threads)
    start_run(here, threads, finishes=False)
    with threads.editing(KEY) as editable:
        editable.not_a_fix(classification, "nothing for the agent to change")
    drain(threads)
    return here, threads


def _assumed_done_on_my_pr(settings):
    return _declined_on_my_pr(settings, Classification.ACKNOWLEDGEMENT)


def test_on_my_pr_a_run_that_commits_nothing_lands_where_its_classification_says(settings):
    landed = {}
    for classification in Classification:
        _, threads = _declined_on_my_pr(settings, classification)
        held = threads.get(KEY)
        landed[classification] = (held.standing, held.state, held.fix.state)

    assumed_done = (ConversationState.ASSUMED_DONE, "assumed_done", "declined")
    needs_a_look = (ConversationState.READY, "open", "declined")
    a_reply_to_accept = (ConversationState.READY, "open", "proposed")
    assert landed == {Classification.ACKNOWLEDGEMENT: assumed_done,
                      Classification.NEEDS_HUMAN: needs_a_look,
                      Classification.RISKY: needs_a_look,
                      Classification.ALREADY_DONE: a_reply_to_accept,
                      Classification.QUESTION: a_reply_to_accept,
                      Classification.UNCLEAR: a_reply_to_accept,
                      Classification.OUT_OF_SCOPE: a_reply_to_accept}


def test_a_reviewers_new_comment_on_my_assumed_done_thread_reopens_it_and_runs_the_agent(
        settings):
    here, threads = _declined_on_my_pr(settings, Classification.ACKNOWLEDGEMENT)
    on_github(here.github, KEY, said(101, "thanks, looks good"),
              said(102, "actually, one more thing"))

    hear(threads)

    held = threads.get(KEY)
    assert held.standing is ConversationState.QUEUED
    assert held.operations[-1].kind is OperationKind.FIRST


def _placed_on_my_pr(threads, to):
    with threads.editing(KEY) as editable:
        asked = editable.place(to)
    drain(threads)
    return asked


def test_on_my_pr_an_assumed_done_thread_is_placed_in_each_of_my_outcomes(settings):
    placed = {}
    for to in (ConversationState.DONE, ConversationState.READY, ConversationState.WAITING,
               ConversationState.QUEUED, ConversationState.NOT_MINE):
        _, threads = _assumed_done_on_my_pr(settings)
        assert threads.get(KEY).standing is ConversationState.ASSUMED_DONE
        placed[to] = _code(_placed_on_my_pr(threads, to))
        if not isinstance(placed[to], ErrorCode):
            placed[to] = threads.get(KEY).standing

    assert placed == {ConversationState.DONE: ConversationState.DONE,
                      ConversationState.READY: ConversationState.READY,
                      ConversationState.WAITING: ConversationState.WAITING,
                      ConversationState.QUEUED: ConversationState.QUEUED,
                      ConversationState.NOT_MINE: ErrorCode.MALFORMED_REQUEST}


def test_needs_a_fix_on_my_pr_queues_a_fresh_first_run_and_needs_a_reply_queues_none(settings):
    _, fixing = _assumed_done_on_my_pr(settings)
    _, replying = _assumed_done_on_my_pr(settings)

    _placed_on_my_pr(fixing, ConversationState.QUEUED)
    _placed_on_my_pr(replying, ConversationState.READY)

    fresh = fixing.get(KEY).operations[-1]
    assert (fresh.kind, fresh.state) == (OperationKind.FIRST, OperationState.PENDING)
    assert replying.get(KEY).operations[-1].kind is OperationKind.PLACE


def test_your_own_confirmed_thread_counts_as_answered(settings):
    board = Board(settings, _review_thread("PRRT_one", _said(1, ME, "rename this"))).heard()
    board.agent_runs.give("assumed-done")

    _confirmed(board)

    assert board.manager.counts().answered == ("PRRT_one",)


def test_a_new_comment_on_a_confirmed_thread_brings_it_back_unread_and_asks_again(settings):
    board = _one_review_thread(settings)
    board.agent_runs.give("assumed-done")
    _confirmed(board)
    board.here.github.add_thread(THE_PR, _review_thread(
        "PRRT_one", _said(1, "ben", "rename this"),
        _said(2, "ben", "one more thing", "2026-09-01T11:00:00Z")))

    held = board.heard().get("PRRT_one")

    assert (held.standing, held.unread) == (ConversationState.READY, True)
    assert len(board.agent_runs.verdicts_asked()) == 2


def test_a_confirmed_thread_reopens_by_hand_and_takes_no_reply(settings):
    board = _one_review_thread(settings)
    board.agent_runs.give("assumed-done")
    _confirmed(board)

    with board.manager.editing("PRRT_one") as editable:
        replied = editable.reply("one more thing")
        reopened = editable.unpark()
    board.manager.tick(FakeNotifications(), on_hold=False)

    assert _code(replied) is ErrorCode.ALREADY_CLOSED
    assert not isinstance(reopened, Denied), reopened
    assert board.get("PRRT_one").standing is ConversationState.READY


def test_a_reviewers_new_comment_on_my_confirmed_thread_reopens_it_and_runs_the_agent(settings):
    here, threads = _assumed_done_on_my_pr(settings)
    _placed_on_my_pr(threads, ConversationState.DONE)
    on_github(here.github, KEY, said(101, "thanks, looks good"),
              said(102, "actually, one more thing"))

    hear(threads)

    assert threads.get(KEY).standing is ConversationState.QUEUED


def test_placing_a_reopened_thread_by_hand_clears_its_reopened_mark(settings):
    board = _one_review_thread(settings, _said(1, "ben", "rename this"),
                               _said(2, ME, "which helper?", "2026-09-01T10:30:00Z"))
    board.here.github.add_thread(THE_PR, _review_thread(
        "PRRT_one", _said(1, "ben", "rename this"),
        _said(2, ME, "which helper?", "2026-09-01T10:30:00Z"),
        _said(3, "ben", "never mind, carol is on it", "2026-09-01T11:00:00Z")))
    board.heard()
    board.agent_runs.give("not-mine")
    assert board.get("PRRT_one").reopened is True

    _placed(board, ConversationState.READY)

    assert board.get("PRRT_one").reopened is False
