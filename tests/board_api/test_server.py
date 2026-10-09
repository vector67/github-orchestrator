import json
import socket
import time
import urllib.parse
import urllib.request

import pytest

from github_orchestrator.board_api.fake import FakeManagerPanel
from tests.board_api.support import THE_PR, fake_threads
from tests.board_api.test_contract import served
from tests.board_api.test_page import built_app
from tests.conversation.support import hear, on_github, said

MAX_REQUEST_BYTES = 1024 * 1024


@pytest.fixture
def app_root(tmp_path):
    return built_app(tmp_path)


@pytest.fixture
def started(app_root):
    fake = fake_threads()
    board_api = served(fake, fake.working_copies, app_root)

    def start(is_author=True, base_branch="main"):
        fake.watch(THE_PR, is_author=is_author, title="T", base_branch=base_branch)
        return board_api.start(THE_PR, port=0, manager=FakeManagerPanel())

    def queued():
        url = start()
        on_github(fake.github, "PRRT_2314159", said(2314159, "please rename this helper"),
                  pr=THE_PR)
        hear(fake.of(THE_PR))
        return url

    start.board_api = board_api
    start.queued = queued
    yield start
    board_api.stop()


def _raw(url, headers, body=b"", request_line="POST /api/conversations/PRRT_2314159/operations:stop",
         whole=False):
    host, _, port = urllib.parse.urlsplit(url).netloc.partition(":")
    request = (f"{request_line} HTTP/1.1\r\n"
               f"Host: {host}:{port}\r\n"
               + "".join(f"{name}: {value}\r\n" for name, value in headers)
               + "Connection: close\r\n\r\n").encode() + body
    with socket.create_connection((host, int(port)), timeout=5) as sock:
        sock.sendall(request)
        sock.settimeout(5)
        answer = b""
        while whole or b"\r\n\r\n" not in answer:
            chunk = sock.recv(4096)
            if not chunk:
                break
            answer += chunk
    return answer


def _raw_post(url, headers, body=b""):
    return _raw(url, headers, body).split(b"\r\n", 1)[0]


def _read(url, path):
    with urllib.request.urlopen(f"{url}{path}", timeout=5) as answer:
        return json.loads(answer.read())


def test_a_body_too_big_to_read_is_refused_before_it_is_read(started):
    status = _raw_post(started.queued(), [("Content-Length", str(MAX_REQUEST_BYTES + 1))])

    assert b"413" in status


def test_a_post_that_names_no_length_is_refused(started):
    assert b"411" in _raw_post(started.queued(), [])


def test_a_post_whose_length_is_not_a_number_is_refused(started):
    assert b"400" in _raw_post(started.queued(), [("Content-Length", "lots")])


def test_stop_returns_promptly(started):
    started()
    begun = time.monotonic()

    started.board_api.stop()

    assert time.monotonic() - begun < 0.25


def test_the_app_route_climbs_out_of_no_directory(tmp_path, started):
    (tmp_path / "secret.txt").write_text("not yours")

    answer = _raw(started(), [], request_line="GET /../secret.txt",
                  whole=True)

    assert b"not yours" not in answer, (
        "a path that escapes the built app falls back to the index, never "
        "to a file beside it")
