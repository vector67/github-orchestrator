from pathlib import Path

import pytest

from github_orchestrator.domain import Side
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.notifications.fake import FakeNotifications
from tests.board_api.support import (
    ACCOUNT,
    KEY,
    THE_PR,
    WORKTREE,
    board_on,
    client_of,
    fake_threads,
    heard_on,
)
from tests.board_api.test_contract_writes import NOW, asked, tag_of
from tests.conversation.support import at

PATH = "billing/invoice_writer.py"

BEFORE = "".join(f"line {number}\n" for number in range(1, 13))

AFTER = BEFORE.replace("line 11\n", "line eleven\n")


def reviewing(github=None, before=BEFORE, after=AFTER, now=NOW, agent_runs=None):
    fake = fake_threads(github or FakeGitHub(account=ACCOUNT), agent_runs=agent_runs,
                        clock=at(now))
    copies = fake.working_copies
    copies.add_repo(Path(WORKTREE), {"f": "one\n"}, "first")
    copies.place(THE_PR, WORKTREE)
    copies.commit(WORKTREE, {PATH: before}, "the writer")
    copies.checkout(THE_PR).push()
    head = copies.commit(WORKTREE, {PATH: after}, "call it eleven")
    return fake, head


def _board(fake, head):
    return board_on(fake, is_author=False, head_sha=head)


@pytest.fixture
def scene():
    return reviewing()


@pytest.fixture
def board(scene):
    return _board(*scene)


def _drafted(client, body="call it write_iso", line=11, path=PATH, **fields):
    return client.post("/api/operations:create-draft",
                       json={"body": body, "path": path, "line": line,
                             **fields})


def _key_of(answer):
    return answer.json()["conversation"]


def _read(client, key):
    return client.get(f"/api/conversations/{key}").json()


def test_create_draft_mints_a_draft_with_nothing_on_github(board):
    client = client_of(board)

    answer = _drafted(client)

    assert answer.status_code == 202
    created = answer.json()
    assert (created["kind"], created["state"], created["body"]) == (
        "create-draft", "applied", "call it write_iso")
    assert created["anchor"]["path"] == PATH
    assert client.get(answer.headers["Location"]).json() == created
    drafted = _read(client, _key_of(answer))
    assert (drafted["kind"], drafted["state"], drafted["github_node_id"]) == (
        "draft", "draft", None)
    assert drafted["anchor"]["side"] == "RIGHT"
    assert [(one["id"], one["author"]) for one in drafted["comments"]] == [
        (None, ACCOUNT)]


def test_a_draft_needs_something_in_it(board):
    answer = _drafted(client_of(board), body="")

    assert answer.status_code == 400
    assert answer.json()["errors"][0]["code"] == "malformed-request"


def test_an_edit_replaces_the_body_and_the_anchor_and_edits_collapse(board):
    client = client_of(board)
    key = _key_of(_drafted(client))

    asked(client, "edit-draft", key=key, body="first", path=PATH, line=10)
    board.threads.tick(FakeNotifications(), on_hold=False)
    asked(client, "edit-draft", key=key, body="second", path=PATH, line=11,
          start_line=10, side="LEFT")
    board.threads.tick(FakeNotifications(), on_hold=False)

    drafted = _read(client, key)
    assert drafted["anchor"]["line"] == 11
    assert drafted["anchor"]["start_line"] == 10
    assert drafted["anchor"]["side"] == "LEFT"
    comments = client.get(f"/api/conversations/{key}/comments").json()
    assert comments[0]["body"] == "second"
    assert [one["kind"] for one in drafted["operations"]] == [
        "create-draft", "edit-draft"]


def test_enrol_puts_a_draft_whose_anchor_is_in_the_diff_into_the_review(board):
    client = client_of(board)
    key = _key_of(_drafted(client))

    answer = asked(client, "enrol", key=key)
    board.threads.tick(FakeNotifications(), on_hold=False)

    assert answer.status_code == 202
    assert _read(client, key)["state"] == "enrolled"


def test_enrol_refuses_an_anchor_that_is_not_in_the_diff(board):
    client = client_of(board)
    key = _key_of(_drafted(client, line=400))
    tag = tag_of(client, key)

    answer = asked(client, "enrol", key=key, tag=tag)

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "anchor-not-in-diff"
    assert tag_of(client, key) == tag


def test_an_anchor_on_the_old_side_is_checked_against_the_old_lines(board):
    client = client_of(board)
    on_the_right = _key_of(_drafted(client, line=11, side="LEFT"))

    assert asked(client, "enrol", key=on_the_right).status_code == 202
    gone = _key_of(_drafted(client, line=13, side="LEFT"))
    assert asked(client, "enrol", key=gone).status_code == 409


def test_a_range_is_in_the_diff_only_where_all_of_it_is_in_one_hunk(board):
    client = client_of(board)
    inside = _key_of(_drafted(client, line=11, start_line=9))
    reaching_out = _key_of(_drafted(client, line=11, start_line=2))

    assert asked(client, "enrol", key=inside).status_code == 202
    assert asked(client, "enrol", key=reaching_out).json()["errors"][0]["code"] == (
        "anchor-not-in-diff")


TWENTY = "".join(f"line {number}\n" for number in range(1, 21))

TWO_HUNKS = TWENTY.replace("line 3\nline 4\n", "").replace("line 15\n", "line fifteen\n")


@pytest.fixture
def two_hunks():
    return client_of(_board(*reviewing(before=TWENTY, after=TWO_HUNKS)))


def _refusal(answer):
    [error] = answer.json()["errors"]
    return error["code"], error["detail"]


def test_a_range_may_start_on_the_old_side_and_end_on_the_new_in_one_hunk(two_hunks):
    key = _key_of(_drafted(two_hunks, line=5, start_line=6, start_side="LEFT"))

    assert asked(two_hunks, "enrol", key=key).status_code == 202


def test_a_range_that_starts_in_another_hunk_than_it_ends_is_refused(two_hunks):
    key = _key_of(_drafted(two_hunks, line=13, start_line=2, start_side="LEFT"))

    assert _refusal(asked(two_hunks, "enrol", key=key)) == (
        "anchor-not-in-diff",
        f"{PATH}:2 on the old side is in another hunk than {PATH}:13 on the new "
        f"side; GitHub takes a range only inside one hunk")


def test_a_range_across_sides_that_ends_before_it_starts_is_refused(two_hunks):
    key = _key_of(_drafted(two_hunks, line=6, side="LEFT", start_line=5,
                           start_side="RIGHT"))

    assert _refusal(asked(two_hunks, "enrol", key=key)) == (
        "anchor-not-in-diff",
        f"{PATH}:5 on the new side comes after {PATH}:6 on the old side in the "
        f"diff; a range starts before it ends")


def test_a_range_whose_start_is_no_line_of_the_diff_says_which_end(two_hunks):
    key = _key_of(_drafted(two_hunks, line=13, start_line=8))

    assert _refusal(asked(two_hunks, "enrol", key=key)) == (
        "anchor-not-in-diff",
        f"{PATH}:8 on the new side is not a line of the pull request's diff")


def test_a_line_of_a_file_the_pr_does_not_touch_is_not_in_the_diff(board):
    client = client_of(board)
    key = _key_of(_drafted(client, path="billing/other.py", line=11))

    assert asked(client, "enrol", key=key).json()["errors"][0]["code"] == (
        "anchor-not-in-diff")


def test_a_range_that_ends_before_it_starts_is_not_in_the_diff(board):
    client = client_of(board)
    key = _key_of(_drafted(client, line=10, start_line=12))

    assert asked(client, "enrol", key=key).json()["errors"][0]["code"] == (
        "anchor-not-in-diff")


def test_enrol_says_so_when_git_cannot_produce_the_diff(scene):
    fake, _ = scene
    board = _board(fake, "e" * 40)
    client = client_of(board)
    key = _key_of(_drafted(client))

    answer = asked(client, "enrol", key=key)

    assert answer.status_code == 500
    assert answer.json()["errors"][0]["code"] == "git-failed"


def test_withdraw_takes_an_enrolled_draft_back_out_of_the_review(board):
    client = client_of(board)
    key = _key_of(_drafted(client))
    asked(client, "enrol", key=key)
    board.threads.tick(FakeNotifications(), on_hold=False)

    answer = asked(client, "withdraw-from-review", key=key)
    board.threads.tick(FakeNotifications(), on_hold=False)

    assert answer.status_code == 202
    assert _read(client, key)["state"] == "draft"


def test_a_discarded_draft_is_done_and_one_unpark_brings_it_back(board):
    client = client_of(board)
    key = _key_of(_drafted(client))

    asked(client, "discard", key=key)
    board.threads.tick(FakeNotifications(), on_hold=False)
    discarded = _read(client, key)["state"]
    asked(client, "unpark", key=key)
    board.threads.tick(FakeNotifications(), on_hold=False)

    assert discarded == "done"
    assert _read(client, key)["state"] == "draft"


def posted_threads(github):
    return [thread for thread in github.prs[(THE_PR)].threads
            if thread.key != KEY]


def test_post_now_puts_the_draft_on_github_under_the_key_it_always_had(scene):
    fake, head = scene
    board = _board(fake, head)
    client = client_of(board)
    key = _key_of(_drafted(client, line=11, start_line=10))

    answer = asked(client, "post-now", key=key)
    board.threads.tick(FakeNotifications(), on_hold=False)

    assert answer.status_code == 202
    [on_github] = posted_threads(fake.github)
    [comment] = on_github.comments
    assert (on_github.path, on_github.anchor.original_start_line,
            on_github.line, on_github.anchor.side, comment.body) == (
        PATH, 10, 11, Side.AFTER, "call it write_iso")
    posted = _read(client, key)
    assert posted["key"] == key
    assert (posted["kind"], posted["state"], posted["github_node_id"]) == (
        "review", "waiting", on_github.key)
    operation = client.get(answer.headers["Location"]).json()
    assert (operation["kind"], operation["state"],
            operation["posted_comment"]) == ("post-now", "applied", comment.id)


def test_fix_puts_an_agent_on_a_posted_draft(scene):
    fake, head = scene
    board = _board(fake, head)
    client = client_of(board)
    key = _key_of(_drafted(client, line=11))
    asked(client, "post-now", key=key)
    board.threads.tick(FakeNotifications(), on_hold=False)

    answer = asked(client, "fix", key=key)
    board.threads.tick(FakeNotifications(), on_hold=False)

    assert answer.status_code == 202
    assert answer.json()["operation"]["kind"] == "first"
    assert _read(client, key)["state"] in ("queued", "working")


def test_a_range_that_crosses_sides_goes_to_github_with_the_side_it_starts_on(scene):
    fake, head = scene
    board = _board(fake, head)
    client = client_of(board)
    key = _key_of(_drafted(client, line=11, start_line=10, start_side="LEFT"))

    drafted = _read(client, key)["anchor"]
    asked(client, "post-now", key=key)
    board.threads.tick(FakeNotifications(), on_hold=False)

    assert (drafted["start_line"], drafted["start_side"], drafted["line"],
            drafted["side"]) == (10, "LEFT", 11, "RIGHT")
    [on_github] = posted_threads(fake.github)
    assert (on_github.anchor.original_start_line, on_github.anchor.start_side,
            on_github.line, on_github.anchor.side) == (10, Side.BEFORE, 11, Side.AFTER)
    assert _read(client, key)["anchor"]["start_side"] == "LEFT"


def test_a_range_given_no_start_side_starts_on_its_side(board):
    client = client_of(board)
    key = _key_of(_drafted(client, line=11, start_line=10, side="LEFT"))

    assert _read(client, key)["anchor"]["start_side"] == "LEFT"


def test_a_single_line_draft_has_no_start_side(board):
    client = client_of(board)
    key = _key_of(_drafted(client, line=11, start_side="LEFT"))

    assert _read(client, key)["anchor"]["start_side"] is None


def test_post_now_refuses_an_anchor_that_is_not_in_the_diff(board):
    client = client_of(board)
    key = _key_of(_drafted(client, line=400))

    answer = asked(client, "post-now", key=key)

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "anchor-not-in-diff"


def test_the_pull_requests_own_verbs_are_not_served_under_a_thread(board):
    heard_on(board)
    client = client_of(board)

    for verb in ("create-draft", "send-review"):
        answer = asked(client, verb, key=KEY, tag=tag_of(client),
                       body="x", path=PATH, line=1)

        assert answer.status_code == 404, verb
        assert answer.json()["errors"][0]["code"] == "not-found", verb
