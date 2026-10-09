from github_orchestrator.github.fake import FakeGitHub, GhError
from github_orchestrator.notifications.fake import FakeNotifications
from tests.board_api.support import ACCOUNT, THE_PR, client_of
from tests.board_api.test_contract_drafts import (
    _board,
    _drafted,
    _key_of,
    _read,
    reviewing,
)
from tests.board_api.test_contract_writes import asked

SEND = "/api/operations:send-review"


def _enrolled(board, client, count):
    keys = []
    for number in range(count):
        key = _key_of(_drafted(client, body=f"finding {number}", line=11))
        asked(client, "enrol", key=key)
        keys.append(key)
    board.threads.tick(FakeNotifications(), on_hold=False)
    return keys


def _reviews_sent(github):
    return github.prs[(THE_PR)].state.reviews


def _summaries(github):
    return [thread for thread in github.prs[(THE_PR)].threads
            if thread.key.startswith("PRR_")]


def test_six_enrolled_drafts_go_out_as_one_review_and_each_is_posted():
    fake, head = reviewing()
    github = fake.github
    board = _board(fake, head)
    client = client_of(board)
    keys = _enrolled(board, client, 6)

    answer = client.post(SEND, json={"verdict": "REQUEST_CHANGES",
                                     "body": "a few things"})
    board.threads.tick(FakeNotifications(), on_hold=False)

    assert answer.status_code == 202
    assert (answer.json()["kind"], answer.json()["state"],
            answer.json()["conversation"]) == ("send-review", "pending", None)
    [sent] = _reviews_sent(github)
    [summary] = _summaries(github)
    [(review_id, drafts)] = github.prs[(THE_PR)].review_comments.items()
    assert (sent.requests_changes, summary.comments[0].body) == (True,
                                                      "a few things")
    assert sorted(draft.comment.body for draft in drafts) == [
        f"finding {number}" for number in range(6)]
    review = client.get(answer.headers["Location"]).json()
    assert (review["state"], review["verdict"], review["body"],
            review["posted_review"]) == ("applied", "REQUEST_CHANGES",
                                         "a few things", review_id)
    assert review["drafts"] == sorted(keys)
    for key in keys:
        posted = _read(client, key)
        assert (posted["key"], posted["kind"], posted["state"]) == (
            key, "review", "waiting")
        assert posted["github_node_id"].startswith("PRRT_")
        assert posted["operations"][-1]["kind"] == "posted"
        [operation] = [one for one in client.get(
            f"/api/conversations/{key}/operations").json()
            if one["kind"] == "posted"]
        assert (operation["state"], operation["review"],
                operation["github_node_id"]) == (
            "applied", review["id"], posted["github_node_id"])
        assert operation["posted_comment"] is not None


def test_a_verdict_that_is_not_an_approval_needs_a_body_before_anything_is_sent():
    fake, head = reviewing()
    github = fake.github
    board = _board(fake, head)
    client = client_of(board)
    _enrolled(board, client, 1)

    for verdict, body in (("REQUEST_CHANGES", None), ("COMMENT", "  ")):
        answer = client.post(SEND, json={"verdict": verdict, "body": body})

        assert answer.status_code == 400, verdict
        assert answer.json()["errors"][0]["code"] == "empty-body", verdict
    board.threads.tick(FakeNotifications(), on_hold=False)
    assert board.threads.reviews() == []
    assert _reviews_sent(github) == ()


def test_an_approval_needs_no_body():
    fake, head = reviewing()
    github = fake.github
    board = _board(fake, head)
    client = client_of(board)

    answer = client.post(SEND, json={"verdict": "APPROVE"})
    board.threads.tick(FakeNotifications(), on_hold=False)

    assert answer.status_code == 202
    [sent] = _reviews_sent(github)
    assert (sent.approves, sent.commit_id) == (True, head)
    assert _summaries(github) == []
    assert list(github.prs[(THE_PR)].review_comments.values()) == [[]]


class TurnsDownReviews(FakeGitHub):
    def post_review(self, pr, head, verdict, body, comments):
        raise GhError("HTTP 422: Review Can not approve your own pull request")


def test_a_review_github_rejects_leaves_every_draft_enrolled_with_its_words():
    board = _board(*reviewing(TurnsDownReviews(account=ACCOUNT)))
    client = client_of(board)
    keys = _enrolled(board, client, 2)

    answer = client.post(SEND, json={"verdict": "APPROVE"})
    board.threads.tick(FakeNotifications(), on_hold=False)

    for key in keys:
        assert _read(client, key)["state"] == "enrolled"
    review = client.get(answer.headers["Location"]).json()
    assert (review["state"], review["reason_code"]) == (
        "refused", "github-rejected")
    assert "Can not approve your own pull request" in review["reason"]


def test_a_second_review_while_one_is_going_out_is_refused():
    client = client_of(_board(*reviewing()))

    client.post(SEND, json={"verdict": "APPROVE"})
    answer = client.post(SEND, json={"verdict": "COMMENT", "body": "again"})

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "review-in-flight"


def test_a_review_going_out_is_work_in_flight():
    client = client_of(_board(*reviewing()))

    queued = client.post(SEND, json={"verdict": "APPROVE"}).json()

    assert client.get("/api/operations").json() == [queued]


def test_a_summary_longer_than_github_takes_is_too_long():
    answer = client_of(_board(*reviewing())).post(SEND, json={
        "verdict": "COMMENT", "body": "x" * (64 * 1024 + 1)})

    assert answer.status_code == 413
    assert answer.json()["errors"][0]["code"] == "body-too-long"
