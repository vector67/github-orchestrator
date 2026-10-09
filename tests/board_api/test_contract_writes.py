from pathlib import Path

import pytest

from github_orchestrator.agent_runs.fake import Outcome
from github_orchestrator.conversation import Classification, ConversationState
from github_orchestrator.github import CommentKind
from github_orchestrator.github.fake import FakeGitHub, GhError
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.board_api.support import (
    ACCOUNT,
    BODY,
    COMMENT_ID,
    KEY,
    PORT,
    THE_PR,
    WORKTREE,
    board_on,
    client_of,
    disk_board,
    fake_threads,
    heard_on,
    proposed,
    running,
)
from tests.board_api.test_contract_reads import corrupt
from tests.conversation.support import at, said, start_run

NOW = "2026-09-07T12:00:00Z"


def board_of(github=None, working_copies=None, **pr_state):
    return board_on(fake_threads(github or FakeGitHub(account=ACCOUNT), working_copies,
                                 clock=at(NOW)), **pr_state)


def heard(*comments, **fields):
    board = board_of()
    heard_on(board, KEY, *comments, **fields)
    return board


@pytest.fixture
def board():
    return heard()


@pytest.fixture
def at_work(board):
    running(board)
    return board


@pytest.fixture
def ready(board):
    proposed(board)
    return board


def tag_of(client, key=KEY):
    return client.get(f"/api/conversations/{key}").json()["etag"]


def asked(client, verb, key=KEY, tag=None, **body):
    headers = {"If-Match": tag if tag is not None else tag_of(client, key)}
    return client.post(f"/api/conversations/{key}/operations:{verb}",
                       headers=headers, json=body)


def drained(board):
    board.threads.tick(FakeNotifications(), on_hold=False)
    return board.threads.get(KEY)


def settled_by(board, verb, **body):
    answer = asked(client_of(board), verb, **body)
    assert answer.status_code == 202, answer.json()
    return drained(board)


def pending_kinds(client, key=KEY):
    return [one["kind"] for one in client.get(f"/api/conversations/{key}/operations").json()
            if one["state"] == "pending"]


def test_stop_hands_a_running_thread_back(at_work):
    answer = asked(client_of(at_work), "stop")

    assert answer.status_code == 202
    halted = drained(at_work)
    assert halted.standing is ConversationState.READY
    assert halted.state_changed_at == NOW


def test_stop_answers_the_operation_it_queued(at_work):
    answer = asked(client_of(at_work), "stop")

    operation_id = answer.json()["operation"]["id"]
    assert answer.json()["operation"] == {
        "id": operation_id, "conversation": KEY, "kind": "stop",
        "state": "pending", "reason": None, "reason_code": None,
        "requested_at": NOW, "settled_at": None, "stopped": f"{KEY}.1"}
    assert answer.headers["Location"] == (
        f"/api/conversations/{KEY}/operations/{operation_id}")


def test_the_operation_a_202_names_can_be_read_before_the_drain_takes_it(at_work):
    client = client_of(at_work)
    answer = asked(client, "stop")

    read = client.get(answer.headers["Location"])

    assert read.status_code == 200
    assert read.json() == answer.json()["operation"]


def test_the_drain_records_the_operation_under_the_id_the_202_gave(at_work):
    client = client_of(at_work)
    answer = asked(client, "stop")

    drained(at_work)
    settled = client.get(answer.headers["Location"])

    assert settled.status_code == 200
    assert settled.json()["state"] == "applied"
    assert settled.json()["requested_at"] == NOW
    stopped = client.get(
        f"/api/conversations/{KEY}/operations/{KEY}.1").json()
    assert (stopped["state"], stopped["reason_code"]) == ("refused",
                                                          "withdrawn")


def landing(board):
    board.stage.working_copies.fail_pushes(OSError("the network went away"))
    answer = asked(client_of(board), "approve", reply="landing this")
    assert answer.status_code == 202, answer.json()
    assert drained(board).standing is ConversationState.LANDING
    return board


def test_stop_hands_a_landing_back_with_its_proposal_waiting(ready):
    client = client_of(landing(ready))
    [approve] = [one["id"] for one in client.get(f"/api/conversations/{KEY}/operations").json()
                 if one["kind"] == "approve"]

    answer = asked(client, "stop")

    assert answer.status_code == 202, answer.json()
    assert answer.json()["operation"]["stopped"] == approve
    halted = drained(ready)
    assert halted.standing is ConversationState.READY
    assert halted.fix.is_proposed
    withdrawn = client.get(f"/api/conversations/{KEY}/operations/{approve}").json()
    assert (withdrawn["state"], withdrawn["reason_code"]) == ("refused", "withdrawn")
    assert pending_kinds(client) == []


def test_stopping_a_landing_takes_its_unpushed_commit_off_the_pr_branch(ready):
    copies = ready.stage.working_copies
    before = copies.head_of(WORKTREE)
    landing(ready)
    assert copies.head_of(WORKTREE) != before

    settled_by(ready, "stop")

    assert copies.head_of(WORKTREE) == before


def test_a_landing_stopped_after_the_branch_moved_says_its_commit_is_still_there(ready):
    client = client_of(landing(ready))
    moved = ready.stage.working_copies.commit(WORKTREE, {"h": "meanwhile\n"}, "meanwhile")

    settled_by(ready, "stop")

    assert ready.stage.working_copies.head_of(WORKTREE) == moved
    [approve] = [one for one in client.get(f"/api/conversations/{KEY}/operations").json()
                 if one["kind"] == "approve"]
    assert (approve["state"], approve["reason_code"]) == ("refused", "withdrawn")
    assert "still on the PR branch" in approve["reason"]


def test_a_stopped_landing_is_not_pushed_once_the_network_is_back(ready):
    copies = ready.stage.working_copies
    client = client_of(landing(ready))
    asked(client, "stop")
    copies.fail_pushes(None)
    pushes = copies.pushes

    halted = drained(ready)

    assert copies.pushes == pushes
    assert halted.fix.is_proposed and not halted.fix.pushed


def test_a_landing_stopped_before_its_pick_hands_the_proposal_back(ready):
    copies = ready.stage.working_copies
    before = copies.head_of(WORKTREE)

    def git_went_away():
        raise OSError("git went away")

    copies.on_pick = git_went_away
    asked(client_of(ready), "approve", reply="landing this")
    assert drained(ready).standing is ConversationState.LANDING

    halted = settled_by(ready, "stop")

    assert halted.standing is ConversationState.READY
    assert halted.fix.is_proposed
    assert copies.head_of(WORKTREE) == before


class RepliesRefused(FakeGitHub):
    def reply_to_thread(self, key, body):
        raise GhError("gh api failed: HTTP 502")


def test_stop_refuses_a_landing_whose_fix_is_already_pushed():
    github = RepliesRefused(account=ACCOUNT)
    board = board_of(github)
    heard_on(board)
    proposed(board)
    pushed = settled_by(board, "approve", reply="landing this")
    assert pushed.fix.pushed and pushed.fix.reply_error

    answer = asked(client_of(board), "stop")

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "nothing-in-flight"
    assert board.stage.working_copies.head_of(WORKTREE) == str(pushed.fix.landed_sha)


def test_queuing_a_verb_moves_the_threads_tag(ready):
    client = client_of(ready)
    tag = tag_of(client)
    asked(client, "approve", tag=tag, reply="landing this")

    answer = asked(client, "reject", tag=tag)

    assert tag_of(client) != tag, (
        "the queued approve is on the thread's operations, so the tag that "
        "hashes them has moved")
    assert answer.status_code == 412


def test_stop_refuses_a_thread_whose_run_has_left_a_proposal(ready):
    client = client_of(ready)
    tag = tag_of(client)

    answer = asked(client, "stop", tag=tag)

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "proposal-exists"
    assert tag_of(client) == tag


def test_a_tag_from_before_the_thread_moved_is_refused(at_work):
    client = client_of(at_work)
    tag = tag_of(client)

    answer = asked(client, "stop", tag='"7b3c1f"')

    assert answer.status_code == 412
    assert answer.json()["errors"][0]["code"] == "precondition-failed"
    assert tag_of(client) == tag


def test_a_write_without_the_precondition_is_malformed(at_work):
    client = client_of(at_work)
    tag = tag_of(client)

    answer = client.post(f"/api/conversations/{KEY}/operations:stop")

    assert answer.status_code == 400
    assert answer.json()["errors"][0]["code"] == "malformed-request"
    assert tag_of(client) == tag


def test_approve_lands_the_proposal_and_answers_the_comment(ready):
    landed = settled_by(ready, "approve", reply="landing this")

    assert landed.fix.pushed
    assert landed.standing is ConversationState.DONE
    assert landed.state_changed_at == NOW
    [reply] = [comment.body for comment in ready.stage.github.thread(KEY).comments[1:]]
    assert reply.startswith("landing this")


def test_a_ticked_approve_lands_the_proposal_and_resolves_the_thread(ready):
    answer = asked(client_of(ready), "approve", resolve=True)

    assert answer.status_code == 202
    landed = drained(ready)
    assert landed.fix.pushed
    assert ready.stage.github.thread(KEY).is_resolved


def test_an_approve_carries_the_message_the_commit_lands_with(ready):
    settled_by(ready, "approve", message="Rename the helper, as asked")

    copies = ready.stage.working_copies
    assert copies.commits[copies.head_of(WORKTREE)].message == "Rename the helper, as asked"


def test_a_ticked_approve_on_a_comment_with_no_thread_is_refused_up_front():
    board = heard(kind=CommentKind.ISSUE)
    proposed(board)
    client = client_of(board)
    tag = tag_of(client)

    answer = asked(client, "approve", tag=tag, resolve=True)

    assert answer.json()["errors"][0]["code"] == "malformed-request"
    assert tag_of(client) == tag


def test_approve_refuses_a_thread_with_nothing_to_land(at_work):
    with at_work.threads.editing(KEY) as editable:
        editable.not_a_fix(Classification.RISKY, "it wants a schema change")

    answer = asked(client_of(at_work), "approve", reply="landing this")

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "no-proposal"


def test_rework_sends_the_proposal_back_with_its_brief(ready):
    answer = asked(client_of(ready), "rework", note="the other way round",
                   pointed=[{"file": "f.py", "line": 3, "text": "here"}])

    assert answer.status_code == 202
    assert answer.json()["operation"]["brief"]["note"] == "the other way round"
    sent_back = drained(ready)
    assert sent_back.standing is ConversationState.REWORK
    assert sent_back.fix.run.brief.pointed[0].text == "here"
    assert sent_back.state_changed_at == NOW


def test_rework_refuses_a_brief_with_nothing_in_it(ready):
    answer = asked(client_of(ready), "rework")

    assert answer.status_code == 400
    assert answer.json()["errors"][0]["code"] == "empty-brief"


def test_rework_refuses_a_thread_a_run_is_already_working_on(at_work):
    answer = asked(client_of(at_work), "rework", note="again")

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "operation-outstanding"


def test_start_session_opens_a_session_on_the_thread(ready):
    ready.stage.agent_runs.pr_processes.open(THE_PR, Path(WORKTREE))

    answer = asked(client_of(ready), "start-session", steer="try the other way")

    assert answer.status_code == 202
    assert answer.json()["operation"]["steer"] == "try the other way"
    steered = drained(ready)
    assert steered.standing is ConversationState.IN_SESSION
    assert steered.state_changed_at == NOW


def test_start_session_hands_the_session_the_lines_it_was_pointed_at(ready):
    ready.stage.agent_runs.pr_processes.open(THE_PR, Path(WORKTREE))

    asked(client_of(ready), "start-session", steer="the other way round",
          pointed=[{"file": "f.py", "line": 3, "text": "here"}])
    drained(ready)

    [opened] = ready.stage.agent_runs.sessions
    assert [one.text for one in opened.fix.pointed] == ["here"]


def test_start_session_refuses_a_thread_that_is_parked(ready):
    settled_by(ready, "defer", until="manual")

    answer = asked(client_of(ready), "start-session")

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "parked"


def test_retry_queues_the_agent_again(board):
    attempts = board.threads.get(KEY).run_holder.attempts_allowed
    for _ in range(attempts):
        start_run(board.stage, board.threads)
        with board.threads.editing(KEY) as editable:
            editable.fail("the tests would not run")
    assert board.threads.get(KEY).fix.has_failed
    board.stage.agent_runs.script(Outcome(finishes=False))

    again = settled_by(board, "retry")

    assert again.standing is ConversationState.WORKING
    assert again.fix.attempts == 1
    assert again.state_changed_at == NOW


def test_retry_refuses_a_thread_that_already_has_a_proposal(ready):
    answer = asked(client_of(ready), "retry")

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "proposal-exists"


def test_resolve_closes_the_thread(ready):
    answer = asked(client_of(ready), "resolve")

    assert answer.status_code == 202
    assert answer.json()["operation"]["kind"] == "resolve"
    closed = drained(ready)
    assert closed.standing is ConversationState.DONE
    assert closed.state_changed_at == NOW


def test_a_ticked_resolve_resolves_the_thread_on_github(ready):
    answer = asked(client_of(ready), "resolve", resolve=True)

    assert answer.status_code == 202
    assert drained(ready).standing is ConversationState.DONE
    assert ready.stage.github.thread(KEY).is_resolved


def test_resolve_refuses_a_thread_that_is_already_closed(ready):
    settled_by(ready, "resolve")

    answer = asked(client_of(ready), "resolve")

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "already-closed"


def test_reject_turns_a_finished_proposal_down(ready):
    answer = asked(client_of(ready), "reject")

    assert answer.status_code == 202
    assert answer.json()["operation"]["kind"] == "reject"
    turned_down = drained(ready)
    assert turned_down.standing is ConversationState.DONE
    assert turned_down.state_changed_at == NOW


def test_reject_refuses_a_thread_with_work_running(at_work):
    client = client_of(at_work)
    tag = tag_of(client)

    answer = asked(client, "reject", tag=tag)

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "work-in-flight"
    assert tag_of(client) == tag


def test_reject_refuses_a_thread_with_no_proposal_to_turn_down():
    board = board_of(is_author=False)
    heard_on(board, KEY, said(COMMENT_ID, BODY), said(102, "agreed", author=ACCOUNT))

    answer = asked(client_of(board), "reject")

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "no-proposal"


def test_defer_parks_the_thread_until_its_wake_condition(ready):
    answer = asked(client_of(ready), "defer", until="ci", note="after the ci")

    assert answer.status_code == 202
    assert answer.json()["operation"]["until"] == "ci"
    parked = drained(ready)
    assert parked.standing is ConversationState.DEFERRED
    assert parked.wake_on == "ci"
    assert parked.defer_note == "after the ci"
    assert parked.state_changed_at == NOW


def test_defer_until_the_next_push_waits_on_the_head_the_drain_reads():
    board = board_of(head_sha="8f73fe8")
    heard_on(board)
    proposed(board)

    parked = settled_by(board, "defer", until="push")

    assert parked.wake_on == "push:8f73fe8"


def test_a_wake_condition_the_board_cannot_parse_is_malformed(ready):
    answer = asked(client_of(ready), "defer", until="a week on tuesday")

    assert answer.status_code == 400
    assert answer.json()["errors"][0]["code"] == "malformed-request"


def refusing_remote(github):
    copies = FakeWorkingCopies(github)
    copies.refuse_pushes("rejected: non-fast-forward")
    return copies


def test_defer_refuses_a_landing_it_cannot_park():
    github = FakeGitHub(account=ACCOUNT)
    board = board_of(github, refusing_remote(github))
    heard_on(board)
    proposed(board)
    settled_by(board, "approve", reply="landing this")

    answer = asked(client_of(board), "defer", until="manual")

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "operation-outstanding"


def test_unpark_brings_a_deferred_thread_back(ready):
    settled_by(ready, "defer", until="manual")

    back = settled_by(ready, "unpark")

    assert back.standing is ConversationState.READY
    assert back.state_changed_at == NOW


def test_unpark_refuses_a_thread_that_was_never_parked(ready):
    answer = asked(client_of(ready), "unpark")

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "not-parked"


def test_reply_posts_to_the_thread_and_parks_it_on_the_other_party(ready):
    answer = asked(client_of(ready), "reply", body="have another look")

    assert answer.status_code == 202
    assert answer.json()["operation"]["body"] == "have another look"
    spoken = drained(ready)
    assert spoken.standing is ConversationState.WAITING
    assert spoken.state_changed_at == NOW


def test_reply_refuses_a_body_of_nothing_but_space(ready):
    answer = asked(client_of(ready), "reply", body="   ")

    assert answer.status_code == 400
    assert answer.json()["errors"][0]["code"] == "empty-body"


def test_reply_refuses_a_thread_that_is_closed(ready):
    settled_by(ready, "resolve")

    answer = asked(client_of(ready), "reply", body="one more thing")

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "already-closed"


def test_a_reply_longer_than_github_takes_is_refused_before_it_is_queued(ready):
    client = client_of(ready)
    tag = tag_of(client)

    answer = asked(client, "approve", tag=tag, reply="x" * (64 * 1024 + 1))

    assert answer.status_code == 413
    assert answer.json()["errors"][0]["code"] == "body-too-long"
    assert tag_of(client) == tag


def test_a_second_verb_while_the_first_is_queued_is_refused(ready):
    client = client_of(ready)
    asked(client, "approve", reply="landing this")

    answer = asked(client, "reject")

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "operation-outstanding"
    assert pending_kinds(client) == ["approve"]


def test_a_second_verb_sent_with_the_answered_threads_tag_is_refused_as_waiting(ready):
    client = client_of(ready)
    first = asked(client, "approve", reply="landing this")

    answer = asked(client, "reject", tag=first.json()["conversation"]["etag"])

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "operation-outstanding"


def _shown(conversation):
    return {name: value for name, value in conversation.items()
            if name not in ("etag", "updated_at")}


def test_a_verb_answers_the_thread_as_the_drain_then_leaves_it(at_work):
    client = client_of(at_work)
    answer = asked(client, "stop")

    projected = answer.json()["conversation"]
    drained(at_work)

    assert projected["state"] == "ready"
    assert _shown(projected) == _shown(client.get(f"/api/conversations/{KEY}").json())


def test_an_approve_answers_the_thread_landing_before_the_drain_takes_it(ready):
    answer = asked(client_of(ready), "approve", reply="landing this")

    assert answer.json()["conversation"]["state"] == "landing"
    assert answer.json()["operation"]["kind"] == "approve"


class Ticking:
    def __init__(self, iso):
        self.to(iso)

    def to(self, iso):
        self.moment = at(iso)()

    def __call__(self):
        return self.moment


def test_the_answered_thread_is_stamped_when_the_verb_was_asked():
    clock = Ticking(NOW)
    board = board_on(fake_threads(FakeGitHub(account=ACCOUNT), clock=clock))
    heard_on(board, KEY)
    running(board)
    client = client_of(board)
    clock.to("2026-09-07T12:00:05Z")

    answer = asked(client, "stop")
    read_before_the_drain = client.get(f"/api/conversations/{KEY}").json()
    clock.to("2026-09-07T12:00:09Z")
    drained(board)

    assert answer.json()["conversation"]["updated_at"] == "2026-09-07T12:00:05Z"
    assert read_before_the_drain["updated_at"] == NOW
    assert client.get(f"/api/conversations/{KEY}").json()["updated_at"] == (
        "2026-09-07T12:00:09Z")


def test_a_verb_while_a_reply_is_queued_is_refused(ready):
    client = client_of(ready)
    asked(client, "reply", body="have another look")

    answer = asked(client, "resolve")

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "operation-outstanding"
    assert pending_kinds(client) == ["reply"]


def test_a_verb_on_a_record_that_will_not_parse_says_so(tmp_path):
    corrupt(tmp_path, "PRRT_shredded")

    answer = asked(client_of(disk_board(tmp_path)), "resolve", key="PRRT_shredded",
                   tag='"7b3c1f"')

    assert answer.status_code == 500
    assert answer.json()["errors"][0]["code"] == "unreadable-record"


def test_a_write_from_another_origin_is_refused_and_queues_nothing(at_work):
    client = client_of(at_work)
    tag = tag_of(client)

    answer = client.post(f"/api/conversations/{KEY}/operations:stop",
                         headers={"If-Match": tag, "Origin": "http://evil.example"})

    assert answer.status_code == 403
    assert answer.json()["errors"][0]["code"] == "foreign-origin"
    assert tag_of(client) == tag


def test_a_write_the_board_page_sends_is_taken(at_work):
    client = client_of(at_work)

    answer = client.post(f"/api/conversations/{KEY}/operations:stop",
                         headers={"If-Match": tag_of(client),
                                  "Sec-Fetch-Site": "same-origin",
                                  "Origin": f"http://127.0.0.1:{PORT}"})

    assert answer.status_code == 202


def mine(*replies, kind=CommentKind.REVIEW):
    board = heard(said(COMMENT_ID, BODY, author=ACCOUNT), *replies, kind=kind)
    proposed(board)
    return board


def deletes(board):
    answer = asked(client_of(board), "approve", delete_comment=True)
    assert answer.status_code == 202
    return answer.json()["operation"]["delete_comment"]


def refused_delete(board):
    client = client_of(board)
    answer = asked(client, "approve", delete_comment=True)
    assert answer.status_code == 409
    [error] = answer.json()["errors"]
    assert error["code"] == "not-deletable"
    assert pending_kinds(client) == []
    return error["detail"]


def test_a_card_carrying_my_own_comment_can_be_deleted():
    assert deletes(mine()) is True


def test_a_reviewers_comment_is_never_mine_to_delete(ready):
    assert refused_delete(ready) == "reviewer wrote that comment, so it is not yours to delete"


def test_a_review_summary_has_no_delete_endpoint_so_its_delete_is_refused():
    assert refused_delete(mine(kind=CommentKind.REVIEW_SUMMARY)) == (
        "GitHub deletes no review-summary comment")


def test_a_conversation_comment_of_my_own_can_be_deleted():
    assert deletes(mine(kind=CommentKind.ISSUE)) is True


def test_a_thread_someone_else_joined_is_not_mine_to_delete():
    assert refused_delete(mine(said(99, "agreed"))) == (
        "reviewer has replied in the thread, so the comment is not yours to delete")


def test_a_thread_i_replied_to_myself_is_still_mine_to_delete():
    assert deletes(mine(said(99, "landed", author=ACCOUNT))) is True


def test_a_proposal_diff_on_a_pr_with_no_worktree_says_there_is_none(ready):
    client = client_of(ready)
    [proposal] = client.get(f"/api/conversations/{KEY}/proposals").json()
    commits = proposal["commits"]
    ready.stage.working_copies.placed.clear()

    answer = client.get(f"/api/diffs/{commits['base']}..{commits['head']}")

    assert answer.status_code == 404
    assert answer.json()["errors"][0]["code"] == "no-such-commit"
    assert "worktree is not known" in answer.json()["errors"][0]["detail"]
