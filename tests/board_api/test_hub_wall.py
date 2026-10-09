from dataclasses import replace

from github_orchestrator.board_api.fake import (
    IDLE,
    FakeDashboards,
    FakeHoldings,
    FakeManagerPanel,
)
from tests.board_api.support import (
    client_for,
    holding,
    served_hub,
)
from tests.builders import a_pr

REPO = "acme/widgets"
SECOND = a_pr(54, REPO)

GROUPS = [
    {"group": "needs-you", "name": "Needs you"},
    {"group": "draft", "name": "Draft"},
    {"group": "agent-working", "name": "Agent working"},
    {"group": "waiting-on-others", "name": "Waiting on others"},
    {"group": "on-hold", "name": "On hold"},
    {"group": "mentioned", "name": "Mentioned"},
]


def snapshot(pr, **fields):
    return replace(IDLE, pr=pr, **fields)


def wall(holdings=None, dashboards=None, *prs, managers=None):
    return served_hub(dashboards=dashboards or FakeDashboards(),
                      told=holding(*prs, managers=managers), holdings=holdings or FakeHoldings())


def rows(web):
    return web.get("/api/pull-requests").json()["pull_requests"]


def served_as_a_board_serves(dashboard):
    return client_for(manager=FakeManagerPanel(now=dashboard)).get("/api/dashboard").json()


def test_each_row_carries_the_dashboard_built_from_what_is_on_disk():
    rebuilt = snapshot(SECOND, on_hold=True)
    web = wall(FakeHoldings(), FakeDashboards({SECOND: rebuilt}), SECOND,
                  managers={SECOND: "exited"})

    assert rows(web) == [{
        "repo": REPO, "number": 54, "manager": "exited", "board_url": "/pr/acme/widgets/54",
        "dashboard": served_as_a_board_serves(rebuilt),
    }]


def test_every_row_links_to_its_pull_requests_page_on_the_hub():
    web = wall(FakeHoldings(), FakeDashboards(), SECOND, managers={SECOND: "no-window"})

    [row] = rows(web)

    assert row["board_url"] == "/pr/acme/widgets/54"


def test_the_wall_lists_its_groups_in_order_with_their_names():
    web = wall()

    assert web.get("/api/pull-requests").json()["groups"] == GROUPS


def test_the_wall_is_not_modified_while_nothing_changes():
    web = wall(FakeHoldings(), FakeDashboards(), SECOND)
    first = web.get("/api/pull-requests")

    again = web.get("/api/pull-requests", headers={"If-None-Match": first.headers["ETag"]})

    assert again.status_code == 304
