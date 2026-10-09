from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from github_orchestrator.agent_runs.fake import FakeAgentRuns
from github_orchestrator.board_api.fake import FakeHoldings
from github_orchestrator.domain import HubState
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.watcher import Health
from tests.board_api.support import HUB_PORT, Pulse, served_hub
from tests.builders import a_pr

REPO = "acme/widgets"
HELD = a_pr(84, REPO)
CLOSED = a_pr(82, REPO)

NOW = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
MINUTE = timedelta(minutes=1)

POLLING = Health(alive=True, since_last_poll=timedelta(seconds=19), last_error=None, fix=None,
                 polls_every=MINUTE)


def ledger():
    return FakeAgentRuns(FakePrProcesses())


def runs_read(runs=None, health=POLLING, *held):
    hub, listening = served_hub(ledger=runs or ledger(), pulse=Pulse(health), clock=lambda: NOW)
    url = hub.start(HUB_PORT, FakeHoldings(), HubState.WATCHING)
    hub.show(list(held))
    return TestClient(listening.app, base_url=url).get("/api/runs")


def test_a_run_is_listed_with_how_long_it_took_how_it_ended_and_what_it_cost():
    runs = ledger().ran(HELD, "ci-failed", 95.5, NOW - timedelta(hours=1), cost_usd=0.42)

    [run] = runs_read(runs, POLLING, HELD).json()["runs"]

    assert run == {"ended_at": "2026-09-28T09:00:00+00:00", "repo": REPO, "number": 84,
                   "event": "ci-failed", "elapsed_seconds": 95.5, "exit_code": 0,
                   "cost_usd": 0.42, "failed": False, "board_url": "/pr/acme/widgets/84"}


def test_runs_come_newest_first():
    runs = (ledger().ran(HELD, "review-requested", 10, NOW - 3 * MINUTE)
            .ran(HELD, "ci-failed", 10, NOW - MINUTE))

    assert [run["event"] for run in runs_read(runs, POLLING, HELD).json()["runs"]] == [
        "ci-failed", "review-requested"]


def test_a_failed_run_says_so():
    runs = ledger().ran(HELD, "ci-failed", 10, NOW - MINUTE, exit_code=1)

    [run] = runs_read(runs, POLLING, HELD).json()["runs"]

    assert (run["exit_code"], run["failed"]) == (1, True)


def test_a_run_on_a_pr_the_watcher_no_longer_holds_opens_nothing():
    runs = ledger().ran(CLOSED, "ci-failed", 10, NOW - MINUTE)

    [run] = runs_read(runs, POLLING, HELD).json()["runs"]

    assert (run["number"], run["board_url"]) == (82, None)


def test_a_run_on_no_pr_names_none():
    runs = ledger().ran(None, "ci-failed", 10, NOW - MINUTE)

    [run] = runs_read(runs).json()["runs"]

    assert (run["repo"], run["number"], run["board_url"]) == (None, None, None)


def test_the_runs_of_the_last_seven_days_are_listed_and_older_ones_are_not():
    runs = (ledger().ran(HELD, "old", 10, NOW - timedelta(days=7, minutes=1))
            .ran(HELD, "last-week", 10, NOW - timedelta(days=6, hours=23)))

    assert [run["event"] for run in runs_read(runs).json()["runs"]] == ["last-week"]


def test_today_counts_the_runs_since_local_midnight_and_what_they_cost():
    runs = (ledger().ran(HELD, "yesterday", 10, NOW - timedelta(days=1), cost_usd=5.0)
            .ran(HELD, "ci-failed", 10, NOW - 30 * MINUTE, cost_usd=0.25)
            .ran(HELD, "review-requested", 10, NOW - 20 * MINUTE, cost_usd=0.5)
            .ran(HELD, "manual-continue", 10, NOW - 10 * MINUTE))

    assert runs_read(runs).json()["today"] == {"runs": 3, "cost_usd": 0.75, "unpriced": 1}


def test_a_day_whose_runs_reported_no_cost_has_none():
    runs = ledger().ran(HELD, "ci-failed", 10, NOW - MINUTE)

    assert runs_read(runs).json()["today"] == {"runs": 1, "cost_usd": None, "unpriced": 1}


def test_the_watcher_says_when_it_last_polled_and_when_it_polls_next():
    assert runs_read().json()["watcher"] == {
        "polled_at": "2026-09-28T09:59:41+00:00",
        "next_poll_at": "2026-09-28T10:00:41+00:00", "overdue": False, "last_error": None,
        "fix": None}


def test_a_watcher_that_never_polled_says_no_time():
    never = Health(alive=True, since_last_poll=None, last_error=None, fix=None, polls_every=MINUTE)

    watcher = runs_read(health=never).json()["watcher"]

    assert (watcher["polled_at"], watcher["next_poll_at"]) == (None, None)


def test_the_runs_are_not_modified_while_nothing_changes():
    hub, listening = served_hub(ledger=ledger(), pulse=Pulse(POLLING), clock=lambda: NOW)
    url = hub.start(HUB_PORT, FakeHoldings(), HubState.WATCHING)
    web = TestClient(listening.app, base_url=url)
    first = web.get("/api/runs")

    again = web.get("/api/runs", headers={"If-None-Match": first.headers["ETag"]})

    assert again.status_code == 304


def test_a_failing_watcher_says_why_and_what_to_do_about_it():
    failing = Health(alive=True, since_last_poll=None, last_error="gh auth token failed",
                     fix="Log in with `gh auth login`, then this page retries.",
                     polls_every=MINUTE)

    watcher = runs_read(health=failing).json()["watcher"]

    assert (watcher["last_error"], watcher["fix"]) == (
        "gh auth token failed", "Log in with `gh auth login`, then this page retries.")
