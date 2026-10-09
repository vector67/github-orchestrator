import json

from tests.builders import a_pr
from tests.change_detection.support import polled_on_disk, seen, state_file


def test_status_lists_a_healthy_pr_beside_a_state_file_that_will_not_parse(machine, run_cli):
    state_dir = machine.settings().state_dir
    polled_on_disk(state_dir, a_pr(1, "org/aaaa"), seen("octocat"))
    corrupt = state_file(state_dir, a_pr(2, "org/zzzz"))
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("not json")
    machine.answering_hubs.add("http://127.0.0.1:8720")
    machine.settings().watcher_heartbeat.write_text(machine.now.isoformat())

    ran = run_cli("status")

    assert ran.code == 0
    lines = ran.out.splitlines()
    assert "Tracked PRs: 2" in lines
    assert any(line.startswith("  org/aaaa#1  ci=pending") for line in lines)
    assert any(line.startswith("  org/zzzz#2  [corrupt state file: ") for line in lines)


def test_queue_lists_a_good_event_beside_one_that_will_not_parse(machine, run_cli):
    queue_dir = machine.settings().queues_dir / "org" / "repo" / "1"
    queue_dir.mkdir(parents=True)
    (queue_dir / "0000000001-evt.json").write_text("garbage")
    (queue_dir / "0000000002-good.json").write_text(json.dumps(
        {"type": "ci-failed", "payload": {"check": "lint"}}))

    ran = run_cli("queue", "1")

    lines = ran.out.splitlines()
    assert lines[0] == "Queue: org/repo#1"
    assert lines[1].startswith("  [corrupt: ")
    assert lines[1].endswith("]  queued 1970-01-01T00:00:00+00:00")
    assert lines[2] == "  [ci-failed]  queued 1970-01-01T00:00:00+00:00"
