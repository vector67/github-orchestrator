from datetime import timedelta

from github_orchestrator.terminal_sessions import Activity
from github_orchestrator.terminal_sessions.fake import FakeTerminals
from tests.board_api.support import MOMENT, holding, served_hub
from tests.builders import a_pr
from tests.conversation.support import at

REPO = "acme/widgets"
SECOND = a_pr(54, REPO)
THIRD = a_pr(55, REPO)
NOW = at(MOMENT)()


def _hub(terminals: FakeTerminals):
    return served_hub(told=holding(SECOND, THIRD), terminals=terminals)


def _listed(web):
    return web.get("/api/terminal-sessions").json()["sessions"]


def test_each_session_names_its_pull_request_its_program_and_when_it_started():
    terminals = FakeTerminals()
    started = terminals.of(THIRD).start("/w/55", ["git", "commit"])
    terminals.of(THIRD).mark(started, Activity.WORKING, started_at=NOW - timedelta(minutes=5))

    assert _listed(_hub(terminals)) == [{
        "repo": REPO, "number": 55, "board_url": "/pr/acme/widgets/55", "id": started,
        "argv": ["git", "commit"], "worktree": "/w/55", "branch": None, "thread": None,
        "started_at": (NOW - timedelta(minutes=5)).isoformat(), "activity": "working",
        "waiting_since": None,
    }]


def test_a_session_a_thread_opened_names_that_thread():
    terminals = FakeTerminals()
    terminals.of(THIRD).start_kept("/w/55", ["claude"], thread="PRRT_9")

    assert [one["thread"] for one in _listed(_hub(terminals))] == ["PRRT_9"]


def test_each_session_names_the_branch_it_started_on(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/feature-55\n")
    terminals = FakeTerminals()
    terminals.of(THIRD).start(str(tmp_path), ["zsh", "-l"])

    assert [one["branch"] for one in _listed(_hub(terminals))] == ["feature-55"]


def test_waiting_sessions_come_first_with_the_longest_wait_at_the_top_then_working_then_idle():
    terminals = FakeTerminals()
    seconds, thirds = terminals.of(SECOND), terminals.of(THIRD)
    idle = seconds.start("/w/54", ["zsh", "-l"])
    seconds.mark(idle, Activity.IDLE)
    working = seconds.start("/w/54", ["claude"])
    short_wait = thirds.start("/w/55", ["git", "rebase", "-i", "HEAD~3"])
    thirds.mark(short_wait, Activity.WAITING, since=NOW - timedelta(minutes=1))
    long_wait = seconds.start("/w/54", ["codex"])
    seconds.mark(long_wait, Activity.WAITING, since=NOW - timedelta(minutes=20))

    listed = _listed(_hub(terminals))

    assert [(one["id"], one["activity"]) for one in listed] == [
        (long_wait, "waiting"), (short_wait, "waiting"), (working, "working"), (idle, "idle")]
    assert listed[0]["waiting_since"] == (NOW - timedelta(minutes=20)).isoformat()


def test_a_session_of_a_pull_request_the_watcher_no_longer_holds_is_not_listed():
    terminals = FakeTerminals()
    terminals.of(a_pr(99, REPO)).start("/w/99", ["zsh", "-l"])

    assert _listed(_hub(terminals)) == []


def test_a_wall_row_counts_its_pull_request_s_waiting_sessions():
    terminals = FakeTerminals()
    seconds = terminals.of(SECOND)
    for since in (1, 2):
        waiting = seconds.start("/w/54", ["claude"])
        seconds.mark(waiting, Activity.WAITING, since=NOW - timedelta(minutes=since))
    seconds.mark(seconds.start("/w/54", ["zsh", "-l"]), Activity.IDLE)
    terminals.of(THIRD).start("/w/55", ["claude"])

    rows = _hub(terminals).get("/api/pull-requests").json()["pull_requests"]

    assert {row["number"]: row["terminals_waiting"] for row in rows} == {54: 2, 55: 0}
