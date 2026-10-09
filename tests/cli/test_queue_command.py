from tests.builders import a_pr
from tests.pr_event_queue.support import ci_failed, disk_event_queue, mergeable

REPO = "acme/widgets"


def test_the_queue_command_lists_what_is_in_flight_before_what_is_pending(status_dirs, run_cli, settings):
    disk_event_queue(settings.queues_dir).add(a_pr(86, REPO), ci_failed())
    disk_event_queue(settings.queues_dir).add(a_pr(86, REPO), mergeable())
    disk_event_queue(settings.queues_dir).next(a_pr(86, REPO), is_author=True, agents_enabled=True)
    lines = run_cli("queue", "86").out.splitlines()
    assert lines[:2] == [f"Queue: {REPO}#86", "  [PROCESSING] ci-failed"]
    assert lines[2].startswith("  [became-mergeable]  ")
    assert len(lines) == 3


def test_the_queue_command_says_a_drained_queue_is_empty(status_dirs, run_cli, settings):
    disk_event_queue(settings.queues_dir).add(a_pr(86, REPO), ci_failed())
    disk_event_queue(settings.queues_dir).next(a_pr(86, REPO), is_author=True, agents_enabled=True).done()
    assert run_cli("queue", "86").out.splitlines() == [f"Queue: {REPO}#86", "  (empty)"]


def test_the_queue_command_says_when_no_pr_has_that_number(status_dirs, run_cli):
    assert run_cli("queue", "86").out == "No queue found for a PR numbered 86\n"
