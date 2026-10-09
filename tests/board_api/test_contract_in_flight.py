from pathlib import Path

from github_orchestrator.agent_runs.fake import FakeAgentRuns
from github_orchestrator.agent_runs.fake import Outcome as RunOutcome
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.pr_processes.fake import FakePrProcesses
from tests.board_api.support import (
    ACCOUNT,
    KEY,
    THE_PR,
    WORKTREE,
    board_on,
    client_of,
    fake_threads,
    heard_on,
    proposed,
)
from tests.board_api.test_contract_writes import NOW
from tests.conversation.support import at, commit_fix, said


class KeepingRuns(FakeAgentRuns):
    def __init__(self):
        super().__init__(FakePrProcesses())
        self.runs = []

    def fix(self, fix):
        run = super().fix(fix)
        self.runs.append(run)
        return run


def test_an_agent_at_work_moves_the_fast_poll_every_tick_and_never_the_list():
    agent_runs = KeepingRuns()
    board = board_on(fake_threads(FakeGitHub(account=ACCOUNT), agent_runs=agent_runs,
                                  clock=at(NOW)))
    heard_on(board, "PRRT_2", said(2, "two"))
    proposed(board, "PRRT_2")
    heard_on(board)
    agent_runs.script(RunOutcome(finishes=False))
    board.threads.tick(FakeNotifications(), on_hold=False)
    copies = board.stage.working_copies
    checkout = copies.thread_checkout(THE_PR, KEY)
    client = client_of(board)
    listed = client.get("/api/conversations").headers["ETag"]
    polled = client.get("/api/operations")
    seen = {polled.headers["ETag"]}

    for second in range(1, 6):
        agent_runs.runs[-1].last_action = f"editing step_{second}.py"
        copies.commit(checkout, {f"step_{second}.py": "done\n"}, f"step {second}")
        board.threads.tick(FakeNotifications(), on_hold=False)

        polled = client.get("/api/operations",
                            headers={"If-None-Match": polled.headers["ETag"]})
        again = client.get("/api/conversations",
                           headers={"If-None-Match": listed})

        assert polled.status_code == 200, f"tick {second} moved nothing"
        [run] = polled.json()
        assert (run["kind"], run["state"]) == ("first", "running")
        assert run["last_action"] == f"editing step_{second}.py"
        assert run["progress"] == ("1 commit" if second == 1 else f"{second} commits")
        assert again.status_code == 304, (
            f"tick {second} moved the list; the summary carries a field "
            f"that changes while an agent works")
        seen.add(polled.headers["ETag"])

    assert len(seen) == 6


def test_a_session_runs_while_its_pane_is_open_and_settles_when_claude_reports():
    board = board_on(fake_threads(FakeGitHub(account=ACCOUNT), clock=at(NOW)))
    heard_on(board)
    proposed(board)
    board.stage.agent_runs.pr_processes.open(THE_PR, Path(WORKTREE))
    client = client_of(board)
    tag = client.get(f"/api/conversations/{KEY}").json()["etag"]
    asked = client.post(f"/api/conversations/{KEY}/operations:start-session",
                        headers={"If-Match": tag},
                        json={"steer": "look at the caller"})

    board.threads.tick(FakeNotifications(), on_hold=False)
    [session] = client.get("/api/operations").json()
    with board.threads.editing(KEY) as editable:
        editable.ready(sha=commit_fix(board.stage, KEY, {"f": "session\n"}, pr=THE_PR),
                       summary="renamed it in the session")
    settled = client.get(asked.headers["Location"]).json()
    [proposal] = client.get(f"/api/conversations/{KEY}/proposals").json()

    assert (session["id"], session["kind"], session["state"]) == (
        asked.json()["operation"]["id"], "start-session", "running")
    assert session["steer"] == "look at the caller"
    assert client.get("/api/operations").json() == []
    assert settled["state"] == "applied"
    assert settled["settled_at"] == NOW
    assert proposal["operation"] == session["id"], (
        "a proposal a session left names the session")
    assert settled["proposal"] == proposal["id"]
    assert proposal["summary"] == "renamed it in the session"
