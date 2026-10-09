import os
import socket

import pytest

from github_orchestrator.board_api import BoardApi
from github_orchestrator.board_api.fake import FakeBoardApi, FakeManagerPanel
from github_orchestrator.conversation import ConversationManagerFactory
from github_orchestrator.settings.fake import fake_settings
from github_orchestrator.terminal_sessions import TerminalSessions
from github_orchestrator.terminal_sessions.fake import FakeTerminalSessions
from github_orchestrator.wiring import (
    BoardApiWiring,
    board_font_dir,
    listen_on_loopback,
    wire,
)
from github_orchestrator.working_copies import WorkingCopies
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.board_api.support import THE_PR, UNBUILT, fake_threads
from tests.conftest import clocks_of, fake_provider


def served(conversation_managers, working_copies=None, app_root=UNBUILT) -> BoardApi:
    return wire(
        fake_provider(ConversationManagerFactory, conversation_managers),
        fake_provider(WorkingCopies, working_copies or FakeWorkingCopies()),
        fake_provider(TerminalSessions, FakeTerminalSessions()),
        clocks_of(),
        BoardApiWiring(listen_on_loopback, app_root=app_root, font_dir=None,
                       check_presence=False, hub_port=8720, first_names_only=False),
    ).get(BoardApi)


@pytest.fixture(params=["fake", "served"])
def kind(request):
    return request.param


@pytest.fixture
def conversation_managers():
    return fake_threads()


@pytest.fixture
def board_api(kind, conversation_managers):
    api = FakeBoardApi() if kind == "fake" else served(conversation_managers)
    yield api
    api.stop()


def start(api, port=0):
    return api.start(THE_PR, port=port, manager=FakeManagerPanel())


def test_a_board_that_was_never_started_is_not_running(board_api):
    assert board_api.is_running() is False


def test_a_started_board_answers_on_loopback_and_is_running(board_api):
    url = start(board_api)

    assert url.startswith("http://127.0.0.1:")
    assert board_api.is_running() is True


def test_starting_a_running_board_again_answers_the_same_address(board_api):
    first = start(board_api)

    assert start(board_api) == first


def test_stopping_a_running_board_says_it_stopped_one(board_api):
    start(board_api)

    assert board_api.stop() is True
    assert board_api.is_running() is False


def test_stopping_a_board_that_is_not_running_does_nothing(board_api):
    assert board_api.stop() is False


def test_a_stopped_board_starts_again(board_api):
    start(board_api)
    board_api.stop()

    start(board_api)

    assert board_api.is_running() is True


@pytest.fixture
def taken(kind, conversation_managers):
    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen()
    port = holder.getsockname()[1]
    api = FakeBoardApi(taken={port}) if kind == "fake" else served(conversation_managers)
    yield api, port
    api.stop()
    holder.close()


def test_a_port_something_else_holds_refuses_the_start(taken):
    board_api, port = taken

    with pytest.raises(OSError):
        start(board_api, port=port)

    assert board_api.is_running() is False


@pytest.mark.parametrize(("configured", "expected"), [
    ("~/design/fonts", os.path.expanduser("~/design/fonts")),
    ("", None),
])
def test_the_board_is_built_with_the_configured_font_directory(tmp_path, configured, expected):
    assert board_font_dir(fake_settings(tmp_path, board_font_dir=configured)) == expected
