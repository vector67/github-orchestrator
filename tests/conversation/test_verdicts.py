import json
from datetime import timedelta

from github_orchestrator.agent_runs.fake import HeldVerdicts, VerdictAsked
from github_orchestrator.change_detection import Poll
from github_orchestrator.conversation import ConversationState
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    ReviewState,
    Thread,
    ThreadComment,
)
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.pr_processes.fake import FakePrProcesses
from tests.builders import a_pr
from tests.change_detection.support import POLLED_AT
from tests.conftest import ticking_clock
from tests.conversation.support import PR, REPO, world

THE_PR = a_pr(PR, REPO)
ME = "octocat"
AUTHOR = "anna"


def _said(comment_id, author, body, at="2026-09-01T10:00:00Z"):
    return ThreadComment(id=comment_id, author=author, body=body, created_at=at,
                         updated_at=at)


def _review_thread(key, *comments):
    return Thread(key=key, kind=CommentKind.REVIEW, path="f", line=1, comments=comments)


def _issue(key, comment):
    return Thread(key=key, kind=CommentKind.ISSUE, comments=(comment,))


def _review_body(key, comment):
    return Thread(key=key, kind=CommentKind.REVIEW_SUMMARY, state=ReviewState.COMMENTED,
                  comments=(comment,))


class Board:
    def __init__(self, settings, *threads, body="", author=AUTHOR):
        self.agent_runs = HeldVerdicts(FakePrProcesses())
        self.later = timedelta(0)
        ticking = ticking_clock()
        self.here = world(settings, agent_runs=self.agent_runs,
                          clock=lambda: ticking() + self.later)
        self.state = PullRequestState(author=author, body=body)
        self.here.github.add_pr(THE_PR, self.state)
        for thread in threads:
            self.here.github.add_thread(THE_PR, thread)
        self.here.change_detection.advance(THE_PR, Poll(self.state, POLLED_AT), set())
        self.manager = self.here.conversation_managers.of(THE_PR)

    def heard(self):
        polled = self.manager.poll(self.state)
        polled.commit()
        if polled.activity is not None:
            self.manager.absorb(polled.activity)
        self.here.change_detection.advance(
            THE_PR, Poll(self.state, POLLED_AT, mentions=polled.mentions), set())
        return self

    def get(self, key):
        return self.manager.get(key)

    def tick_after(self, minutes):
        self.later += timedelta(minutes=minutes)
        self.manager.tick(FakeNotifications(), on_hold=False)


def test_a_colleagues_single_comment_is_my_move_not_yet_read(settings):
    board = Board(settings, _review_thread("PRRT_one", _said(1, "ben", "rename this"))).heard()

    held = board.get("PRRT_one")

    assert held.standing is ConversationState.READY
    assert held.unread is True


def test_a_colleagues_single_comment_asks_for_a_verdict_with_the_facts(settings):
    board = Board(settings, _review_thread("PRRT_one", _said(1, "ben", "rename this"))).heard()

    [asked] = board.agent_runs.verdicts_asked()

    assert asked == VerdictAsked(
        key="PRRT_one", comments=(("colleague", "ben", "rename this"),), viewer=ME,
        pr_author=AUTHOR, spoke_last="colleague ben", viewer_commented=False,
        mentions_viewer=False, kind="review thread on a line")


def _one_review_thread(settings, *comments):
    return Board(settings, _review_thread("PRRT_one", *(comments or (
        _said(1, "ben", "rename this"),)))).heard()


def test_the_pr_description_is_my_move_not_waiting_on_its_author(settings):
    board = Board(settings, body="A description.\n\ncc @octocat").heard()

    held = board.get("pr-body")

    assert (held.standing, held.unread) == (ConversationState.READY, True)
    [asked] = board.agent_runs.verdicts_asked()
    assert (asked.kind, asked.comments[0][0], asked.mentions_viewer) == (
        "PR description", "PR author", True)


def test_a_bots_summary_is_my_move_not_waiting_on_the_bot(settings):
    board = Board(settings, _review_body(
        "PRR_1", _said(3, "claude[bot]", "@octocat here is a summary"))).heard()

    held = board.get("PRR_1")

    assert (held.standing, held.unread) == (ConversationState.READY, True)
    [asked] = board.agent_runs.verdicts_asked()
    assert (asked.kind, asked.spoke_last) == ("review summary", "bot claude[bot]")


def test_the_facts_label_each_comment_and_say_the_viewer_spoke(settings):
    board = _one_review_thread(settings, _said(1, ME, "rename this"),
                               _said(2, AUTHOR, "which one?", "2026-09-01T11:00:00Z"),
                               _said(3, "ben", "@octocat the helper", "2026-09-01T12:00:00Z"))

    [asked] = board.agent_runs.verdicts_asked()

    assert asked.comments == (("you", ME, "rename this"), ("PR author", AUTHOR, "which one?"),
                              ("colleague", "ben", "@octocat the helper"))
    assert (asked.viewer_commented, asked.mentions_viewer, asked.spoke_last) == (
        True, True, "colleague ben")


def test_each_verdict_places_the_thread_where_the_spec_says(settings):
    placed = {}
    for word, standing in (("my-move", ConversationState.READY),
                           ("their-move", ConversationState.WAITING),
                           ("assumed-done", ConversationState.ASSUMED_DONE),
                           ("not-mine", ConversationState.NOT_MINE)):
        board = _one_review_thread(settings)
        board.agent_runs.give(word)
        held = board.get("PRRT_one")
        placed[word] = (held.standing, held.unread)
        assert held.standing is standing

    assert placed == {"my-move": (ConversationState.READY, False),
                      "their-move": (ConversationState.WAITING, False),
                      "assumed-done": (ConversationState.ASSUMED_DONE, False),
                      "not-mine": (ConversationState.NOT_MINE, False)}


def test_a_verdict_for_an_older_comment_than_the_newest_is_dropped(settings):
    board = _one_review_thread(settings)
    board.here.github.add_thread(THE_PR, _review_thread(
        "PRRT_one", _said(1, "ben", "rename this"),
        _said(2, AUTHOR, "done in abc123", "2026-09-01T11:00:00Z")))
    board.heard()

    board.agent_runs.give("not-mine", at=0)

    held = board.get("PRRT_one")
    assert (held.standing, held.unread) == (ConversationState.READY, True)
    board.agent_runs.give("assumed-done")
    assert board.get("PRRT_one").standing is ConversationState.ASSUMED_DONE


def test_a_new_comment_on_a_thread_that_is_not_mine_brings_it_back_unread(settings):
    board = _one_review_thread(settings)
    board.agent_runs.give("not-mine")
    board.here.github.add_thread(THE_PR, _review_thread(
        "PRRT_one", _said(1, "ben", "rename this"),
        _said(2, "ben", "@octocat what do you think?", "2026-09-01T11:00:00Z")))

    held = board.heard().get("PRRT_one")

    assert (held.standing, held.unread) == (ConversationState.READY, True)
    assert len(board.agent_runs.verdicts_asked()) == 2


def test_a_reply_from_the_board_parks_the_thread_then_asks_again(settings):
    board = _one_review_thread(settings)
    board.agent_runs.give("my-move")

    with board.manager.editing("PRRT_one") as editable:
        editable.reply("which helper?")
    board.manager.tick(FakeNotifications(), on_hold=False)

    assert board.get("PRRT_one").standing is ConversationState.WAITING
    assert board.agent_runs.verdicts_asked()[-1].spoke_last == "you octocat"
    board.agent_runs.give("assumed-done")
    assert board.get("PRRT_one").standing is ConversationState.ASSUMED_DONE


def test_resolving_on_github_still_moves_an_assumed_done_thread_to_done(settings):
    board = _one_review_thread(settings)
    board.agent_runs.give("assumed-done")
    board.here.github.add_thread(THE_PR, Thread(
        key="PRRT_one", kind=CommentKind.REVIEW, path="f", line=1, is_resolved=True,
        comments=(_said(1, "ben", "rename this"),)))

    held = board.heard().get("PRRT_one")

    assert held.standing is ConversationState.DONE


def test_a_verdict_is_asked_once_per_newest_comment_however_many_ticks_pass(settings):
    board = _one_review_thread(settings)

    for _ in range(3):
        board.manager.tick(FakeNotifications(), on_hold=False)

    assert len(board.agent_runs.verdicts_asked()) == 1


def test_deferring_then_waking_by_hand_puts_the_thread_back_unread_and_asks_again(settings):
    board = _one_review_thread(settings)
    board.agent_runs.give("their-move")
    with board.manager.editing("PRRT_one") as editable:
        editable.place(ConversationState.DEFERRED)
    board.manager.tick(FakeNotifications(), on_hold=False)
    with board.manager.editing("PRRT_one") as editable:
        editable.unpark()
    board.manager.tick(FakeNotifications(), on_hold=False)

    held = board.get("PRRT_one")

    assert (held.standing, held.unread) == (ConversationState.READY, True)
    assert len(board.agent_runs.verdicts_asked()) == 2


def test_a_mention_waiting_on_its_writer_is_no_longer_lifted_into_my_move(settings):
    board = Board(settings, _issue("IC_1", _said(1, "ben", "@octocat ping"))).heard()
    board.agent_runs.give("their-move")

    assert board.get("IC_1").standing is ConversationState.WAITING
    assert board.get("IC_1").mention is True


def test_a_failed_verdict_call_leaves_the_thread_my_move_not_yet_read(settings):
    board = _one_review_thread(settings)
    board.agent_runs.held.clear()

    board.manager.tick(FakeNotifications(), on_hold=False)

    held = board.get("PRRT_one")
    assert (held.standing, held.unread) == (ConversationState.READY, True)
    assert len(board.agent_runs.verdicts_asked()) == 1


def test_a_failed_verdict_call_is_asked_again_on_a_later_tick(settings):
    board = _one_review_thread(settings)
    board.agent_runs.held.clear()

    board.tick_after(minutes=15)

    assert len(board.agent_runs.verdicts_asked()) == 2
    board.agent_runs.give("their-move")
    assert board.get("PRRT_one").standing is ConversationState.WAITING


def test_a_failed_verdict_call_is_not_asked_again_within_ten_minutes(settings):
    board = _one_review_thread(settings)
    board.agent_runs.held.clear()

    board.tick_after(minutes=5)

    assert len(board.agent_runs.verdicts_asked()) == 1


def test_a_verdict_is_asked_at_most_three_times_for_one_newest_comment(settings):
    board = _one_review_thread(settings)

    for _ in range(4):
        board.agent_runs.held.clear()
        board.tick_after(minutes=15)

    held = board.get("PRRT_one")
    assert len(board.agent_runs.verdicts_asked()) == 3
    assert (held.standing, held.unread) == (ConversationState.READY, True)


def test_a_new_comment_after_three_failed_asks_is_asked_again(settings):
    board = _one_review_thread(settings)
    for _ in range(3):
        board.agent_runs.held.clear()
        board.tick_after(minutes=15)
    board.here.github.add_thread(THE_PR, _review_thread(
        "PRRT_one", _said(1, "ben", "rename this"),
        _said(2, "ben", "any news?", "2026-09-01T11:00:00Z")))

    board.heard()

    assert len(board.agent_runs.verdicts_asked()) == 4


def _rewritten(board, key, state, *dropped):
    records = board.here.thread_records.of(THE_PR)
    document = json.loads(records.load("json", key))
    for field_name in dropped:
        document.pop(field_name)
    document["conversation_state"] = state
    records.save("json", key, json.dumps(document).encode())


def _written_before_verdicts(board, key, state):
    _rewritten(board, key, state, "verdict", "verdict_for", "verdict_asked_for",
               "verdict_asks", "verdict_asked_at")


def _written_by_step_one_after_a_failed_ask(board, key, state):
    _rewritten(board, key, state, "verdict_asks", "verdict_asked_at")


def test_a_waiting_record_from_before_verdicts_reads_my_move_not_yet_read(settings):
    board = _one_review_thread(settings)
    _written_before_verdicts(board, "PRRT_one", "waiting_on_reviewer")

    held = board.get("PRRT_one")

    assert (held.standing, held.unread) == (ConversationState.READY, True)


def test_a_waiting_record_whose_step_one_ask_failed_reads_my_move_and_is_asked_again(settings):
    board = _one_review_thread(settings)
    board.agent_runs.held.clear()
    _written_by_step_one_after_a_failed_ask(board, "PRRT_one", "waiting_on_reviewer")

    held = board.get("PRRT_one")
    board.manager.tick(FakeNotifications(), on_hold=False)

    assert (held.standing, held.unread) == (ConversationState.READY, True)
    assert len(board.agent_runs.verdicts_asked()) == 2
    board.agent_runs.give("their-move")
    assert board.get("PRRT_one").standing is ConversationState.WAITING


def test_a_waiting_record_from_before_verdicts_is_asked_once_on_the_next_tick(settings):
    board = _one_review_thread(settings)
    _written_before_verdicts(board, "PRRT_one", "waiting_on_reviewer")

    board.manager.tick(FakeNotifications(), on_hold=False)
    board.manager.tick(FakeNotifications(), on_hold=False)

    assert len(board.agent_runs.verdicts_asked()) == 2
    board.agent_runs.give("my-move")
    held = board.get("PRRT_one")
    assert (held.standing, held.unread) == (ConversationState.READY, False)


def test_an_open_record_from_before_verdicts_reads_not_yet_read(settings):
    board = _one_review_thread(settings)
    _written_before_verdicts(board, "PRRT_one", "open")

    held = board.get("PRRT_one")

    assert (held.standing, held.unread, held.verdict) == (ConversationState.READY, True, None)


def test_your_own_thread_assumed_done_is_answered_and_not_mine_is_not(settings):
    board = Board(settings, _review_thread("PRRT_one", _said(1, ME, "rename this")),
                  _review_thread("PRRT_two", _said(2, ME, "and this"))).heard()
    board.agent_runs.give("assumed-done", key="PRRT_one")
    board.agent_runs.give("not-mine", key="PRRT_two")

    assert board.manager.counts().answered == ("PRRT_one",)


def test_a_colleagues_thread_a_verdict_parked_is_not_reopened_by_another_colleague(settings):
    board = _one_review_thread(settings)
    board.agent_runs.give("their-move")
    board.here.github.add_thread(THE_PR, _review_thread(
        "PRRT_one", _said(1, "ben", "rename this"),
        _said(2, "carol", "agreed, rename it", "2026-09-01T11:00:00Z")))

    held = board.heard().get("PRRT_one")

    assert (held.standing, held.reopened) == (ConversationState.READY, False)


def test_a_thread_the_viewer_commented_on_is_reopened_when_it_lands_in_answered(settings):
    board = _one_review_thread(settings, _said(1, "ben", "rename this"),
                               _said(2, ME, "which helper?", "2026-09-01T10:30:00Z"))
    board.here.github.add_thread(THE_PR, _review_thread(
        "PRRT_one", _said(1, "ben", "rename this"),
        _said(2, ME, "which helper?", "2026-09-01T10:30:00Z"),
        _said(3, AUTHOR, "the reader one", "2026-09-01T11:00:00Z")))

    held = board.heard().get("PRRT_one")

    assert (held.standing, held.reopened) == (ConversationState.READY, True)
