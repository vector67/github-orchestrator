from datetime import timedelta

from tests.builders import a_pr

THE_PR = a_pr(7, "o/n")


def _ran(machine, seconds, when, event="ci-failed", pr=THE_PR, cost=None):
    machine.runs().ran(pr, event, seconds, when, cost_usd=cost)


def test_reports_todays_count_total_and_longest(machine, run_cli):
    midday = machine.now
    _ran(machine, 60, midday - timedelta(hours=1))
    _ran(machine, 120, midday - timedelta(minutes=30), event="new-comments",
         pr=a_pr(9, "o/n"))
    _ran(machine, 30, midday)
    _ran(machine, 9999, midday - timedelta(days=1))
    out = run_cli("runs").out
    assert out.splitlines()[0] == "Runs today (2026-09-24): 3 runs, 3m30s total"
    assert "  longest: new-comments on o/n#9 — 2m00s" in out.splitlines()


def test_a_longest_run_on_no_known_pr_is_on_an_unknown_pr(machine, run_cli):
    _ran(machine, 120, machine.now, event="new-comments", pr=None)
    assert "  longest: new-comments on ? — 2m00s" in run_cli("runs").out.splitlines()


def test_a_run_ending_just_before_local_midnight_counts_for_that_day(machine, run_cli):
    machine.now = machine.now.replace(hour=0, minute=30)
    _ran(machine, 60, machine.now - timedelta(hours=1))
    _ran(machine, 90, machine.now)
    assert run_cli("runs").out.startswith("Runs today (2026-09-24): 1 runs, 1m30s total")


def test_an_hour_long_run_is_shown_in_hours_and_minutes(machine, run_cli):
    _ran(machine, 3 * 3600 + 5 * 60, machine.now)
    assert "3h05m total" in run_cli("runs").out


def test_no_runs_today_reports_none(machine, run_cli):
    ran = run_cli("runs")
    assert ran.code == 0
    assert "0 runs" in ran.out


def test_the_total_is_not_presented_as_money_out_of_pocket(machine, run_cli):
    _ran(machine, 60, machine.now, cost=0.4)
    _ran(machine, 30, machine.now, cost=1.25)
    out = run_cli("runs").out
    assert "~$1.65 API-equivalent" in out
    assert "subscription" in out


def test_a_run_that_reported_no_cost_is_named_rather_than_counted_as_free(machine, run_cli):
    _ran(machine, 60, machine.now, cost=0.4)
    _ran(machine, 30, machine.now)
    out = run_cli("runs").out
    assert "$0.40" in out
    assert "1 run ended without reporting a cost" in out


def test_runs_with_no_costs_at_all_say_nothing_about_money(machine, run_cli):
    _ran(machine, 60, machine.now)
    assert "$" not in run_cli("runs").out


def test_runs_with_nothing_from_today_report_none(machine, run_cli):
    _ran(machine, 60, machine.now - timedelta(days=2))
    ran = run_cli("runs")
    assert ran.code == 0
    assert "0 runs" in ran.out
