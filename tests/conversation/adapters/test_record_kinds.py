import json
import os

import pytest

from github_orchestrator.github import PullRequestState
from github_orchestrator.notifications.fake import CommentArrived, FakeNotifications
from github_orchestrator.settings.fake import fake_settings
from tests.builders import a_pr
from tests.conversation.support import (
    THE_PR,
    WORKTREE,
    World,
    drain,
    hear,
    on_github,
    repo_at,
    said,
    world,
)
from tests.disk_layout import (
    thread_action_file,
    thread_dir,
    thread_file,
    thread_intent_file,
    thread_reply_file,
)
from tests.thread_records.support import disk_thread_records

KEY = "PRRT_kwDO"


@pytest.fixture
def here(tmp_path) -> World:
    settings = fake_settings(tmp_path / "data")
    built = world(settings, thread_records=disk_thread_records(tmp_path))
    repo_at(built.working_copies, WORKTREE)
    return built


@pytest.fixture
def threads(here):
    on_github(here.github, KEY, said(101, "rename it"))
    heard = here.threads()
    hear(heard)
    return heard


def _left(path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content)


def _replies(here: World) -> list[str]:
    return [comment.body for comment in here.github.thread(KEY).comments[1:]]


def test_a_reply_with_nothing_in_it_is_never_posted(tmp_path, here, threads):
    known = threads.get(KEY).operations
    _left(thread_reply_file(tmp_path, THE_PR, KEY), "  \n")

    assert threads.get(KEY).operations == known
    drain(threads)
    assert _replies(here) == []


def _garbled(path) -> None:
    _left(path, b"appro\xffve")


def _a_word_of_no_verb(path) -> None:
    _left(path, "obliterate")


def _pointing_nowhere(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(path.parent / "nothing")


@pytest.mark.parametrize("leave", [_garbled, _a_word_of_no_verb],
                         ids=["bytes-that-will-not-decode", "no-verb"])
def test_a_decision_that_will_not_parse_asks_nothing(tmp_path, threads, leave):
    known = threads.get(KEY).operations
    leave(thread_intent_file(tmp_path, THE_PR, KEY))

    assert threads.get(KEY).operations == known


@pytest.mark.parametrize("leave", [_garbled, _a_word_of_no_verb],
                         ids=["bytes-that-will-not-decode", "no-verb"])
def test_a_decision_that_will_not_parse_is_swept_up_by_the_drain(tmp_path, threads, leave):
    intent = thread_intent_file(tmp_path, THE_PR, KEY)
    leave(intent)

    drain(threads)

    assert not intent.is_symlink() and not intent.exists()
    assert not threads.get(KEY).is_unreadable


def test_a_decision_file_that_points_nowhere_never_hides_its_thread_from_the_listing(
    tmp_path, threads,
):
    _pointing_nowhere(thread_intent_file(tmp_path, THE_PR, KEY))

    [listed] = threads.all()

    assert listed.key == KEY
    assert not listed.is_unreadable


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads anything")
def test_a_decision_whose_file_will_not_open_leaves_its_thread_unreadable(tmp_path, threads):
    _left(thread_intent_file(tmp_path, THE_PR, KEY), "approve")
    thread_intent_file(tmp_path, THE_PR, KEY).chmod(0)

    assert threads.get(KEY).is_unreadable


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads anything")
def test_a_reply_whose_file_will_not_open_asks_nothing(tmp_path, threads):
    known = threads.get(KEY).operations
    _left(thread_reply_file(tmp_path, THE_PR, KEY), "what did you mean?")
    thread_reply_file(tmp_path, THE_PR, KEY).chmod(0)

    conversation = threads.get(KEY)

    assert not conversation.is_unreadable
    assert conversation.operations == known


@pytest.mark.parametrize("stem", ["PRRT%zz", "PRRT%"])
def test_a_decision_no_writer_of_ours_named_is_cleared_where_it_lies(tmp_path, here, stem):
    stray = thread_dir(tmp_path, THE_PR) / f"{stem}.intent"
    _left(stray, "approve")

    drain(here.threads())

    assert not stray.exists()


def test_an_action_whose_bytes_will_not_decode_is_no_last_action(tmp_path, threads):
    _left(thread_action_file(tmp_path, THE_PR, KEY), b"\xff")

    assert threads.activity(threads.get(KEY)).last_action is None


def _arrived(threads) -> list[int | None]:
    news = FakeNotifications()
    threads.poll(PullRequestState()).announce(news)
    return [item.comment_id for item in news.gathered if isinstance(item, CommentArrived)]


@pytest.mark.parametrize("text", ["{", "[1, 2]"])
def test_a_cursor_that_holds_no_object_is_a_pr_never_polled(tmp_path, here, text):
    on_github(here.github, KEY, said(101, "rename it"))
    _left(thread_dir(tmp_path, THE_PR) / "poll.cursor", text)

    assert _arrived(here.threads()) == []


def test_a_cursor_that_reads_announces_what_arrived_since(tmp_path, here):
    on_github(here.github, KEY, said(101, "rename it"))
    _left(thread_dir(tmp_path, THE_PR) / "poll.cursor", "{}")

    assert _arrived(here.threads()) == [101]


@pytest.mark.parametrize("text", ["{not json", "[1, 2]"])
def test_a_review_that_will_not_read_is_passed_over(tmp_path, here, text):
    base = thread_dir(tmp_path, THE_PR)
    _left(base / "op_good.review", json.dumps(
        {"id": "op_good", "verdict": "APPROVE", "state": "pending"}))
    _left(base / "op_bad.review", text)

    assert [review.id for review in here.threads().reviews()] == ["op_good"]


def test_a_thread_whose_bytes_will_not_decode_is_unreadable(tmp_path, here):
    _left(thread_file(tmp_path, THE_PR, KEY), b'{"thread_key": "PRRT_kwDO", "body": "\xff"}')

    assert here.threads().get(KEY).is_unreadable


def test_a_thread_is_kept_under_the_pr_it_was_heard_on(here, threads):
    other = a_pr(THE_PR.number, "acme/other")

    assert here.conversation_managers.of(other).all() == []
    assert [one.key for one in threads.all()] == [KEY]
