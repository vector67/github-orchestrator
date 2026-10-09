import json
import socket
import time

import pytest

from github_orchestrator.board_api.fake import FakeManagerPanel
from tests.board_api.support import Events, board_on, fake_threads
from tests.board_api.test_hub_proxy import OnLoopback


@pytest.fixture
def panel():
    return FakeManagerPanel(changes_text="# What changed\n")


@pytest.fixture
def heartbeat_seconds():
    return 15.0


@pytest.fixture
def board(panel, heartbeat_seconds):
    served = board_on(fake_threads(), manager=panel, listening=OnLoopback(),
                      heartbeat_seconds=heartbeat_seconds)
    yield served
    served.api.stop()


@pytest.fixture
def opened(board):
    streams = []

    def open_stream(path, headers=None):
        stream = Events(board.client.base_url.port, path, headers)
        streams.append(stream)
        return stream

    yield open_stream
    for stream in streams:
        stream.close()


def test_the_notes_stream_opens_with_the_notes_the_agent_has_written(board, opened):
    stream = opened("/api/manager/changes/stream")

    event = stream.event()

    assert stream.answer.getheader("Content-Type").startswith("text/event-stream")
    assert event["event"] == "changes"
    assert json.loads(event["data"]) == {"markdown": "# What changed\n"}
    assert f'"{event["id"]}"' == board.client.get("/api/manager/changes").headers["ETag"]


def test_the_notes_stream_sends_the_notes_again_when_they_change(panel, opened):
    stream = opened("/api/manager/changes/stream")
    stream.event()

    panel.changes_text = "# What changed\n\n- Renamed the helper.\n"

    assert json.loads(stream.event()["data"]) == {
        "markdown": "# What changed\n\n- Renamed the helper.\n"}


@pytest.mark.parametrize("heartbeat_seconds", [0.0])
def test_a_reconnect_that_names_the_last_event_it_saw_hears_only_what_came_after(panel, opened):
    seen = opened("/api/manager/changes/stream").event()["id"]

    again = opened("/api/manager/changes/stream", {"Last-Event-ID": seen})
    assert again.block() == {"retry": "1000"}
    assert again.block() == {"": "heartbeat"}
    panel.changes_text = "# Rewritten\n"

    assert json.loads(again.event()["data"]) == {"markdown": "# Rewritten\n"}


@pytest.mark.parametrize("heartbeat_seconds", [0.0])
def test_a_stream_with_nothing_new_sends_a_heartbeat_comment(opened):
    stream = opened("/api/manager/changes/stream")
    stream.event()

    assert stream.block() == {"": "heartbeat"}


def test_the_claude_output_stream_sends_the_tail_it_was_asked_for(board, panel, opened):
    panel.output = [("first run", False), ("", True), ("second run", False)]
    stream = opened("/api/manager/agent-output/stream?lines=2")

    event = stream.event()

    assert event["event"] == "agent-output"
    assert json.loads(event["data"]) == board.client.get(
        "/api/manager/agent-output?lines=2").json()


def test_the_claude_output_stream_refuses_a_tail_of_no_lines(board):
    assert board.client.get("/api/manager/agent-output/stream?lines=0").status_code == 400


def test_the_dashboard_stream_sends_what_the_dashboard_read_answers(board, opened):
    event = opened("/api/dashboard/stream").event()

    assert event["event"] == "dashboard"
    assert json.loads(event["data"]) == board.client.get("/api/dashboard").json()


def test_the_dashboard_stream_waits_out_a_manager_still_starting(board, panel, opened):
    first = panel.now
    panel.now = None
    stream = opened("/api/dashboard/stream")
    assert stream.block() == {"retry": "1000"}

    panel.now = first

    assert json.loads(stream.event()["data"]) == board.client.get("/api/dashboard").json()


def test_a_board_stops_at_once_and_ends_the_stream_a_page_holds_open(board, opened):
    port = board.client.base_url.port
    stream = opened("/api/manager/changes/stream")
    stream.event()
    begun = time.monotonic()

    board.api.stop()

    assert time.monotonic() - begun < 0.5
    with pytest.raises(EOFError):
        stream.block()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
