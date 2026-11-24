import contextlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime

import pytest

from github_orchestrator.domain import DescriptionMoved
from github_orchestrator.thread_records.fake import FakePrRecords, FakeThreadRecords
from tests.board_api.support import (
    THE_PR,
    TITLE,
    board_on,
    fake_threads,
)
from tests.conversation.support import at

SAVE = "/api/pull-request/description:save"
CHECK = "/api/pull-request/description:check"
WRITTEN = "🤖 Renames the helper."
POLLED = "2026-08-28T10:00:00Z"
SAVED = "2026-08-28T10:05:00Z"
LONE_SURROGATE = "\ud800"


class Clock:
    def __init__(self, iso: str) -> None:
        self.now = at(iso)()

    def __call__(self) -> datetime:
        return self.now

    def move_to(self, iso: str) -> None:
        self.now = at(iso)()


def described(body: str = WRITTEN, polls: Clock | None = None):
    fake = fake_threads(clock=polls or Clock(POLLED))
    board = board_on(fake, body=body, clock=at(SAVED))
    return fake, board


def on_github(fake):
    return fake.github.prs[THE_PR].state


def changed_on_github(fake, body: str) -> None:
    record = fake.github.prs[THE_PR]
    record.state = replace(record.state, body=body)


def test_the_pull_request_read_carries_the_description_unchecked():
    _, board = described()

    answer = board.client.get("/api/pull-request").json()

    assert answer["body"] == WRITTEN
    assert answer["description_checked"] is False
    assert answer["description_saved_at"] is None


def test_a_saved_description_changes_the_title_and_body_on_github_and_counts_as_checked():
    fake, board = described()

    answer = board.client.post(SAVE, json={"title": "Rename the helper for good",
                                           "body": "🤖 Renames it.", "title_started_from": TITLE, "started_from": WRITTEN})

    assert answer.status_code == 200
    saved = answer.json()
    assert saved["saved"] is True
    assert (saved["title_on_github"], saved["on_github"]) == ("Rename the helper for good",
                                                              "🤖 Renames it.")
    assert (on_github(fake).title, on_github(fake).body) == ("Rename the helper for good",
                                                              "🤖 Renames it.")
    pull = saved["pull_request"]
    assert (pull["title"], pull["body"]) == ("Rename the helper for good", "🤖 Renames it.")
    assert pull["description_checked"] is True
    assert pull["description_saved_at"] == at(SAVED)().isoformat()


def test_a_description_changed_on_github_since_the_edit_started_is_not_saved_over():
    fake, board = described()
    changed_on_github(fake, "A teammate's words.")

    answer = board.client.post(SAVE, json={"title": TITLE, "body": "🤖 Renames it.",
                                           "title_started_from": TITLE, "started_from": WRITTEN})

    assert answer.status_code == 200
    assert answer.json()["saved"] is False
    assert answer.json()["on_github"] == "A teammate's words."
    assert answer.json()["pull_request"]["description_saved_at"] is None
    assert on_github(fake).body == "A teammate's words."


def test_a_title_renamed_on_github_since_the_edit_started_is_not_saved_over():
    fake, board = described()
    record = fake.github.prs[THE_PR]
    record.state = replace(record.state, title="Rename the helper, says a teammate")

    answer = board.client.post(SAVE, json={"title": TITLE, "body": "🤖 Renames it.",
                                           "title_started_from": TITLE, "started_from": WRITTEN})

    assert answer.status_code == 200
    assert answer.json()["saved"] is False
    assert (answer.json()["title_on_github"], answer.json()["on_github"]) == (
        "Rename the helper, says a teammate", WRITTEN)
    assert (on_github(fake).title, on_github(fake).body) == (
        "Rename the helper, says a teammate", WRITTEN)


def test_github_refusing_the_save_says_why():
    fake, board = described()
    del fake.github.prs[THE_PR]

    answer = board.client.post(SAVE, json={"title": TITLE, "body": "🤖 Renames it.",
                                           "title_started_from": TITLE, "started_from": WRITTEN})

    assert answer.status_code == 502
    assert answer.json()["errors"][0]["code"] == "github-rejected"
    assert "Not Found" in answer.json()["errors"][0]["detail"]


def test_a_saved_description_is_served_until_a_poll_newer_than_the_save_reads_it():
    polls = Clock(POLLED)
    fake, board = described(polls=polls)
    board.client.post(SAVE, json={"title": TITLE, "body": "🤖 Renames it.",
                                  "title_started_from": TITLE, "started_from": WRITTEN})

    before = board.client.get("/api/pull-request").json()
    changed_on_github(fake, "A teammate's words.")
    polls.move_to("2026-08-28T10:06:00Z")
    fake.hear(THE_PR)
    after = board.client.get("/api/pull-request").json()

    assert before["body"] == "🤖 Renames it."
    assert after["body"] == "A teammate's words."


def test_checking_the_description_the_page_showed_marks_it_checked():
    _, board = described()

    answer = board.client.post(CHECK, json={"body": WRITTEN})

    assert answer.status_code == 200
    assert answer.json()["description_checked"] is True
    assert board.client.get("/api/pull-request").json()["description_checked"] is True


def test_a_check_expires_once_the_description_changes_anywhere_else():
    polls = Clock(POLLED)
    fake, board = described(polls=polls)
    board.client.post(CHECK, json={"body": WRITTEN})

    changed_on_github(fake, WRITTEN + "\n\nDetailed reviewer: @octocat")
    polls.move_to("2026-08-28T10:06:00Z")
    fake.hear(THE_PR)

    assert board.client.get("/api/pull-request").json()["description_checked"] is False


def test_checking_a_description_that_has_since_changed_leaves_it_unchecked():
    _, board = described()

    answer = board.client.post(CHECK, json={"body": "🤖 What the page showed before."})

    assert answer.json()["description_checked"] is False


def posted(board, path: str, fields: dict[str, str]):
    return board.client.post(path, content=json.dumps(fields),
                             headers={"Content-Type": "application/json"})


@pytest.mark.parametrize("fields", [
    {"title": TITLE, "body": "🤖 Renames it" + LONE_SURROGATE, "title_started_from": TITLE, "started_from": WRITTEN},
    {"title": "Rename" + LONE_SURROGATE, "body": "🤖 Renames it.", "title_started_from": TITLE, "started_from": WRITTEN},
])
def test_a_save_holding_a_lone_surrogate_is_refused_before_github_hears_it(fields):
    fake, board = described()

    answer = posted(board, SAVE, fields)

    assert answer.status_code == 400
    assert answer.json()["errors"][0]["code"] == "malformed-request"
    assert (on_github(fake).title, on_github(fake).body) == (TITLE, WRITTEN)


def test_a_check_holding_a_lone_surrogate_is_refused():
    _, board = described()

    answer = posted(board, CHECK, {"body": WRITTEN + LONE_SURROGATE})

    assert answer.status_code == 400
    assert answer.json()["errors"][0]["code"] == "malformed-request"


class ReadThenWaitToWrite:
    def __init__(self, github, both_read: threading.Barrier) -> None:
        self.github = github
        self.both_read = both_read

    def edit_description(self, pr, title, body, *, title_started_from, started_from):
        on_github = self.github.prs[pr].state
        if on_github.body != started_from:
            return DescriptionMoved(on_github.title, on_github.body)
        with contextlib.suppress(threading.BrokenBarrierError):
            self.both_read.wait(timeout=0.5)
        record = self.github.prs[pr]
        record.state = replace(record.state, title=title, body=body)
        return None


def test_of_two_saves_from_the_same_description_the_second_finds_the_first():
    fake = fake_threads(clock=Clock(POLLED))
    board = board_on(fake, body=WRITTEN, clock=at(SAVED),
                     descriptions=ReadThenWaitToWrite(fake.github, threading.Barrier(2)))

    with ThreadPoolExecutor(2) as saving:
        answers = list(saving.map(
            lambda body: board.client.post(SAVE, json={"title": TITLE, "body": body,
                                                       "title_started_from": TITLE, "started_from": WRITTEN}).json(),
            ["🤖 One tab's words.", "🤖 The other tab's words."]))

    assert sorted(answer["saved"] for answer in answers) == [False, True]


class ChecksWaitForASave(FakeThreadRecords):
    def __init__(self) -> None:
        super().__init__()
        self.check_writing = threading.Event()
        self.saved = threading.Event()

    def pr(self, pr):
        return self.prs.setdefault(pr, PausedRecords(self))


class PausedRecords(FakePrRecords):
    def __init__(self, waits: ChecksWaitForASave) -> None:
        super().__init__()
        self.waits = waits

    def save(self, kind, key, document):
        if kind == "description" and json.loads(document)["saved_body"] is None:
            self.waits.check_writing.set()
            self.waits.saved.wait(timeout=0.5)
            super().save(kind, key, document)
            return
        super().save(kind, key, document)
        if kind == "description":
            self.waits.saved.set()


def test_a_check_beside_a_save_keeps_the_save():
    records = ChecksWaitForASave()
    fake = fake_threads(clock=Clock(POLLED))
    board = board_on(fake, body=WRITTEN, clock=at(SAVED), records=records)

    with ThreadPoolExecutor(2) as both:
        checking = both.submit(board.client.post, CHECK, json={"body": WRITTEN})
        assert records.check_writing.wait(timeout=5)
        both.submit(board.client.post, SAVE, json={"title": TITLE, "body": "🤖 Renames it.",
                                                   "title_started_from": TITLE, "started_from": WRITTEN}).result()
        checking.result()

    pull = board.client.get("/api/pull-request").json()
    assert (pull["body"], pull["description_saved_at"]) == ("🤖 Renames it.",
                                                            at(SAVED)().isoformat())
