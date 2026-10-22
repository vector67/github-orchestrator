from dataclasses import replace
from pathlib import Path

from github_orchestrator.board_api.fake import IDLE, FakeManagerPanel
from github_orchestrator.domain import Repo
from github_orchestrator.github import PullRequestState, ReviewState
from github_orchestrator.github.fake import Review
from github_orchestrator.settings.fake import RepoEntry, fake_settings
from tests.board_api.support import (
    THE_PR,
    WORKTREE,
    board_on,
    branched_from_main,
    client_of,
    fake_threads,
)
from tests.thread_records.support import disk_thread_records
from tests.watcher.support import watcher_over, watching

COMMITS = "/api/pull-request/commits"
REVIEWED_AT = "2026-01-02T00:00:00Z"


def reviewed_on(sha):
    return FakeManagerPanel(now=replace(IDLE, my_review="commented", my_review_at=REVIEWED_AT,
                                        my_review_sha=sha))


def board_of(copies, panel, records):
    return client_of(board_on(fake_threads(working_copies=copies), base_branch="main",
                              manager=panel, records=records))


def two_commits():
    copies, base, head = branched_from_main()
    tidied = copies.publish("feature", head, {"src/foo.py": "tidied\n"}, "tidy up")
    copies.fetch_pr_branch(Path(WORKTREE), THE_PR, "feature", "main")
    return copies, base, head, tidied


def watched_reviewing(tmp_path, copies, sha):
    settings = fake_settings(tmp_path / "data", repos=(
        RepoEntry(Repo("acme", "widgets"), "/nonexistent/repo"),))
    github = watching(settings)
    github.add_pr(THE_PR, PullRequestState(
        author="alice", head_sha=sha, branch="feature", base_branch="main",
        reviews=(Review(settings.config.gh_account, ReviewState.COMMENTED, REVIEWED_AT, sha),)),
        review_requested=True)
    watcher_over(settings, github=github, working_copies=copies,
                 thread_records=disk_thread_records(tmp_path / "threads")).run_cycle()


def rebased(copies):
    redone = copies.publish("feature", copies.origin["main"], {"src/foo.py": "redone\n"},
                            "check first")
    copies.publish("feature", redone, {"src/foo.py": "new\n"}, "something new")
    copies.fetch_pr_branch(Path(WORKTREE), THE_PR, "feature", "main")


def test_a_review_the_watcher_saw_is_served_once_a_force_push_rewrote_it(tmp_path):
    copies, base, head, tidied = two_commits()
    watched_reviewing(tmp_path, copies, tidied)
    rebased(copies)

    answer = board_of(copies, reviewed_on(tidied),
                      disk_thread_records(tmp_path / "threads")).get(COMMITS).json()

    assert answer["fork"] == copies.origin["main"]
    assert answer["reviewed"] == {
        "sha": tidied,
        "fork": base,
        "commits": [
            {"sha": head, "parents": [base], "subject": "check first",
             "author": "T", "authored_at": "2026-01-01T00:02:00Z"},
            {"sha": tidied, "parents": [head], "subject": "tidy up",
             "author": "T", "authored_at": "2026-01-01T00:04:00Z"},
        ],
    }


def test_a_review_still_among_the_commits_is_not_served_as_rewritten(tmp_path):
    copies, _, _, tidied = two_commits()
    watched_reviewing(tmp_path, copies, tidied)
    copies.publish("feature", tidied, {"src/foo.py": "more\n"}, "more")
    copies.fetch_pr_branch(Path(WORKTREE), THE_PR, "feature", "main")

    answer = board_of(copies, reviewed_on(tidied),
                      disk_thread_records(tmp_path / "threads")).get(COMMITS).json()

    assert [commit["subject"] for commit in answer["commits"]] == [
        "check first", "tidy up", "more"]
    assert answer["reviewed"] is None


def test_reading_the_commits_keeps_nothing_of_a_review(tmp_path):
    copies, _, _, tidied = two_commits()
    records = disk_thread_records(tmp_path / "threads")
    board_of(copies, reviewed_on(tidied), records).get(COMMITS)
    rebased(copies)

    answer = board_of(copies, reviewed_on(tidied), records).get(COMMITS).json()

    assert answer["reviewed"] is None
