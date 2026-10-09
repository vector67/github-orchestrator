import json
from types import SimpleNamespace

import pytest

from github_orchestrator.agent_runs.fake import FakeAgentRuns
from github_orchestrator.pr_processes.fake import FakePrProcesses
from tests.agent_runs.scripted_claude import ScriptedClaude
from tests.agent_runs.support import real_agent_runs
from tests.builders import a_pr

BOUNDARY = ("", True)


def prose(*texts: str) -> list[tuple[str, bool]]:
    return [(text, False) for text in texts]


def assistant(*blocks: dict) -> dict:
    return {"type": "assistant", "message": {"content": list(blocks)}}


def tool_result(content: str) -> dict:
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "content": content}]}}


@pytest.fixture
def world(tmp_path):
    fake = FakeAgentRuns(FakePrProcesses())
    runs = real_agent_runs(fake, ScriptedClaude(fake), tmp_path)
    path = tmp_path / "transcripts" / "o" / "n" / "42.jsonl"
    path.parent.mkdir(parents=True)
    return SimpleNamespace(runs=runs, path=path)


@pytest.fixture
def tail(world):
    return lambda limit: world.runs.transcript_tail(a_pr(42, "o/n"), limit)


@pytest.fixture
def summarize_event(world, tail):
    def shown(event):
        write_transcript(world.path, [event])
        return [line for line, boundary in tail(100) if not boundary]
    return shown


def test_assistant_text_becomes_its_prose(summarize_event):
    event = assistant({"type": "text", "text": "Working tree is clean."})
    assert summarize_event(event) == ["Working tree is clean."]


def test_tool_use_becomes_a_bulleted_name_and_argument(summarize_event):
    event = assistant({
        "type": "tool_use",
        "name": "Read",
        "input": {"file_path": "/repo/src/loop.py"},
    })
    assert summarize_event(event) == ["● Read loop.py"]


def test_thinking_becomes_a_marker_not_its_text(summarize_event):
    event = assistant({"type": "thinking", "thinking": "Long private reasoning."})
    assert summarize_event(event) == ["✻ thinking"]


def test_tool_results_are_dropped(summarize_event):
    event = {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "content": "42 files"}]},
    }
    assert summarize_event(event) == []


def test_failed_tool_results_are_kept(summarize_event):
    event = {
        "type": "user",
        "message": {"content": [
            {"type": "tool_result", "is_error": True, "content": "No such file"},
        ]},
    }
    assert summarize_event(event) == ["↳ error: No such file"]


def test_result_event_reports_completion_and_duration(summarize_event):
    event = {"type": "result", "subtype": "success", "duration_ms": 134_000}
    assert summarize_event(event) == ["✓ done (2m14s)"]


def test_a_failed_result_event_reads_as_a_failure(summarize_event):
    event = {
        "type": "result",
        "subtype": "error_during_execution",
        "is_error": True,
        "duration_ms": 4_000,
        "result": "Execution error\nstack",
    }
    assert summarize_event(event) == ["✗ failed (4s): Execution error"]


def test_a_failed_result_event_skips_a_leading_blank_line(summarize_event):
    event = {
        "type": "result",
        "subtype": "error_during_execution",
        "is_error": True,
        "duration_ms": 4_000,
        "result": "\nExecution error\nstack",
    }
    assert summarize_event(event) == ["✗ failed (4s): Execution error"]


def test_a_failed_result_event_whose_text_is_all_blank_says_what_the_subtype_is(summarize_event):
    event = {
        "type": "result",
        "subtype": "error_max_turns",
        "is_error": True,
        "duration_ms": 4_000,
        "result": "\n  \n",
    }
    assert summarize_event(event) == ["✗ failed (4s): hit the turn limit"]


def test_an_unknown_failure_subtype_still_names_itself(summarize_event):
    event = {
        "type": "result",
        "subtype": "error_something_new",
        "is_error": True,
        "duration_ms": 4_000,
    }
    assert summarize_event(event) == ["✗ failed (4s): error_something_new"]


def test_system_events_are_dropped(summarize_event):
    assert summarize_event({"type": "system", "subtype": "init"}) == []
    assert summarize_event({"type": "system", "subtype": "hook_started"}) == []
    assert summarize_event({"type": "rate_limit_event"}) == []


def write_transcript(path, events):
    path.write_text("".join(json.dumps(event) + "\n" for event in events))


def test_tail_gives_up_rather_than_scanning_the_whole_transcript(world, tail):
    write_transcript(world.path, [
        assistant({"type": "text", "text": "ancient history"}),
        *[tool_result("x" * 100_000) for _ in range(45)],
        assistant({"type": "text", "text": "recent"}),
    ])
    lines = tail(1000)
    assert ("ancient history", False) not in lines
    assert lines[-1] == ("recent", False)


def test_a_large_dropped_event_does_not_starve_the_screen(world, tail):
    path = world.path
    write_transcript(path, [
        assistant({"type": "text", "text": "before the big read"}),
        tool_result("x" * 400_000),
        assistant({"type": "text", "text": "after the big read"}),
    ])
    assert tail(10) == prose(
        "before the big read", "after the big read")


def test_a_boundary_never_lands_at_the_top_of_the_result(world, tail):
    path = world.path
    write_transcript(path, [
        assistant({"type": "text", "text": "the run before"}),
        {"type": "system", "subtype": "init"},
        assistant({"type": "text", "text": "new run line one"}),
        assistant({"type": "text", "text": "new run line two"}),
    ])
    assert tail(3) == prose(
        "new run line one", "new run line two")


def test_tail_skips_unparseable_lines(world, tail):
    path = world.path
    path.write_text(
        json.dumps(assistant({"type": "text", "text": "good"})) + "\n"
        + "{not json\n"
        + json.dumps(assistant({"type": "text", "text": "also good"})) + "\n"
    )
    assert tail(10) == prose("good", "also good")


def test_a_new_run_is_marked_where_the_previous_one_ended(world, tail):
    path = world.path
    write_transcript(path, [
        assistant({"type": "text", "text": "first run"}),
        {"type": "result", "subtype": "success", "duration_ms": 1000},
        {"type": "system", "subtype": "init"},
        assistant({"type": "text", "text": "second run"}),
    ])
    lines = tail(10)
    assert lines.count(BOUNDARY) == 1
    assert lines == [*prose("first run", "✓ done (1s)"), BOUNDARY, *prose("second run")]


def test_other_system_events_do_not_start_a_run(world, tail):
    path = world.path
    write_transcript(path, [
        assistant({"type": "text", "text": "before"}),
        {"type": "system", "subtype": "hook_started"},
        assistant({"type": "text", "text": "after"}),
    ])
    assert tail(10) == prose("before", "after")


def test_prose_that_reads_exactly_like_the_rule_stays_prose(world, tail):
    path = world.path
    write_transcript(path, [assistant({"type": "text", "text": "── new run"})])
    assert tail(10) == prose("── new run")
