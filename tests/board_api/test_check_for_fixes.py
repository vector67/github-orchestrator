from github_orchestrator.agent_runs.fake import HeldVerdicts
from github_orchestrator.github.fake import ThreadAnchor
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.pr_processes.fake import FakePrProcesses
from tests.board_api.support import (
    KEY,
    board_on,
    branched_from_main,
    client_of,
    fake_threads,
    heard_on,
)
from tests.conversation.support import said

CHECK_THE_PR = "/api/pull-request/operations:check-for-fixes"


def check_the_thread(key=KEY):
    return f"/api/conversations/{key}/operations:check-for-fixes"


def waiting(verdict="their-move"):
    copies, base, head = branched_from_main()
    agent_runs = HeldVerdicts(FakePrProcesses())
    board = board_on(fake_threads(working_copies=copies, agent_runs=agent_runs),
                     is_author=False, branch="feature")
    heard_on(board, KEY, said(1, "call check() before write()", author="octocat"),
             path="src/foo.py", line=1, anchor=ThreadAnchor(original_commit=base))
    board.threads.tick(FakeNotifications(), on_hold=False)
    agent_runs.give(verdict)
    return board, agent_runs, base, head


def test_checking_a_thread_for_fixes_asks_about_the_changes_up_to_origins_head():
    board, agent_runs, base, head = waiting()

    answer = client_of(board).post(check_the_thread())

    assert answer.status_code == 204
    assert [(asked.key, asked.base, asked.head)
            for asked in agent_runs.fix_checks_asked()] == [(KEY, base, head)]


def pushed_since_the_last_fetch(board):
    copies = board.stage.working_copies
    return copies.publish("feature", copies.origin["feature"],
                          {"src/foo.py": "def write():\n    check()\n    write_it()\n"},
                          "Write after the check")


def test_checking_a_thread_for_fixes_fetches_first_so_it_sees_the_newest_push():
    board, agent_runs, _, _ = waiting()
    pushed = pushed_since_the_last_fetch(board)

    client_of(board).post(check_the_thread())

    assert [asked.head for asked in agent_runs.fix_checks_asked()] == [pushed]


def test_checking_the_pull_request_for_fixes_fetches_first_so_it_sees_the_newest_push():
    board, agent_runs, _, _ = waiting()
    pushed = pushed_since_the_last_fetch(board)

    client_of(board).post(CHECK_THE_PR)

    assert [asked.head for asked in agent_runs.fix_checks_asked()] == [pushed]


def test_a_thread_not_waiting_on_the_author_is_refused_a_check_for_fixes():
    board, agent_runs, _, _ = waiting("my-move")

    answer = client_of(board).post(check_the_thread())

    assert (answer.status_code, answer.json()["errors"][0]["code"]) == (409, "not-parked")
    assert agent_runs.fix_checks_asked() == []


def test_checking_the_pull_request_for_fixes_names_each_waiting_thread_it_skipped_and_why():
    board, agent_runs, _, _ = waiting()
    heard_on(board, "PRRT_unanchored", said(2, "drop the print", author="octocat"),
             path="src/foo.py", line=7)
    board.threads.tick(FakeNotifications(), on_hold=False)
    agent_runs.give("their-move", key="PRRT_unanchored")

    answer = client_of(board).post(CHECK_THE_PR)

    assert answer.json() == {
        "asked": [KEY],
        "skipped": [{"key": "PRRT_unanchored", "where": "src/foo.py:7",
                     "reason": "the board does not know which commit your comment "
                               "was made on"}]}


def test_checking_the_pull_request_for_fixes_asks_about_each_waiting_thread():
    board, agent_runs, base, head = waiting()

    answer = client_of(board).post(CHECK_THE_PR)

    assert answer.status_code == 200
    assert [(asked.key, asked.base, asked.head)
            for asked in agent_runs.fix_checks_asked()] == [(KEY, base, head)]
