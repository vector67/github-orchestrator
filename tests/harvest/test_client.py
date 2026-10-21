import subprocess
from collections.abc import Callable
from datetime import datetime

from github_orchestrator.harvest import Timesheet
from github_orchestrator.wiring import HarvestWiring, wire
from tests.conftest import clocks_of
from tests.harvest.scripted_harvest import ACCOUNT, ME, TOKEN, Entry, ScriptedHarvest

WIDGETS = (111, 222)
GADGETS = (333, 444)
TODAY = datetime.fromisoformat("2026-10-21T09:00:00+02:00")


def timesheet(harvest: ScriptedHarvest, token: Callable[[], str] = lambda: TOKEN) -> Timesheet:
    timesheet: Timesheet = wire(HarvestWiring(ACCOUNT, {}, token, harvest),
                                clocks_of(local=lambda: TODAY)).get(Timesheet)
    return timesheet


def test_a_project_is_running_while_my_timer_runs_on_its_task():
    harvest = ScriptedHarvest([Entry(1, ME, *WIDGETS, "2026-10-21")])

    assert timesheet(harvest).running(*WIDGETS) is True
    assert timesheet(harvest).running(*GADGETS) is False


def test_someone_else_s_timer_on_the_project_is_not_mine():
    harvest = ScriptedHarvest([Entry(1, ME + 1, *WIDGETS, "2026-10-21")])

    assert timesheet(harvest).running(*WIDGETS) is False


def test_starting_runs_a_timer_on_the_project_s_task_today_in_place_of_the_one_running():
    harvest = ScriptedHarvest([Entry(1, ME, *GADGETS, "2026-10-21")])

    assert timesheet(harvest).start(*WIDGETS) is None

    assert harvest.running() == [WIDGETS]
    assert harvest.entries[-1].spent_date == "2026-10-21"


def test_stopping_stops_the_project_s_timer():
    harvest = ScriptedHarvest([Entry(1, ME, *WIDGETS, "2026-10-21")])

    assert timesheet(harvest).stop(*WIDGETS) is None

    assert harvest.running() == []


def test_stopping_leaves_another_project_s_timer_running():
    harvest = ScriptedHarvest([Entry(1, ME, *GADGETS, "2026-10-21")])

    assert timesheet(harvest).stop(*WIDGETS) is None

    assert harvest.running() == [GADGETS]


def test_harvest_refusing_is_said_and_never_read_as_a_timer_stopped():
    harvest = ScriptedHarvest(refusing=401)

    assert timesheet(harvest).running(*WIDGETS) is None
    assert "401" in (timesheet(harvest).start(*WIDGETS) or "")
    assert "401" in (timesheet(harvest).stop(*WIDGETS) or "")


def test_no_token_in_the_keychain_is_said_and_asks_harvest_nothing():
    harvest = ScriptedHarvest()

    def no_token() -> str:
        raise subprocess.CalledProcessError(44, ["security"])

    said = timesheet(harvest, no_token).start(*WIDGETS)

    assert "harvest-api" in (said or "")
    assert harvest.sent == []
