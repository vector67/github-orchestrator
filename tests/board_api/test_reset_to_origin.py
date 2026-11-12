import json
from dataclasses import replace

import pytest

from github_orchestrator.board_api.fake import IDLE, FakeManagerPanel
from github_orchestrator.board_api.interface import ManagerStanding
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.thread_records.fake import FakeThreadRecords
from github_orchestrator.wiring import RecordShelves
from tests.board_api.support import (
    KEY,
    THE_PR,
    WORKTREE,
    board_on,
    branched_from_main,
    client_of,
    fake_threads,
    heard_on,
    proposed,
)

RESET = "/api/pull-request/operations:reset-to-origin"
QUEUE = "/api/pull-request/operations:queue-reset-to-origin"
CANCEL = "/api/pull-request/operations:cancel-reset-to-origin"
DIVERGED = replace(IDLE, diverged=True)
WORKING = FakeManagerPanel(now=replace(DIVERGED, working_on="ci-failed"))


def kept(records):
    return RecordShelves(records).of(THE_PR).list("reset")


def reset_board(copies, manager=None, records=None):
    serving = {"manager": manager or FakeManagerPanel(now=DIVERGED)}
    if records is not None:
        serving["records"] = records
    return client_of(board_on(fake_threads(working_copies=copies), base_branch="main",
                              branch="feature", **serving))


def shown(copies):
    return {"head": copies.head_of(WORKTREE)}


def diverged():
    copies, _, _ = branched_from_main()
    copies.commit(WORKTREE, {"src/foo.py": "local work\n"}, "local work")
    rewritten = copies.publish("feature", copies.origin["main"],
                               {"src/foo.py": "rewritten\n"}, "check first")
    return copies, rewritten


def test_resetting_to_origin_puts_the_worktree_on_origins_current_head():
    copies, rewritten = diverged()

    answer = reset_board(copies).post(RESET, json=shown(copies))

    assert answer.status_code == 204
    assert copies.head_of(WORKTREE) == rewritten


def test_a_worktree_with_uncommitted_changes_is_left_as_it_is():
    copies, _ = diverged()
    before = copies.head_of(WORKTREE)
    copies.edit(WORKTREE, "src/foo.py", "half done\n")

    answer = reset_board(copies).post(RESET, json=shown(copies))

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "uncommitted-changes"
    assert copies.head_of(WORKTREE) == before


def test_a_missing_worktree_is_refused_as_missing_not_as_uncommitted_changes():
    copies, _ = diverged()
    head = shown(copies)
    client = reset_board(copies)
    copies.lose_worktree(WORKTREE)
    copies.placed.pop(THE_PR)

    answer = client.post(RESET, json=head)

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "worktree-missing"


def test_a_worktree_an_agent_is_working_in_is_left_as_it_is():
    copies, _ = diverged()
    before = copies.head_of(WORKTREE)
    working = FakeManagerPanel(now=replace(DIVERGED, working_on="ci-failed"))

    answer = reset_board(copies, working).post(RESET, json=shown(copies))

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "agent-working"
    assert copies.head_of(WORKTREE) == before


@pytest.mark.parametrize(("manager", "code"), [
    (FakeManagerPanel(now=replace(DIVERGED, standing=ManagerStanding.GONE)), "manager-down"),
    (FakeManagerPanel(now=replace(DIVERGED, standing=ManagerStanding.STARTING)), "manager-down"),
    (FakeManagerPanel(now=replace(DIVERGED, frozen_on="someone-elses-branch")), "worktree-frozen"),
], ids=["gone", "starting", "frozen"])
def test_a_worktree_whose_manager_cannot_say_no_agent_works_in_it_is_left_as_it_is(manager, code):
    copies, _ = diverged()
    before = copies.head_of(WORKTREE)

    answer = reset_board(copies, manager).post(RESET, json=shown(copies))

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == code
    assert copies.head_of(WORKTREE) == before


@pytest.mark.parametrize(("operation", "working_on"), [(RESET, None), (QUEUE, "ci-failed")])
def test_a_worktree_only_ahead_of_origin_keeps_its_unpushed_commits(operation, working_on):
    copies, _, _ = branched_from_main()
    unpushed = copies.commit(WORKTREE, {"src/foo.py": "not pushed yet\n"}, "mine")
    only_ahead = FakeManagerPanel(now=replace(IDLE, working_on=working_on))
    records = FakeThreadRecords()

    answer = reset_board(copies, only_ahead, records).post(operation, json=shown(copies))

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "not-diverged"
    assert copies.head_of(WORKTREE) == unpushed
    assert kept(records) == {}


def test_a_reset_queued_while_an_agent_works_is_kept_for_when_its_run_ends():
    copies, _ = diverged()
    before = copies.head_of(WORKTREE)
    records = FakeThreadRecords()

    answer = reset_board(copies, WORKING, records).post(QUEUE)

    assert answer.status_code == 204
    [document] = kept(records).values()
    assert document is not None
    fields = json.loads(document)
    assert isinstance(fields.pop("queued_at"), str)
    assert fields == {"ran_at": None, "refused": None}
    assert copies.head_of(WORKTREE) == before


def test_a_reset_is_not_queued_when_no_agent_is_working():
    copies, _ = diverged()
    records = FakeThreadRecords()

    answer = reset_board(copies, records=records).post(QUEUE)

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "no-agent-working"
    assert kept(records) == {}


def test_cancelling_a_queued_reset_forgets_it():
    copies, _ = diverged()
    records = FakeThreadRecords()
    board = reset_board(copies, WORKING, records)
    board.post(QUEUE)

    answer = board.post(CANCEL)

    assert answer.status_code == 204
    assert kept(records) == {}


def test_a_fix_picked_but_not_pushed_keeps_the_worktree_from_a_reset():
    copies, _, _ = branched_from_main()
    copies.refuse_pushes("rejected: non-fast-forward")
    board = board_on(fake_threads(working_copies=copies), base_branch="main", branch="feature",
                     manager=FakeManagerPanel(now=DIVERGED))
    heard_on(board)
    proposed(board)
    client = client_of(board)
    tag = client.get(f"/api/conversations/{KEY}").json()["etag"]
    assert client.post(f"/api/conversations/{KEY}/operations:approve",
                       headers={"If-Match": tag}, json={}).status_code == 202
    board.threads.tick(FakeNotifications(), on_hold=False)
    landed = board.threads.get(KEY).fix.landed_sha
    assert landed is not None and copies.head_of(WORKTREE) == str(landed)
    copies.publish("feature", copies.origin["main"], {"src/foo.py": "rewritten\n"},
                   "check first")

    answer = client.post(RESET, json=shown(copies))

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "fix-awaits-push"
    assert answer.json()["errors"][0]["detail"] == KEY
    assert copies.head_of(WORKTREE) == str(landed)


def test_a_worktree_that_moved_since_the_page_drew_it_keeps_its_new_commit():
    copies, _ = diverged()
    drawn = shown(copies)
    moved = copies.commit(WORKTREE, {"src/bar.py": "the agent's fix\n"}, "after the page drew")

    answer = reset_board(copies).post(RESET, json=drawn)

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "worktree-moved"
    assert answer.json()["errors"][0]["detail"] == moved
    assert copies.head_of(WORKTREE) == moved
