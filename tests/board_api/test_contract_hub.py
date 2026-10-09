import socket

import pytest

from github_orchestrator.board_api import Hub
from github_orchestrator.board_api.fake import FakeHoldings, FakeHub
from github_orchestrator.domain import HubState
from github_orchestrator.wiring import listen_on_loopback
from tests.board_api.support import hub_on


def served() -> Hub:
    return hub_on(listen_on_loopback)


@pytest.fixture(params=["fake", "served"])
def kind(request):
    return request.param


@pytest.fixture
def hub(kind):
    made = FakeHub() if kind == "fake" else served()
    yield made
    made.stop()


def start(hub, port=0):
    return hub.start(port, FakeHoldings(), HubState.WATCHING)


def test_a_started_hub_answers_on_loopback(hub):
    assert start(hub).startswith("http://127.0.0.1:")


def test_starting_a_running_hub_again_answers_the_same_address(hub):
    first = start(hub)

    assert start(hub) == first


def test_stopping_a_running_hub_says_it_stopped_one_and_only_once(hub):
    start(hub)

    assert hub.stop() is True
    assert hub.stop() is False


def test_a_hub_that_was_never_started_has_nothing_to_stop(hub):
    assert hub.stop() is False


def test_a_stopped_hub_starts_again(hub):
    start(hub)
    hub.stop()

    assert start(hub).startswith("http://127.0.0.1:")


def test_a_hub_takes_the_prs_it_is_shown_before_it_starts(hub):
    hub.show([])

    assert start(hub).startswith("http://127.0.0.1:")


@pytest.fixture
def taken(kind):
    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen()
    port = holder.getsockname()[1]
    made = FakeHub(taken={port}) if kind == "fake" else served()
    yield made, port
    made.stop()
    holder.close()


def test_a_port_something_else_holds_refuses_the_start_and_a_later_start_can_still_succeed(taken):
    hub, port = taken

    with pytest.raises(OSError):
        start(hub, port)

    assert start(hub).startswith("http://127.0.0.1:")
