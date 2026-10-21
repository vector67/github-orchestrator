import csv
from datetime import datetime
from pathlib import Path

import pytest

from github_orchestrator.domain import Repo
from github_orchestrator.github.fake import GhError
from tests.builders import a_pr
from tests.github.scripted_gh import Failure, Raw, ScriptedGh
from tests.github.support import real_github

REPO = Repo.parse("acme/widgets")
SEARCH_URL = "https://api.github.com/search/issues?q=repo%3Aacme%2Fwidgets"


def _exchange(url: str, method: str = "GET", status: str | None = "200 OK",
              headers: tuple[str, ...] = (), body: str = '{\n  "items": []\n}') -> str:
    path = url.removeprefix("https://api.github.com")
    lines = ["* Request at 2026-01-01 12:00:00.1 +0000 UTC m=+0.04",
             f"* Request to {url}",
             f"> {method} {path} HTTP/1.1",
             "> Authorization: token ████",
             "", ""]
    if status is None:
        lines += ["* dial tcp: connect: connection refused"]
    else:
        lines += [f"< HTTP/2.0 {status}", "< Content-Type: application/json",
                  *(f"< {header}" for header in headers), "", body, ""]
    lines += ["* Request took 512.3ms"]
    return "\n".join(lines) + "\n"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def _search(tmp_path: Path, answer: Raw | Failure) -> Path:
    log = tmp_path / "gh_calls.csv"
    github = real_github(gh=ScriptedGh().answer("search prs", answer), requests_log=log)
    try:
        github.search([REPO], "author")
    except GhError:
        pass
    return log


def test_every_request_gh_makes_is_a_row_with_its_account_url_status_and_size(tmp_path):
    body = '{\n  "data": {}\n}'
    log = _search(tmp_path, Raw("[]", _exchange("https://api.github.com/graphql", "POST",
                                                 body=body) + _exchange(SEARCH_URL)))

    rows = _rows(log)
    assert [(row["account"], row["method"], row["url"], row["exit"], row["status"])
            for row in rows] == [
        ("octocat", "POST", "https://api.github.com/graphql", "0", "200"),
        ("octocat", "GET", SEARCH_URL, "0", "200"),
    ]
    assert rows[0]["bytes"] == str(len(body))
    assert datetime.fromisoformat(rows[0]["at"])


def test_a_403_row_keeps_retry_after_and_the_rate_limit_headers(tmp_path):
    log = _search(tmp_path, Failure(
        _exchange(SEARCH_URL, status="403 Forbidden", headers=(
            "Retry-After: 60", "X-Ratelimit-Limit: 30", "X-Ratelimit-Remaining: 0",
            "X-Ratelimit-Reset: 1792559472", "X-Ratelimit-Resource: search",
            "X-Ratelimit-Used: 30", "X-Github-Request-Id: 0000:1111"))
        + "gh: You have exceeded a secondary rate limit. (HTTP 403)\n"))

    [row] = _rows(log)
    assert (row["exit"], row["status"], row["retry_after"]) == ("1", "403", "60")
    assert [row[f"ratelimit_{name}"] for name in
            ("limit", "remaining", "reset", "resource", "used")] == [
        "30", "0", "1792559472", "search", "30"]


def test_a_request_that_succeeds_leaves_the_rate_limit_columns_empty(tmp_path):
    log = _search(tmp_path, Raw("[]", _exchange(SEARCH_URL,
                                                headers=("X-Ratelimit-Remaining: 26",))))

    [row] = _rows(log)
    assert row["ratelimit_remaining"] == ""


def test_a_request_github_never_answered_has_no_status_or_size(tmp_path):
    log = _search(tmp_path, Failure(_exchange(SEARCH_URL, status=None)
                                    + 'Get "x": connection refused\n'))

    [row] = _rows(log)
    assert (row["status"], row["bytes"]) == ("", "")


def test_rows_from_later_calls_follow_the_first_under_one_header(tmp_path):
    log = tmp_path / "gh_calls.csv"
    gh = ScriptedGh().always("search prs", Raw("[]", _exchange(SEARCH_URL)))
    github = real_github(gh=gh, requests_log=log)

    github.search([REPO], "author")
    github.search([REPO], "author")

    assert len(_rows(log)) == 2


def test_gh_is_asked_for_its_debug_output(tmp_path):
    gh = ScriptedGh().answer("search prs", [])

    real_github(gh=gh, requests_log=tmp_path / "gh_calls.csv").search([REPO], "author")

    assert gh.environments[-1]["GH_DEBUG"] == "api"


def test_a_refusal_carries_ghs_own_words_without_its_debug_output(tmp_path):
    gh = ScriptedGh().answer("graphql mergeStateStatus", Failure(
        _exchange("https://api.github.com/graphql", "POST", status="404 Not Found")
        + "gh: Not Found (HTTP 404)"))
    log = tmp_path / "gh_calls.csv"

    with pytest.raises(GhError) as excinfo:
        real_github(gh=gh, requests_log=log).pr_state(a_pr(7, "acme/widgets"))

    assert "Request to" not in str(excinfo.value)
    assert "gh: Not Found (HTTP 404)" in str(excinfo.value)
    assert [row["status"] for row in _rows(log)] == ["404"]
