from dataclasses import replace
from pathlib import Path

from github_orchestrator.board_api.fake import IDLE, FakeManagerPanel
from tests.board_api.support import (
    MOMENT,
    THE_PR,
    WORKTREE,
    board_on,
    branched_from_main,
    client_of,
    fake_threads,
)
from tests.thread_records.support import disk_thread_records

COMMITS = "/api/pull-request/commits"


def reviewed_on(sha):
    return FakeManagerPanel(now=replace(IDLE, my_review="approved",
                                        my_review_at="2026-01-02T00:00:00Z",
                                        my_review_sha=sha))


def board_of(copies, panel, records):
    return client_of(board_on(fake_threads(working_copies=copies), base_branch="main",
                              manager=panel, records=records))


def two_commits_reviewed(tmp_path):
    copies, base, head = branched_from_main()
    tidied = copies.publish("feature", head, {"src/foo.py": "tidied\n"}, "tidy up")
    copies.fetch_pr_branch(Path(WORKTREE), THE_PR, "feature", "main")
    board = board_of(copies, reviewed_on(tidied), disk_thread_records(tmp_path))
    return copies, base, head, tidied, board


def test_a_review_on_one_of_the_commits_is_not_served_as_rewritten(tmp_path):
    copies, _, _, _, board = two_commits_reviewed(tmp_path)
    copies.publish("feature", copies.origin["feature"], {"src/foo.py": "more\n"}, "more")
    copies.fetch_pr_branch(Path(WORKTREE), THE_PR, "feature", "main")

    answer = board.get(COMMITS).json()

    assert [commit["subject"] for commit in answer["commits"]] == [
        "check first", "tidy up", "more"]
    assert answer["reviewed"] is None


def test_once_the_branch_is_rewritten_what_the_review_saw_is_served_beside_the_commits(tmp_path):
    copies, base, head, tidied, board = two_commits_reviewed(tmp_path)
    board.get(COMMITS)
    main = copies.origin["main"]
    redone = copies.publish("feature", main, {"src/foo.py": "redone\n"}, "check first")
    copies.publish("feature", redone, {"src/foo.py": "new\n"}, "something new")
    copies.fetch_pr_branch(Path(WORKTREE), THE_PR, "feature", "main")

    answer = board_of(copies, reviewed_on(tidied), disk_thread_records(tmp_path)).get(
        COMMITS).json()

    assert answer["fork"] == main
    assert answer["reviewed"] == {
        "sha": tidied,
        "fork": base,
        "commits": [
            {"sha": head, "parents": [base], "subject": "check first",
             "author": "T", "authored_at": "2026-01-01T00:02:00Z"},
            {"sha": tidied, "parents": [head], "subject": "tidy up",
             "author": "T", "authored_at": "2026-01-01T00:04:00Z"},
        ],
        "rewritten_at": MOMENT,
    }


def test_a_review_the_board_never_saw_among_the_commits_has_nothing_to_serve(tmp_path):
    copies, _, _ = branched_from_main()
    board = board_of(copies, reviewed_on("0" * 40), disk_thread_records(tmp_path))

    assert board.get(COMMITS).json()["reviewed"] is None
