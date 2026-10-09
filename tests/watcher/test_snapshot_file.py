from dataclasses import replace

import pytest

from github_orchestrator.domain import Repo
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    ReviewState,
    Thread,
    ThreadComment,
)
from github_orchestrator.github.fake import Check, FakeGitHub, PushEvent, Review
from github_orchestrator.settings.fake import RepoEntry, fake_settings
from tests.builders import a_pr
from tests.conversation.support import at
from tests.disk_layout import thread_dir
from tests.pr_event_queue.support import disk_event_queue, pending_of
from tests.watcher.support import watcher_over

REPO = "acme/widgets"
PR = 42
THE_PR = a_pr(PR, REPO)

def _github(**changes):
    github = FakeGitHub()
    github.add_pr(THE_PR, review_requested=True, state=replace(PullRequestState(
        title="Add widgets", url="https://github.com/acme/widgets/pull/42",
        author="alice", branch="PROJ-1-widgets", base_branch="main", head_sha="sha2",
        body="Detailed reviewer: @octocat", changed_files=3, additions=10, deletions=2,
        mergeable=True, mergeable_state="clean",
        checks=(Check("tests", "completed", "success", "https://ci/tests", "all green"),),
        reviews=(Review("octocat", ReviewState.CHANGES_REQUESTED, "2026-08-31T00:00:00Z", "sha1"),),
        review_decision="CHANGES_REQUESTED", pending_reviewers=("bob",),
        ready_for_review_at="2026-08-30T00:00:00Z",
        push_events=(PushEvent("committed", "2026-08-31T12:00:00Z"),),
    ), **changes))
    github.add_thread(THE_PR, Thread(
        key="PRRT_one", kind=CommentKind.REVIEW, path="src/w.py", line=3,
        comments=(ThreadComment(id=7, author="bob", body="rename",
                                created_at="2026-08-31T01:00:00Z"),),
    ))
    return github


@pytest.fixture
def settings(tmp_path):
    return fake_settings(tmp_path, repos=(RepoEntry(Repo.parse(REPO), str(tmp_path / "clone")),))


def _poll(settings, **changes):
    watcher_over(settings, github=_github(**changes),
                 clock=at("2026-09-01T10:00:05Z")).run_cycle()
    return [event.kind for event in pending_of(disk_event_queue(settings.queues_dir), THE_PR)]


def test_a_poll_writes_the_thread_cursor_beside_the_prs_thread_records(settings):
    _poll(settings)

    written = (thread_dir(settings.threads_dir, THE_PR) / "poll.cursor").read_text()

    assert written.startswith('{"PRRT_one": {"comments": [[7, "')
    assert written.endswith('"]], "is_resolved": false}}')


def test_a_restarted_watcher_raises_nothing_for_a_pr_that_did_not_change(settings):
    trouble = {"mergeable_state": "dirty",
               "checks": (Check("tests", "completed", "failure"),)}

    first = _poll(settings, **trouble)

    assert sorted(first) == ["became-unmergeable", "ci-failed", "review-requested",
                             "thread-activity"]
    assert _poll(settings, **trouble) == first
