import re
import shlex

import pytest

from github_orchestrator.agent_runs import FixComment, ThreadFix
from github_orchestrator.agent_runs.fake import FakeAgentRuns
from github_orchestrator.pr_processes.fake import FakePrProcesses
from tests.agent_runs.cli_flags import assert_the_cli_takes, invocations
from tests.agent_runs.scripted_claude import ScriptedClaude
from tests.agent_runs.support import (
    PYTEST_WORKERS,
    PYTHON,
    finish,
    real_agent_runs,
)
from tests.builders import a_pr

THE_PR = a_pr(7, "acme/widgets")
KEY = "PRRT_1"
ONTO = "b" * 40
LEVELS = ("low", "medium", "high")
PAIRING_ADVICE = "Pass one `--file` per `--step`, in the same order"
CONFIDENCE_ADVICE = "Pass all three every time you report"


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


@pytest.fixture
def worktree(tmp_path):
    made = tmp_path / "wt"
    made.mkdir()
    return str(made)


def _fix(worktree, **fields):
    return ThreadFix(**{
        "pr": THE_PR, "key": KEY, "worktree": worktree, "author": "reviewer",
        "path": "src/foo.py", "line": 4, "body": "rename this",
        "comments": (FixComment("reviewer", "rename this", "2026-08-28T10:00:00Z"),),
        "confidence_levels": LEVELS, **fields})


def _ran(runs, claude, run):
    finish(run)
    return claude.prompts[-1]


def _fixed(runs, claude, worktree, **fields):
    return _ran(runs, claude, runs.fix(_fix(worktree, **fields)))


def _rebased(runs, claude, worktree, **fields):
    return _ran(runs, claude, runs.rebase_fix(_fix(worktree, **fields), ONTO))


def _reworked(runs, claude, worktree, **fields):
    return _ran(runs, claude, runs.rework(_fix(worktree, **fields)))


def _filing(runs, claude, worktree, tracker):
    return _ran(runs, claude, runs.file_ticket(_fix(
        worktree, tracker=tracker, tracker_project="PROJ", ticket_project="PROJ",
        ticket_title="Cache models", ticket_body="Each export reads its model again.")))


def _every(runs, claude, worktree):
    return [_fixed(runs, claude, worktree), _rebased(runs, claude, worktree),
            _reworked(runs, claude, worktree, note="do it again")]


def _fixing(runs, claude, worktree):
    return [_fixed(runs, claude, worktree),
            _reworked(runs, claude, worktree, note="do it again")]


def _in_session(world, runs, fix, steer=None):
    runs.open_session(fix, steer)
    [session] = world.pr_processes.sessions[fix.pr]
    return shlex.join(session.argv)


def _line_with(prompt, phrase):
    return next(line for line in prompt.splitlines() if phrase in line)


def test_every_report_command_a_prompt_prints_names_the_flags_the_cli_requires(
        runs, claude, worktree):
    for prompt in _every(runs, claude, worktree):
        found = invocations(prompt)
        assert found
        for verb, flags in found:
            assert_the_cli_takes(verb, flags)


@pytest.mark.parametrize("tracker", ["jira", "github"])
def test_the_filing_prompt_reports_through_commands_that_name_the_flags_the_cli_requires(
        runs, claude, worktree, tracker):
    found = invocations(_filing(runs, claude, worktree, tracker))

    assert sorted(verb for verb, _ in found) == ["fail", "filed"]
    for verb, flags in found:
        assert_the_cli_takes(verb, flags)


def test_the_thread_prompt_is_self_contained(runs, claude, worktree):
    prompt = _fixed(runs, claude, worktree, body="Please rename this helper.\nIt shadows a builtin.",
                    comments=(FixComment("reviewer",
                                         "Please rename this helper.\nIt shadows a builtin.",
                                         "2026-08-28T10:00:00Z"),))

    assert worktree in prompt
    assert "Please rename this helper.\nIt shadows a builtin." in prompt
    assert "reviewer" in prompt
    assert "src/foo.py" in prompt
    for verb in ("skip", "reply", "ready", "fail"):
        assert (
            f"{PYTHON} -m github_orchestrator.cli "
            f"thread {verb} --repo acme/widgets --pr 7 --thread-id {KEY}"
        ) in prompt
    for word in ("safe", "acknowledgement", "question", "unclear", "risky"):
        assert f"**{word}**" in prompt
    assert "not-a-change" not in prompt
    assert "general" in prompt
    assert "I'll" in prompt
    assert "--tests unverified" in prompt
    assert "Never push" in prompt
    assert ".claude/skills" not in prompt
    assert "handle-pull-request-feedback-autonomous" not in prompt


SKIPPED_AS = "risky|acknowledgement|needs-human"
REPLIED_AS = "unclear|out-of-scope|already-done|question"


def test_every_prompt_offers_a_reply_for_a_comment_that_needs_an_answer_and_no_code(
        runs, claude, worktree):
    for prompt in _every(runs, claude, worktree):
        reply = _line_with(prompt, "thread reply")
        assert f"--classification {REPLIED_AS}" in reply
        assert "--body" in reply


def test_the_thread_prompt_skips_only_what_needs_neither_code_nor_an_answer(
        runs, claude, worktree):
    prompt = _fixed(runs, claude, worktree)

    assert f"--classification {SKIPPED_AS} " in _line_with(prompt, "thread skip")
    assert "clarifying question" in prompt
    assert "outside this pull request" in prompt


def test_a_rework_from_a_reply_starts_from_the_reply_it_proposed(runs, claude, worktree):
    prompt = _reworked(runs, claude, worktree, note="say why it runs once",
                       reply="It runs once per poll.")

    assert "It runs once per poll." in prompt
    assert prompt.index("It runs once per poll.") < prompt.index("say why it runs once")


def test_a_thread_nobody_had_replied_to_says_nothing_about_before(runs, claude, worktree):
    assert "Before the newest reply" not in _fixed(runs, claude, worktree)


def test_the_prompts_cap_test_parallelism_at_the_workers_this_machine_allows(
        runs, claude, worktree):
    for prompt in _every(runs, claude, worktree):
        assert f"-n {PYTEST_WORKERS}" in prompt
        assert "-n auto" in prompt
        assert "other agents" in prompt.lower()


def test_every_prompt_asks_for_the_full_sha_git_log_oneline_does_not_print(
        runs, claude, worktree):
    for prompt in _every(runs, claude, worktree):
        reported = _line_with(prompt, "--sha")
        assert "full 40-character sha" in reported
        assert "`git rev-parse HEAD`" in reported


def test_every_prompt_that_asks_for_a_fix_asks_for_the_steps_first(runs, claude, worktree):
    for prompt in _fixing(runs, claude, worktree):
        assert prompt.index("thread plan") < prompt.index("thread step")
        assert "--step" in _line_with(prompt, "thread plan")
        assert "--done" in _line_with(prompt, "thread step")
        assert PAIRING_ADVICE in prompt


def test_the_plan_pairs_every_step_with_the_file_it_touches(runs, claude, worktree):
    plan = _line_with(_fixed(runs, claude, worktree), "thread plan")

    assert plan.count("--step") == plan.count("--file") == 2
    assert re.search(r"--step .*--file .*--step .*--file ", plan), plan


def test_the_plan_is_written_before_the_change_it_describes(runs, claude, worktree):
    prompt = _fixed(runs, claude, worktree)

    assert prompt.index("thread plan") < prompt.index("make the change")


def test_a_plan_of_steps_is_never_read_as_a_licence_to_commit_each_one(runs, claude, worktree):
    for prompt in _fixing(runs, claude, worktree):
        assert "one commit is how the fix lands" in prompt


def test_every_prompt_asks_what_the_fix_does_and_how_sure_the_agent_is(runs, claude, worktree):
    for prompt in _every(runs, claude, worktree):
        ready = _line_with(prompt, "--sha")
        assert "--summary" in ready
        assert "--confidence-note" in ready
        assert "low|medium|high" in ready


def test_every_prompt_that_can_report_ready_says_to_pass_all_three(runs, claude, worktree):
    for prompt in _every(runs, claude, worktree):
        assert CONFIDENCE_ADVICE in prompt, (
            "the flags render bracketed, so a prompt that shows them and says "
            "nothing reads as permission to leave them off"
        )


@pytest.mark.parametrize(("classification", "called"), [
    (None, "not safe"),
])
def test_a_session_on_a_skipped_fix_repeats_why_it_was_skipped(world, runs, worktree,
                                                                classification, called):
    prompt = _in_session(world, runs, _fix(worktree, classification=classification,
                                           skipped_because="two plausible readings"))

    assert f"It was classified {called} and skipped: two plausible readings" in prompt


def test_a_fix_that_was_not_skipped_says_nothing_about_a_skip(world, runs, worktree):
    prompt = _in_session(world, runs, _fix(worktree, classification="ambiguous"))

    assert "skipped" not in prompt
    assert "None" not in prompt


JIRA = {"tracker": "jira", "tracker_project": "PROJ", "branch_ticket": "PROJ-21"}
GITHUB_ISSUES = {"tracker": "github"}


def _tracked(runs, claude, worktree, tracker):
    return [_fixed(runs, claude, worktree, **tracker),
            _reworked(runs, claude, worktree, note="do it again", **tracker)]


def test_with_no_tracker_no_prompt_offers_a_ticket(runs, claude, worktree):
    for prompt in _every(runs, claude, worktree):
        assert "thread ticket" not in prompt
        assert "outside this pull request" in prompt


@pytest.mark.parametrize("tracker", [JIRA, GITHUB_ISSUES])
def test_with_a_tracker_the_fix_and_rework_offer_a_ticket_the_cli_takes(
        runs, claude, worktree, tracker):
    for prompt in _tracked(runs, claude, worktree, tracker):
        verbs = [verb for verb, _ in invocations(prompt)]
        assert "ticket" in verbs
        for verb, flags in invocations(prompt):
            assert_the_cli_takes(verb, flags)


@pytest.mark.parametrize("tracker", [JIRA, GITHUB_ISSUES])
def test_out_of_scope_work_is_searched_for_before_a_ticket_is_proposed(
        runs, claude, worktree, tracker):
    for prompt in _tracked(runs, claude, worktree, tracker):
        assert prompt.index("Search the tracker") < prompt.index("thread ticket")
        assert "Never file the ticket yourself" in prompt


def test_a_jira_prompt_names_the_default_project_the_repo_and_the_branch_s_ticket(
        runs, claude, worktree):
    prompt = _fixed(runs, claude, worktree, **JIRA)

    assert "Atlassian MCP" in prompt
    assert "JQL" in prompt
    assert "PROJ-21" in prompt
    assert "acme/widgets" in prompt
    assert '--project "<PROJ' in _line_with(prompt, "thread ticket")


def test_a_github_prompt_searches_and_proposes_issues_on_the_watched_repo(
        runs, claude, worktree):
    prompt = _fixed(runs, claude, worktree, **GITHUB_ISSUES)

    assert "gh issue list --repo acme/widgets" in prompt
    assert "--project acme/widgets " in _line_with(prompt, "thread ticket")
    assert "This branch's ticket" not in prompt


def test_a_rework_from_a_ticket_starts_from_the_ticket_it_proposed(runs, claude, worktree):
    prompt = _reworked(runs, claude, worktree, note="it belongs in WEB",
                       reply="I've proposed a ticket.", ticket_project="PROJ",
                       ticket_title="Cache models", ticket_body="Each export reads it again.",
                       **JIRA)

    for said in ("PROJ", "Cache models", "Each export reads it again.",
                 "I've proposed a ticket."):
        assert prompt.index(said) < prompt.index("it belongs in WEB")
    assert "proposed this reply instead of a change" not in prompt
