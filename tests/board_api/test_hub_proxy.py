import base64
import hashlib
import http.client
import json
import logging
import socket
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import anyio
import pytest
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect

from github_orchestrator.board_api.fake import FakeHoldings
from github_orchestrator.domain import HubState
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.terminal_sessions.fake import FakeTerminalSessions
from github_orchestrator.wiring import listen_on_loopback
from tests.board_api.support import (
    ACCOUNT,
    KEY,
    THE_PR,
    Events,
    board_on,
    fake_threads,
    heard_on,
    hub_contract,
    hub_on,
    running,
)
from tests.board_api.test_hub import client
from tests.builders import a_pr
from tests.waiting import until


class OnLoopback:
    def __init__(self):
        self.app = None
        self._real = None

    def __call__(self, port):
        self._real = listen_on_loopback(port)
        return self

    @property
    def port(self):
        return self._real.port

    def serve(self, app):
        self.app = app
        self._real.serve(app)

    def close(self):
        self._real.close()
        self.app = None


@pytest.fixture
def heartbeat_seconds():
    return 15.0


@pytest.fixture
def sessions():
    return FakeTerminalSessions()


@pytest.fixture
def board(heartbeat_seconds, sessions):
    served = board_on(fake_threads(FakeGitHub(account=ACCOUNT)), listening=OnLoopback(),
                      heartbeat_seconds=heartbeat_seconds, sessions=sessions)
    yield served
    served.api.stop()


@pytest.fixture
def at_work(board):
    heard_on(board)
    running(board)
    return board


def port_of(board):
    return board.client.base_url.port


def hub_before(board):
    return client(FakeHoldings(ports={THE_PR: port_of(board)}), THE_PR)


def tag_of(web, prefix=""):
    return web.get(f"{prefix}/api/conversations/{KEY}").json()["etag"]


def test_a_read_under_a_held_prs_path_answers_what_its_board_answers(board):
    answer = hub_before(board).get("/pr/acme/widgets/54/api/pull-request")

    assert answer.status_code == 200
    assert answer.json() == board.client.get("/api/pull-request").json()
    assert answer.headers["Content-Type"] == "application/json"
    assert answer.headers["ETag"] == board.client.get("/api/pull-request").headers["ETag"]


def test_a_read_the_page_already_holds_is_not_modified_through_the_hub(board):
    tag = board.client.get("/api/conversations").headers["ETag"]

    answer = hub_before(board).get("/pr/acme/widgets/54/api/conversations", headers={"If-None-Match": tag})

    assert answer.status_code == 304
    assert answer.content == b""


def test_a_write_through_the_hub_reaches_the_board_and_names_where_to_read_it_under_the_pr(at_work):
    web = hub_before(at_work)

    answer = web.post(f"/pr/acme/widgets/54/api/conversations/{KEY}/operations:stop",
                      headers={"If-Match": tag_of(at_work.client)}, json={})

    assert answer.status_code == 202
    assert answer.headers["Location"] == (
        f"/pr/acme/widgets/54/api/conversations/{KEY}/operations/{answer.json()['operation']['id']}")
    assert web.get(answer.headers["Location"]).json() == answer.json()["operation"]


def test_a_pr_the_hub_does_not_hold_is_not_found(board):
    answer = hub_before(board).get("/pr/acme/widgets/77/api/pull-request")

    assert answer.status_code == 404
    assert answer.json()["errors"][0]["code"] == "not-found"


def test_two_held_prs_with_one_number_are_reached_each_under_its_own_repo(board):
    gadgets = a_pr(54, "acme/gadgets")
    web = client(FakeHoldings(ports={THE_PR: port_of(board)}), THE_PR, gadgets)

    widgets_answer = web.get("/pr/acme/widgets/54/api/pull-request")
    gadgets_answer = web.get("/pr/acme/gadgets/54/api/pull-request")

    assert widgets_answer.status_code == 200
    assert widgets_answer.json()["repo"] == "acme/widgets"
    assert gadgets_answer.status_code == 503
    assert gadgets_answer.json()["errors"][0]["detail"] == "acme/gadgets#54's board is not answering"


def test_a_number_held_only_in_another_repo_is_not_found(board):
    answer = hub_before(board).get("/pr/acme/gadgets/54/api/pull-request")

    assert answer.status_code == 404
    assert answer.json()["errors"][0]["code"] == "not-found"


def test_a_held_pr_with_no_board_answers_that_its_board_is_unreachable():
    answer = client(FakeHoldings(), THE_PR).get("/pr/acme/widgets/54/api/pull-request")

    assert answer.status_code == 503
    assert answer.json()["errors"][0]["code"] == "board-unreachable"


def test_a_held_pr_whose_board_has_stopped_answers_that_its_board_is_unreachable(board):
    web = hub_before(board)
    board.api.stop()

    answer = web.get("/pr/acme/widgets/54/api/pull-request")

    assert answer.status_code == 503
    assert answer.json()["errors"][0]["code"] == "board-unreachable"


def test_a_write_another_sites_page_sends_is_refused_at_the_hub(at_work):
    answer = hub_before(at_work).post(
        f"/pr/acme/widgets/54/api/conversations/{KEY}/operations:stop",
        headers={"If-Match": tag_of(at_work.client), "Origin": "https://evil.example"}, json={})

    assert answer.status_code == 403
    assert answer.json()["errors"][0]["code"] == "foreign-origin"
    assert at_work.client.get(f"/api/conversations/{KEY}/operations").json()[-1]["kind"] != "stop"


def test_a_command_with_no_body_through_the_hub_is_handed_to_the_manager(board):
    answer = hub_before(board).post("/pr/acme/widgets/54/api/manager:hold")

    assert answer.status_code == 202
    assert answer.headers["Location"] == "/pr/acme/widgets/54/api/dashboard"
    assert board.manager.dashboard().on_hold is True


def dripping(release):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"text/event-stream")]})
        await send({"type": "http.response.body", "body": b"data: first\n\n", "more_body": True})
        await anyio.to_thread.run_sync(release.wait, 5)
        await send({"type": "http.response.body", "body": b"data: second\n\n"})
    return app


def test_an_answer_the_board_streams_reaches_the_page_a_piece_at_a_time():
    release = threading.Event()
    upstream = listen_on_loopback(0)
    upstream.serve(dripping(release))
    hub = hub_on(listen_on_loopback)
    hub.show([THE_PR])
    url = hub.start(0, FakeHoldings(ports={THE_PR: upstream.port}), HubState.WATCHING)
    page = http.client.HTTPConnection("127.0.0.1", int(url.rsplit(":", 1)[1]), timeout=5)
    try:
        page.request("GET", "/pr/acme/widgets/54/api/events")
        answer = page.getresponse()
        first = answer.read1(1024)
        release.set()
        rest = answer.read()
    finally:
        release.set()
        page.close()
        hub.stop()
        upstream.close()

    assert answer.getheader("Content-Type") == "text/event-stream"
    assert first == b"data: first\n\n"
    assert rest == b"data: second\n\n"


class DroppingBoard:
    def __init__(self, opening, piece):
        self.release = threading.Event()
        self._listener = socket.create_server(("127.0.0.1", 0))
        self.port = self._listener.getsockname()[1]
        self._opening = opening
        self._piece = piece
        self._thread = threading.Thread(target=self._answer, daemon=True)
        self._thread.start()

    def _answer(self):
        taken, _ = self._listener.accept()
        with taken:
            asked = b""
            while b"\r\n\r\n" not in asked:
                asked += taken.recv(4096)
            taken.sendall(self._opening(asked))
            taken.sendall(self._piece)
            self.release.wait(5)

    def close(self):
        self.release.set()
        self._thread.join(5)
        self._listener.close()


def chunked_event_stream(asked):
    return (b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n"
            b"d\r\ndata: first\n\n\r\n")


def hub_before_dropping(dropping):
    hub = hub_on(listen_on_loopback)
    hub.show([THE_PR])
    url = hub.start(0, FakeHoldings(ports={THE_PR: dropping.port}), HubState.WATCHING)
    return hub, url


def test_a_board_going_away_mid_stream_ends_the_pages_stream_through_the_hub(caplog):
    caplog.set_level(logging.INFO)
    dropping = DroppingBoard(chunked_event_stream, b"20\r\ndata: sec")
    hub, url = hub_before_dropping(dropping)
    page = http.client.HTTPConnection("127.0.0.1", int(url.rsplit(":", 1)[1]), timeout=5)
    try:
        page.request("GET", "/pr/acme/widgets/54/api/manager/changes/stream")
        answer = page.getresponse()
        first = answer.read1(1024)
        dropping.release.set()
        rest = answer.read()
    finally:
        page.close()
        hub.stop()
        dropping.close()

    assert first == b"data: first\n\n"
    assert rest == b"data: sec"
    assert [record.levelno for record in caplog.records
            if "/pr/acme/widgets/54/api/manager/changes/stream" in record.getMessage()] == [logging.INFO]
    assert [record for record in caplog.records if record.levelno >= logging.ERROR] == []


def websocket_opening(asked):
    key = next(line.split(b":", 1)[1].strip() for line in asked.split(b"\r\n")
               if line.lower().startswith(b"sec-websocket-key:"))
    accept = base64.b64encode(hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
    return (b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
            b"Connection: Upgrade\r\nSec-WebSocket-Accept: " + accept + b"\r\n\r\n"
            b"\x82\x05wt $ ")


def test_a_board_going_away_mid_terminal_closes_the_page_saying_it_is_unreachable(caplog):
    caplog.set_level(logging.INFO)
    dropping = DroppingBoard(websocket_opening, b"\x82\x20README")
    hub, url = hub_before_dropping(dropping)
    try:
        with connect(f"ws{url.removeprefix('http')}/pr/acme/widgets/54/api/terminal/sessions/one",
                     origin=url, open_timeout=5) as page:
            assert page.recv(timeout=5) == b"wt $ "
            dropping.release.set()
            with pytest.raises(ConnectionClosed) as closed:
                page.recv(timeout=5)
    finally:
        hub.stop()
        dropping.close()

    assert closed.value.rcvd.code == 4503
    assert [record for record in caplog.records if record.levelno >= logging.ERROR] == []


@pytest.fixture
def hub_streams(board):
    hub = hub_on(listen_on_loopback)
    hub.show([THE_PR])
    url = hub.start(0, FakeHoldings(ports={THE_PR: port_of(board)}), HubState.WATCHING)
    streams = []

    def open_stream(path, headers=None):
        stream = Events(int(url.rsplit(":", 1)[1]), path, headers)
        streams.append(stream)
        return stream

    open_stream.url = url
    open_stream.hub = hub
    yield open_stream
    for stream in streams:
        stream.close()
    hub.stop()


def test_a_board_stream_reaches_the_page_through_the_hub_as_it_changes(board, hub_streams):
    stream = hub_streams("/pr/acme/widgets/54/api/manager/changes/stream")
    assert json.loads(stream.event()["data"]) == {"markdown": None}

    board.manager.changes_text = "# Renamed the helper\n"

    assert json.loads(stream.event()["data"]) == {"markdown": "# Renamed the helper\n"}


@pytest.mark.parametrize("heartbeat_seconds", [0.0])
def test_a_stream_through_the_hub_resumes_from_the_last_event_the_page_saw(board, hub_streams):
    seen = hub_streams("/pr/acme/widgets/54/api/manager/changes/stream").event()["id"]

    again = hub_streams("/pr/acme/widgets/54/api/manager/changes/stream", {"Last-Event-ID": seen})

    assert again.block() == {"retry": "1000"}
    assert again.block() == {"": "heartbeat"}


def _timed_read(url):
    begun = time.monotonic()
    with urllib.request.urlopen(url, timeout=10) as answer:
        answer.read()
    return time.monotonic() - begun


def test_fifty_open_streams_leave_the_wall_and_a_pr_page_answering_promptly(hub_streams):
    with ThreadPoolExecutor(max_workers=50) as pool:
        list(pool.map(lambda _: hub_streams("/pr/acme/widgets/54/api/manager/changes/stream").event(),
                      range(50)))

    assert _timed_read(f"{hub_streams.url}/api/pull-requests") < 2
    assert _timed_read(f"{hub_streams.url}/pr/acme/widgets/54/api/pull-request") < 2


def test_a_stream_the_page_closed_gives_its_place_to_the_next_one_at_once(board):
    hub = hub_on(listen_on_loopback, open_streams=1)
    hub.show([THE_PR])
    port = int(hub.start(0, FakeHoldings(ports={THE_PR: port_of(board)}), HubState.WATCHING).rsplit(":", 1)[1])
    first = Events(port, "/pr/acme/widgets/54/api/manager/changes/stream")
    first.event()
    first.close()
    begun = time.monotonic()
    try:
        Events(port, "/pr/acme/widgets/54/api/manager/changes/stream").event()
    finally:
        hub.stop()

    assert time.monotonic() - begun < 3


def test_the_hub_stops_at_once_and_ends_the_stream_a_page_holds_through_it(hub_streams):
    stream = hub_streams("/pr/acme/widgets/54/api/manager/changes/stream")
    stream.event()
    begun = time.monotonic()

    hub_streams.hub.stop()

    assert time.monotonic() - begun < 0.5
    with pytest.raises(EOFError):
        stream.block()


def _terminal_through(hub_streams, session, origin=None):
    url = hub_streams.url
    return connect(f"ws{url.removeprefix('http')}/pr/acme/widgets/54/api/terminal/sessions/{session}",
                   origin=origin or url, open_timeout=5)


def test_a_terminal_through_the_hub_carries_what_the_session_prints_and_what_the_page_types(
        hub_streams, sessions):
    session = sessions.start("/wt", ["/bin/zsh", "-l"])
    sessions.print(session, b"wt $ ")

    with _terminal_through(hub_streams, session) as page:
        assert page.recv(timeout=5) == b"wt $ "
        page.send(json.dumps({"columns": 90, "rows": 20}))
        page.send(b"ls\r")
        sessions.print(session, b"README.md")
        assert page.recv(timeout=5) == b"README.md"
        until(lambda: sessions.sessions[session].typed and sessions.sessions[session].size,
              seconds=5)

    assert sessions.sessions[session].typed == [b"ls\r"]
    assert sessions.sessions[session].size == (90, 20)


def test_a_session_ending_through_the_hub_tells_the_page_its_exit_code(hub_streams, sessions):
    session = sessions.start("/wt", ["git", "commit"])

    with _terminal_through(hub_streams, session) as page:
        sessions.end(session, 0)

        assert json.loads(page.recv(timeout=5)) == {"exit_code": 0}
        with pytest.raises(ConnectionClosed) as closed:
            page.recv(timeout=5)

    assert closed.value.rcvd.code == 1000


def test_a_page_leaving_the_hub_lets_go_of_the_session_and_leaves_it_running(
        hub_streams, sessions):
    session = sessions.start("/wt", ["/bin/zsh", "-l"])

    with _terminal_through(hub_streams, session) as page:
        page.send(b"ls\r")
        deadline = time.monotonic() + 5
        while sessions.sessions[session].typed == [] and time.monotonic() < deadline:
            time.sleep(0.02)

    deadline = time.monotonic() + 5
    while sessions.sessions[session].connections and time.monotonic() < deadline:
        time.sleep(0.02)
    assert sessions.sessions[session].connections == 0
    assert [listed.id for listed in sessions.listed()] == [session]


def test_a_gone_session_through_the_hub_closes_the_page_as_the_board_closes_it(hub_streams):
    with _terminal_through(hub_streams, "no-such-session") as page:
        with pytest.raises(ConnectionClosed) as closed:
            page.recv(timeout=5)

    assert closed.value.rcvd.code == 4404


def test_another_sites_page_cannot_reach_a_terminal_through_the_hub(hub_streams, sessions):
    session = sessions.start("/wt", ["/bin/zsh", "-l"])

    with pytest.raises(InvalidStatus):
        _terminal_through(hub_streams, session, origin="http://evil.example")

    assert sessions.sessions[session].connected_once is False


def test_a_terminal_of_a_pr_whose_board_is_down_closes_the_page_saying_so(sessions):
    hub = hub_on(listen_on_loopback)
    hub.show([THE_PR])
    url = hub.start(0, FakeHoldings(ports={}), HubState.WATCHING)
    try:
        with connect(f"ws{url.removeprefix('http')}/pr/acme/widgets/54/api/terminal/sessions/one",
                     origin=url, open_timeout=5) as page:
            with pytest.raises(ConnectionClosed) as closed:
                page.recv(timeout=5)
    finally:
        hub.stop()

    assert closed.value.rcvd.code == 4503


def test_the_contract_declares_the_proxy_with_the_refusals_the_hub_gives_itself():
    contract = hub_contract()

    proxied = contract["paths"]["/pr/{owner}/{name}/{number}/api/{path}"]

    assert set(proxied) == {"get", "post"}
    assert all({"404", "503"} <= set(operation["responses"]) for operation in proxied.values())
