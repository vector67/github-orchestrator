import threading
import time
from collections.abc import Callable

import pytest

from github_orchestrator.conversation import Conversation, ConversationState, Denied
from github_orchestrator.domain import Location, Side
from github_orchestrator.github import CommentKind
from github_orchestrator.github.fake import FakeGitHub, GhError
from tests.conversation.support import (
    THE_PR,
    WORKTREE,
    diff_over,
    drain,
    hear,
    on_github,
    propose,
    repo_at,
    said,
    start_run,
    world,
)
from tests.thread_records.support import disk_thread_records

KEY = "PRRT_101"
COMMENT_ID = 101
BODY = "Please rename this helper."
WAIT = 5


class CountingGitHub(FakeGitHub):
    def __init__(self) -> None:
        super().__init__()
        self.asks = 0
        self.answer: Callable[[], bool | None] | None = None

    def comment_exists(self, pr, kind: str,
                       comment_id: int) -> bool | None:
        self.asks += 1
        if self.answer is not None:
            return self.answer()
        return super().comment_exists(pr, kind, comment_id)


def eventually(condition: Callable[[], bool]) -> bool:
    deadline = time.monotonic() + WAIT
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.005)
    return condition()


def quiet() -> bool:
    return eventually(lambda: not any(thread.name == "presence"
                                      for thread in threading.enumerate()))


def _commented(settings, github: CountingGitHub, **fakes):
    here = world(settings, github=github, **fakes)
    repo_at(here.working_copies, WORKTREE, {"f": "old\n"})
    threads = here.threads()
    on_github(here.github, KEY, said(COMMENT_ID, BODY))
    hear(threads)
    return here, threads


def _proposed(settings, github: CountingGitHub, **fakes):
    here, threads = _commented(settings, github, **fakes)
    propose(here, threads, KEY)
    github.asks = 0
    return here, threads


def _gone(github: FakeGitHub) -> None:
    github.delete_comment(THE_PR, CommentKind.REVIEW, COMMENT_ID)


def checked(threads, key: str = KEY):
    threads.recheck(threads.get(key))
    assert quiet()
    return threads.get(key)


def _resolved(here, threads) -> None:
    propose(here, threads, KEY)
    with threads.editing(KEY) as editable:
        editable.resolve()
    drain(threads)


def _landed(here, threads) -> None:
    propose(here, threads, KEY)
    with threads.editing(KEY) as editable:
        editable.approve()
    drain(threads)


def _running(here, threads) -> None:
    start_run(here, threads, finishes=False)


def test_a_deferred_check_hands_the_caller_back_before_github_answers(settings):
    asked, release = threading.Event(), threading.Event()
    github = CountingGitHub()
    _, threads = _proposed(settings, github)
    proposed = threads.get(KEY)
    github.answer = lambda: (asked.set(), release.wait(WAIT), False)[-1]

    threads.recheck(threads.get(KEY))

    assert asked.wait(WAIT)
    assert threads.get(KEY) == proposed
    release.set()
    assert eventually(lambda: threads.get(KEY).is_removed)


def test_a_second_deferred_check_while_one_is_in_flight_asks_once(settings):
    asked, release = threading.Event(), threading.Event()
    github = CountingGitHub()
    _, threads = _proposed(settings, github)
    github.answer = lambda: (asked.set(), release.wait(WAIT), False)[-1]

    threads.recheck(threads.get(KEY))
    assert asked.wait(WAIT)
    threads.recheck(threads.get(KEY))
    release.set()

    assert quiet()
    assert github.asks == 1


def test_a_check_that_raises_lets_the_next_one_through(settings):
    def blows_up_once() -> bool:
        if github.asks == 1:
            raise GhError("gh: Bad Gateway (HTTP 502)")
        return False

    github = CountingGitHub()
    _, threads = _proposed(settings, github)
    proposed = threads.get(KEY)
    github.answer = blows_up_once

    assert checked(threads) == proposed
    stored = checked(threads)

    assert stored.is_removed
    assert github.asks == 2


@pytest.mark.parametrize("settle", [_resolved, _landed, _running])
def test_a_conversation_nobody_may_remove_is_only_flagged(settings, settle):
    github = CountingGitHub()
    here, threads = _commented(settings, github)
    settle(here, threads)
    settled = threads.get(KEY)
    _gone(github)

    stored = checked(threads)

    assert not stored.is_removed
    assert stored.standing is settled.standing
    assert stored.fix.is_settled == settled.fix.is_settled
    assert stored.comment_deleted is True


@pytest.mark.parametrize("answer", ["present", "unknown"])
def test_a_present_or_unknown_answer_changes_nothing(settings, answer):
    github = CountingGitHub()
    _, threads = _proposed(settings, github)
    proposed = threads.get(KEY)
    if answer == "unknown":
        github.answer = lambda: None

    assert checked(threads) == proposed
    assert github.asks == 1


def _removed_already(settings, github):
    _, threads = _proposed(settings, github)
    _gone(github)
    checked(threads)
    return threads, KEY


def _flagged_already(settings, github):
    here, threads = _commented(settings, github)
    _running(here, threads)
    _gone(github)
    checked(threads)
    return threads, KEY


def _a_draft(settings, github):
    here = world(settings, github=github)
    github.add_pr(THE_PR)
    diff_over(here, "f")
    threads = here.threads()
    drafted = threads.open_draft("rename it", Location(path="f", line=1, side=Side.AFTER))
    assert not isinstance(drafted, Denied), drafted
    return threads, drafted.key


@pytest.mark.parametrize("nothing_to_check", [_removed_already, _flagged_already, _a_draft])
def test_a_conversation_with_nothing_to_check_is_never_asked_about(settings,
                                                                   nothing_to_check):
    github = CountingGitHub()
    threads, key = nothing_to_check(settings, github)
    before = threads.get(key)
    github.asks = 0

    assert checked(threads, key) == before
    assert github.asks == 0


def test_a_conversation_with_no_record_is_nothing_to_check(settings):
    github = CountingGitHub()
    threads = world(settings, github=github).threads()

    threads.recheck(Conversation(key=KEY))

    assert quiet()
    assert threads.get(KEY) is None
    assert github.asks == 0
    assert github.asks == 0


def test_the_answer_is_memoised_for_a_minute(settings):
    now = [1000.0]
    github = CountingGitHub()
    _, threads = _proposed(settings, github, monotonic=lambda: now[0])

    checked(threads)
    now[0] += 30
    checked(threads)
    assert github.asks == 1

    now[0] += 31
    checked(threads)
    assert github.asks == 2


def test_an_answer_github_could_not_give_is_not_memoised(settings):
    github = CountingGitHub()
    _, threads = _proposed(settings, github, monotonic=lambda: 1000.0)
    github.answer = lambda: None

    checked(threads)
    checked(threads)

    assert github.asks == 2


def test_the_memo_key_carries_the_comment_type(settings):
    github = CountingGitHub()
    _, threads = _proposed(settings, github, monotonic=lambda: 1000.0)
    on_github(github, "IC_101", said(COMMENT_ID, BODY), kind=CommentKind.ISSUE,
              path=None, line=None)
    hear(threads)
    github.asks = 0

    checked(threads)
    checked(threads, "IC_101")

    assert github.asks == 2


def test_a_conversation_settled_since_it_was_read_is_only_flagged(settings):
    def settles_while_asked() -> bool:
        with threads.editing(KEY) as editable:
            editable.approve()
        drain(threads)
        return False

    github = CountingGitHub()
    _, threads = _proposed(settings, github)
    github.answer = settles_while_asked

    stored = checked(threads)

    assert not stored.is_removed
    assert stored.standing is ConversationState.DONE
    assert stored.fix.picked
    assert stored.comment_deleted is True


def test_a_conversation_that_has_gone_while_it_was_checked_stays_gone(settings, tmp_path):
    def forgotten_while_asked() -> bool:
        here.thread_records.forget(THE_PR)
        return False

    github = CountingGitHub()
    here, threads = _proposed(settings, github,
                              thread_records=disk_thread_records(tmp_path / "threads"))
    github.answer = forgotten_while_asked

    assert checked(threads) is None
    assert github.asks == 1
