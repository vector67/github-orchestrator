import json
from dataclasses import replace
from pathlib import Path

import pytest

from github_orchestrator.agent_runs.fake import FilingTicket, Outcome
from github_orchestrator.conversation import Classification
from github_orchestrator.github import CommentKind
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.working_copies import FileDiff
from github_orchestrator.working_copies.fake import (
    DiffHunk,
    DiffLine,
    FakeWorkingCopies,
)
from tests.board_api.support import (
    MOMENT,
    PR,
    REPO,
    THE_PR,
    WORKTREE,
    board_for,
    board_on,
    client_of,
    disk_board,
    fake_threads,
    heard_on,
    running,
)
from tests.conversation.support import (
    EARLIER,
    Moment,
    commit_fix,
    hear,
    on_github,
    said,
    start_run,
)
from tests.disk_layout import thread_file

KEY = "PRRT_2314159"
COMMENT_ID = 2314159
BODY = "please rename this helper"
STAMPED = "2026-08-28T10:00:00.000000Z"


def card(board, *comments, key=KEY, **fields):
    return heard_on(board, key, *(comments or (said(COMMENT_ID, BODY),)),
                    path="src/foo.py", line=42, **fields)


def spoke(*comments):
    board = board_for()
    card(board, *comments)
    return client_of(board)


def tag_of(client, key=KEY):
    return client.get(f"/api/conversations/{key}").json()["etag"]


def asked(client, verb, key=KEY, **body):
    return client.post(f"/api/conversations/{key}/operations:{verb}",
                       headers={"If-Match": tag_of(client, key)}, json=body)


def drain(board):
    board.threads.tick(FakeNotifications(), on_hold=False)


def left(board, files=None, key=KEY, message="Rename the helper", **ready):
    start_run(board.stage, board.threads)
    sha = commit_fix(board.stage, key, files or {"src/foo.py": "renamed\n"}, pr=THE_PR,
                     message=message)
    with board.threads.editing(key) as editable:
        editable.ready(sha, **ready)
    drain(board)
    return sha


def test_the_viewer_is_the_account_the_board_runs_as():
    client = spoke(said(1, "one", author="octocat", author_name="Octo Cat"),
                   said(2, "two", author="ameier", author_name="Anna Meier"))

    answer = client.get("/api/viewer")

    assert answer.status_code == 200
    assert answer.json() == {"login": "octocat", "name": "Octo Cat"}


def test_a_viewer_nobody_has_named_carries_a_null_name():
    answer = spoke(said(2, "two", author="ameier")).get("/api/viewer")

    assert answer.json() == {"login": "octocat", "name": None}


def test_the_people_read_names_everyone_the_records_mention():
    client = spoke(said(1, "one", author="reviewer"),
                   said(2, "two", author="ameier", author_name="Anna Meier"),
                   said(3, "three", author="octocat"))

    answer = client.get("/api/people")

    assert answer.status_code == 200
    assert answer.json() == [{"login": "ameier", "name": "Anna Meier"},
                             {"login": "octocat", "name": None},
                             {"login": "reviewer", "name": None}]


def test_a_board_set_to_first_names_names_everyone_by_the_first_word_of_their_name():
    board = board_for(first_names_only=True)
    card(board, said(1, "one", author="octocat", author_name="Octo Cat"),
         said(2, "two", author="ada", author_name="Ada Lovelace King"),
         said(3, "three", author="reviewer"))
    client = client_of(board)

    assert client.get("/api/people").json() == [
        {"login": "ada", "name": "Ada"},
        {"login": "octocat", "name": "Octo"},
        {"login": "reviewer", "name": None}]
    assert client.get("/api/people/ada").json() == {"login": "ada", "name": "Ada"}
    assert client.get("/api/viewer").json() == {"login": "octocat", "name": "Octo"}


def test_one_person_is_read_by_login():
    answer = spoke(said(1, "one", author="ameier", author_name="Anna Meier")).get(
        "/api/people/ameier")

    assert answer.json() == {"login": "ameier", "name": "Anna Meier"}


def test_the_collection_says_when_it_was_read_and_its_tag_does_not_move_with_that():
    moment = Moment(MOMENT)
    board = board_on(fake_threads(clock=moment), clock=moment)
    card(board)
    client = client_of(board)
    first = client.get("/api/conversations")

    moment.iso = "2026-08-28T10:05:00Z"
    again = client.get("/api/conversations",
                       headers={"If-None-Match": first.headers["ETag"]})

    assert first.json()["listed_at"] == MOMENT
    assert again.status_code == 304


def test_the_collection_answers_a_threads_stored_facts():
    board = board_for()
    card(board)
    left(board)

    answer = client_of(board).get("/api/conversations")

    assert answer.status_code == 200
    assert answer.json()["unreadable"] == []
    [thread] = answer.json()["conversations"]
    assert thread | {"etag": ""} == {
        "key": KEY,
        "github_node_id": KEY,
        "kind": "review",
        "state": "ready",
        "state_changed_at": MOMENT,
        "reopened": False,
        "etag": "",
        "github_removed": False,
        "github_resolved": None,
        "github_resolved_at": None,
        "created_at": STAMPED,
        "anchor": {"path": "src/foo.py", "line": 42, "start_line": None,
                   "start_side": None, "side": None, "original_line": None,
                   "original_start_line": None, "original_commit": None,
                   "is_outdated": False},
        "gist": BODY,
        "comments": [{"id": COMMENT_ID, "author": "reviewer",
                      "created_at": EARLIER, "review_state": None}],
        "operations": [{"id": f"{KEY}.1", "kind": "first",
                        "state": "applied", "reason": None,
                        "reason_code": None, "requested_at": STAMPED,
                        "settled_at": MOMENT, "steps_done": None,
                        "steps_total": None, "attempts": 1,
                        "attempts_allowed": 3, "lands": None, "ticket_key": None}],
        "mention": False,
        "updated_at": MOMENT,
        "author_kind": "human",
        "unread": False,
        "record_state": "open",
    }
    assert thread["etag"].startswith('"')


def test_each_thread_says_whether_its_author_is_you_a_person_or_a_bot():
    board = board_for()
    card(board, said(1, "mine", author="octocat"), key="PRRT_mine")
    card(board, said(2, "a person", author="ameier"), key="PRRT_human")
    card(board, said(3, "a bot", author="copilot[bot]"), key="PRRT_bot")
    card(board, said(4, "another bot", author="Claude"), key="PRRT_claude")

    answer = client_of(board).get("/api/conversations")

    assert {thread["key"]: thread["author_kind"]
            for thread in answer.json()["conversations"]} == {
        "PRRT_mine": "mine", "PRRT_human": "human", "PRRT_bot": "bot",
        "PRRT_claude": "bot"}


def test_a_save_that_changes_nothing_shown_moves_the_stamp_and_not_the_etag():
    moment = Moment("2026-09-23T09:00:00Z")
    board = board_on(fake_threads(clock=moment))
    card(board)
    client = client_of(board)
    before = client.get(f"/api/conversations/{KEY}").json()

    moment.iso = "2026-09-23T09:05:00Z"
    client.post(f"/api/conversations/{KEY}/seen")
    after = client.get(f"/api/conversations/{KEY}").json()

    assert after["updated_at"] > before["updated_at"]
    assert after["etag"] == before["etag"]


def test_a_mention_on_someone_elses_pr_reads_as_a_mention_and_the_pr_bodys_as_its_own_kind():
    board = board_on(fake_threads(), is_author=False)
    github = board.stage.github
    github.prs[THE_PR].state = replace(github.prs[THE_PR].state, body="cc @octocat")
    on_github(github, "IC_1", said(1, "@octocat ping", author="anna"), kind=CommentKind.ISSUE,
              path=None, line=None, pr=THE_PR)
    on_github(github, "PRRT_1", said(2, "rename this", author="anna"), pr=THE_PR)
    board.stage.hear(THE_PR)

    answer = client_of(board).get("/api/conversations")

    assert {thread["key"]: (thread["kind"], thread["mention"])
            for thread in answer.json()["conversations"]} == {
        "IC_1": ("issue", True), "pr-body": ("pr-body", True), "PRRT_1": ("review", False)}


def test_a_thread_on_someone_elses_pr_with_no_verdict_yet_reads_as_not_yet_read():
    board = board_on(fake_threads(), is_author=False)
    on_github(board.stage.github, "PRRT_1", said(2, "rename this", author="anna"), pr=THE_PR)
    board.stage.hear(THE_PR)

    answer = client_of(board).get("/api/conversations")

    [thread] = answer.json()["conversations"]
    assert (thread["state"], thread["unread"]) == ("ready", True)


def corrupt(tmp_path, key):
    path = thread_file(tmp_path, THE_PR, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not a record")


def test_one_unreadable_record_neither_hides_nor_fails_the_others(tmp_path):
    board = disk_board(tmp_path)
    card(board, said(1, "one"), key="PRRT_1")
    card(board, said(2, "two"), key="PRRT_2")
    corrupt(tmp_path, "PRRT_shredded")

    answer = client_of(board).get("/api/conversations")

    assert answer.status_code == 200
    assert answer.json()["unreadable"] == ["PRRT_shredded"]
    assert {thread["key"] for thread in answer.json()["conversations"]} == {
        "PRRT_1", "PRRT_2"}


def test_a_thread_whose_newest_comment_is_recent_comes_first():
    moment = Moment("2026-09-23T09:00:00Z")
    board = board_on(fake_threads(clock=moment))
    card(board, said(2, "two", author="ameier", created_at="2026-09-22T09:00:00Z"),
         key="PRRT_2")
    moment.iso = "2026-09-25T09:00:00Z"
    card(board, said(1, "one", author="ameier", created_at="2026-09-01T09:00:00Z"),
         key="PRRT_1")

    answer = client_of(board).get("/api/conversations")

    assert [thread["key"] for thread in answer.json()["conversations"]] == [
        "PRRT_2", "PRRT_1"]


def test_a_thread_that_has_never_moved_is_ordered_by_its_comments():
    moment = Moment("2026-09-10T09:00:00Z")
    board = board_on(fake_threads(clock=moment))
    card(board, said(1, "one", author="ameier", created_at="2026-09-09T09:00:00Z"),
         key="PRRT_1")
    left(board, key="PRRT_1")
    moment.iso = "2026-09-22T09:00:00Z"
    card(board, said(2, "two", author="ameier", created_at="2026-09-21T09:00:00Z"),
         key="PRRT_2")

    answer = client_of(board).get("/api/conversations")

    assert [thread["state_changed_at"] for thread in answer.json()["conversations"]] == [
        None, "2026-09-10T09:00:00Z"]
    assert [thread["key"] for thread in answer.json()["conversations"]] == [
        "PRRT_2", "PRRT_1"]


def test_a_conditional_read_of_the_collection_is_not_modified():
    client = spoke()
    first = client.get("/api/conversations")

    again = client.get("/api/conversations",
                       headers={"If-None-Match": first.headers["ETag"]})

    assert again.status_code == 304
    assert again.content == b""


def tags_by_key(answer):
    return {thread["key"]: thread["etag"]
            for thread in answer.json()["conversations"]}


def test_a_threads_own_tag_moves_only_when_that_thread_does():
    board = board_for()
    card(board, said(1, "one"), key="PRRT_1")
    card(board, said(2, "two"), key="PRRT_2")
    client = client_of(board)
    before = tags_by_key(client.get("/api/conversations"))

    card(board, said(2, "two"), said(3, "and another thing"), key="PRRT_2")
    after = tags_by_key(client.get("/api/conversations"))

    assert after["PRRT_1"] == before["PRRT_1"]
    assert after["PRRT_2"] != before["PRRT_2"]


def test_one_thread_is_read_on_its_own():
    answer = spoke().get(f"/api/conversations/{KEY}")

    assert answer.status_code == 200
    assert answer.json()["key"] == KEY
    assert answer.headers["ETag"]


def test_reading_a_thread_that_will_not_parse_says_so(tmp_path):
    corrupt(tmp_path, "PRRT_shredded")

    answer = client_of(disk_board(tmp_path)).get("/api/conversations/PRRT_shredded")

    assert answer.status_code == 500
    assert answer.json()["errors"][0]["code"] == "unreadable-record"


def test_the_operations_read_carries_the_runs_own_fields():
    board = board_for()
    card(board)
    running(board)
    with board.threads.editing(KEY) as editable:
        editable.plan([("rename it", "src/foo.py"),
                      ("update the callers", None)])
    with board.threads.editing(KEY) as editable:
        editable.step_done([1])
    sha = commit_fix(board.stage, KEY, {"src/foo.py": "renamed\n"}, pr=THE_PR)
    with board.threads.editing(KEY) as editable:
        editable.ready(sha)
    drain(board)

    answer = client_of(board).get(f"/api/conversations/{KEY}/operations")

    assert answer.status_code == 200
    assert answer.json() == [{
        "id": f"{KEY}.1",
        "conversation": KEY,
        "kind": "first",
        "state": "applied",
        "reason": None,
        "reason_code": None,
        "requested_at": STAMPED,
        "settled_at": MOMENT,
        "attempts": 1,
        "attempts_allowed": 3,
        "last_action": None,
        "progress": "1 commit",
        "plan": [{"text": "rename it", "file": "src/foo.py", "done": True},
                 {"text": "update the callers", "file": None, "done": False}],
        "onto": None,
        "conflict": None,
        "brief": None,
        "proposal": f"{KEY}.1.proposal",
        "classification": None,
    }]
    assert answer.headers["ETag"]


@pytest.mark.parametrize(("stored", "read"), [
    ("conversational", "question"), ("not-a-change", "question"), ("ambiguous", "unclear"),
    ("risky", "risky")])
def test_a_declined_run_reads_its_stored_classification_in_the_contracts_words(
        tmp_path, stored, read):
    board = disk_board(tmp_path)
    card(board)
    running(board)
    with board.threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.RISKY, "a question")
    path = thread_file(tmp_path, THE_PR, KEY)
    path.write_text(json.dumps(json.loads(path.read_text()) | {"classification": stored}))

    answer = client_of(board).get(f"/api/conversations/{KEY}/operations")

    assert answer.status_code == 200
    assert answer.json()[0]["classification"] == read, (
        "records written before the agent reported in the board's words still say "
        "conversational, ambiguous or not-a-change, which split into acknowledgement and "
        "question and reads as question, the side that still asks for a look")


def test_a_thread_the_board_is_landing_carries_a_running_approve():
    github = FakeGitHub()
    copies = FakeWorkingCopies(github)
    seen = []
    board = board_for(github=github, working_copies=copies)
    card(board)
    left(board)
    client = client_of(board)
    copies.on_push = lambda: seen.append(
        client.get(f"/api/conversations/{KEY}/operations").json())
    asked(client, "approve", reply="landed, thank you")

    drain(board)

    [landing] = seen
    [approve] = [one for one in landing if one["kind"] == "approve"]
    assert (approve["state"], approve["reply"], approve["delete_comment"]) == (
        "running", "landed, thank you", False)
    assert approve["steps"] == {"filed": False, "picked": True, "pushed": False,
                                "answered": False}
    assert approve["landed_base"] is not None


def refusing_remote(github):
    copies = FakeWorkingCopies(github)
    copies.refuse_pushes("rejected: non-fast-forward")
    return copies


def test_one_operation_is_read_by_its_id():
    answer = spoke().get(f"/api/conversations/{KEY}/operations/{KEY}.1")

    assert answer.json()["kind"] == "first"


def test_the_fast_poll_answers_only_what_is_pending_or_running():
    board = board_for()
    card(board, said(2, "two"), key="PRRT_2")
    left(board, key="PRRT_2")
    card(board, said(1, "one"), key="PRRT_1")
    running(board)
    card(board, said(3, "three"), key="PRRT_3")

    answer = client_of(board).get("/api/operations")

    assert answer.status_code == 200
    assert {one["conversation"] for one in answer.json()} == {"PRRT_1", "PRRT_3"}
    assert answer.headers["ETag"]


def test_a_session_is_running_until_it_reports():
    board = board_for()
    card(board)
    left(board)
    board.stage.agent_runs.pr_processes.open(THE_PR, Path(WORKTREE))
    with board.threads.editing(KEY) as editable:
        editable.start_session()
    drain(board)

    answer = client_of(board).get("/api/operations")

    [session] = answer.json()
    assert session["kind"] == "start-session"
    assert session["state"] == "running"
    assert session["steer"] is None


def reworked(**runs):
    moment = Moment("2026-09-20T09:00:00Z")
    board = board_on(fake_threads(clock=moment))
    card(board)
    start_run(board.stage, board.threads)
    moment.iso = "2026-09-20T09:20:00Z"
    sha = commit_fix(board.stage, KEY, {"src/foo.py": "renamed\n"}, pr=THE_PR)
    with board.threads.editing(KEY) as editable:
        editable.ready(sha)
    drain(board)
    moment.iso = "2026-09-21T09:00:00Z"
    client = client_of(board)
    rework = asked(client, "rework", note="the other way").json()["operation"]["id"]
    if runs:
        board.stage.agent_runs.script(Outcome(**runs))
        drain(board)
    return board, client, rework, moment


def test_the_first_run_keeps_its_id_once_the_thread_is_sent_back():
    _, client, rework, _ = reworked()

    first = client.get(f"/api/conversations/{KEY}/operations/{KEY}.1")
    listed = client.get(f"/api/conversations/{KEY}/operations")

    assert first.status_code == 200
    assert (first.json()["kind"], first.json()["state"]) == ("first", "applied")
    assert [one["id"] for one in listed.json()] == [f"{KEY}.1", rework]


def test_a_summary_carries_the_stamps_the_history_holds():
    _, client, _, _ = reworked()

    answer = client.get(f"/api/conversations/{KEY}")

    first, rework = answer.json()["operations"]
    assert (first["requested_at"], first["settled_at"]) == (
        "2026-09-20T09:00:00.000000Z", "2026-09-20T09:20:00Z")
    assert (rework["requested_at"], rework["settled_at"]) == (
        "2026-09-21T09:00:00Z", None)


def test_only_the_run_the_fix_is_on_carries_the_plan():
    board, client, _, _ = reworked(finishes=False)
    with board.threads.editing(KEY) as editable:
        editable.plan([("rename it", None), ("update the callers", None)])
    with board.threads.editing(KEY) as editable:
        editable.step_done([1])

    answer = client.get(f"/api/conversations/{KEY}")

    first, rework = answer.json()["operations"]
    assert (first["steps_done"], first["steps_total"]) == (None, None)
    assert (rework["steps_done"], rework["steps_total"]) == (1, 2)


def test_a_kind_that_does_not_attempt_carries_no_attempt_count():
    board = board_for()
    card(board)
    left(board)
    client = client_of(board)
    asked(client, "defer", until="manual")
    drain(board)

    answer = client.get(f"/api/conversations/{KEY}")

    defer = answer.json()["operations"][1]
    assert defer["kind"] == "defer"
    assert (defer["attempts"], defer["attempts_allowed"]) == (None, None)


def test_the_proposal_names_the_run_that_left_it_and_when():
    board, client, rework, moment = reworked(finishes=False)
    moment.iso = "2026-09-21T09:30:00Z"
    sha = commit_fix(board.stage, KEY, {"src/foo.py": "the other way\n"}, pr=THE_PR)
    with board.threads.editing(KEY) as editable:
        editable.ready(sha)
    drain(board)

    answer = client.get(f"/api/conversations/{KEY}/proposals")

    [proposal] = answer.json()
    assert proposal["id"] == f"{rework}.proposal"
    assert proposal["operation"] == rework
    assert proposal["created_at"] == "2026-09-21T09:30:00Z"


def repo_of(before, working_copies=None):
    copies = working_copies or FakeWorkingCopies()
    base = copies.add_repo(Path(WORKTREE), before, "first")
    copies.place(THE_PR, WORKTREE)
    return copies, base


def left_on(copies, after, message="check first", **ready):
    board = board_for(working_copies=copies)
    card(board)
    head = left(board, after, message=message, **ready)
    return board, head


def test_the_proposals_read_carries_what_the_run_left_behind():
    copies, base = repo_of({"src/foo.py": "a\nb\n"})
    board, head = left_on(copies, {"src/foo.py": "c\nd\ne\nb\n"},
                          "Rename the helper\n\nIt said the wrong thing.\n",
                          summary="renamed the helper", note="the callers were fine",
                          confidence="high", confidence_note="the tests cover it",
                          tests="passed", tests_note="ran the unit suite")

    answer = client_of(board).get(f"/api/conversations/{KEY}/proposals")

    assert answer.status_code == 200
    assert answer.json() == [{
        "directory": str(copies.thread_checkout(THE_PR, KEY)),
        "id": f"{KEY}.1.proposal",
        "kind": "commit",
        "reply": None,
        "ticket": None,
        "operation": f"{KEY}.1",
        "conversation": KEY,
        "created_at": MOMENT,
        "updated_at": MOMENT,
        "commits": {"base": base, "head": head},
        "summary": "renamed the helper",
        "agent_note": "the callers were fine",
        "confidence": "high",
        "confidence_note": "the tests cover it",
        "tests": "passed",
        "tests_note": "ran the unit suite",
        "commit_message": "Rename the helper\n\nIt said the wrong thing.\n",
    }]
    assert answer.headers["ETag"]


def test_moving_the_base_moves_the_proposals_commits_and_its_stamp():
    moment = Moment("2026-09-20T09:00:00Z")
    board = board_on(fake_threads(clock=moment))
    card(board)
    head = left(board)
    client = client_of(board)
    [before] = client.get(f"/api/conversations/{KEY}/proposals").json()

    moment.iso = "2026-09-20T10:00:00Z"
    with board.threads.editing(KEY) as editable:
        editable.move_base(head)
    [after] = client.get(f"/api/conversations/{KEY}/proposals").json()

    assert (before["updated_at"], after["updated_at"]) == (
        "2026-09-20T09:00:00Z", "2026-09-20T10:00:00Z")
    assert after["commits"] == {"base": head, "head": head}


def replied(board, classification=Classification.QUESTION, body="It runs once per poll."):
    start_run(board.stage, board.threads)
    with board.threads.editing(KEY) as editable:
        editable.not_a_fix(classification, body)
    drain(board)


def test_a_proposed_reply_is_read_as_a_reply_with_no_commit():
    board = board_for()
    card(board)
    replied(board)

    [proposal] = client_of(board).get(f"/api/conversations/{KEY}/proposals").json()

    assert (proposal["kind"], proposal["reply"]) == ("reply", "It runs once per poll.")
    assert (proposal["commits"], proposal["commit_message"]) == (None, None)


def test_accepting_a_proposed_reply_answers_the_thread_landing_until_the_reply_is_posted():
    board = board_for()
    card(board)
    replied(board)
    client = client_of(board)
    tag = client.get(f"/api/conversations/{KEY}").json()["etag"]

    answer = client.post(f"/api/conversations/{KEY}/operations:approve",
                         headers={"If-Match": tag}, json={"reply": "It runs once per poll."})
    drain(board)

    assert answer.json()["conversation"]["state"] == "landing"
    assert client.get(f"/api/conversations/{KEY}").json()["state"] == "done"


def test_a_proposed_commit_is_read_as_a_commit_with_no_reply():
    board = board_for()
    card(board)
    left(board)

    [proposal] = client_of(board).get(f"/api/conversations/{KEY}/proposals").json()

    assert (proposal["kind"], proposal["reply"]) == ("commit", None)


def test_a_proposed_ticket_is_read_with_its_project_title_body_and_reply():
    board = board_for()
    card(board)
    start_run(board.stage, board.threads)
    with board.threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.OUT_OF_SCOPE, "I've proposed a ticket for it.",
                           ticket_project="PROJ", ticket_title="Cache models",
                           ticket_body="Each export reads its model again.")
    drain(board)

    [proposal] = client_of(board).get(f"/api/conversations/{KEY}/proposals").json()

    assert (proposal["kind"], proposal["reply"]) == ("ticket", "I've proposed a ticket for it.")
    assert proposal["ticket"] == {"project": "PROJ", "title": "Cache models",
                                  "body": "Each export reads its model again."}
    assert (proposal["commits"], proposal["commit_message"]) == (None, None)


def test_an_accepted_ticket_is_filed_as_edited_and_its_landing_shows_the_filing():
    board = board_for()
    card(board)
    start_run(board.stage, board.threads)
    with board.threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.OUT_OF_SCOPE, "I've proposed a ticket for it.",
                           ticket_project="PROJ", ticket_title="Cache models",
                           ticket_body="Each export reads its model again.")
    drain(board)
    client = client_of(board)
    asked(client, "approve", reply="Filed it.", ticket={
        "project": "WEB", "title": "One model cache", "body": "Exports share it."})
    drain(board)
    filing = client.get(f"/api/conversations/{KEY}/operations").json()
    [being_filed] = client.get(f"/api/conversations/{KEY}/proposals").json()

    with board.threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.OUT_OF_SCOPE, "", filed_key="WEB-12",
                           filed_url="https://example.atlassian.net/browse/WEB-12")
    drain(board)
    landed = client.get(f"/api/conversations/{KEY}/operations").json()

    [filed] = [started.work.fix for started in board.stage.agent_runs.started
               if isinstance(started.work, FilingTicket)]
    assert (filed.ticket_project, filed.ticket_title, filed.ticket_body) == (
        "WEB", "One model cache", "Exports share it.")
    assert [(one["kind"], one["state"]) for one in filing[-2:]] == [
        ("approve", "requeued"), ("file", "running")]
    assert (being_filed["kind"], being_filed["ticket"]["title"]) == ("ticket", "One model cache")
    [approve] = [one for one in landed if one["kind"] == "approve"]
    assert approve["state"] == "applied"
    assert approve["steps"] == {"filed": True, "picked": False, "pushed": False,
                                "answered": True}
    assert (approve["ticket_key"], approve["ticket_url"]) == (
        "WEB-12", "https://example.atlassian.net/browse/WEB-12")
    assert landed[-1]["kind"] == "file" and landed[-1]["state"] == "applied"
    [summarised] = [one for one in client.get(f"/api/conversations/{KEY}").json()["operations"]
                    if one["kind"] == "approve"]
    assert (summarised["lands"], summarised["ticket_key"]) == ("ticket", "WEB-12")


def test_a_thread_no_agent_has_finished_has_no_proposals():
    answer = spoke().get(f"/api/conversations/{KEY}/proposals")

    assert answer.json() == []


def test_one_proposal_is_read_by_its_id():
    board = board_for()
    card(board)
    left(board, summary="renamed the helper")

    answer = client_of(board).get(f"/api/conversations/{KEY}/proposals/{KEY}.1.proposal")

    assert answer.json()["summary"] == "renamed the helper"


def scripted_diff(files):
    copies = FakeWorkingCopies()
    copies.show_diff(files)
    return copies


ONE_FILE = (FileDiff(
    path="src/foo.py", old_path=None, status="modified", added=1, removed=0,
    is_binary=False,
    hunks=(DiffHunk(old_start=1, old_lines=1, new_start=1, new_lines=2,
                    section="def write():",
                    lines=(DiffLine(kind="context", old_line=1, new_line=1,
                                    text="def write():"),
                           DiffLine(kind="added", old_line=None, new_line=2,
                                    text="    check()"))),),),)


def landed_in(copies, after, before=None):
    _, base = repo_of(before or {"src/foo.py": "def write():\n"}, copies)
    board, head = left_on(copies, after)
    return board, base, head


def diff_of(board, base, head):
    return client_of(board).get(f"/api/diffs/{base}..{head}")


def test_the_diff_read_answers_files_hunks_and_lines():
    board, base, head = landed_in(scripted_diff(ONE_FILE), {
        "src/foo.py": "def write():\n    check()\n    more()\n"})

    answer = diff_of(board, base, head)

    assert answer.status_code == 200
    assert answer.json() == {
        "base": base,
        "head": head,
        "files": [{
            "path": "src/foo.py", "old_path": None, "status": "modified",
            "added": 1, "removed": 0, "is_binary": False,
            "line_count": 3,
            "hunks": [{
                "old_start": 1, "old_lines": 1, "new_start": 1,
                "new_lines": 2, "section": "def write():",
                "lines": [
                    {"kind": "context", "old_line": 1, "new_line": 1,
                     "text": "def write():"},
                    {"kind": "added", "old_line": None, "new_line": 2,
                     "text": "    check()"},
                ]}]}],
    }
    assert answer.headers["ETag"]


def test_a_file_the_head_no_longer_holds_has_no_line_count():
    board, base, head = landed_in(scripted_diff(ONE_FILE), {"src/bar.py": "moved\n"},
                                  before={"src/bar.py": "here\n"})

    assert diff_of(board, base, head).json()["files"][0]["line_count"] is None


def test_a_diff_git_will_not_produce_says_git_failed():
    board, base, head = landed_in(scripted_diff(None),
                                  {"src/foo.py": "def write():\n    check()\n"})

    answer = diff_of(board, base, head)

    assert answer.status_code == 500
    assert answer.json()["errors"][0]["code"] == "git-failed"


def branched_from_main(copies=None, branch="feature"):
    copies = copies or FakeWorkingCopies()
    base = copies.add_repo(Path("/nonexistent/repo"), {"src/foo.py": "def write():\n"}, "first")
    head = copies.publish(branch, base, {"src/foo.py": "def write():\n    check()\n"},
                          "check first")
    copies.publish("main", base, {"src/elsewhere.py": "merged since\n"}, "someone else's")
    copies.add_worktree(WORKTREE, None)
    copies.check_out(WORKTREE, branch)
    copies.place(THE_PR, WORKTREE)
    copies.fetch_pr_branch(Path(WORKTREE), THE_PR, branch, "main")
    return copies, base, head


def pr_board(copies):
    return client_of(board_on(fake_threads(working_copies=copies), base_branch="main"))


def pr_diff_of(copies, **params):
    return pr_board(copies).get("/api/pull-request/diff", params=params)


def test_the_pull_requests_diff_runs_from_the_merge_base_to_the_head():
    copies, base, head = branched_from_main()

    answer = pr_diff_of(copies)

    assert answer.status_code == 200
    assert answer.json() == {
        "base": base,
        "head": head,
        "files": [{
            "path": "src/foo.py", "old_path": None, "status": "modified",
            "added": 1, "removed": 0, "is_binary": False,
            "line_count": 2,
            "hunks": [{
                "old_start": 1, "old_lines": 1, "new_start": 1,
                "new_lines": 2, "section": None,
                "lines": [
                    {"kind": "context", "old_line": 1, "new_line": 1,
                     "text": "def write():"},
                    {"kind": "added", "old_line": None, "new_line": 2,
                     "text": "    check()"},
                ]}]}],
    }
    assert answer.headers["ETag"]


def test_the_origin_diff_leaves_out_commits_the_worktree_has_not_pushed():
    copies, _, pushed = branched_from_main()
    copies.commit(WORKTREE, {"src/foo.py": "not pushed\n"}, "local only")

    assert pr_diff_of(copies, source="origin").json()["head"] == pushed


def test_the_local_diff_runs_to_the_worktrees_own_commit():
    copies, _, _ = branched_from_main()
    local = copies.commit(WORKTREE, {"src/foo.py": "not pushed\n"}, "local only")

    answer = pr_diff_of(copies, source="local")

    assert answer.json()["head"] == local
    assert answer.json()["files"][0]["hunks"][0]["lines"][-1]["text"] == "not pushed"


def test_fetching_brings_what_was_pushed_since_into_the_origin_diff():
    copies, _, pushed = branched_from_main()
    newer = copies.publish("feature", pushed, {"src/foo.py": "pushed since\n"}, "elsewhere")
    client = pr_board(copies)
    before = client.get("/api/pull-request/diff").json()["head"]

    fetched = client.post("/api/pull-request:fetch")

    assert fetched.status_code == 204
    assert (before, client.get("/api/pull-request/diff").json()["head"]) == (pushed, newer)


def test_a_fetch_git_refuses_says_git_failed():
    copies, _, _ = branched_from_main()
    copies.check_out(WORKTREE, "never-pushed")

    answer = pr_board(copies).post("/api/pull-request:fetch")

    assert answer.status_code == 500
    assert answer.json()["errors"][0]["code"] == "git-failed"


def test_a_pull_request_diff_git_will_not_produce_says_git_failed():
    copies, _, _ = branched_from_main(scripted_diff(None))

    answer = pr_diff_of(copies)

    assert answer.status_code == 500
    assert answer.json()["errors"][0]["code"] == "git-failed"


def not_text():
    copies = FakeWorkingCopies()
    copies.serve_as_binary("src/foo.py")
    return copies


def reading(files, copies=None, **params):
    copies, sha = repo_of(files, copies)
    return sha, client_of(board_for(working_copies=copies)).get(
        "/api/files", params={"sha": sha, "path": "src/foo.py"} | params)


def test_the_files_read_answers_numbered_lines():
    sha, answer = reading({"src/foo.py": "one\ntwo\nthree\n"}, from_line=2, to_line=3)

    assert answer.status_code == 200
    assert answer.json() == {
        "sha": sha, "path": "src/foo.py", "from_line": 2, "to_line": 3,
        "truncated": False,
        "lines": [{"number": 2, "text": "two"},
                  {"number": 3, "text": "three"}],
    }
    assert answer.headers["ETag"]


def test_a_file_read_without_a_range_starts_at_the_first_line():
    _, answer = reading({"src/foo.py": "one\ntwo\n"})

    assert answer.json()["from_line"] == 1
    assert answer.json()["to_line"] == 2
    assert answer.json()["truncated"] is False


def test_a_file_longer_than_the_ceiling_says_it_was_cut():
    whole = "\n".join(str(number) for number in range(1, 2502))

    _, answer = reading({"src/foo.py": whole})

    assert answer.json()["to_line"] == 2000
    assert answer.json()["truncated"] is True
    assert len(answer.json()["lines"]) == 2000


def test_a_range_wider_than_the_ceiling_is_refused_rather_than_clipped():
    whole = "\n".join(str(number) for number in range(1, 5000))

    _, answer = reading({"src/foo.py": whole}, from_line=1, to_line=4000)

    assert answer.status_code == 400
    assert answer.json()["errors"][0]["code"] == "range-too-wide"
    assert "lines" not in answer.json()


def test_a_file_that_is_not_text_is_refused():
    _, answer = reading({"src/foo.py": "a picture"}, not_text())

    assert answer.status_code == 415
    assert answer.json()["errors"][0]["code"] == "not-text"


def test_the_comments_read_carries_what_people_wrote():
    answer = spoke().get(f"/api/conversations/{KEY}/comments")

    assert answer.status_code == 200
    assert answer.json() == [{
        "id": COMMENT_ID,
        "author": "reviewer",
        "created_at": EARLIER,
        "review_state": None,
        "body": BODY,
        "updated_at": EARLIER,
        "html_url": f"https://github.com/{REPO}/pull/{PR}#discussion_r{COMMENT_ID}",
        "posted_by_board": False,
        "deleted": False,
        "deleted_by_board": False,
    }]
    assert answer.headers["ETag"]


def test_a_comment_the_board_posted_says_so():
    board = board_for()
    card(board)
    left(board)
    client = client_of(board)
    asked(client, "reply", body="on it")
    drain(board)
    hear(board.threads)

    answer = client.get(f"/api/conversations/{KEY}/comments")

    assert [comment["posted_by_board"] for comment in answer.json()
            if comment["body"] == "on it"] == [True]


def test_one_comment_is_read_by_its_github_id():
    answer = spoke().get(f"/api/conversations/{KEY}/comments/{COMMENT_ID}")

    assert answer.json()["body"] == BODY
