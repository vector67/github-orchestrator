from dataclasses import replace
from datetime import datetime

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
                                           "body": "🤖 Renames it.", "started_from": WRITTEN})

    assert answer.status_code == 200
    saved = answer.json()
    assert saved["saved"] is True
    assert saved["on_github"] == "🤖 Renames it."
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
                                           "started_from": WRITTEN})

    assert answer.status_code == 200
    assert answer.json()["saved"] is False
    assert answer.json()["on_github"] == "A teammate's words."
    assert answer.json()["pull_request"]["description_saved_at"] is None
    assert on_github(fake).body == "A teammate's words."


def test_github_refusing_the_save_says_why():
    fake, board = described()
    del fake.github.prs[THE_PR]

    answer = board.client.post(SAVE, json={"title": TITLE, "body": "🤖 Renames it.",
                                           "started_from": WRITTEN})

    assert answer.status_code == 502
    assert answer.json()["errors"][0]["code"] == "github-rejected"
    assert "Not Found" in answer.json()["errors"][0]["detail"]


def test_a_saved_description_is_served_until_a_poll_newer_than_the_save_reads_it():
    polls = Clock(POLLED)
    fake, board = described(polls=polls)
    board.client.post(SAVE, json={"title": TITLE, "body": "🤖 Renames it.",
                                  "started_from": WRITTEN})

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
