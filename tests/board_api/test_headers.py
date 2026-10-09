import re
from html.parser import HTMLParser

import pytest

from tests.board_api.support import PORT, SERVED_APP, board_for, client_for, client_of
from tests.board_api.test_page import built_app

POLICY = ("default-src 'self'; img-src 'self'; object-src 'none'; "
          "style-src-elem 'self' 'unsafe-inline'; style-src-attr 'unsafe-inline'; "
          "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


@pytest.fixture
def served(tmp_path):
    return board_for(app_root=built_app(tmp_path))


def as_addressed_to(board, host, path):
    return client_of(board).get(path, headers={"Host": host})


def test_a_read_addressed_to_another_host_is_refused(served):
    answer = as_addressed_to(served, "evil.example", "/")

    assert answer.status_code == 403, (
        "a page on a name its owner points at 127.0.0.1 reads the board as "
        "its own origin unless the Host is checked on every method")
    assert answer.json()["errors"][0]["code"] == "foreign-origin"


def test_a_read_to_the_rebound_name_on_the_boards_own_port_is_refused(
        served):
    answer = as_addressed_to(served, f"evil.example:{PORT}", "/")

    assert answer.status_code == 403


def test_a_read_addressed_to_the_board_is_answered(served):
    assert as_addressed_to(served, f"localhost:{PORT}", "/").status_code == 200


def answers(board):
    client = client_of(board)
    return {
        "a read": client.get("/api/pull-request"),
        "the page": client.get("/"),
        "a stylesheet": client.get("/palette.css"),
        "nothing there": client.get("/api/nothing"),
        "a refused write": client.post("/api/operations:send-review",
                                       headers={"Origin": "http://evil"},
                                       json={"verdict": "APPROVE"}),
        "a foreign host": as_addressed_to(board, "evil.example", "/"),
    }


def test_no_answer_may_be_framed(served):
    for what, answer in answers(served).items():
        assert answer.headers.get("X-Frame-Options") == "DENY", what
        assert "frame-ancestors 'none'" in answer.headers.get(
            "Content-Security-Policy", ""), what


def test_no_answer_is_sniffed_into_another_type(served):
    for what, answer in answers(served).items():
        assert answer.headers.get("X-Content-Type-Options") == "nosniff", what


def test_the_page_runs_only_what_the_board_serves(served):
    answer = client_of(served).get("/")

    assert answer.headers["Content-Security-Policy"] == POLICY


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.inline: list[str] = []
        self.fetched: list[str] = []
        self.in_script = False

    def handle_starttag(self, tag, attrs):
        named = dict(attrs)
        if tag == "script":
            self.in_script = True
            if named.get("src") is None:
                self.inline.append("<script> with no src")
            else:
                self.fetched.append(named["src"] or "")
        if tag == "link":
            self.fetched.append(named.get("href") or "")
        if tag == "style":
            self.inline.append("<style>")
        for name, value in attrs:
            if name == "style" or name.startswith("on"):
                self.inline.append(f"{tag} {name}={value}")

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_script and data.strip():
            self.inline.append("a script body")


def test_the_built_page_loads_under_its_policy():
    if not (SERVED_APP / "index.html").is_file():
        pytest.skip("make build_frontend has not built the page")
    page = _Page()
    page.feed(client_for(app_root=SERVED_APP).get("/").text)

    assert page.inline == [], (
        "the policy allows no inline script or style, so the built page "
        "would not run")
    assert page.fetched
    for reference in page.fetched:
        assert re.match(r"^/(?!/)", reference), (
            f"{reference} is not the board's own; the policy is 'self'")
