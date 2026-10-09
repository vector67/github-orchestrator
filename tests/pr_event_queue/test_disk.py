import json
import os
import shutil
import threading
import time
from pathlib import Path
from unittest import mock

import pytest

from github_orchestrator.domain import Repo
from tests.builders import a_pr
from tests.pr_event_queue.support import (
    EPOCH,
    ci_failed,
    ci_succeeded,
    closed,
    disk_event_queue,
    kinds,
    mergeable,
    pending_of,
    queue_of,
)

REPO = "acme/widgets"


@pytest.fixture
def queues(tmp_path):
    return tmp_path / "queues"


@pytest.fixture
def event_queue(queues):
    return disk_event_queue(queues)


THE_PR = a_pr(23, REPO)


def _queue_dir(queues, pr=THE_PR):
    return queues / pr.repo.owner / pr.repo.name / str(pr.number)


def _take(event_queue, pr=THE_PR):
    return event_queue.next(pr, is_author=True, agents_enabled=True)


def _write_event(directory, name, event_type, payload=None, pr=THE_PR):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(
        {"type": event_type, "repo": str(pr.repo), "pr": pr.number, "payload": payload or {}}))


def test_an_added_event_is_one_file_named_for_its_kind_in_the_prs_queue_directory(
        queues, event_queue):
    event_queue.add(THE_PR, ci_failed("tests"))

    [written] = list(_queue_dir(queues).iterdir())
    stamp, pid, counter, rest = written.name.split("-", 3)
    assert (stamp.isdigit(), pid, counter.isdigit(), rest) == (
        True, str(os.getpid()), True, "ci-failed.json")


def test_an_event_says_it_was_queued_at_the_time_its_file_was_written(queues, event_queue):
    _write_event(_queue_dir(queues), "1788766390585798000-25796-9-ci-failed.json", "ci-failed",
                 {"check": "lint"})

    [entry] = queue_of(event_queue, THE_PR).entries

    assert entry.queued_at.isoformat() == "2026-09-07T07:33:10.585798+00:00"


def test_events_queued_before_a_restart_are_taken_in_the_order_of_their_names(queues, event_queue):
    directory = _queue_dir(queues)
    _write_event(directory, "2000-1-0-became-mergeable.json", "became-mergeable",
                 {"reason": "approved"})
    _write_event(directory, "1000-1-0-ci-succeeded.json", "ci-succeeded", {"checks": []})

    assert [_take(event_queue).response.event.kind for _ in range(2)] == [
        "ci-succeeded", "became-mergeable"]


def test_a_taken_event_is_renamed_in_flight_and_removed_when_done(queues, event_queue):
    event_queue.add(THE_PR, ci_failed())

    taken = _take(event_queue)
    [in_flight] = list(_queue_dir(queues).iterdir())
    assert in_flight.suffix == ".processing"

    taken.done()
    assert list(_queue_dir(queues).iterdir()) == []


def test_a_failed_event_is_kept_under_the_time_it_failed(queues, event_queue):
    event_queue.add(THE_PR, ci_failed())
    before = time.time_ns()

    _take(event_queue).failed()

    [failed] = list(_queue_dir(queues).iterdir())
    stamp = failed.suffix.removeprefix(".failed-")
    assert int(stamp) >= before


def test_a_closed_pr_leaves_the_tombstone_the_watcher_reaps_on(queues, event_queue):
    event_queue.add(THE_PR, closed())

    _take(event_queue).done()

    assert [p.name for p in _queue_dir(queues).iterdir()] == ["pr-closed.done"]


def test_an_event_left_in_flight_by_a_dead_manager_goes_back_to_the_front(queues, event_queue):
    directory = _queue_dir(queues)
    _write_event(directory, "1000-1-0-ci-failed.json", "ci-failed", {"check": "lint"})
    _take(event_queue)
    _write_event(directory, "2000-1-0-became-mergeable.json", "became-mergeable",
                 {"reason": "approved"})

    event_queue.recover(THE_PR)

    assert sorted(p.name for p in directory.iterdir()) == [
        "1000-1-0-ci-failed.json", "2000-1-0-became-mergeable.json"]
    assert kinds(pending_of(event_queue, THE_PR)) == ["ci-failed", "became-mergeable"]


def test_two_events_added_in_the_same_nanosecond_both_survive(event_queue):
    with mock.patch("github_orchestrator.pr_event_queue._disk.time.time_ns",
                    return_value=1_700_000_000_000_000_000):
        event_queue.add(a_pr(1, "org/repo"), ci_failed("one"))
        event_queue.add(a_pr(1, "org/repo"), ci_failed("two"))

    assert len(pending_of(event_queue, a_pr(1, "org/repo"))) == 2


def test_events_added_from_many_threads_are_all_kept(event_queue):
    errors = []

    def worker(seq):
        try:
            event_queue.add(a_pr(1, "org/repo"), ci_failed(f"check-{seq}"))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(pending_of(event_queue, a_pr(1, "org/repo"))) == 50


def test_two_managers_taking_at_once_get_the_event_at_most_once(event_queue):
    event_queue.add(a_pr(1, "org/repo"), mergeable())
    results = []
    barrier = threading.Barrier(2)

    def worker():
        barrier.wait()
        try:
            results.append(event_queue.next(a_pr(1, "org/repo"), is_author=True,
                                            agents_enabled=True))
        except FileNotFoundError:
            results.append(None)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len([r for r in results if r is not None]) <= 1


def test_a_disk_full_while_writing_lands_no_event(queues, event_queue):
    with mock.patch.object(Path, "write_text", side_effect=OSError("No space left on device")):
        with pytest.raises(OSError):
            event_queue.add(a_pr(1, "org/repo"), ci_failed())

    assert list(_queue_dir(queues, a_pr(1, "org/repo")).iterdir()) == []


def test_a_disk_full_while_renaming_leaves_no_temporary_file(queues, event_queue):
    def fail_rename(self, target):
        raise OSError("No space left on device")

    with mock.patch.object(Path, "rename", fail_rename):
        with pytest.raises(OSError):
            event_queue.add(a_pr(1, "org/repo"), ci_failed())

    assert list(_queue_dir(queues, a_pr(1, "org/repo")).iterdir()) == []


def test_an_unreadable_event_is_skipped_named_and_then_dropped(queues, event_queue):
    directory = _queue_dir(queues)
    directory.mkdir(parents=True)
    (directory / "0000000001-bad.json").write_text("this is not json {{{{")
    event_queue.add(THE_PR, ci_failed())

    assert kinds(pending_of(event_queue, THE_PR)) == ["ci-failed"]
    [bad, good] = queue_of(event_queue, THE_PR).pending
    assert (bad.event, bad.problem is not None) == (None, True)
    assert good.event == ci_failed()

    assert _take(event_queue).response.event.kind == "ci-failed"
    assert not (directory / "0000000001-bad.json").exists()


def test_an_event_of_a_kind_nobody_raises_is_unreadable_and_dropped(queues, event_queue):
    _write_event(_queue_dir(queues), "0000000001-1-0-new-comments.json", "new-comments")

    [unknown] = queue_of(event_queue, THE_PR).pending

    assert (unknown.event, unknown.problem is not None) == (None, True)
    assert _take(event_queue) is None
    assert list(_queue_dir(queues).iterdir()) == []


def test_files_that_are_not_events_are_ignored(queues, event_queue):
    directory = _queue_dir(queues)
    directory.mkdir(parents=True)
    (directory / "notes.txt").write_text("some stray file")
    (directory / "README.md").write_text("# ignore me")
    (directory / "0000000001-fake.json").mkdir()
    event_queue.add(THE_PR, ci_failed())

    assert len(pending_of(event_queue, THE_PR)) == 1
    assert _take(event_queue).response.event.kind == "ci-failed"


def test_an_unreadable_failure_is_listed_without_its_event(queues, event_queue):
    event_queue.add(a_pr(40, "acme/app"), ci_failed())
    _take(event_queue, a_pr(40, "acme/app")).failed()
    [failed] = list(_queue_dir(queues, a_pr(40, "acme/app")).iterdir())
    failed.write_text("{not json")

    assert [(f.pr.number, f.event) for f in event_queue.failed_since(EPOCH)] == [(40, None)]


def test_a_directory_that_is_not_a_prs_queue_is_not_listed(queues, event_queue):
    _write_event(queues / "acme" / "app" / "not-a-number", "1-ci-failed.json", "ci-failed",
                 {"check": "lint"})
    event_queue.add(THE_PR, ci_failed())

    assert [q.pr for q in event_queue.queues()] == [THE_PR]


def test_queues_are_listed_in_the_order_of_their_directories(event_queue):
    event_queue.add(a_pr(10, REPO), ci_failed())
    event_queue.add(a_pr(9, REPO), ci_failed())

    assert [q.pr.number for q in event_queue.queues()] == [10, 9]


def test_a_queue_that_cannot_be_removed_is_reported(queues, event_queue):
    event_queue.add(THE_PR, ci_failed())
    parent = _queue_dir(queues).parent
    parent.chmod(0o555)
    try:
        assert event_queue.forget(THE_PR) is False
    finally:
        parent.chmod(0o755)


def test_a_queue_whose_directory_was_removed_is_empty_and_comes_back_on_add(queues, event_queue):
    event_queue.add(a_pr(1, "org/repo"), ci_failed())
    taken = _take(event_queue, a_pr(1, "org/repo"))
    shutil.rmtree(queues)

    assert pending_of(event_queue, a_pr(1, "org/repo")) == []
    assert _take(event_queue, a_pr(1, "org/repo")) is None
    taken.done()

    event_queue.add(a_pr(1, "org/repo"), mergeable())
    assert kinds(pending_of(event_queue, a_pr(1, "org/repo"))) == ["became-mergeable"]


def test_repos_whose_names_differ_only_by_slash_and_dash_do_not_share_a_queue(event_queue):
    event_queue.add(a_pr(1, "org/my-repo"), ci_failed("slash"))
    event_queue.add(a_pr(1, "org-my/repo"), ci_failed("dash"))

    assert pending_of(event_queue, a_pr(1, "org/my-repo")) == [ci_failed("slash")]
    assert pending_of(event_queue, a_pr(1, "org-my/repo")) == [ci_failed("dash")]


def test_an_archived_queue_keeps_its_events_where_it_was_moved(event_queue, queues, tmp_path):
    event_queue.add(a_pr(2, "acme/other"), ci_succeeded("lint"))
    into = tmp_path / "archive" / "queues"

    [archived] = event_queue.archive_other_repos({Repo.parse(REPO)}, into)

    assert not (queues / "acme" / "other").exists()
    assert [event.name.endswith("ci-succeeded.json")
            for event in (archived / "2").glob("*.json")] == [True]


def test_archiving_leaves_files_that_are_not_a_repos_queues(event_queue, queues, tmp_path):
    queues.mkdir()
    (queues / "stray.txt").write_text("x")
    (queues / "acme").mkdir()
    (queues / "acme" / "notes.txt").write_text("x")

    assert event_queue.archive_other_repos({Repo.parse(REPO)}, tmp_path / "archive" / "queues") == []
    assert (queues / "stray.txt").exists()
    assert (queues / "acme" / "notes.txt").exists()


def test_archiving_an_event_queue_nobody_wrote_to_moves_nothing(event_queue, tmp_path):
    assert event_queue.archive_other_repos({Repo.parse(REPO)}, tmp_path / "archive" / "queues") == []


def test_an_unreadable_event_is_not_counted_as_waiting_nor_hides_what_is_next(queues, event_queue):
    directory = _queue_dir(queues)
    directory.mkdir(parents=True)
    (directory / "0001-x-ci-failed.json").write_text("{not json")
    _write_event(directory, "0002-y-pr-closed.json", "pr-closed", {"merged": True})

    waiting = event_queue.waiting(THE_PR)

    assert (waiting.count, waiting.closing) == (1, True)
