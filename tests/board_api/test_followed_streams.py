import json
import time
from urllib.parse import urlencode

import pytest

from github_orchestrator.board_api.fake import FakeManagerPanel
from tests.board_api.support import (
    STREAM_CHECK_SECONDS,
    THE_PR,
    Events,
    on_loopback,
    one_server,
)
from tests.builders import a_pr
from tests.waiting import until

GADGETS = a_pr(54, "acme/gadgets")
WIDGETS_NOTES = "/pr/acme/widgets/54/api/manager/changes/stream"
GADGETS_NOTES = "/pr/acme/gadgets/54/api/manager/changes/stream"
UNHELD_NOTES = "/pr/acme/widgets/55/api/manager/changes/stream"


@pytest.fixture
def server():
    served = {}

    def app_at(port):
        served["server"] = one_server(THE_PR, GADGETS, port=port)
        return served["server"].client.app

    with on_loopback(app_at) as port:
        served["port"] = port
        yield served


@pytest.fixture
def followed(server):
    streams = []

    def follow(*paths):
        stream = Events(server["port"], f"/api/streams?{urlencode([('follow', p) for p in paths])}")
        streams.append(stream)
        return stream

    yield follow
    for stream in streams:
        stream.close()


def test_one_connection_carries_each_followed_streams_events_tagged_with_its_path(followed):
    stream = followed(WIDGETS_NOTES, GADGETS_NOTES)

    events = [stream.event(), stream.event()]

    assert stream.answer.getheader("Content-Type").startswith("text/event-stream")
    assert sorted((one["event"], json.loads(one["data"])["path"]) for one in events) == [
        ("changes", GADGETS_NOTES), ("changes", WIDGETS_NOTES)]
    assert json.loads(events[0]["data"])["data"] == {"markdown": None}


def test_a_followed_stream_that_changes_is_sent_again(server, followed):
    stream = followed(WIDGETS_NOTES)
    stream.event()

    server["server"].panels.panel.changes_text = "# Renamed the helper\n"

    assert json.loads(stream.event()["data"]) == {
        "path": WIDGETS_NOTES, "data": {"markdown": "# Renamed the helper\n"}}


class CountedChanges(FakeManagerPanel):
    read = 0

    def changes(self) -> str | None:
        self.read += 1
        return super().changes()


def unread_for_a_while(counted: CountedChanges) -> bool:
    before = counted.read
    time.sleep(STREAM_CHECK_SECONDS * 6)
    return counted.read == before


def test_a_page_that_hangs_up_stops_every_followed_stream(server, followed):
    counted = server["server"].panels.panel = CountedChanges()
    stream = followed(WIDGETS_NOTES, GADGETS_NOTES)
    stream.event()
    assert not unread_for_a_while(counted)

    stream.close()

    assert until(lambda: unread_for_a_while(counted), seconds=3)


def test_a_followed_stream_the_hub_refuses_is_sent_as_refused_with_its_status(followed):
    stream = followed(UNHELD_NOTES)

    event = stream.event()

    assert event["event"] == "refused"
    assert json.loads(event["data"]) == {"path": UNHELD_NOTES, "status": 404}


@pytest.mark.parametrize("path", ["/api/pull-requests", "/pr/acme/widgets/54/api/dashboard",
                                  "https://example.com/pr/acme/widgets/54/api/dashboard/stream"])
def test_following_anything_but_a_pull_requests_stream_is_refused(server, path):
    answer = server["server"].client.get(f"/api/streams?{urlencode({'follow': path})}")

    assert answer.status_code == 400
    assert answer.json()["errors"][0]["code"] == "malformed-request"


def test_following_nothing_is_refused(server):
    assert server["server"].client.get("/api/streams").status_code == 400
