from dataclasses import replace

from github_orchestrator.board_api.fake import IDLE, FakeManagerPanel
from tests.board_api.support import (
    WORKTREE,
    board_on,
    branched_from_main,
    client_of,
    fake_threads,
)

RESET = "/api/pull-request/operations:reset-to-origin"


def reset_board(copies, manager=None):
    serving = {} if manager is None else {"manager": manager}
    return client_of(board_on(fake_threads(working_copies=copies), base_branch="main",
                              **serving))


def diverged():
    copies, _, _ = branched_from_main()
    copies.commit(WORKTREE, {"src/foo.py": "local work\n"}, "local work")
    rewritten = copies.publish("feature", copies.origin["main"],
                               {"src/foo.py": "rewritten\n"}, "check first")
    return copies, rewritten


def test_resetting_to_origin_puts_the_worktree_on_origins_current_head():
    copies, rewritten = diverged()

    answer = reset_board(copies).post(RESET)

    assert answer.status_code == 204
    assert copies.head_of(WORKTREE) == rewritten


def test_a_worktree_with_uncommitted_changes_is_left_as_it_is():
    copies, _ = diverged()
    before = copies.head_of(WORKTREE)
    copies.edit(WORKTREE, "src/foo.py", "half done\n")

    answer = reset_board(copies).post(RESET)

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "uncommitted-changes"
    assert copies.head_of(WORKTREE) == before


def test_a_worktree_an_agent_is_working_in_is_left_as_it_is():
    copies, _ = diverged()
    before = copies.head_of(WORKTREE)
    working = FakeManagerPanel(now=replace(IDLE, working_on="ci-failed"))

    answer = reset_board(copies, working).post(RESET)

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "agent-working"
    assert copies.head_of(WORKTREE) == before
