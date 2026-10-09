import pytest

from tests.builders import a_pr
from tests.change_detection.support import (
    disk_change_detection,
    failing,
    polled_on_disk,
    seen,
)
from tests.disk_layout import dismissed_file
from tests.pr_event_queue.support import ci_failed, disk_event_queue, mergeable
from tests.settings.support import disk_dismissals, disk_holds

REPO = "acme/widgets"


def track(settings, pr, **fields):
    polled_on_disk(settings.state_dir, a_pr(pr, REPO), seen(
        settings.config.gh_account, **{"checks": (failing(),), "mergeable": True, **fields}))


def pr_line(out, pr):
    return next(line for line in out.splitlines() if f"#{pr}" in line)


def queue_line(out):
    return next(line for line in out.splitlines() if line.startswith("  Queue "))


def test_a_pr_on_hold_says_so_on_its_own_line(status_dirs, run_cli, settings):
    track(settings, 86)
    disk_holds(settings.data_dir).set_on_hold(a_pr(86, REPO), True)
    status = run_cli("status")
    assert pr_line(status.out, 86).endswith("[ON HOLD]")


def test_a_dismissed_pr_names_the_mode_it_was_dismissed_with(status_dirs, run_cli, settings):
    track(settings, 67)
    track(settings, 68)
    disk_dismissals(settings.data_dir).dismiss_until_next_event(a_pr(67, REPO))
    disk_dismissals(settings.data_dir).dismiss_forever(a_pr(68, REPO))
    status = run_cli("status")
    out = status.out
    assert pr_line(out, 67).endswith("[DISMISSED until-event]")
    assert pr_line(out, 68).endswith("[DISMISSED forever]")


def test_a_pr_that_is_neither_carries_no_marker(status_dirs, run_cli, settings):
    track(settings, 82, review_decision="APPROVED")
    status = run_cli("status")
    line = pr_line(status.out, 82)
    assert line == f"  {REPO}#82  ci=failing  mergeable=True  review=approved"


def test_a_dismissed_pr_with_no_state_file_is_still_listed(status_dirs, run_cli, settings):
    disk_dismissals(settings.data_dir).dismiss_forever(a_pr(67, REPO))
    status = run_cli("status")
    out = status.out
    assert "[DISMISSED forever]" in pr_line(out, 67)


def test_a_tracked_pr_is_never_listed_twice_by_its_flag(status_dirs, run_cli, settings):
    track(settings, 86)
    disk_holds(settings.data_dir).set_on_hold(a_pr(86, REPO), True)
    status = run_cli("status")
    out = status.out
    assert len([line for line in out.splitlines() if "#86" in line]) == 1


def test_a_flag_whose_contents_are_not_a_valid_mode_is_not_a_dismissal(status_dirs, run_cli, settings):
    flag = dismissed_file(settings.dismissed_dir, a_pr(67, REPO))
    flag.parent.mkdir(parents=True)
    flag.write_text("sort-of-dismissed")
    status = run_cli("status")
    out = status.out
    assert "67" not in out
    assert "On hold or dismissed" not in out


def test_a_pr_that_is_both_on_hold_and_dismissed_reports_both(status_dirs, run_cli, settings):
    track(settings, 86)
    disk_holds(settings.data_dir).set_on_hold(a_pr(86, REPO), True)
    disk_dismissals(settings.data_dir).dismiss_forever(a_pr(86, REPO))
    status = run_cli("status")
    assert pr_line(status.out, 86).endswith("[ON HOLD]  [DISMISSED forever]")


def test_the_untracked_block_is_absent_when_nothing_is_flagged(status_dirs, run_cli, settings):
    track(settings, 82)
    status = run_cli("status")
    assert "On hold or dismissed" not in status.out


def test_the_untracked_block_is_set_apart_from_the_blocks_around_it(status_dirs, run_cli, settings):
    track(settings, 82)
    disk_event_queue(settings.queues_dir).add(a_pr(82, REPO), ci_failed())
    disk_dismissals(settings.data_dir).dismiss_forever(a_pr(67, REPO))
    status = run_cli("status")
    lines = status.out.splitlines()
    header = next(i for i, line in enumerate(lines) if "On hold or dismissed" in line)
    assert lines[header - 1] == ""
    assert lines[header + 1] == f"    {REPO}#67  [DISMISSED forever]"
    assert lines[header + 2] == ""
    assert lines[header + 3].startswith("  Queue ")


def test_an_unflagged_report_keeps_the_queue_block_where_it_was(status_dirs, run_cli, settings):
    track(settings, 82)
    disk_event_queue(settings.queues_dir).add(a_pr(82, REPO), ci_failed())
    status = run_cli("status")
    lines = status.out.splitlines()
    queue = next(i for i, line in enumerate(lines) if line.startswith("  Queue "))
    assert lines[queue - 1].startswith(f"  {REPO}#82  ci=")


def test_a_state_file_missing_its_own_fields_is_identified_by_its_path(status_dirs, run_cli, settings):
    disk_change_detection(settings.state_dir).close(a_pr(86, REPO))
    disk_holds(settings.data_dir).set_on_hold(a_pr(86, REPO), True)
    status = run_cli("status")
    line = pr_line(status.out, 86)
    assert line.startswith(f"  {REPO}#86  ")
    assert line.endswith("[ON HOLD]")


def _unreadable_bytes(flag):
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_bytes(b"\xff\xfe forever")


@pytest.mark.parametrize("sabotage", [_unreadable_bytes])
def test_a_dismissed_flag_status_cannot_read_never_stops_the_report(
    status_dirs, run_cli, sabotage, settings,
):
    track(settings, 86)
    flag = dismissed_file(settings.dismissed_dir, a_pr(86, REPO))
    sabotage(flag)
    try:
        status = run_cli("status")
    finally:
        if flag.is_file():
            flag.chmod(0o600)
    out = status.out
    assert out.splitlines()[2].startswith("Watcher:")
    assert "[DISMISSED" not in pr_line(out, 86)


def test_pending_events_on_a_pr_on_hold_say_nothing_will_run(status_dirs, run_cli, settings):
    track(settings, 86)
    disk_holds(settings.data_dir).set_on_hold(a_pr(86, REPO), True)
    for _ in range(6):
        disk_event_queue(settings.queues_dir).add(a_pr(86, REPO), mergeable())
    status = run_cli("status")
    line = queue_line(status.out)
    assert "6 pending" in line
    assert line.endswith("(on hold - nothing will run)")


def test_pending_events_on_a_pr_dismissed_forever_say_nothing_will_run(status_dirs, run_cli, settings):
    track(settings, 67)
    disk_dismissals(settings.data_dir).dismiss_forever(a_pr(67, REPO))
    disk_event_queue(settings.queues_dir).add(a_pr(67, REPO), mergeable())
    status = run_cli("status")
    assert queue_line(status.out).endswith("(dismissed - nothing will run)")


def test_pending_events_on_a_pr_dismissed_until_event_still_drain(status_dirs, run_cli, settings):
    track(settings, 68)
    disk_dismissals(settings.data_dir).dismiss_until_next_event(a_pr(68, REPO))
    disk_event_queue(settings.queues_dir).add(a_pr(68, REPO), mergeable())
    status = run_cli("status")
    assert queue_line(status.out) == f"  Queue {REPO}#68: 1 pending, 0 processing"


def test_pending_events_on_a_running_pr_keep_the_plain_queue_line(status_dirs, run_cli, settings):
    track(settings, 86)
    disk_event_queue(settings.queues_dir).add(a_pr(86, REPO), mergeable())
    status = run_cli("status")
    out = status.out
    assert queue_line(out) == f"  Queue {REPO}#86: 1 pending, 0 processing"


def test_an_event_in_flight_counts_as_processing(status_dirs, run_cli, settings):
    track(settings, 86)
    disk_event_queue(settings.queues_dir).add(a_pr(86, REPO), ci_failed())
    disk_event_queue(settings.queues_dir).add(a_pr(86, REPO), mergeable())
    disk_event_queue(settings.queues_dir).next(a_pr(86, REPO), is_author=True, agents_enabled=True)
    status = run_cli("status")
    assert queue_line(status.out) == f"  Queue {REPO}#86: 1 pending, 1 processing"
