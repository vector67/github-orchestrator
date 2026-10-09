from pathlib import Path

import pytest

from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.board_api.support import (
    KEY,
    PORT,
    THE_PR,
    WORKTREE,
    board_on,
    client_of,
    fake_threads,
    heard_on,
    proposed,
    running,
)
from tests.conversation.support import said

LONG_REPLY = "x" * (64 * 1024 + 1)

IDLE = "PRRT_202"


def _tag(client):
    return client.get(f"/api/conversations/{KEY}").json()["etag"]


def _stop(client, tag, **headers):
    return client.post(f"/api/conversations/{KEY}/operations:stop",
                       headers={"If-Match": tag, **headers})


def _twice(client):
    _stop(client, _tag(client))
    return client.post(f"/api/conversations/{KEY}/operations:reply",
                       headers={"If-Match": _tag(client)}, json={"body": "on it"})


REFUSALS = {
    "a thread the board has not got": (
        lambda client, sha: client.get("/api/conversations/PRRT_nobody"),
        404, "not-found", "this board has no thread called PRRT_nobody"),
    "a person nobody has heard from": (
        lambda client, sha: client.get("/api/people/nobody"),
        404, "not-found", "nobody called nobody has spoken on this pull request"),
    "a comment the thread does not hold": (
        lambda client, sha: client.get(f"/api/conversations/{KEY}/comments/999"),
        404, "not-found", f"thread {KEY} holds no comment 999"),
    "an operation the thread does not hold": (
        lambda client, sha: client.get(f"/api/conversations/{KEY}/operations/op_x"),
        404, "not-found", f"thread {KEY} holds no operation op_x"),
    "an operation the pull request does not hold": (
        lambda client, sha: client.get("/api/operations/op_x"),
        404, "not-found", "this pull request holds no operation op_x"),
    "a proposal the thread does not hold": (
        lambda client, sha: client.get(f"/api/conversations/{KEY}/proposals/p_x"),
        404, "not-found", f"thread {KEY} holds no proposal p_x"),
    "a path under the api that serves nothing": (
        lambda client, sha: client.get("/api/nothing"),
        404, "not-found", "this board serves nothing at /api/nothing"),
    "a commit the worktree has not got": (
        lambda client, sha: client.get("/api/files", params={"sha": "a1b2c3d", "path": "f"}),
        404, "no-such-commit", "this repository has no commit a1b2c3d"),
    "a diff from a commit the worktree has not got": (
        lambda client, sha: client.get(f"/api/diffs/a1b2c3d..{sha}"),
        404, "no-such-commit", "this repository has no commit a1b2c3d"),
    "a diff to a commit the worktree has not got": (
        lambda client, sha: client.get(f"/api/diffs/{sha}..a1b2c3d"),
        404, "no-such-commit", "this repository has no commit a1b2c3d"),
    "a path the commit does not hold": (
        lambda client, sha: client.get("/api/files", params={"sha": sha, "path": "gone"}),
        404, "no-such-path", "{sha} holds nothing at gone"),
    "a range that runs backwards": (
        lambda client, sha: client.get("/api/files", params={
            "sha": sha, "path": "f", "from_line": 3, "to_line": 2}),
        400, "range-inverted", "line 2 comes before line 3"),
    "a range wider than one read": (
        lambda client, sha: client.get("/api/files", params={
            "sha": sha, "path": "f", "from_line": 1, "to_line": 2001}),
        400, "range-too-wide", "lines 1 to 2001 is more than the 2000 this read returns at once"),
    "a line number that is not a number": (
        lambda client, sha: client.get("/api/files", params={
            "sha": sha, "path": "f", "from_line": "plenty"}),
        400, "malformed-request",
        "query.from_line: Input should be a valid integer, unable to parse string as an integer"),
    "a tag from before the thread moved": (
        lambda client, sha: _stop(client, '"7b3c1f"'),
        412, "precondition-failed", f'thread {KEY} has moved since "7b3c1f" was read'),
    "a second operation before the first is taken": (
        lambda client, sha: _twice(client),
        409, "operation-outstanding",
        f"thread {KEY} already has an operation waiting for the board to take it"),
    "a reply longer than GitHub takes": (
        lambda client, sha: client.post(f"/api/conversations/{KEY}/operations:reply",
                                        headers={"If-Match": _tag(client)},
                                        json={"body": LONG_REPLY}),
        413, "body-too-long", "that reply is too long; GitHub takes at most 65536 bytes"),
    "a delete of a comment someone else wrote": (
        lambda client, sha: client.post(
            f"/api/conversations/{IDLE}/operations:resolve",
            headers={"If-Match": client.get(f"/api/conversations/{IDLE}").json()["etag"]},
            json={"delete_comment": True}),
        409, "not-deletable", "reviewer wrote that comment, so it is not yours to delete"),
    "a review with no summary": (
        lambda client, sha: client.post("/api/operations:send-review",
                                        json={"verdict": "COMMENT", "body": ""}),
        400, "empty-body", "GitHub takes no comment without a summary"),
    "a write from another site's page": (
        lambda client, sha: _stop(client, _tag(client), Origin="http://evil.example"),
        403, "foreign-origin", "a write from another site's page is refused"),
    "a read addressed to another host": (
        lambda client, sha: client.get("/api/pull-request", headers={"Host": "evil.example"}),
        403, "foreign-origin", f"this board answers 127.0.0.1:{PORT}, not evil.example"),
}


@pytest.mark.parametrize("what", REFUSALS)
def test_each_refusal_says_what_it_refuses_in_words_of_its_own(what):
    github = FakeGitHub()
    copies = FakeWorkingCopies(github)
    sha = copies.add_repo(Path(WORKTREE), {"f": "one\ntwo\nthree\n"}, "first")
    copies.place(THE_PR, WORKTREE)
    board = board_on(fake_threads(github, copies))
    heard_on(board)
    running(board)
    heard_on(board, IDLE, said(202, "Tidy this up."))
    proposed(board, IDLE)
    client = client_of(board)
    request, status, code, detail = REFUSALS[what]

    answer = request(client, sha)

    assert answer.status_code == status
    assert answer.json()["errors"] == [
        {"status": status, "code": code, "detail": detail.format(sha=sha)}]
