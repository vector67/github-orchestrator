import socket
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from github_orchestrator.board_api.fake import (
    IDLE,
    FakeDashboards,
    FakeHoldings,
    FakeManagerPanel,
)
from github_orchestrator.domain import HubState
from github_orchestrator.github.fake import FakeGitHub
from tests.board_api.support import (
    ACCOUNT,
    HUB_PORT,
    THE_PR,
    board_on,
    client_for,
    fake_threads,
    served_hub,
)
from tests.board_api.test_hub_proxy import OnLoopback, port_of
from tests.builders import a_pr

REPO = "acme/widgets"
FIRST = a_pr(77, REPO)
SECOND = a_pr(54, REPO)
THIRD = a_pr(5, "octocat/hello-world")
FOURTH = a_pr(59, REPO)

START = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)

GROUPS = [
    {"group": "needs-you", "name": "Needs you"},
    {"group": "draft", "name": "Draft"},
    {"group": "agent-working", "name": "Agent working"},
    {"group": "waiting-on-others", "name": "Waiting on others"},
    {"group": "on-hold", "name": "On hold"},
    {"group": "mentioned", "name": "Mentioned"},
]


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def later(self, minutes=1):
        self.now += timedelta(minutes=minutes)


def snapshot(pr, **fields):
    return replace(IDLE, pr=pr, **fields)


def wall(holdings=None, dashboards=None, *prs, clock=None, board_seconds=2.0):
    hub, listening = served_hub(dashboards=dashboards or FakeDashboards(),
                                clock=clock or Clock(), board_seconds=board_seconds)
    url = hub.start(HUB_PORT, holdings or FakeHoldings(), HubState.WATCHING)
    hub.show(list(prs))
    return TestClient(listening.app, base_url=url), hub


def rows(web):
    return web.get("/api/pull-requests").json()["pull_requests"]


def served_as_a_board_serves(dashboard):
    return client_for(manager=FakeManagerPanel(now=dashboard)).get("/api/dashboard").json()


def test_a_pr_whose_board_is_not_up_carries_the_dashboard_built_from_what_is_on_disk():
    rebuilt = snapshot(SECOND, on_hold=True)
    web, _ = wall(FakeHoldings(managers={SECOND: "exited"}),
                  FakeDashboards({SECOND: rebuilt}), SECOND)

    assert rows(web) == [{
        "repo": REPO, "number": 54, "manager": "exited", "board_url": None,
        "board_answered": False,
        "dashboard": served_as_a_board_serves(rebuilt),
    }]


@pytest.fixture
def board():
    working = snapshot(THE_PR, working_on="ci-failed", elapsed_seconds=75.0,
                       silent_seconds=4.0)
    served = board_on(fake_threads(FakeGitHub(account=ACCOUNT)), listening=OnLoopback(),
                      manager=FakeManagerPanel(now=working))
    yield served
    served.api.stop()


def test_a_pr_whose_board_answers_carries_the_dashboard_its_board_serves(board):
    web, _ = wall(FakeHoldings(managers={THE_PR: "running"}, ports={THE_PR: port_of(board)}),
                  FakeDashboards({THE_PR: snapshot(THE_PR)}), THE_PR)

    [row] = rows(web)

    assert (row["board_url"], row["board_answered"]) == ("/pr/acme/widgets/54", True)
    assert row["dashboard"] == board.client.get("/api/dashboard").json()
    assert row["dashboard"]["manager"]["working_on"] == "ci-failed"


def _closed_port():
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def test_a_board_that_is_down_gives_way_to_the_dashboard_built_from_disk():
    rebuilt = snapshot(SECOND, frozen_on="another-pr")
    web, _ = wall(FakeHoldings(ports={SECOND: _closed_port()}),
                  FakeDashboards({SECOND: rebuilt}), SECOND)

    [row] = rows(web)

    assert (row["board_url"], row["board_answered"]) == ("/pr/acme/widgets/54", False)
    assert row["dashboard"] == served_as_a_board_serves(rebuilt)


@pytest.fixture
def silent_boards():
    listeners = []
    for _ in range(3):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(8)
        listeners.append(listener)
    yield [listener.getsockname()[1] for listener in listeners]
    for listener in listeners:
        listener.close()


def test_boards_that_take_the_request_and_never_answer_cost_one_wait_not_one_each(
        silent_boards):
    prs = (FIRST, SECOND, FOURTH)
    holdings = FakeHoldings(ports=dict(zip(prs, silent_boards, strict=True)))
    web, _ = wall(holdings, FakeDashboards(), *prs, board_seconds=0.1)

    began = time.monotonic()
    answered = rows(web)
    took = time.monotonic() - began

    assert [row["board_answered"] for row in answered] == [False, False, False]
    assert took < 0.25


def test_the_wall_lists_its_groups_in_order_with_their_names():
    web, _ = wall()

    assert web.get("/api/pull-requests").json()["groups"] == GROUPS


def test_the_wall_is_not_modified_while_nothing_changes():
    web, _ = wall(FakeHoldings(), FakeDashboards(), SECOND)
    first = web.get("/api/pull-requests")

    again = web.get("/api/pull-requests", headers={"If-None-Match": first.headers["ETag"]})

    assert again.status_code == 304


def test_a_board_that_misses_one_read_keeps_its_last_answer(board):
    clock = Clock()
    holdings = FakeHoldings(ports={THE_PR: port_of(board), FIRST: _closed_port()})
    web, _ = wall(holdings, FakeDashboards({THE_PR: snapshot(THE_PR)}),
                  THE_PR, FIRST, clock=clock)
    rows(web)

    board.api.stop()
    clock.later(0.25)
    row = next(row for row in rows(web) if row["number"] == THE_PR.number)

    assert (row["board_answered"], row["dashboard"]["manager"]["working_on"]) == (
        True, "ci-failed")


def test_a_board_silent_for_longer_than_it_is_trusted_gives_way_to_the_dashboard_from_disk(board):
    clock = Clock()
    web, _ = wall(FakeHoldings(ports={THE_PR: port_of(board)}),
                  FakeDashboards({THE_PR: snapshot(THE_PR)}), THE_PR, clock=clock)
    rows(web)

    board.api.stop()
    clock.later(1)
    [row] = rows(web)

    assert (row["board_answered"], row["dashboard"]["manager"]["working_on"]) == (
        False, None)
