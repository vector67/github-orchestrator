from dataclasses import replace

from github_orchestrator.board_api.fake import IDLE, FakeManagerPanel
from github_orchestrator.domain import AuthorKind, Mention, ThreadRow
from tests.board_api.support import board_contract, client_for

WORKING = replace(
    IDLE, working_on="new-comments", elapsed_seconds=75.0, silent_seconds=4.0,
    queued_events=2, on_hold=True, unpushed_commits=3, last_run_event="ci-failed",
    last_run_exit_code=1, last_run_ended_at="2026-09-26T21:40:00+00:00", threads_queued=1,
    threads_live=2, threads_proposed=4, threads_drafts=0, needs_rebase=True,
    notice="an agent is already running")

FROZEN = replace(IDLE, frozen_on="PROJ-31-split-2", expected_branch="PROJ-34-remove-changes",
                 seconds_left=2280.0, run_working=True, release_requested=False)


def test_the_dashboard_read_answers_what_the_manager_last_drew():
    answer = client_for(manager=FakeManagerPanel(now=WORKING)).get("/api/dashboard")

    assert answer.status_code == 200
    assert answer.json() == {
        "pr": {"repo": "o/n", "number": 1, "title": "Remove the changes field",
               "url": "https://github.com/o/n/pull/1", "branch": "PROJ-34-remove-changes",
               "ticket": "PROJ-34", "author": "octocat"},
        "polled": True,
        "status": {"detailed_reviewer": "carol", "you_are_the_detailed_reviewer": False,
                   "mergeable": True, "needs_rebase": True,
                   "last_event_at": "2026-06-10T10:30:00Z",
                   "review_ready_at": "2026-06-09T08:00:00Z", "since_you_last_acted": None,
                   "failed_checks": [], "checks_done": 4, "checks_total": 4,
                   "changed_files": 7, "approved_by": []},
        "system": {
            "agent": {"name": "Agent", "enabled": True, "state": "working",
                      "event": "new-comments", "elapsed_seconds": 75.0, "silent_seconds": 4.0},
            "last_run": {"event": "ci-failed", "exit_code": 1,
                         "ended_at": "2026-09-26T21:40:00+00:00"},
            "queued_events": 2,
            "on_hold": True,
            "unpushed_commits": 3,
            "threads": {"queued": 1, "live": 2, "proposed": 4, "drafts": 0},
        },
        "frozen": None,
        "undismiss_command": "github-orchestrator undismiss --repo o/n 1",
        "notice": "an agent is already running",
        "facts": {"polled_at": "2026-06-10T10:30:00Z", "ended": False, "is_author": True,
                  "changes_requested_by": [], "pending_reviewers": ["carol"],
                  "ci_status": "passing", "merge_state": "clean", "draft": False,
                  "review_decision": None, "my_review": None, "my_review_at": None,
                  "viewer_requested": False, "mentioned": False, "mentions": [],
                  "unresolved_threads": 0},
        "manager": {"frozen_on": None, "on_hold": True, "working_on": "new-comments",
                    "hidden": False, "threads_live": 2, "changed_at": None},
        "threads": [],
        "unreadable": [],
        "listed_at": None,
    }


def test_the_dashboard_read_ships_the_facts_flags_and_threads_the_next_move_reads():
    asked = Mention(author="anna", at="2026-10-08T08:00:00Z", kind="issue", thread=None,
                    comment_id=11, body="@octocat?", answered=False)
    drawn = replace(
        WORKING, polled_at="2026-10-08T09:00:00Z", ended=False, draft=True,
        merge_state="behind", viewer_requested=True, mentioned=True, mentions=(asked,),
        my_review="approved", my_review_at="2026-10-07T12:00:00Z",
        changes_requested_by=("bob",), review_decision="changes-requested", hidden=True,
        flags_changed_at="2026-10-08T09:01:00Z",
        unreadable_threads=(), threads_listed_at="2026-10-08T08:59:00Z",
        thread_rows=(ThreadRow(key="PRRT_1", standing="ready", state="open",
                               author_kind=AuthorKind.BOT, updated_at="2026-10-08T08:30:00Z"),))

    answer = client_for(manager=FakeManagerPanel(now=drawn)).get("/api/dashboard").json()

    assert answer["facts"] == {
        "polled_at": "2026-10-08T09:00:00Z", "ended": False, "is_author": True,
        "changes_requested_by": ["bob"], "pending_reviewers": ["carol"], "ci_status": "passing",
        "merge_state": "behind", "draft": True, "review_decision": "changes-requested",
        "my_review": "approved", "my_review_at": "2026-10-07T12:00:00Z",
        "viewer_requested": True, "mentioned": True,
        "mentions": [{"author": "anna", "at": "2026-10-08T08:00:00Z", "answered": False}],
        "unresolved_threads": 0}
    assert answer["manager"] == {
        "frozen_on": None, "on_hold": True, "working_on": "new-comments", "hidden": True,
        "threads_live": 2, "changed_at": "2026-10-08T09:01:00Z"}
    assert answer["threads"] == [{"key": "PRRT_1", "state": "ready", "record_state": "open",
                                  "author_kind": "bot", "updated_at": "2026-10-08T08:30:00Z"}]
    assert answer["listed_at"] == "2026-10-08T08:59:00Z"


def test_a_dashboard_before_the_first_poll_ships_no_facts():
    unpolled = replace(IDLE, polled=False)

    answer = client_for(manager=FakeManagerPanel(now=unpolled)).get("/api/dashboard").json()

    assert answer["facts"] is None


def test_an_idle_manager_with_no_run_behind_it_says_so():
    answer = client_for(manager=FakeManagerPanel(now=IDLE)).get("/api/dashboard")

    assert answer.json()["system"]["agent"] == {
        "name": "Agent", "enabled": True, "state": "idle", "event": None,
        "elapsed_seconds": None, "silent_seconds": None}
    assert answer.json()["system"]["last_run"] is None


def test_a_frozen_manager_answers_the_worktree_and_both_branches():
    answer = client_for(manager=FakeManagerPanel(now=FROZEN)).get("/api/dashboard")

    assert answer.json()["frozen"] == {
        "worktree": "/wt", "here": "PROJ-31-split-2", "expected": "PROJ-34-remove-changes",
        "seconds_left": 2280.0, "run_working": True, "release_requested": False}
    assert answer.json()["manager"]["frozen_on"] == "PROJ-31-split-2"


def test_a_stopped_last_run_and_a_frozen_worktree_out_of_grace_are_still_answered():
    stopped = replace(FROZEN, seconds_left=0.0, last_run_event="ci-failed",
                      last_run_exit_code=None, last_run_ended_at="2026-09-30T08:00:00+00:00")

    answer = client_for(manager=FakeManagerPanel(now=stopped)).get("/api/dashboard").json()

    assert answer["system"]["last_run"] == {
        "event": "ci-failed", "exit_code": None, "ended_at": "2026-09-30T08:00:00+00:00"}
    assert answer["frozen"]["seconds_left"] == 0.0


def test_what_happened_since_you_acted_is_answered_as_counts_for_the_page_to_word():
    reviewed = replace(IDLE, since_commits=2, since_force_push=True, since_reviews=1,
                       since_comments=4, since_resolved=1)

    answer = client_for(manager=FakeManagerPanel(now=reviewed)).get("/api/dashboard")

    assert answer.json()["status"]["since_you_last_acted"] == {
        "commits": 2, "force_pushed": True, "reviews": 1, "comments": 4,
        "threads_resolved": 1}


def test_a_manager_that_has_not_finished_its_first_tick_asks_the_page_to_come_back():
    answer = client_for(manager=FakeManagerPanel(now=None)).get("/api/dashboard")

    assert answer.status_code == 503
    assert answer.headers["Retry-After"] == "1"
    assert answer.json()["errors"][0]["code"] == "manager-starting"


def test_the_changes_read_answers_the_agent_changes_text():
    panel = FakeManagerPanel(changes_text="# What changed\n\n- Renamed the helper.\n")

    answer = client_for(manager=panel).get("/api/manager/changes")

    assert answer.status_code == 200
    assert answer.json() == {"markdown": "# What changed\n\n- Renamed the helper.\n"}


def test_the_changes_read_answers_null_where_the_agent_has_written_none():
    answer = client_for(manager=FakeManagerPanel(changes_text=None)).get("/api/manager/changes")

    assert answer.json() == {"markdown": None}


def test_the_claude_output_read_answers_the_transcripts_tail_with_its_run_boundaries():
    panel = FakeManagerPanel(output=[("first run", False), ("", True), ("second run", False),
                                     ("still going", False)])

    answer = client_for(manager=panel).get("/api/manager/agent-output?lines=3")

    assert answer.status_code == 200
    assert answer.json() == {"lines": [
        {"text": "", "run_boundary": True},
        {"text": "second run", "run_boundary": False},
        {"text": "still going", "run_boundary": False},
    ]}


def test_the_claude_output_read_refuses_a_tail_of_no_lines():
    answer = client_for().get("/api/manager/agent-output?lines=0")

    assert answer.status_code == 400
    assert answer.json()["errors"][0]["code"] == "malformed-request"


def test_hold_is_accepted_and_handed_to_the_manager():
    panel = FakeManagerPanel()

    answer = client_for(manager=panel).post("/api/manager:hold")

    assert answer.status_code == 202
    assert answer.headers["Location"] == "/api/dashboard"
    assert panel.dashboard().on_hold is True


def test_resume_is_accepted_and_handed_to_the_manager():
    panel = FakeManagerPanel(now=replace(IDLE, on_hold=True))

    answer = client_for(manager=panel).post("/api/manager:resume")

    assert answer.status_code == 202
    assert panel.dashboard().on_hold is False


def test_carry_on_is_accepted_and_handed_to_the_manager():
    panel = FakeManagerPanel()

    answer = client_for(manager=panel).post("/api/manager:carry-on")

    assert answer.status_code == 202
    assert panel.carried_on == 1


def test_start_review_is_accepted_and_handed_to_the_manager():
    panel = FakeManagerPanel()

    answer = client_for(manager=panel).post("/api/manager:start-review")

    assert answer.status_code == 202
    assert panel.reviews_started == 1


def test_dismiss_is_accepted_and_handed_to_the_manager_until_the_next_event_or_forever():
    until, forever = FakeManagerPanel(), FakeManagerPanel()

    one = client_for(manager=until).post("/api/manager:dismiss", json={"forever": False})
    other = client_for(manager=forever).post("/api/manager:dismiss", json={"forever": True})

    assert (one.status_code, other.status_code) == (202, 202)
    assert (until.dismissed, forever.dismissed) == ("until the next event", "forever")


def test_dismiss_that_does_not_say_how_long_is_refused_and_dismisses_nothing():
    panel = FakeManagerPanel()

    answer = client_for(manager=panel).post("/api/manager:dismiss", json={})

    assert answer.status_code == 400
    assert panel.dismissed is None


def test_close_is_accepted_and_handed_to_the_manager():
    panel = FakeManagerPanel()

    answer = client_for(manager=panel).post("/api/manager:close")

    assert answer.status_code == 202
    assert panel.closed == 1


def test_every_manager_command_declares_the_hand_over_and_where_to_poll():
    contract = board_contract()

    commands = {path: operations["post"] for path, operations in contract["paths"].items()
                if path.startswith("/api/manager:")}

    assert set(commands) == {"/api/manager:hold", "/api/manager:resume",
                             "/api/manager:carry-on", "/api/manager:start-review",
                             "/api/manager:dismiss", "/api/manager:close"}
    assert all(command["responses"]["202"]["headers"]["Location"]
               for command in commands.values())


def test_git_runs_a_captured_command_through_the_manager_and_answers_its_output():
    panel = FakeManagerPanel(git_answer=(1, ["To github.com:o/n.git", " ! [rejected] main"], 2.5))

    answer = client_for(manager=panel).post("/api/manager/git", json={"keys": "p"})

    assert answer.status_code == 200
    assert answer.json() == {"exit_code": 1, "lines": ["To github.com:o/n.git",
                                                       " ! [rejected] main"],
                             "seconds": 2.5, "truncated": False}
    assert panel.ran == ["p"]


def test_git_runs_each_command_the_page_offers_and_shows_log_and_diff_read_only():
    panel = FakeManagerPanel()
    client = client_for(manager=panel)

    answers = [client.post("/api/manager/git", json={"keys": keys}).status_code
               for keys in ("f", "p", "pra", "s", "l", "d")]

    assert answers == [200] * 6
    assert panel.ran == ["f", "p", "pra", "s", "l", "d"]


def test_git_refuses_a_command_that_needs_a_terminal_and_runs_nothing():
    panel = FakeManagerPanel()

    answers = [client_for(manager=panel).post("/api/manager/git", json={"keys": keys})
               for keys in ("a", "c", "i3", "r", "rm -rf")]

    assert [one.status_code for one in answers] == [400] * 5
    assert panel.ran == []


def test_git_output_past_the_cap_is_cut_to_its_first_lines_and_says_so():
    many = [f"commit {n}" for n in range(2500)]
    panel = FakeManagerPanel(git_answer=(0, many, 0.4))

    answer = client_for(manager=panel).post("/api/manager/git", json={"keys": "l"})

    assert answer.json()["lines"] == many[:2000]
    assert answer.json()["truncated"] is True


def test_every_stream_declares_its_event_and_the_read_its_data_repeats():
    contract = board_contract()

    streams = {path: operations["get"]["responses"]["200"]["content"]
               for path, operations in contract["paths"].items() if path.endswith("/stream")}

    assert {path: (content["text/event-stream"]["itemSchema"]["properties"]["event"]["const"],
                   content["text/event-stream"]["itemSchema"]["properties"]["data"]["contentSchema"])
            for path, content in streams.items()} == {
        "/api/dashboard/stream": ("dashboard", {"$ref": "#/components/schemas/Dashboard"}),
        "/api/manager/changes/stream": ("changes", {"$ref": "#/components/schemas/ManagerChanges"}),
        "/api/manager/agent-output/stream": ("agent-output",
                                              {"$ref": "#/components/schemas/AgentOutput"}),
    }
    assert all(set(content) == {"text/event-stream"} for content in streams.values())


def test_the_dashboard_names_the_agent_the_manager_runs():
    codex = replace(IDLE, agent_name="Codex")

    answer = client_for(manager=FakeManagerPanel(now=codex)).get("/api/dashboard").json()

    assert answer["system"]["agent"]["name"] == "Codex"
