from dataclasses import replace
from pathlib import Path

from github_orchestrator.board_api.fake import (
    IDLE,
    FakeDashboards,
    FakeHoldings,
    FakeManagerPanel,
)
from github_orchestrator.pr_summaries import PrSummaries, Summary
from github_orchestrator.wiring import PrSummariesWiring, wire
from tests.board_api.support import (
    MOMENT,
    client_for,
    holding,
    served_hub,
    summaries_in,
)
from tests.builders import a_pr
from tests.conftest import clocks_of
from tests.conversation.support import at

REPO = "acme/widgets"
SECOND = a_pr(54, REPO)
THIRD = a_pr(55, REPO)

GROUPS = [
    {"group": "needs-you", "name": "Needs you"},
    {"group": "agent-working", "name": "Agent working"},
    {"group": "waiting-on-others", "name": "Waiting on others"},
    {"group": "parked", "name": "Parked"},
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
        "dashboard": served_as_a_board_serves(rebuilt), "mismatches": None,
    }]


def stored(directory: Path, pr, summary: Summary) -> None:
    summaries: PrSummaries = wire(PrSummariesWiring(directory), clocks_of(at(MOMENT))).get(PrSummaries)
    summaries.save(pr, summary)


def test_each_row_carries_the_mismatch_count_of_its_stored_summary(tmp_path):
    stored(tmp_path, SECOND, Summary(head_sha="a" * 40, mismatches=3))
    web = served_hub(told=holding(SECOND, THIRD), summaries=summaries_in(tmp_path))

    assert {row["number"]: row["mismatches"] for row in rows(web)} == {54: 3, 55: None}


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
