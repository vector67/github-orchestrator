import json
import re
from pathlib import Path

from github_orchestrator.agent_runs.fake import HeldVerdicts
from github_orchestrator.conversation import Classification
from github_orchestrator.domain import Side
from github_orchestrator.github import ReviewState, ThreadComment
from github_orchestrator.github.fake import FakeGitHub, GhError, ThreadAnchor
from github_orchestrator.pr_processes.fake import FakePrProcesses
from tests.board_api.support import (
    THE_PR,
    WORKTREE,
    board_on,
    client_of,
    fake_threads,
    heard_on,
    proposed,
    rewritten,
    running,
)
from tests.board_api.test_contract_drafts import PATH, reviewing
from tests.board_api.test_contract_writes import asked
from tests.conversation.support import at, drain, lost, said, start_run

FIXTURE = Path(__file__).parents[2] / "frontend" / "tests" / "helpers" / "thread-phases.ts"
VIEWER = "octocat"
REVIEWER = "anna"
KEY = "PRRT_a"
DRAFT = "draft_0000000000000001"
COMMENT_ID = 1
SAID_AT = "2026-09-12T10:00:00Z"
ANSWERED_AT = "2026-09-12T10:30:00Z"
NOW = "2026-09-12T11:00:00Z"
WHERE = {"path": "src/foo.py", "line": 42,
         "anchor": ThreadAnchor(side=Side.AFTER, original_line=42, original_commit="a1b2c3d")}
OPERATION_ID = re.compile(r"op_[0-9a-f]{12}")


class FirstReplyRefused(FakeGitHub):
    refused = False

    def reply_to_thread(self, key, body):
        if not self.refused:
            self.refused = True
            raise GhError("gh graphql mutation failed: Could not resolve to a node with "
                          f"the global id of '{key}'")
        return super().reply_to_thread(key, body)


def _asking_for_a_change():
    return ThreadComment(id=COMMENT_ID, author=REVIEWER, body="rename the helper",
                         created_at=SAID_AT, author_name="Anna Example",
                         review_state=ReviewState.CHANGES_REQUESTED)


def _heard(github=None):
    board = board_on(fake_threads(github or FakeGitHub(account=VIEWER), clock=at(NOW)),
                     is_author=True,
                     base_branch="main", head_sha="c0ffee1", branch="fix-the-widget")
    heard_on(board, KEY, _asking_for_a_change(), **WHERE)
    return board


def _proposed(github=None):
    board = _heard(github)
    proposed(board, KEY)
    return board


def _settled(board, verb, key=KEY, **body):
    answer = asked(client_of(board), verb, key=key, **body)
    assert answer.status_code == 202, answer.json()
    drain(board.threads)
    return board


def _reported(board, verb, *args, **kwargs):
    with board.threads.editing(KEY) as editable:
        getattr(editable, verb)(*args, **kwargs)
    return board


def queued():
    return _heard()


def working():
    board = _heard()
    running(board)
    return board


def session():
    board = _proposed()
    board.stage.agent_runs.pr_processes.open(THE_PR, Path(WORKTREE))
    return _settled(board, "start-session")


def rework():
    board = _proposed()
    asked(client_of(board), "rework", key=KEY, note="narrow it")
    running(board)
    return board


def landing():
    board = _proposed()
    board.stage.working_copies.fail_pushes(OSError("the network went away"))
    return _settled(board, "approve", reply="Renamed it.")


def rebasing():
    board = _proposed()
    board.stage.working_copies.commit(WORKTREE, {"f": "moved on\n"}, "change f on main")
    asked(client_of(board), "approve", key=KEY, reply="Renamed it.")
    running(board)
    return board


def proposed_():
    return _proposed()


def declined():
    return _reported(working(), "not_a_fix", Classification.NEEDS_HUMAN,
                     "only the author can choose between the two")


def assumed_done():
    return _reported(working(), "not_a_fix", Classification.ACKNOWLEDGEMENT,
                     "thanks the author, asks for nothing")


def failed():
    board = _heard()
    for _ in range(board.threads.get(KEY).run_holder.attempts_allowed):
        start_run(board.stage, board.threads)
        _reported(board, "fail", "the tests would not run")
    return board


def stopped():
    return _settled(working(), "stop")


def removed():
    board = _proposed()
    github = board.stage.github
    github.delete_comment(THE_PR, github.thread(KEY).kind, COMMENT_ID)
    lost(board.threads, KEY)
    return board


def push_failed():
    board = _proposed()
    board.stage.working_copies.refuse_pushes(
        "To github.com:o/r.git\n ! [rejected]  fix-the-widget -> fix-the-widget (fetch first)\n"
        "error: failed to push some refs to 'github.com:o/r.git'")
    return _settled(board, "approve", reply="Renamed it.")


def reply_failed():
    return _settled(_proposed(FirstReplyRefused(account=VIEWER)), "approve",
                    reply="Renamed it.")


def filing():
    board = _heard()
    start_run(board.stage, board.threads)
    _reported(board, "not_a_fix", Classification.OUT_OF_SCOPE,
              "That reaches past this PR, so I've proposed a ticket for it.",
              ticket_project="PROJ", ticket_title="Share one model cache",
              ticket_body="Every export builds its own cache.")
    return _settled(board, "approve", reply="That reaches past this PR; I've filed a ticket.",
                    ticket={"project": "PROJ", "title": "Share one model cache",
                            "body": "Every export builds its own cache."})


def filing_failed():
    board = filing()
    _reported(board, "fail", "Jira refused the project key PROJ")
    drain(board.threads)
    drain(board.threads)
    return board


def waiting():
    return _settled(_proposed(), "reply", body="Which helper?")


def deferred():
    return _settled(_proposed(), "defer", until="manual", note="after the export rewrite")


def landed():
    return _settled(_proposed(), "approve", reply="Renamed it.")


def rejected():
    return _settled(_proposed(), "reject")


def resolved():
    return _settled(_proposed(), "resolve", reply="Fixed in the last push.")


AUTHOR = {
    "queued": queued, "working": working, "session": session, "rework": rework,
    "landing": landing, "rebasing": rebasing, "proposed": proposed_,
    "declined": declined, "assumed-done": assumed_done, "failed": failed, "stopped": stopped, "removed": removed,
    "push failed": push_failed, "reply failed": reply_failed,
    "filing": filing, "filing failed": filing_failed, "waiting": waiting,
    "deferred": deferred, "landed": landed, "rejected": rejected, "resolved": resolved,
    "draft": lambda: draft(is_author=True), "enrolled": lambda: enrolled(is_author=True),
    "discarded": lambda: discarded(is_author=True),
}


def _on_a_diff(is_author=False, agent_runs=None):
    fake, head = reviewing(FakeGitHub(account=VIEWER), now=NOW, agent_runs=agent_runs)
    return board_on(fake, is_author=is_author, head_sha=head)


def _theirs(*comments, verdict=None):
    verdicts = HeldVerdicts(FakePrProcesses())
    board = _on_a_diff(agent_runs=verdicts)
    heard_on(board, KEY, *comments, **WHERE)
    if verdict is not None:
        verdicts.give(verdict)
    return board


def _asked_of_the_author():
    return ThreadComment(id=COMMENT_ID, author=VIEWER, body="rename the helper",
                         created_at=SAID_AT, review_state=ReviewState.CHANGES_REQUESTED)


def _answered_by_the_author(verdict):
    return _theirs(_asked_of_the_author(),
                   said(COMMENT_ID + 1, "Renamed it.", author=REVIEWER, created_at=ANSWERED_AT,
                        author_name="Anna Example"), verdict=verdict)


def reviewer_answered():
    return _answered_by_the_author("my-move")


def reviewer_waiting():
    return _settled(reviewer_answered(), "reply", body="Which helper?")


def reviewer_assumed_done():
    return _answered_by_the_author("assumed-done")


def reviewer_not_mine():
    return _theirs(said(COMMENT_ID, "this could use a docstring", author="ben",
                        created_at=SAID_AT), verdict="not-mine")


def reviewer_confirmed():
    return _settled(reviewer_assumed_done(), "confirm")


def reviewer_deferred():
    return _settled(reviewer_answered(), "defer", until="push", note="once the guard is in")


def reviewer_resolved():
    return _settled(reviewer_answered(), "resolve", reply="Confirmed, thanks.", resolve=True)


def _drafted(is_author):
    board = _on_a_diff(is_author)
    answer = client_of(board).post("/api/operations:create-draft",
                                   json={"body": "call it write_iso", "path": PATH, "line": 11})
    assert answer.status_code == 202, answer.json()
    return board, answer.json()["conversation"]


def draft(is_author=False):
    board, _ = _drafted(is_author)
    return board


def enrolled(is_author=False):
    board, key = _drafted(is_author)
    return _settled(board, "enrol", key=key)


def discarded(is_author=False):
    board, key = _drafted(is_author)
    return _settled(board, "discard", key=key)


REVIEWER_PHASES = {
    "answered": reviewer_answered, "waiting": reviewer_waiting,
    "assumed-done": reviewer_assumed_done, "not-mine": reviewer_not_mine,
    "confirmed": reviewer_confirmed,
    "deferred": reviewer_deferred, "resolved": reviewer_resolved,
    "draft": draft, "enrolled": enrolled, "discarded": discarded,
}


def _recorded(phase, board):
    [served] = client_of(board).get("/api/conversations").json()["conversations"]
    text = json.dumps(served).replace(served["key"], DRAFT if served["kind"] == "draft" else KEY)
    minted = list(dict.fromkeys(OPERATION_ID.findall(text)))
    for number, operation_id in enumerate(minted, start=1):
        text = text.replace(operation_id, f"op_{number:012d}")
    return {**json.loads(text), "etag": f'"{phase}"'}


def test_the_board_app_offers_threads_the_machine_reached_in_each_phase():
    phases = {role: {phase: _recorded(phase, reached()) for phase, reached in reached_in.items()}
              for role, reached_in in (("author", AUTHOR), ("reviewer", REVIEWER_PHASES))}
    wanted = ("import type { Conversation } from 'frontend/data/api';\n\n"
              f"export const RECORDED = {json.dumps(phases, indent=1, sort_keys=True)} "
              "satisfies Record<'author' | 'reviewer', Record<string, Conversation>>;\n")

    held = rewritten(FIXTURE, wanted)

    assert held == wanted, (
        f"{FIXTURE.name} was behind what the conversation machine and the board's "
        "projection answer for each phase and has been rewritten; commit it and run "
        "the ember suite, whose FakeBoard.threadIn offers threads from it")
