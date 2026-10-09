from datetime import timedelta

from github_orchestrator.agent_runs.fake import HeldVerdicts
from github_orchestrator.change_detection import Poll
from github_orchestrator.conversation import ConversationState
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    Thread,
    ThreadComment,
)
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.pr_processes.fake import FakePrProcesses
from tests.builders import a_pr
from tests.change_detection.support import POLLED_AT
from tests.conftest import ticking_clock
from tests.conversation.support import PR, REPO, WORKTREE, repo_at, world

THE_PR = a_pr(PR, REPO)
ME = "octocat"
AUTHOR = "anna"
KEY = "PRRT_one"


def _said(comment_id, author, body, at="2026-09-01T10:00:00Z"):
    return ThreadComment(id=comment_id, author=author, body=body, created_at=at,
                         updated_at=at)


class Board:
    def __init__(self, settings):
        self.agent_runs = HeldVerdicts(FakePrProcesses())
        self.later = timedelta(0)
        ticking = ticking_clock()
        self.here = world(settings, agent_runs=self.agent_runs,
                          clock=lambda: ticking() + self.later)
        repo_at(self.here.working_copies, WORKTREE, {"helpers.py": "def old_name():\n"})
        self.state = PullRequestState(author=AUTHOR)
        self.here.github.add_pr(THE_PR, self.state)
        self.here.change_detection.advance(THE_PR, Poll(self.state, POLLED_AT), set())
        self.manager = self.here.conversation_managers.of(THE_PR)

    def commit(self, files, message):
        return self.here.working_copies.commit(WORKTREE, files, message)

    def thread(self, *comments):
        self.here.github.add_thread(THE_PR, Thread(
            key=KEY, kind=CommentKind.REVIEW, path="helpers.py", line=1, comments=comments))
        polled = self.manager.poll(self.state)
        polled.commit()
        if polled.activity is not None:
            self.manager.absorb(polled.activity)
        self.here.change_detection.advance(THE_PR, Poll(self.state, POLLED_AT), set())
        return self

    def tick_after(self, minutes=0):
        self.later += timedelta(minutes=minutes)
        self.manager.tick(FakeNotifications(), on_hold=False)
        return self

    def get(self):
        return self.manager.get(KEY)


def _answered_with_a_commit(settings, reply="Fixed in {sha}"):
    board = Board(settings)
    sha = board.commit({"helpers.py": "def new_name():\n"}, "Rename the helper")
    board.thread(_said(1, ME, "rename old_name"),
                 _said(2, AUTHOR, reply.format(sha=sha[:7]), "2026-09-01T11:00:00Z"))
    return board.tick_after(), sha


def test_a_reply_naming_a_commit_asks_whether_that_commit_answers_the_comment(settings):
    board, sha = _answered_with_a_commit(settings)

    [asked] = board.agent_runs.commit_checks_asked()

    assert (asked.key, asked.sha, asked.path, asked.line) == (KEY, sha, "helpers.py", 1)
    assert asked.comments == (("you", ME, "rename old_name"),
                              ("PR author", AUTHOR, f"Fixed in {sha[:7]}"))
    assert "Rename the helper" in asked.patch
    assert "+def new_name():" in asked.patch


def test_a_commit_link_is_checked_like_a_bare_hash(settings):
    board, sha = _answered_with_a_commit(
        settings, "Done: https://github.com/acme/widgets/pull/7/commits/{sha}")

    [asked] = board.agent_runs.commit_checks_asked()

    assert asked.sha == sha


def test_a_reply_naming_no_commit_asks_no_check(settings):
    board = Board(settings).thread(
        _said(1, ME, "rename old_name"),
        _said(2, AUTHOR, "will do", "2026-09-01T11:00:00Z")).tick_after()

    assert board.agent_runs.commit_checks_asked() == []


def test_a_commit_named_by_the_viewer_is_not_checked(settings):
    board = Board(settings)
    sha = board.commit({"helpers.py": "def new_name():\n"}, "Rename the helper")
    board.thread(_said(1, ME, f"compare with {sha[:7]}")).tick_after()

    assert board.agent_runs.commit_checks_asked() == []


def test_a_word_that_only_looks_like_a_hash_asks_no_check(settings):
    board = Board(settings).thread(
        _said(1, ME, "rename old_name"),
        _said(2, AUTHOR, "fixed, see deadbeef", "2026-09-01T11:00:00Z")).tick_after()

    assert board.agent_runs.commit_checks_asked() == []


def test_the_check_is_asked_once_however_many_ticks_come_within_ten_minutes(settings):
    board, _ = _answered_with_a_commit(settings)

    board.tick_after(3).tick_after(3).tick_after(3)

    assert len(board.agent_runs.commit_checks_asked()) == 1


def test_a_commit_that_does_not_address_the_comment_moves_the_thread_to_my_move(settings):
    board, sha = _answered_with_a_commit(settings)
    board.agent_runs.give("assumed-done")

    board.agent_runs.give_check("not-addressed", "it renames a different helper")

    held = board.get()
    assert held.standing is ConversationState.READY
    assert (str(held.commit_check.sha), held.commit_check.verdict.value,
            held.commit_check.reasoning) == (sha, "not-addressed",
                                             "it renames a different helper")


def test_a_commit_that_addresses_the_comment_leaves_the_verdict_where_it_put_it(settings):
    board, _ = _answered_with_a_commit(settings)
    board.agent_runs.give("assumed-done")

    board.agent_runs.give_check("addressed", "old_name is now new_name")

    assert board.get().standing is ConversationState.ASSUMED_DONE


def test_a_partly_addressed_commit_leaves_the_verdict_where_it_put_it(settings):
    board, _ = _answered_with_a_commit(settings)
    board.agent_runs.give("assumed-done")

    board.agent_runs.give_check("partly", "renamed, but one caller still uses old_name")

    assert board.get().standing is ConversationState.ASSUMED_DONE


def test_a_verdict_after_a_not_addressed_check_does_not_undo_it(settings):
    board, _ = _answered_with_a_commit(settings)
    board.agent_runs.give_check("not-addressed", "it renames a different helper")

    board.agent_runs.give("assumed-done")

    assert board.get().standing is ConversationState.READY


def test_a_newer_comment_lets_its_verdict_place_the_thread_again(settings):
    board, sha = _answered_with_a_commit(settings)
    board.agent_runs.give("assumed-done")
    board.agent_runs.give_check("not-addressed", "it renames a different helper")
    board.thread(_said(1, ME, "rename old_name"),
                 _said(2, AUTHOR, f"Fixed in {sha[:7]}", "2026-09-01T11:00:00Z"),
                 _said(3, ME, "that is the wrong helper", "2026-09-01T12:00:00Z"))

    board.agent_runs.give("their-move")

    assert board.get().standing is ConversationState.WAITING


def test_a_check_that_gets_no_answer_is_asked_again_after_ten_minutes(settings):
    board, _ = _answered_with_a_commit(settings)

    board.tick_after(9)
    assert len(board.agent_runs.commit_checks_asked()) == 1
    board.tick_after(1)
    assert len(board.agent_runs.commit_checks_asked()) == 2


def test_a_check_is_asked_at_most_three_times_for_one_comment(settings):
    board, _ = _answered_with_a_commit(settings)

    for _ in range(5):
        board.tick_after(10)

    assert len(board.agent_runs.commit_checks_asked()) == 3


def test_the_newest_comment_naming_a_commit_the_checkout_has_is_the_one_checked(settings):
    board = Board(settings)
    sha = board.commit({"helpers.py": "def new_name():\n"}, "Rename the helper")
    board.thread(_said(1, ME, "rename old_name"),
                 _said(2, AUTHOR, "Fixed in abcdef1", "2026-09-01T11:00:00Z"),
                 _said(3, AUTHOR, f"sorry, I meant {sha[:7]}", "2026-09-01T11:05:00Z"))
    board.tick_after()

    [asked] = board.agent_runs.commit_checks_asked()

    assert asked.sha == sha
