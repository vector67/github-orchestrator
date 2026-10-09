from datetime import datetime, timedelta, timezone

import pytest

from github_orchestrator.agent_runs import ThreadFix
from github_orchestrator.agent_runs.fake import FakeAgentRuns, Outcome
from github_orchestrator.pr_processes.fake import FakePrProcesses
from tests.agent_runs.scripted_claude import ScriptedClaude
from tests.agent_runs.support import (
    finish,
    ledger_file,
    pump_until,
    real_agent_runs,
)
from tests.builders import a_pr

REPO = "o/n"
PR = 7
THE_PR = a_pr(PR, REPO)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class World:
    def __init__(self, kind, tmp_path):
        self.clock = Clock()
        self.fake = FakeAgentRuns(FakePrProcesses(), clock=self.clock)
        self.claude = ScriptedClaude(self.fake)
        self.data = tmp_path / "data"
        self.worktree = str(tmp_path)
        if kind == "fake":
            self.runs = self.fake
        else:
            self.runs = real_agent_runs(self.fake, self.claude, self.data, self.clock)
        self.kind = kind

    def ledger(self):
        if self.kind == "fake":
            return list(self.fake.ledger)
        return ledger_file(self.data / "runs.jsonl")

    def summaries_written(self):
        if self.kind == "claude":
            assert self.runs.drain_summaries(10)

    def script(self, *outcomes):
        self.fake.script(*outcomes)
        return self

    def started_in(self):
        if self.kind == "fake":
            return [started.worktree for started in self.fake.started]
        return [spawned.cwd for spawned in self.claude.spawned]

    def start(self, event_type="ci-failed", repo=REPO, pr=PR):
        return self.runs.fix_check(self.worktree, a_pr(pr, repo), event_type,
                                   check="tests", summary=None, push=True)

    def restarted(self):
        if self.kind == "fake":
            return self.fake.restarted()
        return real_agent_runs(self.fake, self.claude, self.data, self.clock)

    def ran(self, *event_types, repo=REPO, pr=PR, exit_code=0):
        for event_type in event_types:
            self.script(Outcome(exit_code=exit_code))
            finish(self.start(event_type, repo=repo, pr=pr))


@pytest.fixture(params=["fake", "claude"])
def world(request, tmp_path):
    world = World(request.param, tmp_path)
    yield world
    world.claude.reap()


def _said(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def _tool(name, **arguments):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": name, "input": arguments}]}}


INIT = {"type": "system", "subtype": "init", "session_id": "s1"}


def test_a_run_is_started_in_the_working_copy(world):
    finish(world.start())

    assert world.started_in() == [world.worktree]


def test_a_run_carried_on_by_hand_is_a_manual_continue(world):
    run = world.runs.carry_on(world.worktree, THE_PR)
    finish(run)

    assert world.started_in() == [world.worktree]
    assert run.event_type == "manual-continue"


def test_a_run_that_exits_is_over_and_says_how_it_ended(world):
    run = world.script(Outcome(exit_code=3)).start("review-requested")

    finish(run)

    assert run.is_alive() is False
    assert run.pump() is False
    ended = run.finished()
    assert (ended.event_type, ended.exit_code) == ("review-requested", 3)
    assert datetime.fromisoformat(ended.ended_at).tzinfo is not None


def test_a_run_still_going_is_alive(world):
    run = world.script(Outcome(events=(INIT,), finishes=False)).start()

    pump_until(run, world.started_in)

    assert run.pump() is True
    assert run.is_alive() is True
    assert run.finished().exit_code is None


def test_the_last_action_is_the_newest_line_the_run_wrote(world):
    run = world.script(Outcome(events=(
        _tool("Read", file_path="/wt/impact_summary.py"),
        _tool("Bash", command="uv run pytest"),
    ))).start()

    finish(run)

    assert run.last_action == "● Bash uv run pytest"


def test_there_is_no_last_action_before_anything_worth_showing(world):
    run = world.script(Outcome(events=(INIT,))).start()

    finish(run)

    assert run.last_action is None


def test_an_event_with_nothing_to_show_leaves_the_last_action_standing(world):
    run = world.script(Outcome(events=(
        _tool("Bash", command="uv run pytest"),
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
    ))).start()

    finish(run)

    assert run.last_action == "● Bash uv run pytest"


def test_a_run_counts_its_time_from_its_start_and_its_silence_from_its_last_output(world):
    run = world.script(Outcome(events=(_said("working"),), finishes=False)).start()
    world.clock.now = 105.0

    pump_until(run, lambda: run.last_action == "working")
    world.clock.now = 112.0

    assert run.elapsed() == 12.0
    assert run.silent_for() == 7.0


def test_a_finished_run_is_recorded_once(world):
    run = world.script(Outcome(exit_code=-9)).start("ci-failed")
    finish(run)
    run.pump()

    [entry] = world.ledger()
    assert (entry["repo"], entry["pr"], entry["event"], entry["exit_code"]) == (
        REPO, PR, "ci-failed", -9)
    assert isinstance(entry["elapsed_seconds"], (int, float))
    assert datetime.fromisoformat(entry["ended_at"]).tzinfo is not None
    assert "total_cost_usd" not in entry, "a run that reported no result records no cost"
    assert "num_turns" not in entry


def test_the_record_says_what_the_run_cost(world):
    finish(world.script(Outcome(events=({
        "type": "result", "subtype": "success", "total_cost_usd": 0.42,
        "num_turns": 7, "is_error": False, "duration_ms": 4000,
    },))).start())

    [entry] = world.ledger()
    assert (entry["total_cost_usd"], entry["num_turns"], entry["is_error"]) == (0.42, 7, False)


def test_a_terminated_run_is_over_and_recorded(world):
    run = world.script(Outcome(events=(INIT,), finishes=False)).start("new-comments")
    pump_until(run, world.started_in)

    run.terminate()

    assert run.is_alive() is False
    assert run.finished().exit_code == -15
    [entry] = world.ledger()
    assert (entry["event"], entry["exit_code"]) == ("new-comments", -15)


def test_terminating_a_run_that_already_ended_keeps_how_it_ended(world):
    run = world.script(Outcome(exit_code=0)).start()
    finish(run)

    run.terminate()

    assert run.finished().exit_code == 0
    assert len(world.ledger()) == 1


def test_the_last_run_is_this_prs_newest_run(world):
    world.ran("new-comments")
    world.ran("ci-failed", exit_code=-9)

    last = world.runs.last_run(THE_PR)

    assert (last.event_type, last.exit_code) == ("ci-failed", -9)
    assert datetime.fromisoformat(last.ended_at).tzinfo is not None


def test_another_prs_run_is_not_this_prs_last_run(world):
    world.ran("review-requested")
    world.ran("ci-failed", repo="o/other", pr=9)

    assert world.runs.last_run(THE_PR).event_type == "review-requested"


def test_nothing_ran_yet_means_no_last_run(world):
    assert world.runs.last_run(THE_PR) is None


WONT_START = "could not start the agent: [Errno 2] No such file or directory: 'claude'"


def test_a_run_claude_will_not_start_for_answers_why_and_is_not_live(world):
    world.script(Outcome(starts=False))

    assert world.start() == WONT_START

    assert world.runs.live(THE_PR) is False
    assert world.ledger() == []


def test_a_thread_fix_claude_will_not_start_for_answers_why(world):
    world.script(Outcome(starts=False))

    assert world.runs.fix(_thread(world.worktree)) == WONT_START


def _thread(worktree, key="2313088871"):
    return ThreadFix(pr=THE_PR, key=key, worktree=worktree, author="reviewer",
                     path="src/foo.py", line=4, body="rename this")


def _fixed_a_thread(world, key="2313088871"):
    world.script(Outcome())
    finish(world.runs.fix(_thread(world.worktree, key)))


@pytest.mark.parametrize("started", [
    lambda runs, fix: runs.fix(fix),
    lambda runs, fix: runs.rebase_fix(fix, "b" * 40),
    lambda runs, fix: runs.rework(fix),
])
def test_every_run_on_a_thread_is_that_thread_s_run_in_its_worktree(world, started):
    run = started(world.runs, _thread(world.worktree, "PRRT_1"))
    finish(run)

    assert run.event_type == "thread-fix-PRRT_1"
    assert world.started_in() == [world.worktree]


def test_a_thread_run_is_not_this_prs_last_run(world):
    world.ran("ci-failed")
    _fixed_a_thread(world)

    assert world.runs.last_run(THE_PR).event_type == "ci-failed"


def test_a_thread_activity_run_is_still_this_prs_last_run(world):
    world.ran("ci-failed", "thread-activity")

    assert world.runs.last_run(THE_PR).event_type == "thread-activity"


def test_the_transcript_shows_what_each_run_wrote_with_a_break_between_runs(world):
    world.script(Outcome(events=(INIT, _said("first run"))),
                 Outcome(events=(INIT, _tool("Bash", command="ls"), _said("second run"))))
    finish(world.start())
    finish(world.start())

    assert world.runs.transcript_tail(THE_PR, 10) == [
        ("first run", False), ("", True), ("● Bash ls", False), ("second run", False)]


def test_the_transcript_keeps_only_the_last_lines_that_fit(world):
    finish(world.script(Outcome(events=tuple(_said(f"line {n}") for n in range(10)))).start())

    assert world.runs.transcript_tail(THE_PR, 3) == [
        ("line 7", False), ("line 8", False), ("line 9", False)]


def test_another_prs_run_is_not_in_this_prs_transcript(world):
    finish(world.script(Outcome(events=(_said("elsewhere"),))).start(repo="o/other", pr=9))

    assert world.runs.transcript_tail(THE_PR, 10) == []


def test_archiving_moves_every_unwatched_repos_transcripts_and_keeps_every_watched_one(
        world, tmp_path):
    repos = ("o/n", "o/other", "p/third", "p/fourth")
    world.script(*(Outcome(events=(_said(f"in {repo}"),)) for repo in repos))
    for repo in repos:
        finish(world.start(repo=repo, pr=9))
    into = tmp_path / "archive" / "transcripts"

    archived = world.runs.archive_other_repos({THE_PR.repo, a_pr(9, "p/fourth").repo}, into)

    assert sorted(archived) == [into / "o" / "other", into / "p" / "third"]
    assert world.runs.transcript_tail(a_pr(9, "o/n"), 10) == [("in o/n", False)]
    assert world.runs.transcript_tail(a_pr(9, "p/fourth"), 10) == [("in p/fourth", False)]
    assert world.runs.transcript_tail(a_pr(9, "o/other"), 10) == []


def test_archiving_when_only_the_named_repo_has_transcripts_moves_nothing(world, tmp_path):
    finish(world.script(Outcome(events=(_said("here"),))).start())

    assert world.runs.archive_other_repos({THE_PR.repo}, tmp_path / "archive") == []
    assert world.runs.transcript_tail(THE_PR, 10) == [("here", False)]


def test_a_session_opens_in_the_threads_worktree_running_claude(world):
    assert world.runs.open_session(_thread("/tmp/wt"), "Keep the old name.") is None

    [session] = world.fake.pr_processes.sessions[THE_PR]
    assert session.worktree == "/tmp/wt"
    assert session.argv[0] == "claude"


def test_a_session_that_will_not_start_answers_the_reason(world):
    world.fake.pr_processes.refusal = "[Errno 2] No such file or directory: 'claude'"

    assert world.runs.open_session(_thread("/tmp/wt"), None) == (
        "[Errno 2] No such file or directory: 'claude'")
    assert world.fake.pr_processes.sessions == {}


def test_a_rebase_session_runs_claude_on_the_skill_in_the_worktree(world):
    assert world.runs.rebase_in_session(THE_PR, "/tmp/wt") is None

    [session] = world.fake.pr_processes.sessions[THE_PR]
    assert (session.worktree, session.argv) == ("/tmp/wt", ["claude", "/rebase-on-main"])


def test_a_gist_is_the_first_line_the_model_writes(world):
    world.fake.answer("\n  rename the helper  \nand more")
    written = []

    world.runs.summarize_comment("PRRT_x", "src/foo.py", 4, "rename this", written.append,
                                 chars=60)

    world.summaries_written()
    assert written == ["rename the helper"]


@pytest.mark.parametrize("answer", [None, "\n  \n"])
def test_no_gist_is_handed_back_when_the_model_writes_none(world, answer):
    world.fake.answer(answer)
    written = []

    world.runs.summarize_thread("PRRT_x", None, None, [("reviewer", "rename this")],
                                written.append, chars=60)

    world.summaries_written()
    assert written == []


VERDICTS = {"my-move": "the viewer has to answer", "their-move": "someone else has to"}


def _judge(world, done):
    world.runs.judge_thread(
        "PRRT_x", [("PR author", "mei", "fixed in abc123")], viewer="octocat",
        pr_author="mei", spoke_last="PR author", viewer_commented=True,
        mentions_viewer=False, kind="review thread on a line", answers=VERDICTS,
        done=done)


def test_a_verdict_is_the_answer_the_model_gives_first(world):
    world.fake.answer("\n  Their-Move \nbecause the author asked a question")
    given = []

    _judge(world, given.append)

    world.summaries_written()
    assert given == ["their-move"]


@pytest.mark.parametrize("answer", [None, "assumed-done", "the author fixed it"])
def test_no_verdict_is_handed_back_when_the_model_names_none_it_was_offered(world, answer):
    world.fake.answer(answer)
    given = []

    _judge(world, given.append)

    world.summaries_written()
    assert given == []


def test_a_batch_of_fixes_is_summed_up_in_one_line(world):
    world.fake.answer("general cleanup\n")
    written = []

    world.runs.summarize_fixes([([("reviewer", "rename this")], "renamed it")],
                               written.append, chars=100)

    world.summaries_written()
    assert written == ["general cleanup"]


def test_each_comment_of_a_batch_gets_its_own_gist_in_order(world):
    world.fake.answer("rename the helper || add a test")
    written = []

    world.runs.summarize_comments(["rename this", "test this"], written.append, chars=60)

    world.summaries_written()
    assert written == [("rename the helper", "add a test")]


def test_gists_that_do_not_match_the_comments_one_for_one_are_none_at_all(world):
    answer = "one gist for two comments"
    world.fake.answer(answer)
    written = []

    world.runs.summarize_comments(["rename this", "test this"], written.append, chars=60)

    world.summaries_written()
    assert written == [("", "")]


def test_a_comment_the_model_left_no_gist_for_has_none(world):
    world.fake.answer("rename the helper ||  ")
    written = []

    world.runs.summarize_comments(["rename this", "test this"], written.append, chars=60)

    world.summaries_written()
    assert written == [("rename the helper", "")]


def test_a_finished_run_is_among_the_runs_finished_since_it_started(world):
    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    world.ran("ci-failed")

    [finished] = world.runs.finished_since(before)

    assert (finished.pr, finished.event, finished.cost_usd) == (THE_PR, "ci-failed", None)
    assert finished.elapsed_seconds >= 0
    assert (finished.exit_code, finished.failed) == (0, False), (
        "a run that exited cleanly did not fail")


def test_a_finished_run_that_exited_with_an_error_code_failed(world):
    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    world.ran("ci-failed", exit_code=3)

    [finished] = world.runs.finished_since(before)

    assert (finished.exit_code, finished.failed) == (3, True)


def test_a_finished_run_whose_result_says_it_errored_failed_though_it_exited_cleanly(world):
    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    world.script(Outcome(events=({"type": "result", "is_error": True, "duration_ms": 1000,
                                  "subtype": "error_max_turns"},)))
    finish(world.start())

    [finished] = world.runs.finished_since(before)

    assert (finished.exit_code, finished.failed) == (0, True)


def _costing(cost):
    return Outcome(events=({"type": "result", "is_error": False, "duration_ms": 1000,
                            "total_cost_usd": cost},))


def test_today_holds_the_runs_that_ended_since_local_midnight_and_what_they_cost(world):
    world.script(_costing(0.25))
    finish(world.start("ci-failed"))
    world.script(_costing(0.5))
    finish(world.start("review-requested"))

    today = world.runs.finished_today(datetime.now(timezone.utc))

    assert [run.event for run in today.finished] == ["ci-failed", "review-requested"]
    assert (today.cost_usd, today.unpriced) == (0.75, 0)


def test_a_run_that_reported_no_cost_is_counted_unpriced_and_adds_nothing(world):
    world.script(_costing(0.25))
    finish(world.start("ci-failed"))
    world.ran("manual-continue")

    today = world.runs.finished_today(datetime.now(timezone.utc))

    assert (today.cost_usd, today.unpriced) == (0.25, 1)


def test_a_day_on_which_no_run_reported_a_cost_has_none(world):
    world.ran("ci-failed")

    today = world.runs.finished_today(datetime.now(timezone.utc))

    assert (len(today.finished), today.cost_usd, today.unpriced) == (1, None, 1)


def test_a_run_that_ended_before_local_midnight_is_not_among_the_days_runs(world):
    world.ran("ci-failed")

    tomorrow = world.runs.finished_today(datetime.now(timezone.utc) + timedelta(days=1))

    assert tomorrow.finished == ()


def test_a_run_finished_before_the_time_asked_about_is_not(world):
    world.ran("ci-failed")

    assert world.runs.finished_since(datetime.now(timezone.utc) + timedelta(hours=1)) == []


def test_a_pr_run_is_live_until_it_ends(world):
    run = world.script(Outcome(events=(INIT,), finishes=False)).start()

    assert world.runs.live(THE_PR) is True

    run.terminate()

    assert world.runs.live(THE_PR) is False


def test_a_pr_run_that_finished_is_not_live(world):
    world.ran("ci-failed")

    assert world.runs.live(THE_PR) is False


def test_a_pr_no_run_was_started_on_has_none_live(world):
    world.script(Outcome(events=(INIT,), finishes=False)).start(repo="o/other", pr=9)

    assert world.runs.live(THE_PR) is False


def test_a_thread_run_is_not_the_pr_s_live_run(world):
    world.script(Outcome(events=(INIT,), finishes=False))
    world.runs.fix(_thread(world.worktree))

    assert world.runs.live(THE_PR) is False


def test_a_pr_run_cut_off_by_an_interruption_is_interrupted_after_a_restart(world):
    run = world.script(Outcome(events=(INIT,), finishes=False)).start()
    pump_until(run, world.started_in)

    run.interrupt()

    assert run.is_alive() is False
    assert world.restarted().interrupted(THE_PR) == "ci-failed"


def test_an_interrupted_run_is_recorded_as_terminated(world):
    run = world.script(Outcome(events=(INIT,), finishes=False)).start("new-comments")
    pump_until(run, world.started_in)

    run.interrupt()

    [entry] = world.ledger()
    assert (entry["event"], entry["exit_code"]) == ("new-comments", -15)


def test_a_pr_run_its_manager_died_under_is_interrupted_after_a_restart(world):
    run = world.script(Outcome(events=(INIT,), finishes=False)).start("became-unmergeable")
    pump_until(run, world.started_in)

    assert world.restarted().interrupted(THE_PR) == "became-unmergeable"


def test_a_pr_run_that_finished_was_not_interrupted(world):
    world.ran("ci-failed")

    assert world.restarted().interrupted(THE_PR) is None


def test_a_pr_run_terminated_on_purpose_was_not_interrupted(world):
    run = world.script(Outcome(events=(INIT,), finishes=False)).start()
    pump_until(run, world.started_in)

    run.terminate()

    assert world.restarted().interrupted(THE_PR) is None


def test_a_pr_no_run_was_started_on_was_not_interrupted(world):
    world.script(Outcome(events=(INIT,), finishes=False)).start(repo="o/other", pr=9)

    assert world.restarted().interrupted(THE_PR) is None


def test_a_thread_run_cut_off_is_not_the_pr_s_interrupted_run(world):
    world.script(Outcome(events=(INIT,), finishes=False))
    run = world.runs.fix(_thread(world.worktree))
    pump_until(run, world.started_in)

    run.interrupt()

    assert world.restarted().interrupted(THE_PR) is None


def test_the_run_carried_on_from_an_interruption_finishing_ends_the_interruption(world):
    run = world.script(Outcome(events=(INIT,), finishes=False)).start()
    pump_until(run, world.started_in)
    run.interrupt()
    restarted = world.restarted()

    finish(restarted.carry_on(world.worktree, THE_PR))

    assert world.restarted().interrupted(THE_PR) is None
