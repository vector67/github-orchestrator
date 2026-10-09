import json
import logging
import os
import re
import subprocess
import threading
from datetime import datetime, timezone

import pytest

from github_orchestrator.agent_runs import ThreadFix
from github_orchestrator.agent_runs.fake import FakeAgentRuns, Outcome
from github_orchestrator.pr_processes.fake import FakePrProcesses
from tests.agent_runs.scripted_claude import ScriptedClaude
from tests.agent_runs.support import (
    SUMMARY_MODEL,
    finish,
    pump_until,
    real_agent_runs,
)
from tests.builders import a_pr

REPO = "o/n"
PR = 7
THE_PR = a_pr(PR, REPO)


@pytest.fixture
def world():
    return FakeAgentRuns(FakePrProcesses())


@pytest.fixture
def claude(world):
    stand_in = ScriptedClaude(world)
    yield stand_in
    stand_in.reap()


@pytest.fixture
def runs(world, claude, tmp_path):
    return real_agent_runs(world, claude, tmp_path)


def _start(runs, tmp_path, event_type="ci-failed"):
    return runs.fix_check(str(tmp_path), THE_PR, event_type, check="tests", summary=None,
                          push=True)


def _transcript(tmp_path):
    path = tmp_path / "transcripts" / "o" / "n" / f"{PR}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_a_run_is_claude_printing_stream_json_on_the_model(runs, claude, tmp_path):
    finish(_start(runs, tmp_path))

    [spawned] = claude.spawned
    assert spawned.argv == [
        "claude",
        "--print",
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", "auto",
        "--model", "opus",
    ]
    assert spawned.cwd == str(tmp_path)
    assert spawned.stdin == subprocess.PIPE


def test_a_continued_run_asks_claude_to_continue_with_a_prompt_on_stdin(runs, claude, tmp_path):
    finish(runs.carry_on(str(tmp_path), THE_PR))

    [spawned] = claude.spawned
    assert spawned.argv[-1] == "--continue"
    [prompt] = claude.prompts
    assert prompt


WORK = "CLAUDE_CONFIG_DIR=~/.claude-work claude"
WORK_ARGV = ["env", "CLAUDE_CONFIG_DIR=/home/me/.claude-work", "claude"]


@pytest.fixture
def work_runs(world, claude, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", "/home/me")
    return real_agent_runs(world, claude, tmp_path, command=WORK)


def test_a_run_starts_the_configured_command_with_its_settings_and_home_filled_in(
        work_runs, claude, tmp_path):
    finish(_start(work_runs, tmp_path))

    [spawned] = claude.spawned
    assert spawned.argv[:4] == [*WORK_ARGV, "--print"]


def test_a_gist_is_asked_of_the_configured_command(work_runs, world, claude):
    world.answer("rename it")

    work_runs.summarize_comment("PRRT_x", None, None, "rename this", lambda gist: None,
                               chars=60)
    assert work_runs.drain_summaries(10)

    [asked] = claude.asked
    assert asked.argv == [*WORK_ARGV, "--print", "--model", SUMMARY_MODEL]


def test_a_rebase_session_runs_the_configured_command(work_runs, world):
    assert work_runs.rebase_in_session(THE_PR, "/tmp/wt") is None

    [session] = world.pr_processes.sessions[THE_PR]
    assert session.argv == [*WORK_ARGV, "/rebase-on-main"]


def test_a_rework_session_runs_the_configured_command(work_runs, world):
    fix = ThreadFix(pr=THE_PR, key="2313088871", worktree="/tmp/wt", author="reviewer",
                    path="src/foo.py", line=4, body="rename this")

    assert work_runs.open_session(fix, None) is None

    [session] = world.pr_processes.sessions[THE_PR]
    assert session.argv[:len(WORK_ARGV)] == WORK_ARGV


def test_a_run_never_sees_the_console_api_key(runs, claude, tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("SOME_INHERITED_VAR", "kept")

    finish(_start(runs, tmp_path))

    [spawned] = claude.spawned
    assert "ANTHROPIC_API_KEY" not in spawned.env
    assert spawned.env["SOME_INHERITED_VAR"] == "kept"


def test_every_line_claude_writes_is_kept_in_the_prs_transcript(runs, world, tmp_path):
    world.script(Outcome(events=(
        {"type": "system", "subtype": "init", "session_id": "s1"},
        {"type": "assistant", "message": {"role": "assistant"}},
        {"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.0},
    )))

    finish(_start(runs, tmp_path))

    assert [event["type"] for event in _transcript(tmp_path)] == ["system", "assistant", "result"]


LAST_LINE_WITHOUT_NEWLINE = r"""
import json, sys
sys.stdin.read()
sys.stdout.write(json.dumps({"type": "system", "subtype": "init"}) + "\n")
sys.stdout.write(json.dumps({"type": "result", "subtype": "success"}))
sys.stdout.flush()
"""


def test_a_last_line_with_no_newline_is_still_kept(runs, claude, tmp_path):
    claude.scripts.append(LAST_LINE_WITHOUT_NEWLINE)

    finish(_start(runs, tmp_path))

    assert [event["type"] for event in _transcript(tmp_path)] == ["system", "result"]


STDERR_NOISE = r"""
import json, sys
sys.stdin.read()
sys.stderr.write("warning: deprecated option foo\n")
sys.stderr.flush()
sys.stdout.write(json.dumps({"type": "system", "subtype": "init"}) + "\n")
sys.stdout.flush()
sys.stderr.write("debug: non-json diagnostic line\n")
sys.stderr.flush()
sys.stdout.write(json.dumps({"type": "result", "subtype": "success"}) + "\n")
sys.stdout.flush()
"""


def test_stderr_between_events_is_logged_and_kept_out_of_the_transcript(
    runs, claude, tmp_path, caplog,
):
    claude.scripts.append(STDERR_NOISE)

    with caplog.at_level(logging.WARNING):
        finish(_start(runs, tmp_path))

    assert [event["type"] for event in _transcript(tmp_path)] == ["system", "result"]
    assert "warning: deprecated option foo" in caplog.text
    assert "debug: non-json diagnostic line" in caplog.text


EMOJI_ACROSS_A_READ = r"""
import json, sys
sys.stdin.read()
init = (json.dumps({"type": "system", "subtype": "init"}) + "\n").encode()
prefix = '{"type": "assistant", "message": {"padding": "'
filler = "x" * (65536 - 2 - len(init) - len(prefix.encode()))
assistant = prefix + filler + "\U0001F389" + filler + '"}}'
sys.stdout.buffer.write(init)
sys.stdout.buffer.write(assistant.encode() + b"\n")
sys.stdout.buffer.write((json.dumps({"type": "result", "subtype": "success"}) + "\n").encode())
sys.stdout.flush()
"""


def test_a_character_split_across_two_reads_arrives_whole(runs, claude, tmp_path):
    claude.scripts.append(EMOJI_ACROSS_A_READ)

    finish(_start(runs, tmp_path))

    events = _transcript(tmp_path)
    assert [event["type"] for event in events] == ["system", "assistant", "result"]
    assert "\U0001F389" in events[1]["message"]["padding"]


EMOJI_ACROSS_A_PAUSE = r"""
import json, os, sys, time
sys.stdin.read()
emoji = "\U0001F389".encode()
sys.stdout.buffer.write((json.dumps({"type": "system", "subtype": "init"}) + "\n").encode())
sys.stdout.buffer.write(b'{"type": "assistant", "message": {"padding": "' + emoji[:2])
sys.stdout.flush()
while not os.path.exists("go-on"):
    time.sleep(0.005)
sys.stdout.buffer.write(emoji[2:] + b'"}}\n')
sys.stdout.buffer.write((json.dumps({"type": "result", "subtype": "success"}) + "\n").encode())
sys.stdout.flush()
"""


def test_a_character_split_across_a_pause_in_the_output_costs_no_line(runs, claude, tmp_path):
    claude.scripts.append(EMOJI_ACROSS_A_PAUSE)
    run = _start(runs, tmp_path)
    transcript = tmp_path / "transcripts" / "o" / "n" / f"{PR}.jsonl"
    pump_until(run, transcript.exists)
    (tmp_path / "go-on").touch()

    finish(run)

    events = _transcript(tmp_path)
    assert [event["type"] for event in events] == ["system", "assistant", "result"]
    assert "\U0001F389" in events[1]["message"]["padding"]


LAST_WORDS_ON_CUE = r"""
import json, os, sys, time
sys.stdin.read()
while not os.path.exists("go-on"):
    time.sleep(0.005)
sys.stdout.write(json.dumps({"type": "result", "subtype": "success"}) + "\n")
sys.stdout.flush()
"""


def test_what_claude_writes_just_before_it_exits_is_still_kept(runs, claude, tmp_path):
    claude.scripts.append(LAST_WORDS_ON_CUE)
    run = _start(runs, tmp_path)
    proc = run.proc
    poll = proc.poll

    def exits_while_being_asked() -> int | None:
        (tmp_path / "go-on").touch()
        proc.wait(timeout=5)
        return poll()

    proc.poll = exits_while_being_asked

    finish(run)

    assert [event["type"] for event in _transcript(tmp_path)] == ["result"]


RUNAWAY_LINE = r"""
import json, sys
sys.stdin.read()
sys.stdout.write("x" * (224 * 1024))
sys.stdout.write("\n" + json.dumps({"type": "result", "subtype": "success"}) + "\n")
sys.stdout.flush()
"""


def test_a_runaway_line_is_dropped_and_the_run_carries_on(runs, claude, tmp_path, caplog,
                                                          monkeypatch):
    monkeypatch.setattr("github_orchestrator.agent_runs._runs._MAX_BUFFER_BYTES", 128 * 1024)
    claude.scripts.append(RUNAWAY_LINE)

    with caplog.at_level(logging.ERROR):
        finish(_start(runs, tmp_path))

    assert [event["type"] for event in _transcript(tmp_path)] == ["result"]
    assert "stdout buffer exceeded" in caplog.text


class _Racing:
    def __init__(self, step: float) -> None:
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        self.now += self.step
        return self.now


def test_a_run_that_ignores_termination_is_killed(world, claude, tmp_path):
    claude.ignores_terminate = True
    runs = real_agent_runs(world, claude, tmp_path, clock=_Racing(2.5))
    world.script(Outcome(events=({"type": "system", "subtype": "init"},), finishes=False))
    run = _start(runs, tmp_path)
    pump_until(run, (tmp_path / "transcripts" / "o" / "n" / f"{PR}.jsonl").exists)

    run.terminate()

    assert claude.children[0].wait(timeout=5) == -9


def test_an_unwritable_ledger_does_not_stop_the_run_ending(world, claude, tmp_path):
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("")
    runs = real_agent_runs(world, claude, blocked)

    run = _start(runs, tmp_path)
    finish(run)

    assert run.is_alive() is False


def _ledger_line(**fields):
    return json.dumps({"ended_at": "2026-09-01T10:00:00+00:00", "repo": REPO, "pr": PR,
                       "event": "ci-failed", "exit_code": 0, **fields}) + "\n"


def test_a_torn_line_does_not_hide_the_run_under_it(runs, tmp_path):
    (tmp_path / "runs.jsonl").write_text(_ledger_line(event="new-comments") + "{half-written\n")

    assert runs.last_run(THE_PR).event_type == "new-comments"


def test_a_junk_exit_code_reads_as_unknown(runs, tmp_path):
    (tmp_path / "runs.jsonl").write_text(_ledger_line(exit_code="boom"))

    assert runs.last_run(THE_PR).exit_code is None


def test_the_last_run_is_not_looked_for_past_the_newest_quarter_megabyte(runs, tmp_path):
    other = _ledger_line(repo="o/other", pr=9, event="new-comments")
    (tmp_path / "runs.jsonl").write_text(
        _ledger_line() + other * (256 * 1024 // len(other) + 1))

    assert runs.last_run(THE_PR) is None


def test_a_run_inside_the_last_quarter_megabyte_is_found(runs, tmp_path):
    other = _ledger_line(repo="o/other", pr=9, event="new-comments")
    (tmp_path / "runs.jsonl").write_text(
        _ledger_line() + other * (200 * 1024 // len(other)))

    assert runs.last_run(THE_PR).event_type == "ci-failed"


def test_a_gist_is_asked_of_the_summary_model_away_from_any_checkout(runs, world, claude,
                                                                      monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    world.answer("rename it")

    runs.summarize_comment("PRRT_x", None, None, "rename this", lambda gist: None,
                           chars=60)
    assert runs.drain_summaries(10)

    [asked] = claude.asked
    assert asked.argv == ["claude", "--print", "--model", SUMMARY_MODEL]
    assert "ANTHROPIC_API_KEY" not in asked.env
    assert asked.timeout == 300
    assert asked.cwd_existed
    assert asked.cwd != os.getcwd()


def test_no_gist_is_asked_for_when_no_summary_model_is_configured(world, claude, tmp_path):
    runs = real_agent_runs(world, claude, tmp_path, summary_model="")
    world.answer("rename it")
    written = []

    runs.summarize_comment("PRRT_x", None, None, "rename this", written.append,
                           chars=60)

    assert runs.drain_summaries(10)
    assert claude.asked == []
    assert written == []


def test_the_gist_comes_back_on_the_summariser_s_own_thread(runs, world):
    world.answer("rename it")
    threads = []

    runs.summarize_comment("PRRT_x", None, None, "rename this", lambda gist: threads.append(threading.current_thread()),
                           chars=60)

    assert runs.drain_summaries(10)
    assert threads and threading.current_thread() not in threads


def test_a_model_that_cannot_be_reached_writes_no_gist(runs, claude):
    claude.summary_failure = subprocess.TimeoutExpired(["claude"], 300)
    written = []

    runs.summarize_comment("PRRT_x", None, None, "rename this", written.append,
                           chars=60)

    assert runs.drain_summaries(10)
    assert written == []


def _gist_log(caplog, label):
    return [record.getMessage() for record in caplog.records if label in record.getMessage()]


def test_a_gist_job_logs_its_start_and_how_long_the_model_took(runs, world, caplog):
    world.answer("rename it")

    with caplog.at_level(logging.INFO):
        runs.summarize_comment("PRRT_a", None, None, "rename this", lambda gist: None,
                           chars=60)
        assert runs.drain_summaries(10)

    started, finished = _gist_log(caplog, "PRRT_a")
    assert re.fullmatch(rf"gist for PRRT_a started on {SUMMARY_MODEL} after waiting \d+\.\ds for a lane",
                        started)
    assert re.fullmatch(r"gist for PRRT_a written in \d+\.\ds", finished)


def test_a_gist_job_that_gets_no_gist_logs_that_it_came_back_empty(runs, claude, caplog):
    claude.summary_failure = subprocess.TimeoutExpired(["claude"], 300)

    with caplog.at_level(logging.INFO):
        runs.summarize_comment("PRRT_b", None, None, "rename this", lambda gist: None,
                           chars=60)
        assert runs.drain_summaries(10)

    assert re.fullmatch(r"gist for PRRT_b came back empty after \d+\.\ds",
                        _gist_log(caplog, "PRRT_b")[-1])


DAY_START = datetime(2026, 9, 1, tzinfo=timezone.utc)


def test_finished_runs_are_read_off_the_ledger_already_on_disk(runs, tmp_path):
    (tmp_path / "runs.jsonl").write_text(
        _ledger_line(ended_at="2026-08-31T23:00:00+00:00", event="yesterday")
        + _ledger_line(event="new-comments", elapsed_seconds=120.5, total_cost_usd=0.4)
        + _ledger_line(event="ci-failed", elapsed_seconds=30))

    finished = runs.finished_since(DAY_START)

    assert [(run.pr, run.event, run.elapsed_seconds, run.cost_usd) for run in finished] == [
        (THE_PR, "new-comments", 120.5, 0.4), (THE_PR, "ci-failed", 30, None)]
    assert finished[0].ended_at == datetime(2026, 9, 1, 10, tzinfo=timezone.utc)


def test_a_line_that_will_not_read_is_left_out_of_the_finished_runs(runs, tmp_path):
    (tmp_path / "runs.jsonl").write_text(
        _ledger_line() + "{not json\n" + json.dumps(["a list"]) + "\n" + _ledger_line())

    assert len(runs.finished_since(DAY_START)) == 2


@pytest.mark.parametrize(("repo", "pr"), [("no-slash", 9), ("o/n", "nine")])
def test_a_finished_run_whose_pr_will_not_read_is_on_no_pr(runs, tmp_path, repo, pr):
    (tmp_path / "runs.jsonl").write_text(_ledger_line(repo=repo, pr=pr))

    [finished] = runs.finished_since(DAY_START)
    assert finished.pr is None


def test_a_finished_run_that_said_no_time_took_none(runs, tmp_path):
    (tmp_path / "runs.jsonl").write_text(_ledger_line(elapsed_seconds="soon"))

    [finished] = runs.finished_since(DAY_START)
    assert finished.elapsed_seconds == 0


def test_no_ledger_is_no_finished_runs(runs):
    assert runs.finished_since(DAY_START) == []


def test_finished_runs_are_looked_for_only_in_the_ledger_s_newest_stretch(runs, tmp_path,
                                                                        monkeypatch):
    monkeypatch.setattr("github_orchestrator.agent_runs._runs.FINISHED_SCAN_BYTES", 64 * 1024)
    line = _ledger_line()
    written = 80 * 1024 // len(line)
    (tmp_path / "runs.jsonl").write_text(line * written)

    assert 0 < len(runs.finished_since(DAY_START)) < written


def test_a_transcript_that_cannot_be_written_does_not_stop_the_run(runs, world, tmp_path,
                                                                   caplog):
    (tmp_path / "transcripts").write_text("not a folder")
    world.script(Outcome(events=({"type": "assistant", "message": {
        "content": [{"type": "text", "text": "working"}]}},)))
    run = _start(runs, tmp_path)

    with caplog.at_level(logging.WARNING):
        finish(run)

    assert run.last_action == "working"
    assert "could not write the transcript" in caplog.text
