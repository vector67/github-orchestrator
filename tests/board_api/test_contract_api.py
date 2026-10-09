import pytest

from github_orchestrator.conversation import ErrorCode
from tests.board_api.support import (
    PR,
    REPO,
    board_contract,
    client_for,
)


def test_the_pull_request_read_answers_the_contracts_fields():
    answer = client_for().get("/api/pull-request")

    assert answer.status_code == 200
    assert answer.json() == {
        "repo": REPO,
        "number": PR,
        "title": "Rename the helper",
        "html_url": f"https://github.com/{REPO}/pull/{PR}",
        "base_branch": "main",
        "branch": "rename-the-helper",
        "head_sha": "8f73fe8",
    }


def test_a_pull_request_the_board_knows_nothing_about_carries_nulls():
    answer = client_for(pr_title=None, base_branch=None,
                        head_sha=None).get("/api/pull-request")

    assert answer.json()["title"] is None
    assert answer.json()["base_branch"] is None
    assert answer.json()["head_sha"] is None


def test_a_read_conditional_on_a_stale_tag_answers_again():
    answer = client_for().get("/api/pull-request",
                                      headers={"If-None-Match": '"7b3c1f"'})

    assert answer.status_code == 200
    assert answer.json()["repo"] == REPO


def test_the_tag_follows_the_content_and_not_the_run():
    one = client_for().get("/api/pull-request")
    restarted = client_for().get("/api/pull-request")
    moved = client_for(head_sha="a1b2c3d").get("/api/pull-request")

    assert restarted.headers["ETag"] == one.headers["ETag"]
    assert moved.headers["ETag"] != one.headers["ETag"]


def test_a_read_of_nothing_is_refused_in_the_contracts_error_shape():
    answer = client_for().get("/api/proposals")

    assert answer.status_code == 404
    assert answer.headers["content-type"] == "application/json"
    refusals = answer.json()["errors"]
    assert [(one["status"], one["code"]) for one in refusals] == [
        (404, ErrorCode.NOT_FOUND.value)]
    assert refusals[0]["detail"]


@pytest.fixture
def contract():
    return board_contract()


def statuses_in(contract):
    return {status for path in contract["paths"].values()
            for operation in path.values()
            for status in operation["responses"]}


def test_no_route_declares_the_validation_error_no_route_can_give(contract):
    assert "422" not in statuses_in(contract)
    assert "HTTPValidationError" not in contract["components"]["schemas"]
    assert "ValidationError" not in contract["components"]["schemas"]


def test_a_route_with_something_to_validate_declares_the_refusal(contract):
    refused = contract["paths"]["/api/conversations/{key}"]["get"][
        "responses"]["400"]
    assert refused["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Errors"}
    assert refused["description"]


def test_a_route_with_nothing_to_validate_declares_no_refusal(contract):
    assert "400" not in contract["paths"]["/api/pull-request"]["get"][
        "responses"]


def test_a_read_that_sends_a_tag_declares_where_the_tag_comes_from(contract):
    answers = contract["paths"]["/api/conversations"]["get"]["responses"]
    assert answers["200"]["headers"]["ETag"]["schema"] == {"type": "string"}
    assert answers["304"]["headers"]["ETag"]["schema"] == {"type": "string"}


def test_every_read_that_declares_a_304_declares_the_tag_with_it(contract):
    conditional = [answers for path in contract["paths"].values()
                   for operation in path.values()
                   if "304" in (answers := operation["responses"])]
    assert len(conditional) == 18
    assert all("ETag" in answers["200"]["headers"]
               and "ETag" in answers["304"]["headers"]
               for answers in conditional)


VERBS = ("stop", "approve", "rework", "start-session", "retry", "resolve",
         "reject", "defer", "unpark", "reply")


@pytest.mark.parametrize("verb", VERBS)
def test_every_custom_method_takes_the_threads_tag_as_its_precondition(
        contract, verb):
    written = contract["paths"][
        f"/api/conversations/{{key}}/operations:{verb}"]["post"]
    precondition = next(one for one in written["parameters"]
                        if one["name"] == "If-Match")
    assert precondition["required"] is True
    assert precondition["in"] == "header"
    assert set(written["responses"]) >= {"202", "404", "409", "412"}


def test_every_route_on_one_thread_declares_its_record_may_not_parse(contract):
    undeclared = [(path, method) for path, operations in contract["paths"].items()
                  if path.startswith("/api/conversations/{key}")
                  for method, operation in operations.items()
                  if "500" not in operation["responses"]]
    assert undeclared == []


def test_a_read_that_sends_no_tag_declares_no_header(contract):
    assert "headers" not in contract["paths"]["/api/viewer"]["get"][
        "responses"]["200"]


def test_a_key_in_a_path_is_the_key_the_bodies_carry(contract):
    asked = next(one for one in
                 contract["paths"]["/api/conversations/{key}"]["get"][
                     "parameters"] if one["name"] == "key")
    answered = contract["components"]["schemas"]["Conversation"][
        "properties"]["key"]
    assert asked["schema"]["pattern"] == answered["pattern"]


def test_a_key_the_board_could_never_have_minted_is_malformed():
    answer = client_for().get("/api/conversations/not.a.key")

    assert answer.status_code == 400
    assert answer.json()["errors"][0]["code"] == ErrorCode.MALFORMED_REQUEST


def test_a_refusal_the_shared_sentence_covers_keeps_the_shared_one(contract):
    shared = contract["paths"]["/api/conversations/{key}"]["get"][
        "responses"]["404"]["description"]
    assert contract["paths"]["/api/conversations/{key}/comments"]["get"][
        "responses"]["404"]["description"] == shared


def test_a_page_asset_is_gzipped_for_a_client_that_takes_it():
    answer = client_for().get("/palette.css",
                                      headers={"Accept-Encoding": "gzip"})

    assert answer.headers["content-encoding"] == "gzip"
    assert answer.headers["vary"] == "Accept-Encoding"
    assert answer.text.startswith(":root")


@pytest.mark.parametrize(("accepted", "encoding"), [
    ("gzip, deflate", "gzip"),
    ("deflate, gzip;q=0.5", "gzip"),
    ("gzip;q=0", None),
    ("x-gzip", None),
])
def test_a_page_asset_is_gzipped_only_for_a_client_that_takes_gzip(accepted,
                                                                    encoding):
    answer = client_for().get("/palette.css", headers={"Accept-Encoding": accepted})

    assert answer.headers.get("content-encoding") == encoding
    assert answer.text.startswith(":root")


def test_an_answer_too_short_to_win_is_not_gzipped():
    answer = client_for().get("/fonts.css", headers={"Accept-Encoding": "gzip"})

    assert len(answer.content) < 256
    assert "content-encoding" not in answer.headers


def test_an_old_path_the_board_does_not_serve_is_still_a_plain_404():
    answer = client_for().get("/fonts/nothing-here.otf")

    assert answer.status_code == 404
    assert answer.headers["content-type"] == "text/plain; charset=utf-8"
    assert answer.content == b"not found"
