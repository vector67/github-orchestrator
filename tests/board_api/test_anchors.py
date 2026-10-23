from pathlib import Path

from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.board_api.support import (
    THE_PR,
    WORKTREE,
    board_on,
    client_of,
    fake_threads,
)


def pull_request(first, *commits):
    copies = FakeWorkingCopies()
    shas = [copies.add_repo(Path("/nonexistent/repo"), first, "first")]
    for number, files in enumerate(commits):
        shas.append(copies.publish("feature", shas[-1], files, f"commit {number}"))
    copies.add_worktree(WORKTREE, None)
    copies.check_out(WORKTREE, "feature")
    copies.place(THE_PR, WORKTREE)
    copies.fetch_pr_branch(Path(WORKTREE), THE_PR, "feature", "main")
    return client_of(board_on(fake_threads(working_copies=copies), base_branch="main")), shas


def anchors(client, since, until, onto):
    answer = client.get(f"/api/diffs/{since}..{until}/anchors/{onto[0]}..{onto[-1]}")
    assert answer.status_code == 200
    return answer.json()


def onto(answer, path, side, line):
    return next((one["onto"] for file in answer["files"] if file["path"] == path
                 for one in file["lines"] if (one["side"], one["line"]) == (side, line)), None)


def test_an_unchanged_line_of_an_early_commit_sits_at_the_heads_line_number():
    client, shas = pull_request({"src/foo.py": "one\ntwo\nthree\n"},
                                {"src/foo.py": "one\ntwo\nadded\nthree\n"},
                                {"src/foo.py": "top\none\ntwo\nadded\nthree\n"})

    answer = anchors(client, shas[0], shas[1], shas)

    assert onto(answer, "src/foo.py", "RIGHT", 3) == {"side": "RIGHT", "line": 4}


def test_a_line_changed_by_a_later_commit_has_no_place_at_the_head():
    client, shas = pull_request({"src/foo.py": "one\ntwo\nthree\n"},
                                {"src/foo.py": "one\ntwo\nadded\nthree\n"},
                                {"src/foo.py": "one\ntwo\nchanged\nthree\n"})

    answer = anchors(client, shas[0], shas[1], shas)

    assert onto(answer, "src/foo.py", "RIGHT", 3) is None
    assert onto(answer, "src/foo.py", "RIGHT", 4) == {"side": "RIGHT", "line": 4}


def test_no_line_a_commit_left_in_a_file_the_head_deleted_has_a_place():
    client, shas = pull_request({"src/gone.py": "x\ny\n", "src/foo.py": "one\n"},
                                {"src/gone.py": "x\ny\nz\n"},
                                {"src/gone.py": None, "src/foo.py": "one\ntwo\n"})

    answer = anchors(client, shas[0], shas[1], shas)

    assert [one for file in answer["files"] if file["path"] == "src/gone.py"
            for one in file["lines"] if one["side"] == "RIGHT"] == []
    assert onto(answer, "src/gone.py", "LEFT", 1) == {"side": "LEFT", "line": 1}


def test_a_removed_line_sits_on_the_base_side_where_the_base_has_it():
    client, shas = pull_request({"src/foo.py": "one\ntwo\nthree\n"},
                                {"src/foo.py": "top\none\ntwo\nthree\n"},
                                {"src/foo.py": "top\none\nthree\n"})

    answer = anchors(client, shas[1], shas[2], shas)

    assert onto(answer, "src/foo.py", "LEFT", 3) == {"side": "LEFT", "line": 2}


def test_a_line_the_pull_requests_diff_does_not_show_has_no_place():
    client, shas = pull_request({"src/foo.py": "one\ntwo\nthree\n"},
                                {"src/foo.py": "one\nTWO\nthree\n"},
                                {"src/foo.py": "one\ntwo\nthree\n"})

    answer = anchors(client, shas[0], shas[1], shas)

    assert onto(answer, "src/foo.py", "RIGHT", 1) is None
