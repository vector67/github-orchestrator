import logging
import os

from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.board_api.support import asked_with_every_worker_taken, client_for

SHA = "a" * 40


def git_explodes():
    copies = FakeWorkingCopies()
    copies.fail_reads(RuntimeError("git exploded"))
    return copies


def _read_a_file():
    return client_for(working_copies=git_explodes()).get(
        "/api/files", params={"sha": SHA, "path": "f"})


def _boards_own(caplog):
    return "\n".join(record.getMessage() for record in caplog.records
                     if record.name.startswith("github_orchestrator"))


def test_an_unexpected_failure_is_answered_in_the_contracts_shape():
    answer = _read_a_file()

    assert answer.status_code == 500
    [error] = answer.json()["errors"]
    assert (error["status"], error["code"]) == (500, "server-error")
    assert "the PR manager's log" in error["detail"]


def test_an_unexpected_failure_leaves_its_traceback_and_request_in_the_log(caplog):
    with caplog.at_level(logging.WARNING):
        _read_a_file()

    [failure] = [r for r in caplog.records if r.exc_info]
    assert "GET /api/files" in failure.getMessage()
    assert "git exploded" in caplog.text


def test_a_refused_request_is_logged_with_its_answer(caplog):
    with caplog.at_level(logging.INFO):
        client_for().get("/api/proposals")

    assert "GET /api/proposals -> 404" in _boards_own(caplog)


def test_an_ordinary_request_stays_out_of_the_log_at_info(caplog):
    with caplog.at_level(logging.INFO):
        client_for().get("/api/pull-request")

    assert "/api/pull-request" not in _boards_own(caplog)


def test_health_names_the_process_serving_the_board():
    answer = client_for().get("/api/health")

    assert answer.status_code == 200
    assert answer.json() == {"status": "ok", "pid": os.getpid(), "serves": "board",
                             "hub_url": "http://127.0.0.1:8720", "font_problem": None, "state": None,
                             "version": None, "watcher": None, "newest_release": None}


def test_health_answers_while_every_worker_thread_is_taken():
    answer = asked_with_every_worker_taken(client_for(), "/api/health")

    assert answer.json()["serves"] == "board"


def test_an_error_the_page_reports_is_written_to_the_log(caplog):
    with caplog.at_level(logging.WARNING):
        answer = client_for().post("/api/client-errors", json={
            "where": "panel",
            "message": "Cannot read properties of undefined (reading 'etag')",
            "stack": "TypeError: Cannot read properties\n    at loadDetails (threads.ts:220)",
        })

    assert answer.status_code == 204
    assert "board page error in panel: Cannot read properties of undefined" in caplog.text
    assert "at loadDetails (threads.ts:220)" in caplog.text


def test_a_report_with_no_stack_is_still_logged(caplog):
    with caplog.at_level(logging.WARNING):
        answer = client_for().post("/api/client-errors", json={
            "where": "window", "message": "Script error."})

    assert answer.status_code == 204
    assert "board page error in window: Script error." in caplog.text
