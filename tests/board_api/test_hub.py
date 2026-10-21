import logging
from datetime import datetime, timedelta, timezone

import pytest

from github_orchestrator.board_api.fake import (
    FakeEmojis,
    FakeHoldings,
    FakeTold,
    FakeTour,
)
from github_orchestrator.board_api.interface import Held
from github_orchestrator.domain import HubState, Repo
from github_orchestrator.watcher import Health
from tests.board_api.support import (
    HUB_PORT,
    SERVER_PID,
    UNBUILT,
    Pulse,
    Words,
    asked_with_every_worker_taken,
    holding,
    hub_contract,
    served_hub,
)
from tests.builders import a_pr

REPO = "acme/widgets"
MINE = a_pr(54, REPO)
THEIRS = a_pr(17, REPO)
ELSEWHERE = a_pr(5, "octocat/hello-world")


def hub_client(holdings, *prs, app_root=UNBUILT):
    told = holding(*prs)
    web = served_hub(app_root, told=told, holdings=holdings)
    return web, told


def client(holdings, *prs, **kwargs):
    return hub_client(holdings, *prs, **kwargs)[0]


def listed(answer):
    return answer.json()["pull_requests"]


def test_the_list_is_in_repo_then_number_order_whatever_order_the_watcher_gave():
    answer = client(FakeHoldings(), MINE, THEIRS, ELSEWHERE).get("/api/pull-requests")

    assert [(pr["repo"], pr["number"]) for pr in listed(answer)] == [
        (REPO, 17), (REPO, 54), ("octocat/hello-world", 5)]


def test_the_list_names_every_repository_this_instance_watches():
    web = served_hub(watching=[Repo("acme", "widgets"), Repo("acme", "gadgets")], told=holding())

    answer = web.get("/api/pull-requests")

    assert answer.json()["watching"] == ["acme/gadgets", "acme/widgets"]


def test_the_list_is_refused_as_starting_until_the_watcher_says_what_it_holds():
    web = served_hub(told=FakeTold())

    answer = web.get("/api/pull-requests")

    assert answer.status_code == 503
    assert answer.json()["errors"][0]["code"] == "watcher-starting"
    assert answer.headers["Retry-After"] == "1"


def test_the_list_is_empty_once_the_watcher_says_it_holds_nothing():
    assert listed(client(FakeHoldings()).get("/api/pull-requests")) == []


def test_the_list_follows_what_the_watcher_says_after_each_cycle():
    web, told = hub_client(FakeHoldings(), MINE, THEIRS)

    told.now = Held(told=True, managers={THEIRS: "running"})

    assert [pr["number"] for pr in listed(web.get("/api/pull-requests"))] == [17]


def test_hold_sets_the_pr_on_hold_and_answers_that_it_took_it():
    holdings = FakeHoldings()

    answer = client(holdings, MINE).post(f"/api/pull-requests/{REPO}/54:hold")

    assert answer.status_code == 202
    assert answer.headers["Location"] == "/api/pull-requests"
    assert holdings.on_hold == {MINE}


def test_resume_sets_a_held_pr_running():
    holdings = FakeHoldings(on_hold={MINE})

    answer = client(holdings, MINE).post(f"/api/pull-requests/{REPO}/54:resume")

    assert answer.status_code == 202
    assert holdings.on_hold == set()


def test_release_asks_for_a_frozen_prs_worktree_to_be_let_go():
    holdings = FakeHoldings(frozen={THEIRS})

    answer = client(holdings, THEIRS).post(f"/api/pull-requests/{REPO}/17:release")

    assert answer.status_code == 202
    assert holdings.released == {THEIRS}


def test_release_of_a_pr_that_is_not_frozen_is_refused():
    answer = client(FakeHoldings(), MINE).post(
        f"/api/pull-requests/{REPO}/54:release")

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "not-frozen"


def test_a_command_for_a_pr_the_watcher_does_not_hold_is_refused_and_changes_nothing():
    holdings = FakeHoldings()

    answer = client(holdings, MINE).post(f"/api/pull-requests/{REPO}/17:hold")

    assert answer.status_code == 404
    assert answer.json()["errors"][0]["code"] == "not-found"
    assert holdings.on_hold == set()


def test_a_command_from_another_sites_page_is_refused():
    holdings = FakeHoldings()

    answer = client(holdings, MINE).post(f"/api/pull-requests/{REPO}/54:hold",
                                         headers={"Origin": "https://evil.example"})

    assert answer.status_code == 403
    assert holdings.on_hold == set()


def test_a_read_addressed_to_another_name_is_refused():
    answer = client(FakeHoldings(), MINE).get(
        "/api/pull-requests", headers={"Host": f"evil.example:{HUB_PORT}"})

    assert answer.status_code == 403
    assert answer.json()["errors"][0]["code"] == "foreign-origin"


def test_health_says_this_is_the_hub_and_where_it_is():
    answer = client(FakeHoldings()).get("/api/health")

    assert answer.json() == {
        "status": "ok", "pid": SERVER_PID, "serves": "hub",
        "hub_url": f"http://127.0.0.1:{HUB_PORT}", "font_problem": None, "state": "watching",
        "version": "0.1.0",
        "watcher": {"polled_at": "2026-08-28T09:59:40+00:00",
                    "next_poll_at": "2026-08-28T10:00:40+00:00", "overdue": False,
                    "last_error": None, "fix": None},
        "newest_release": None}


def test_health_answers_while_every_worker_thread_is_taken():
    answer = asked_with_every_worker_taken(client(FakeHoldings()), "/api/health")

    assert answer.json()["serves"] == "hub"


def test_the_hub_serves_the_board_app_at_any_page_path(tmp_path):
    (tmp_path / "index.html").write_text("<p>the board app</p>")

    answer = client(FakeHoldings(), app_root=tmp_path).get("/prs")

    assert answer.status_code == 200
    assert "the board app" in answer.text


def test_the_hub_serves_nothing_at_a_path_it_does_not_know():
    answer = client(FakeHoldings()).get("/api/conversations")

    assert answer.status_code == 404
    assert answer.json()["errors"][0]["code"] == "not-found"


def test_an_error_the_hub_page_reports_is_written_to_the_log(caplog):
    with caplog.at_level(logging.WARNING):
        answer = client(FakeHoldings()).post("/api/client-errors", json={
            "where": "prs", "message": "the list would not load"})

    assert answer.status_code == 204
    assert "the list would not load" in caplog.text


def test_every_hub_command_declares_the_hand_over_and_where_to_poll():
    contract = hub_contract()

    commands = {path: operations["post"] for path, operations in contract["paths"].items()
                if path.startswith("/api/pull-requests/")}

    assert set(commands) == {
        "/api/pull-requests/{owner}/{name}/{number}:hold",
        "/api/pull-requests/{owner}/{name}/{number}:resume",
        "/api/pull-requests/{owner}/{name}/{number}:release"}
    assert all(command["responses"]["202"]["headers"]["Location"]
               for command in commands.values())


def test_health_says_which_state_the_watcher_last_told_the_hub():
    told = FakeTold(hub_state=HubState.WATCHING)
    web = served_hub(told=told)

    told.hub_state = HubState.SETUP

    assert web.get("/api/health").json()["state"] == "setup"


def test_health_has_no_state_before_the_watcher_tells_one():
    web = served_hub(told=FakeTold(hub_state=None))

    assert web.get("/api/health").json()["state"] is None


def test_the_list_is_refused_as_starting_before_the_watcher_tells_its_state():
    web = served_hub(told=FakeTold(hub_state=None))

    answer = web.get("/api/pull-requests")

    assert answer.json()["errors"][0]["code"] == "watcher-starting"


FAILING = Health(alive=True, polled_at=None, read_at=datetime(2026, 9, 28, tzinfo=timezone.utc),
                 last_error="gh auth token failed",
                 fix="Log in with `gh auth login`, then this page retries.",
                 polls_every=timedelta(minutes=1))


def test_the_list_is_refused_as_failing_with_the_watchers_error_until_a_cycle_succeeds():
    web = served_hub(pulse=Pulse(FAILING), told=FakeTold())

    answer = web.get("/api/pull-requests")

    assert answer.status_code == 503
    assert answer.json()["errors"][0] == {"status": 503, "code": "watcher-failing",
                                          "detail": "gh auth token failed"}


@pytest.mark.parametrize("state", [HubState.SETUP, HubState.BROKEN])
def test_the_list_is_refused_with_the_configs_problem_while_the_hub_is_not_watching(state):
    problem = "config.toml: the config file does not exist"
    web = served_hub(config_file=Words(problem), told=FakeTold(hub_state=state))

    answer = web.get("/api/pull-requests")

    assert answer.status_code == 503
    assert answer.json()["errors"][0] == {"status": 503, "code": "not-watching",
                                          "detail": problem}


class Seen:
    def __init__(self, version, checked_at, *, newer_than):
        self.version = version
        self.checked_at = checked_at
        self._newer_than = newer_than

    def newer_than(self, running):
        return running in self._newer_than


class Recorded:
    def __init__(self, release):
        self.release = release

    def recorded(self):
        return self.release


CHECKED = datetime(2026, 10, 9, 8, 0, tzinfo=timezone.utc)


def _health_with(release):
    web = served_hub(releases=Recorded(release), told=FakeTold(hub_state=HubState.SETUP))
    return web.get("/api/health").json()["newest_release"]


def test_health_gives_the_newest_release_the_daily_check_recorded_and_that_it_is_newer():
    assert _health_with(Seen("0.2.0", CHECKED, newer_than={"0.1.0"})) == {
        "version": "0.2.0", "checked_at": "2026-10-09T08:00:00+00:00", "newer": True}


def test_health_asks_whether_the_release_is_newer_than_the_version_this_hub_runs():
    assert _health_with(Seen("0.1.0", CHECKED, newer_than={"0.0.9"}))["newer"] is False


def test_health_has_no_newest_release_before_the_first_check():
    assert _health_with(None) is None


def _tour_client(marker):
    web = served_hub(tour=marker)
    return web


def test_the_tour_is_due_when_the_marker_says_so():
    assert _tour_client(FakeTour(True)).get("/api/tour").json() == {"due": True}


def test_the_tour_is_not_due_without_the_marker():
    assert _tour_client(FakeTour(False)).get("/api/tour").json() == {"due": False}


def test_seeing_the_tour_clears_the_marker_so_it_is_shown_once():
    marker = FakeTour(True)
    tour = _tour_client(marker)

    answer = tour.post("/api/tour:seen")

    assert (answer.status_code, marker.is_due, tour.get("/api/tour").json()) == (
        204, False, {"due": False})


def test_the_emojis_are_every_name_github_listed_with_its_picture():
    named = {"shipit": "https://github.githubassets.com/images/icons/emoji/shipit.png?v8"}

    assert served_hub(emojis=FakeEmojis(named)).get("/api/emojis").json() == {"named": named}
