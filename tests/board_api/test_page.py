import re
import threading
import time

from github_orchestrator.github.fake import FakeGitHub
from tests.board_api.support import (
    BODY,
    SERVED_APP,
    board_on,
    client_for,
    client_of,
    css_variables,
    fake_threads,
    heard_on,
)
from tests.conversation.support import said

WAIT = 5


def built_app(tmp_path):
    root = tmp_path / "built-app"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html><body>board</body></html>")
    (root / "robots.txt").write_text("User-agent: *\n")
    return root


def test_the_app_route_serves_the_built_ember_index(tmp_path):
    answer = client_for(app_root=built_app(tmp_path)).get("/")

    assert answer.status_code == 200
    assert answer.headers["content-type"].startswith("text/html")
    assert b"<html" in answer.content.lower()


def test_a_deep_app_route_serves_the_index_so_the_router_can_boot(tmp_path):
    answer = client_for(app_root=built_app(tmp_path)).get(
        "/conversations/PRRT_aa")

    assert answer.status_code == 200
    assert b"board" in answer.content, (
        "the ember router owns every path under the app, and a reload of a "
        "conversation url has to reach the app rather than a 404")


def test_a_built_asset_is_served_with_its_own_type(tmp_path):
    answer = client_for(app_root=built_app(tmp_path)).get("/robots.txt")

    assert answer.status_code == 200
    assert answer.headers["content-type"].startswith("text/plain")
    assert answer.content.startswith(b"User-agent")


def test_nothing_is_served_before_the_front_end_is_built(tmp_path):
    answer = client_for(app_root=tmp_path / "never-built").get("/")

    assert answer.status_code == 404, (
        "a checkout that has not run make build_frontend has no app to "
        "serve, and the board says 404 rather than pretending")


def test_the_server_keeps_its_own_routes_from_the_app(tmp_path):
    client = client_for(app_root=built_app(tmp_path))

    assert client.get("/api/conversations").headers["content-type"] == "application/json"
    assert client.get("/fonts/Acme-Regular.otf").status_code == 404


class SlowToAnswer(FakeGitHub):
    def __init__(self):
        super().__init__()
        self.asked, self.release = threading.Event(), threading.Event()

    def comment_exists(self, pr, kind, comment_id):
        self.asked.set()
        self.release.wait(WAIT)
        return False


def settled(read, deadline=WAIT):
    ends = time.monotonic() + deadline
    while time.monotonic() < ends:
        found = read()
        if found:
            return found
        time.sleep(0.01)
    return read()


def test_reading_a_threads_comments_does_not_wait_for_github_to_confirm_them():
    github = SlowToAnswer()
    board = board_on(fake_threads(github), check_presence=True)
    heard_on(board, "PRRT_aa", said(11, BODY))

    answer = client_of(board).get("/api/conversations/PRRT_aa/comments")

    assert answer.status_code == 200
    assert github.asked.wait(WAIT), (
        "opening a card is what asks GitHub whether its comment is still "
        "there, and the comments are what the card reads when it opens")
    assert answer.json()[0]["deleted"] is False

    github.release.set()
    assert settled(lambda: board.threads.get("PRRT_aa").comment_deleted)


def test_the_palette_is_served_as_css_the_app_can_link():
    answer = client_for().get("/palette.css")

    assert answer.status_code == 200
    assert answer.headers["content-type"].startswith("text/css")
    assert ":root {" in answer.text
    assert "--page:" in answer.text and "--text:" in answer.text


def test_the_palette_css_binds_every_variable_in_both_modes():
    bound = css_variables(client_for().get("/palette.css").text)

    assert bound["light"]
    assert set(bound["light"]) == set(bound["dark"]), (
        "a variable bound in one mode and not the other is a colour that "
        "falls back to the wrong ground")


def test_the_app_never_writes_a_colour_of_its_own():
    frontend = SERVED_APP.parents[4] / "frontend" / "app"
    hexes = {
        path.relative_to(frontend).as_posix()
        for path in frontend.rglob("*")
        if path.is_file() and path.suffix in {".css", ".gts", ".ts"}
        and re.search(r"#[0-9a-fA-F]{3,8}\b", path.read_text())
    }

    assert hexes == set(), (
        "every colour is the board's palette, served as css custom properties; "
        f"the front end may not write one: {sorted(hexes)}")


def fonts_in(tmp_path, *names):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    for name in names:
        (fonts / name).write_bytes(b"OTTO")
    return str(fonts)


def test_the_font_faces_are_served_as_css_when_there_are_fonts(tmp_path):
    font_dir = fonts_in(tmp_path, "Acme-Regular.otf", "Acme-SemiBold.otf")

    answer = client_for(font_dir=font_dir).get("/fonts.css")

    assert answer.status_code == 200
    assert answer.headers["content-type"].startswith("text/css")
    assert "@font-face" in answer.text
    assert "/fonts/Acme-Regular.otf" in answer.text
    assert 'font-family: "Board Face"' in answer.text
    assert '--body-stack: "Board Face",' in answer.text
    assert "--body-stack:" in answer.text, (
        "the app asks for one stack and the server says whether the licensed "
        "face is in it")


def test_health_names_no_font_problem_when_the_faces_are_there(tmp_path):
    font_dir = fonts_in(tmp_path, "Acme-Regular.otf")

    health = client_for(font_dir=font_dir).get("/api/health").json()

    assert health["font_problem"] is None


def test_health_says_the_font_directory_cannot_be_listed(tmp_path):
    missing = tmp_path / "nowhere"

    problem = client_for(font_dir=str(missing)).get("/api/health").json()["font_problem"]

    assert str(missing) in problem
    assert "cannot be listed" in problem


def test_health_says_the_font_directory_holds_no_usable_face(tmp_path):
    font_dir = fonts_in(tmp_path, "Acme-Wobbly.otf", "notes.txt")

    problem = client_for(font_dir=font_dir).get("/api/health").json()["font_problem"]

    assert font_dir in problem
    assert "no <Family>-<Style>.otf face" in problem


def test_the_font_css_is_a_plain_stack_when_there_are_none():
    css = client_for().get("/fonts.css").text

    assert "@font-face" not in css
    assert "--body-stack:" in css
