import json
import os
import threading

import pytest

from github_orchestrator.change_detection import Poll
from github_orchestrator.change_detection.fake import Stored
from github_orchestrator.github import PullRequestState, ReviewState
from github_orchestrator.github.fake import Check, PushEvent, Review
from tests.builders import a_pr
from tests.change_detection.support import (
    PR,
    REPO,
    disk_change_detection,
    poll,
    state_file,
)

THE_PR = a_pr(PR, REPO)


EXPECTED = (
    '{"repo": "acme/widgets", "pr": 42, "title": "Add widgets", '
    '"url": "https://github.com/acme/widgets/pull/42", "branch": "PROJ-1-widgets", '
    '"base_branch": "main", "pr_author": "alice", "changed_files": 3, '
    '"additions": 10, "deletions": 2, "head_sha": "sha2", "mergeable": true, '
    '"mergeable_state": "clean", "draft": false, '
    '"last_poll_timestamp": "2026-09-01T10:00:00Z", "ci_status": "passing", '
    '"review_ready_at": "2026-08-30T00:00:00Z", '
    '"checks": [{"name": "tests", "passed": true, "failed": false, "done": true, '
    '"html_url": "https://ci/tests", "summary": "all green"}], '
    '"review_decision": "changes-requested", "latest_reviewer": "octocat", '
    '"reviewer_status": {"octocat": "changes-requested"}, "pending_reviewers": ["bob"], '
    '"review_requested": true, "unresolved_thread_count": 1, "is_author": false, '
    '"review_anchor_at": "2026-08-31T00:00:00Z", "review_anchor_sha": "sha1", '
    '"since_anchor_commits": 1, "since_anchor_force_push": false, '
    '"since_anchor_comments": 0, "since_anchor_reviews": 0, "since_anchor_resolved": 0, '
    '"detailed_reviewer": "octocat", "is_detailed_reviewer": true, '
    '"my_review_at": "2026-08-31T00:00:00Z", "mentions": [], "mentioned": false, '
    '"ci_failure_handled": {}}'
)



def test_a_poll_writes_the_snapshot_file_every_other_process_reads(tmp_path):
    pr = a_pr(42, REPO)
    disk_change_detection(tmp_path).advance(pr, Poll(PullRequestState(
        title="Add widgets", url="https://github.com/acme/widgets/pull/42",
        author="alice", branch="PROJ-1-widgets", base_branch="main", head_sha="sha2",
        body="Detailed reviewer: @octocat", changed_files=3, additions=10, deletions=2,
        mergeable=True, mergeable_state="clean",
        checks=(Check("tests", "completed", "success", "https://ci/tests", "all green"),),
        reviews=(Review("octocat", ReviewState.CHANGES_REQUESTED, "2026-08-31T00:00:00Z", "sha1"),),
        review_decision="CHANGES_REQUESTED", pending_reviewers=("bob",),
        ready_for_review_at="2026-08-30T00:00:00Z",
        push_events=(PushEvent("committed", "2026-08-31T12:00:00Z"),),
    ), "2026-09-01T10:00:00Z", unresolved_thread_count=1, review_requested=True), set())

    assert state_file(tmp_path, pr).read_text() == EXPECTED


def _corrupt(state_dir, text, repo=REPO, pr=PR):
    path = state_file(state_dir, a_pr(pr, repo))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_a_restarted_process_reads_the_snapshot_the_last_one_saved(tmp_path):
    disk_change_detection(tmp_path).advance(THE_PR, poll(), set())

    restarted = disk_change_detection(tmp_path)

    assert restarted.facts(THE_PR).branch == "PROJ-7-widgets"
    assert restarted.advance(THE_PR, poll(), set()) == []


def test_a_snapshot_is_saved_under_its_owner_name_and_pr(tmp_path):
    disk_change_detection(tmp_path).advance(a_pr(55, "acme/widgets"), poll(), set())

    assert (tmp_path / "acme" / "widgets" / "55.json").is_file()


def test_a_saved_snapshot_is_tracked_under_the_repo_it_was_saved_for(tmp_path):
    disk_change_detection(tmp_path).advance(a_pr(1, "the_eco_lab/calc"), poll(), set())

    assert disk_change_detection(tmp_path).tracked() == [a_pr(1, "the_eco_lab/calc")]


def test_files_that_name_no_pr_are_not_tracked(tmp_path):
    (tmp_path / "owner" / "name").mkdir(parents=True)
    (tmp_path / "just-a-file.json").write_text("{}")
    (tmp_path / "owner" / "name" / "abc.json").write_text("{}")
    (tmp_path / "owner" / "name" / "3.flag").write_text("")

    assert disk_change_detection(tmp_path).tracked() == []


def test_nothing_is_tracked_before_anything_is_saved(tmp_path):
    assert disk_change_detection(tmp_path / "never-created").tracked() == []


def test_a_corrupt_snapshot_reads_as_a_pr_never_polled(tmp_path):
    _corrupt(tmp_path, "{not valid json")

    detection = disk_change_detection(tmp_path)

    assert detection.facts(THE_PR) is None
    assert detection.tracked() == [(THE_PR)]


def test_a_corrupt_snapshot_is_listed_with_what_is_wrong_with_it(tmp_path):
    _corrupt(tmp_path, "[1, 2]")

    assert disk_change_detection(tmp_path).stored() == [
        Stored(THE_PR, None, "expected an object, found list")]


def test_a_poll_after_a_corrupt_snapshot_starts_it_afresh(tmp_path):
    _corrupt(tmp_path, "{not valid json")
    detection = disk_change_detection(tmp_path)

    detection.advance(THE_PR, poll(), set())

    assert json.loads(state_file(tmp_path, THE_PR).read_text())["repo"] == REPO


def test_a_snapshot_that_cannot_be_removed_is_not_forgotten(tmp_path):
    detection = disk_change_detection(tmp_path)
    detection.advance(THE_PR, poll(), set())
    folder = state_file(tmp_path, THE_PR).parent
    folder.chmod(0o500)
    try:
        forgotten = detection.forget(THE_PR)
    finally:
        folder.chmod(0o700)

    assert forgotten is False
    assert detection.facts(THE_PR) is not None


def test_a_save_that_fails_leaves_the_last_snapshot_and_no_temporary_file(tmp_path, monkeypatch):
    detection = disk_change_detection(tmp_path)
    detection.advance(THE_PR, poll(), set())
    before = state_file(tmp_path, THE_PR).read_text()

    def disk_full(fd):
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", disk_full)
    with pytest.raises(OSError):
        detection.advance(THE_PR, poll(at="2026-09-23T11:05:00Z"), set())

    assert state_file(tmp_path, THE_PR).read_text() == before
    assert list(tmp_path.rglob("*.tmp")) == []


def test_a_reader_never_sees_a_half_written_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "fsync", lambda fd: None)
    detection = disk_change_detection(tmp_path)
    detection.advance(THE_PR, poll(), set())
    path = state_file(tmp_path, THE_PR)
    done = threading.Event()
    decode_errors: list[BaseException] = []

    def writer():
        try:
            for _ in range(25):
                detection.advance(THE_PR, poll(), set())
        finally:
            done.set()

    def reader():
        while not done.is_set():
            try:
                json.loads(path.read_text())
            except json.JSONDecodeError as e:
                decode_errors.append(e)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader),
               threading.Thread(target=reader)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert decode_errors == []
