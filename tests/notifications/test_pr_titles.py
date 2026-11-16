import json
from pathlib import Path

import pytest

from github_orchestrator.desktop.fake import FakeDesktop
from tests.builders import a_pr
from tests.conftest import fake_agent_runs
from tests.notifications.support import LONG_AWAKE, Board, Clock, opened

WIDGETS = a_pr(84, "acme/widgets")
GADGETS = a_pr(7, "acme/gadgets")


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def desktop():
    return FakeDesktop()


@pytest.fixture
def runs():
    return fake_agent_runs()


@pytest.fixture
def board():
    board = Board()
    board.titles = {WIDGETS: "Add retry to the widget importer"}
    return board


@pytest.fixture
def store(tmp_path, desktop, clock, runs, board):
    return opened(tmp_path, desktop, clock, runs, board)


def _bodies(desktop):
    return [a.body for a in desktop.announcements]


def test_a_notification_about_a_pr_opens_its_body_with_the_prs_title(store, desktop):
    notifications, courier = store

    notifications.runs.run_failed(WIDGETS, "ci-failed", 1)
    courier.deliver(LONG_AWAKE, None)

    assert _bodies(desktop) == ["Add retry to the widget importer\nci-failed exited 1"]


def test_a_pr_whose_title_is_not_known_keeps_the_body_alone(store, desktop):
    notifications, courier = store

    notifications.runs.run_failed(GADGETS, "ci-failed", 1)
    courier.deliver(LONG_AWAKE, None)

    assert _bodies(desktop) == ["ci-failed exited 1"]


def test_a_long_pr_title_is_cut_to_one_banner_line(store, desktop, board):
    notifications, courier = store
    board.titles[WIDGETS] = "Move the widget importer onto the new queue and retry each failed batch"

    notifications.thread_news.agent_asked(WIDGETS, "PRRT_1", question="Which queue?")
    courier.deliver(LONG_AWAKE, None)

    assert _bodies(desktop) == ["Move the widget importer onto the new queue and r…\nWhich queue?"]


def test_a_fix_ready_batch_opens_with_the_prs_title(store, desktop, clock, runs):
    notifications, courier = store
    runs.answer("rename the helper")

    notifications.thread_news.fix_ready(WIDGETS, "PRRT_1", gist="rename the helper",
                                        comments=[("Ada", "please rename the helper")],
                                        fix_summary="renamed it")
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert _bodies(desktop) == ["Add retry to the widget importer\nrename the helper"]


def test_a_comment_batch_opens_with_the_prs_title(store, desktop, clock, runs):
    notifications, courier = store
    runs.answer(("still flaky",))

    notifications.thread_news.comment_arrived(
        WIDGETS, "PRRT_1", comment_id=1, author="Ada", body="this still fails on staging",
        created_at="2026-09-24T15:46:00Z", opens_thread=False, reopens=False,
        review_comment=False)
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert _bodies(desktop) == [
        "Add retry to the widget importer\nReply | No fix | Ada | summary: still flaky"]


def test_skipped_events_on_one_pr_open_with_its_title(store, desktop, clock):
    notifications, courier = store

    notifications.runs.agent_skipped(WIDGETS, "ci-failed")
    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert _bodies(desktop) == ["Add retry to the widget importer\nwidgets#84: ci-failed"]


def test_a_batch_gathered_before_titles_were_kept_still_goes_out(tmp_path, desktop, clock, runs,
                                                                  board):
    group = Path(tmp_path, "batches", "comments--acme--widgets--84")
    group.mkdir(parents=True)
    group.joinpath("1-1-0.json").write_text(json.dumps({
        "kind": "comment", "repo": "acme/widgets", "pr": 84, "key": "PRRT_1",
        "comment_id": 1, "author": "Ada", "body": "this still fails on staging",
        "created_at": "2026-09-24T15:46:00Z", "action": "Reply", "review_comment": False,
        "posted_at": clock().isoformat()}))
    runs.answer(("still flaky",))
    _, courier = opened(tmp_path, desktop, clock, runs, board)

    clock.advance(minutes=3)
    courier.deliver(LONG_AWAKE, None)

    assert [(a.title, a.body) for a in desktop.announcements] == [
        ("1 comment on widgets#84", "Reply | No fix | Ada | summary: still flaky")]
