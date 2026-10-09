import logging

from tests.board_api.support import SERVER_PID, THE_PR, one_server
from tests.builders import a_pr

BOARD = "/pr/acme/widgets/54"
NOT_HELD = a_pr(55, "acme/widgets")


def test_a_held_prs_board_answers_under_its_prefix():
    answer = one_server(THE_PR).client.get(f"{BOARD}/api/pull-request")

    assert answer.status_code == 200
    assert (answer.json()["repo"], answer.json()["number"]) == ("acme/widgets", 54)


def test_a_pr_the_watcher_does_not_hold_is_not_found():
    answer = one_server(THE_PR).client.get("/pr/acme/widgets/55/api/pull-request")

    assert answer.status_code == 404
    assert answer.json()["errors"][0]["code"] == "not-found"


def test_a_pr_the_watcher_let_go_of_is_not_found_though_its_board_was_built():
    server = one_server(THE_PR)
    server.client.get(f"{BOARD}/api/pull-request")
    server.told.now = one_server(NOT_HELD).told.now

    assert server.client.get(f"{BOARD}/api/pull-request").status_code == 404


def test_a_held_prs_board_is_built_on_its_first_request_and_kept():
    server = one_server(THE_PR)
    built_before = list(server.panels.asked)

    server.client.get(f"{BOARD}/api/dashboard")
    server.client.get(f"{BOARD}/api/manager/changes")

    assert (built_before, server.panels.asked) == ([], [THE_PR])


def test_a_manager_command_points_at_the_dashboard_under_the_prs_prefix():
    web = one_server(THE_PR).client

    answer = web.post(f"{BOARD}/api/manager:hold")

    assert answer.status_code == 202
    assert answer.headers["Location"] == f"{BOARD}/api/dashboard"
    assert web.get(answer.headers["Location"]).status_code == 200


def test_a_new_draft_points_at_its_operation_under_the_prs_prefix():
    web = one_server(THE_PR).client

    answer = web.post(f"{BOARD}/api/operations:create-draft",
                      json={"body": "call it write_iso", "path": "f", "line": 1})

    assert answer.status_code == 202
    assert answer.headers["Location"].startswith(f"{BOARD}/api/conversations/")
    assert web.get(answer.headers["Location"]).json() == answer.json()


def test_a_sent_review_points_at_its_operation_under_the_prs_prefix():
    web = one_server(THE_PR).client

    answer = web.post(f"{BOARD}/api/operations:send-review",
                      json={"verdict": "COMMENT", "body": "a few things"})

    assert answer.status_code == 202
    assert answer.headers["Location"] == f"{BOARD}/api/operations/{answer.json()['id']}"
    assert web.get(answer.headers["Location"]).json()["id"] == answer.json()["id"]


def test_a_held_prs_terminal_sessions_are_listed_under_its_prefix():
    server = one_server(THE_PR)
    server.terminals.of(THE_PR).start("/nonexistent/worktree", ["git", "log"])

    answer = server.client.get(f"{BOARD}/api/terminal/sessions")

    assert [session["argv"] for session in answer.json()["sessions"]] == [["git", "log"]]


def test_the_hub_says_it_serves_from_the_servers_pid():
    answer = one_server(THE_PR).client.get("/api/health")

    assert (answer.json()["serves"], answer.json()["pid"]) == ("hub", SERVER_PID)


def test_the_hub_lists_what_the_watcher_holds():
    answer = one_server(THE_PR).client.get("/api/pull-requests")

    assert [row["number"] for row in answer.json()["pull_requests"]] == [54]


def test_a_board_asked_by_another_name_is_refused():
    answer = one_server(THE_PR, host="widgets.example:8720").client.get(
        f"{BOARD}/api/pull-request")

    assert answer.status_code == 403
    assert answer.json()["errors"][0]["code"] == "foreign-origin"


def test_a_board_write_from_another_sites_page_is_refused():
    answer = one_server(THE_PR).client.post(f"{BOARD}/api/manager:hold",
                                            headers={"Origin": "http://evil.example"})

    assert answer.status_code == 403


def test_a_board_write_from_the_servers_own_page_is_taken():
    answer = one_server(THE_PR, port=18799).client.post(
        f"{BOARD}/api/manager:hold", headers={"Origin": "http://127.0.0.1:18799"})

    assert answer.status_code == 202


def test_a_page_path_under_a_prs_prefix_is_the_page(tmp_path):
    (tmp_path / "index.html").write_text("<p>the board app</p>")

    answer = one_server(THE_PR, app_root=tmp_path).client.get(f"{BOARD}/conversations")

    assert answer.status_code == 200
    assert "the board app" in answer.text


def test_a_boards_request_is_logged_with_its_prs_path(caplog):
    caplog.set_level(logging.INFO, logger="github_orchestrator.board_api._guarded")

    one_server(THE_PR).client.get(f"{BOARD}/api/nothing-here")

    assert f"GET {BOARD}/api/nothing-here -> 404" in caplog.text
