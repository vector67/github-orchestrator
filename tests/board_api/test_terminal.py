import json

import pytest
from starlette.websockets import WebSocketDisconnect

from github_orchestrator.board_api.fake import FakeManagerPanel
from github_orchestrator.terminal_sessions.fake import FakeTerminalSessions
from tests.board_api.support import PORT, WORKTREE, board_for
from tests.waiting import until

HERE = f"http://127.0.0.1:{PORT}"


@pytest.fixture
def sessions():
    return FakeTerminalSessions()


@pytest.fixture
def manager():
    return FakeManagerPanel()


@pytest.fixture
def web(sessions, manager):
    return board_for(sessions=sessions, manager=manager).client


def _socket(web, session, origin=HERE, host=f"127.0.0.1:{PORT}"):
    return web.websocket_connect(f"/api/terminal/sessions/{session}",
                                 headers={"Origin": origin, "Host": host})


def test_the_board_lists_the_terminal_sessions_in_the_order_they_started(web, sessions):
    first = sessions.start(WORKTREE, ["/bin/zsh", "-l"])
    second = sessions.start("/elsewhere", ["git", "add", "-p"])

    answer = web.get("/api/terminal/sessions")

    assert answer.status_code == 200
    assert answer.json() == {"sessions": [
        {"id": first, "argv": ["/bin/zsh", "-l"], "worktree": WORKTREE},
        {"id": second, "argv": ["git", "add", "-p"], "worktree": "/elsewhere"},
    ]}


def test_opening_a_terminal_command_hands_its_keys_to_the_manager(web, manager, sessions):
    sessions.start(WORKTREE, ["git", "add", "-p"])

    answer = web.post("/api/terminal/sessions", json={"keys": "a"})

    assert answer.status_code == 200
    assert manager.opened == ["a"]
    assert [session["argv"] for session in answer.json()["sessions"]] == [["git", "add", "-p"]]


@pytest.mark.parametrize("keys", ["new", "a", "i12"])
def test_every_command_the_terminal_opens_is_taken(web, manager, keys):
    assert web.post("/api/terminal/sessions", json={"keys": keys}).status_code == 200
    assert manager.opened == [keys]


@pytest.mark.parametrize("keys", ["p", "i", ""])
def test_a_command_the_terminal_does_not_open_is_refused_before_the_manager_hears_it(
        web, manager, keys):
    answer = web.post("/api/terminal/sessions", json={"keys": keys})

    assert answer.status_code == 400
    assert manager.opened == []


def test_a_command_the_manager_could_not_open_is_refused_with_its_reason(web, manager):
    manager.terminal_refusal = "refused: the worktree holds another PR's branch"

    answer = web.post("/api/terminal/sessions", json={"keys": "c"})

    assert answer.status_code == 409
    [error] = answer.json()["errors"]
    assert error["code"] == "terminal-refused"
    assert error["detail"] == "refused: the worktree holds another PR's branch"


def test_a_page_connected_to_a_session_sees_what_it_prints(web, sessions):
    session = sessions.start(WORKTREE, ["/bin/zsh", "-l"])
    sessions.print(session, b"worktree $ ")

    with _socket(web, session) as page:
        assert page.receive_bytes() == b"worktree $ "


def test_a_page_resuming_after_what_it_saw_is_sent_only_what_came_after(web, sessions):
    session = sessions.start(WORKTREE, ["/bin/zsh", "-l"])
    sessions.print(session, b"seen ")
    sessions.print(session, b"missed")

    with web.websocket_connect(f"/api/terminal/sessions/{session}?after=5",
                               headers={"Origin": HERE, "Host": f"127.0.0.1:{PORT}"}) as page:
        assert page.receive_bytes() == b"missed"


def test_what_the_page_types_and_its_size_reach_the_session(web, sessions):
    session = sessions.start(WORKTREE, ["/bin/zsh", "-l"])
    sessions.print(session, b"$ ")

    with _socket(web, session) as page:
        page.receive_bytes()
        page.send_text(json.dumps({"columns": 120, "rows": 40}))
        page.send_bytes(b"git status\r")
        sessions.print(session, b"On branch main")
        page.receive_bytes()
        until(lambda: sessions.sessions[session].typed and sessions.sessions[session].size,
              seconds=5)

    assert sessions.sessions[session].typed == [b"git status\r"]
    assert sessions.sessions[session].size == (120, 40)


def test_a_session_that_ends_tells_the_page_its_exit_code_and_closes(web, sessions):
    session = sessions.start(WORKTREE, ["git", "commit"])

    with _socket(web, session) as page:
        sessions.end(session, 1)

        assert json.loads(page.receive_text()) == {"exit_code": 1}
        with pytest.raises(WebSocketDisconnect) as closed:
            page.receive_bytes()

    assert closed.value.code == 1000


def test_a_page_leaving_lets_go_of_the_session_and_leaves_it_running(web, sessions):
    session = sessions.start(WORKTREE, ["/bin/zsh", "-l"])

    with _socket(web, session) as page:
        page.send_bytes(b"ls\r")

    assert sessions.sessions[session].connections == 0
    assert [listed.id for listed in sessions.listed()] == [session]


def test_a_session_that_is_gone_closes_the_page_saying_so(web):
    with _socket(web, "no-such-session") as page:
        with pytest.raises(WebSocketDisconnect) as closed:
            page.receive_bytes()

    assert closed.value.code == 4404


def test_another_sites_page_cannot_connect_to_a_session(web, sessions):
    session = sessions.start(WORKTREE, ["/bin/zsh", "-l"])

    with pytest.raises(WebSocketDisconnect) as refused:
        with _socket(web, session, origin="http://evil.example"):
            pass

    assert refused.value.code == 1008
    assert sessions.sessions[session].connected_once is False


def test_a_connection_that_names_no_origin_is_refused(web, sessions):
    session = sessions.start(WORKTREE, ["/bin/zsh", "-l"])

    with pytest.raises(WebSocketDisconnect) as refused:
        with web.websocket_connect(f"/api/terminal/sessions/{session}",
                                   headers={"Host": f"127.0.0.1:{PORT}"}):
            pass

    assert refused.value.code == 1008
    assert sessions.sessions[session].connected_once is False


def test_a_connection_addressed_to_another_name_is_refused(web, sessions):
    session = sessions.start(WORKTREE, ["/bin/zsh", "-l"])

    with pytest.raises(WebSocketDisconnect) as refused:
        with _socket(web, session, host="rebound.example:8888"):
            pass

    assert refused.value.code == 1008
    assert sessions.sessions[session].connected_once is False
