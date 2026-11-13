import json
import subprocess

import pytest

from github_orchestrator.agent_runs import Agent, ThreadFix
from github_orchestrator.agent_runs.fake import FakeAgentRuns, Outcome
from github_orchestrator.domain import LabelledComment
from github_orchestrator.pr_processes.fake import FakePrProcesses
from tests.agent_runs.scripted_claude import ScriptedClaude
from tests.agent_runs.support import finish, ledger_file, real_agent_runs
from tests.builders import a_pr

THE_PR = a_pr(7, "o/n")
MODEL = "gpt-test"
SUMMARY_MODEL = "gpt-test-mini"
THREAD = "0f3c2a10-1111-4222-8333-944455556666"


@pytest.fixture(autouse=True)
def codex_home(tmp_path, monkeypatch):
    home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))
    return home


@pytest.fixture
def world():
    return FakeAgentRuns(FakePrProcesses())


@pytest.fixture
def codex(world):
    stand_in = ScriptedClaude(world, program="codex")
    yield stand_in
    stand_in.reap()


@pytest.fixture
def runs(world, codex, tmp_path):
    return real_agent_runs(world, codex, tmp_path, agent=Agent.CODEX, command="codex",
                           model=MODEL, summary_model=SUMMARY_MODEL)


def _start(runs, tmp_path):
    return runs.fix_check(str(tmp_path), THE_PR, "ci-failed", check="tests", summary=None,
                          push=True)


def _transcript(tmp_path):
    return tmp_path / "transcripts" / "o" / "n" / "7.jsonl"


def _item(kind, phase="completed", **fields):
    return {"type": f"item.{phase}", "item": {"id": "item_0", "type": kind, **fields}}


A_TURN = (
    {"type": "thread.started", "thread_id": THREAD},
    {"type": "turn.started"},
    _item("reasoning", text="**Looking at the failing check**"),
    _item("agent_message", text="I'll rerun the tests, then fix what fails."),
    _item("command_execution", "started", command="/bin/zsh -lc 'make test'",
          aggregated_output="", exit_code=None, status="in_progress"),
    _item("command_execution", command="/bin/zsh -lc 'make test'",
          aggregated_output="1 failed", exit_code=2, status="failed"),
    _item("file_change", changes=[{"path": "/wt/src/widgets/loop.py", "kind": "update"}],
          status="completed"),
    _item("agent_message", text="Fixed the off-by-one in loop.py.\nTests pass."),
    {"type": "turn.completed", "usage": {"input_tokens": 1200, "cached_input_tokens": 800,
                                         "output_tokens": 90}},
)


def test_a_codex_run_is_exec_printing_json_and_approving_for_itself_on_the_model(
        runs, codex, tmp_path):
    finish(_start(runs, tmp_path))

    [spawned] = codex.spawned
    assert spawned.argv == ["codex", "exec", "--json", "--approve-for-me", "-m", MODEL, "-"]
    assert spawned.cwd == str(tmp_path)
    assert spawned.stdin == subprocess.PIPE
    [prompt] = codex.prompts
    assert "tests" in prompt


def test_carrying_on_resumes_the_thread_the_last_run_started(runs, world, codex, tmp_path):
    world.script(Outcome(events=A_TURN))
    finish(_start(runs, tmp_path))

    finish(runs.carry_on(str(tmp_path), THE_PR, yours=True))

    assert codex.spawned[1].argv == ["codex", "exec", "--json", "--approve-for-me",
                                     "-m", MODEL, "resume", THREAD, "-"]
    assert codex.prompts[1]


def test_carrying_on_with_no_thread_on_record_resumes_the_newest_session(runs, codex, tmp_path):
    finish(runs.carry_on(str(tmp_path), THE_PR, yours=True))

    [spawned] = codex.spawned
    assert spawned.argv == ["codex", "exec", "--json", "--approve-for-me", "-m", MODEL,
                            "resume", "--last", "-"]


def test_a_gist_is_a_read_only_ephemeral_exec_on_the_summary_model(runs, world, codex,
                                                                    monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    world.answer("rename it")
    written = []

    runs.summarize_comment("PRRT_x", None, None, "rename this", written.append, chars=60)
    assert runs.drain_summaries(10)

    [asked] = codex.asked
    assert asked.argv == ["codex", "exec", "--ephemeral", "--skip-git-repo-check",
                          "-s", "read-only", "-m", SUMMARY_MODEL, "-"]
    assert asked.prompt
    assert "OPENAI_API_KEY" not in asked.env
    assert written == ["rename it"]


def _untrusted(worktree):
    return ["-c", f'projects={{"{worktree.resolve()}"={{trust_level="untrusted"}}}}']


def _review(runs, worktree):
    return runs.review(str(worktree), THE_PR, "review-requested", title="Fix bug", url="",
                       branch="fix", additions=1, deletions=1)


def test_a_review_treats_the_branch_as_an_untrusted_project(runs, codex, tmp_path):
    finish(_review(runs, tmp_path))

    [spawned] = codex.spawned
    assert spawned.argv == ["codex", "exec", "--json", "--approve-for-me", "-m", MODEL,
                            *_untrusted(tmp_path), "-"]


def test_a_rereview_treats_the_branch_as_an_untrusted_project(runs, codex, tmp_path):
    finish(runs.rereview(str(tmp_path), THE_PR, "review-requested", title="Fix bug", url="",
                         branch="fix", verdict="commented", said=None, since=None,
                         commits=None, replied=()))

    [spawned] = codex.spawned
    assert spawned.argv[6:8] == _untrusted(tmp_path)


def test_carrying_on_on_someone_else_s_pr_treats_it_as_an_untrusted_project(
        runs, codex, tmp_path):
    finish(runs.carry_on(str(tmp_path), THE_PR, yours=False))

    [spawned] = codex.spawned
    assert spawned.argv == ["codex", "exec", "--json", "--approve-for-me", "-m", MODEL,
                            *_untrusted(tmp_path), "resume", "--last", "-"]


def test_untrusting_names_the_branch_by_its_real_path(runs, codex, tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")

    finish(_review(runs, tmp_path / "link"))

    [spawned] = codex.spawned
    assert spawned.argv[6:8] == _untrusted(tmp_path / "real")


def test_a_review_turns_off_every_skill_the_branch_carries(runs, codex, tmp_path):
    for skill in ("tidy", "group/ship"):
        (tmp_path / ".agents" / "skills" / skill).mkdir(parents=True)
        (tmp_path / ".agents" / "skills" / skill / "SKILL.md").write_text("---\n---\n")

    finish(_review(runs, tmp_path))

    [spawned] = codex.spawned
    skills = tmp_path.resolve() / ".agents" / "skills"
    assert spawned.argv[8:10] == [
        "-c", f'skills.config=[{{path="{skills / "group" / "ship" / "SKILL.md"}",enabled=false}},'
              f'{{path="{skills / "tidy" / "SKILL.md"}",enabled=false}}]']


def _reviewer_s_fix(tmp_path, *, reviewing):
    return ThreadFix(pr=THE_PR, key="2313088871", worktree=str(tmp_path), author="octocat",
                     path="src/foo.py", line=4, body="rename this", reviewing=reviewing)


def test_a_reviewer_s_thread_run_treats_the_branch_as_an_untrusted_project(
        runs, codex, tmp_path):
    finish(runs.fix(_reviewer_s_fix(tmp_path, reviewing=True)))

    [spawned] = codex.spawned
    assert spawned.argv == ["codex", "exec", "--json", "--approve-for-me", "-m", MODEL,
                            *_untrusted(tmp_path), "-"]


@pytest.mark.parametrize("started", [
    pytest.param(lambda runs, fix: runs.carry_on_thread(fix), id="carry-on"),
    pytest.param(lambda runs, fix: runs.answer_thread(fix), id="answer"),
])
def test_carrying_on_a_reviewer_s_thread_run_treats_the_branch_as_an_untrusted_project(
        runs, codex, tmp_path, started):
    finish(started(runs, _reviewer_s_fix(tmp_path, reviewing=True)))

    [spawned] = codex.spawned
    assert spawned.argv == ["codex", "exec", "--json", "--approve-for-me", "-m", MODEL,
                            *_untrusted(tmp_path), "resume", "--last", "-"]


def test_a_thread_run_on_your_own_pr_trusts_the_project(runs, codex, tmp_path):
    finish(runs.fix(_reviewer_s_fix(tmp_path, reviewing=False)))

    [spawned] = codex.spawned
    assert spawned.argv == ["codex", "exec", "--json", "--approve-for-me", "-m", MODEL, "-"]


def test_a_reviewer_s_thread_session_treats_the_branch_as_an_untrusted_project(
        runs, world, tmp_path):
    assert runs.open_session(_reviewer_s_fix(tmp_path, reviewing=True), None) is None

    [session] = world.pr_processes.sessions[THE_PR]
    assert session.argv[:3] == ["codex", *_untrusted(tmp_path)]
    assert "rename this" in session.argv[3]


def test_a_reviewer_s_first_fix_in_a_session_treats_the_branch_as_an_untrusted_project(
        runs, world, tmp_path):
    assert runs.fix_in_session(_reviewer_s_fix(tmp_path, reviewing=True)) is None

    [session] = world.pr_processes.sessions[THE_PR]
    assert session.argv[:3] == ["codex", *_untrusted(tmp_path)]


def test_answering_a_reviewer_s_thread_in_a_session_treats_the_branch_as_an_untrusted_project(
        runs, world, tmp_path):
    assert runs.answer_in_session(_reviewer_s_fix(tmp_path, reviewing=True), None) is None

    [session] = world.pr_processes.sessions[THE_PR]
    assert session.argv == ["codex", *_untrusted(tmp_path), "resume", "--last"]


def test_a_commit_check_treats_the_checkout_as_an_untrusted_project(
        runs, world, codex, tmp_path):
    world.answer("addressed || it renames the helper")

    runs.check_commit("PRRT_x", [LabelledComment("you", "octocat", "rename this")], path=None, line=None,
                      sha="abc1234def", shown="commit abc1234def", worktree=str(tmp_path),
                      answers={"addressed": "yes"}, done=lambda word, reasoning: None)
    assert runs.drain_summaries(10)

    [asked] = codex.asked
    assert asked.argv == ["codex", "exec", "--ephemeral", "-s", "read-only", "-m", MODEL,
                          *_untrusted(tmp_path), "-"]
    assert asked.cwd == str(tmp_path)


def test_a_commit_check_turns_off_every_mcp_server_the_user_configured(
        runs, world, codex, codex_home, tmp_path):
    (codex_home / "config.toml").write_text(
        '[mcp_servers.notes]\ncommand = "notes"\n\n[mcp_servers."acme.tracker"]\nurl = "x"\n')
    world.answer("addressed || it renames the helper")

    runs.check_commit("PRRT_x", [LabelledComment("you", "octocat", "rename this")], path=None, line=None,
                      sha="abc1234def", shown="commit abc1234def", worktree=str(tmp_path),
                      answers={"addressed": "yes"}, done=lambda word, reasoning: None)
    assert runs.drain_summaries(10)

    [asked] = codex.asked
    assert asked.argv[-3:] == [
        "-c", 'mcp_servers={"notes"={enabled=false},"acme.tracker"={enabled=false}}', "-"]


def test_a_gist_turns_off_every_mcp_server_the_user_configured(runs, world, codex, codex_home):
    (codex_home / "config.toml").write_text('[mcp_servers.notes]\ncommand = "notes"\n')
    world.answer("rename it")

    runs.summarize_comment("PRRT_x", None, None, "rename this", lambda text: None, chars=60)
    assert runs.drain_summaries(10)

    [asked] = codex.asked
    assert asked.argv[-3:] == ["-c", 'mcp_servers={"notes"={enabled=false}}', "-"]


def test_a_run_never_sees_the_platform_api_key(runs, codex, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    finish(_start(runs, tmp_path))

    [spawned] = codex.spawned
    assert "OPENAI_API_KEY" not in spawned.env


def test_a_rebase_session_asks_codex_for_the_skill(runs, world):
    assert runs.rebase_in_session(THE_PR, "/tmp/wt", yours=True) is None

    [session] = world.pr_processes.sessions[THE_PR]
    assert session.argv == ["codex", "$rebase-on-main"]


def test_a_rebase_session_on_someone_else_s_pr_treats_it_as_an_untrusted_project(
        runs, world, tmp_path):
    assert runs.rebase_in_session(THE_PR, str(tmp_path), yours=False) is None

    [session] = world.pr_processes.sessions[THE_PR]
    assert session.argv == ["codex", *_untrusted(tmp_path), "$rebase-on-main"]


def test_a_question_on_your_own_pr_trusts_the_project(runs, world, tmp_path):
    assert runs.ask_in_session(THE_PR, str(tmp_path), "Why this name?", yours=True) is None

    [session] = world.pr_processes.sessions[THE_PR]
    assert session.argv == ["codex", "--", "Why this name?"]


def test_a_question_on_someone_else_s_pr_treats_it_as_an_untrusted_project(
        runs, world, tmp_path):
    assert runs.ask_in_session(THE_PR, str(tmp_path), "Why this name?", yours=False) is None

    [session] = world.pr_processes.sessions[THE_PR]
    assert session.argv == ["codex", *_untrusted(tmp_path), "--", "Why this name?"]


def test_a_rework_session_starts_codex_on_the_prompt(runs, world):
    fix = ThreadFix(pr=THE_PR, key="2313088871", worktree="/tmp/wt", author="reviewer",
                    path="src/foo.py", line=4, body="rename this")

    assert runs.open_session(fix, None) is None

    [session] = world.pr_processes.sessions[THE_PR]
    assert session.argv[0] == "codex"
    assert "rename this" in session.argv[1]
    assert len(session.argv) == 2


def test_answering_a_question_resumes_codex_s_newest_session_in_the_worktree(runs, world):
    fix = ThreadFix(pr=THE_PR, key="2313088871", worktree="/tmp/wt", author="reviewer",
                    path="src/foo.py", line=4, body="rename this")

    assert runs.answer_in_session(fix, None) is None

    [session] = world.pr_processes.sessions[THE_PR]
    assert (session.worktree, session.argv) == ("/tmp/wt", ["codex", "resume", "--last"])
    assert session.kept


def test_answering_a_question_resumes_the_thread_that_thread_s_run_started(
        runs, world, tmp_path):
    world.script(Outcome(events=({"type": "thread.started", "thread_id": THREAD},)))
    fix = ThreadFix(pr=THE_PR, key="2313088871", worktree=str(tmp_path), author="reviewer",
                    path="src/foo.py", line=4, body="rename this")
    finish(runs.fix(fix))

    assert runs.answer_in_session(fix, None) is None

    [session] = world.pr_processes.sessions[THE_PR]
    assert session.argv == ["codex", "resume", THREAD]


OTHER_THREAD = "1a2b3c4d-5555-4666-8777-988899990000"


def _thread_fix(tmp_path, key="2313088871", **fields):
    return ThreadFix(pr=THE_PR, key=key, worktree=str(tmp_path), author="reviewer",
                     path="src/foo.py", line=4, body="rename this", **fields)


def test_answering_a_question_in_a_session_hands_codex_the_answer_as_its_first_message(
        runs, world, tmp_path):
    world.script(Outcome(events=({"type": "thread.started", "thread_id": THREAD},)))
    finish(runs.fix(_thread_fix(tmp_path)))

    assert runs.answer_in_session(_thread_fix(tmp_path), "widen the bound") is None

    [session] = world.pr_processes.sessions[THE_PR]
    assert session.argv[:3] == ["codex", "resume", THREAD]
    assert "widen the bound" in session.argv[3]


def test_an_answer_carries_on_the_thread_its_own_run_started_not_the_pr_s_newest(
        runs, world, codex, tmp_path):
    world.script(Outcome(events=({"type": "thread.started", "thread_id": THREAD},)),
                 Outcome(events=({"type": "thread.started", "thread_id": OTHER_THREAD},)))
    finish(runs.fix(_thread_fix(tmp_path)))
    finish(runs.fix(_thread_fix(tmp_path, key="2313088872")))

    finish(runs.answer_thread(_thread_fix(tmp_path, note="widen the bound")))

    assert codex.spawned[-1].argv[-3:] == ["resume", THREAD, "-"]
    assert "widen the bound" in codex.prompts[-1]


def test_an_answer_in_a_session_with_no_codex_session_on_record_resumes_the_newest_with_it(
        runs, world, tmp_path):
    assert runs.answer_in_session(_thread_fix(tmp_path), "widen the bound") is None

    [session] = world.pr_processes.sessions[THE_PR]
    assert session.argv[:3] == ["codex", "resume", "--last"]
    assert "widen the bound" in session.argv[3]
    assert len(session.argv) == 4


def test_an_answer_with_no_codex_session_on_record_resumes_the_newest_with_it_on_stdin(
        runs, codex, tmp_path):
    finish(runs.answer_thread(_thread_fix(tmp_path, note="widen the bound")))

    [spawned] = codex.spawned
    assert spawned.argv[-3:] == ["resume", "--last", "-"]
    assert "widen the bound" in codex.prompts[-1]


def test_a_codex_turn_reads_on_the_board_as_what_it_said_and_ran(runs, world, tmp_path):
    world.script(Outcome(events=A_TURN))

    run = _start(runs, tmp_path)
    finish(run)

    assert runs.transcript_tail(THE_PR, 20) == [
        ("✻ thinking", False),
        ("I'll rerun the tests, then fix what fails.", False),
        ("● make test", False),
        ("↳ error: exit 2", False),
        ("● edit loop.py", False),
        ("Fixed the off-by-one in loop.py.", False),
        ("Tests pass.", False),
        ("✓ done", False),
    ]
    assert run.last_action == "✓ done"
    assert [json.loads(line)["type"] for line in _transcript(tmp_path).read_text().splitlines()
            ] == [event["type"] for event in A_TURN]


def test_a_codex_run_goes_in_the_ledger_unpriced_with_its_turns(runs, world, tmp_path):
    world.script(Outcome(events=A_TURN))

    finish(_start(runs, tmp_path))

    [entry] = ledger_file(tmp_path / "runs.jsonl")
    assert entry["num_turns"] == 1
    assert "total_cost_usd" not in entry
    assert "is_error" not in entry
    assert runs.last_run(THE_PR).exit_code == 0


def test_a_failed_turn_is_an_error_in_the_ledger_and_says_why(runs, world, tmp_path):
    world.script(Outcome(events=(
        {"type": "thread.started", "thread_id": THREAD},
        {"type": "turn.started"},
        {"type": "turn.failed", "error": {"message": "usage limit reached"}},
    ), exit_code=1))

    run = _start(runs, tmp_path)
    finish(run)

    [entry] = ledger_file(tmp_path / "runs.jsonl")
    assert (entry["num_turns"], entry["is_error"]) == (1, True)
    assert run.last_action == "✗ failed: usage limit reached"


def test_a_second_run_is_marked_where_the_first_ended(runs, world, tmp_path):
    world.script(Outcome(events=A_TURN), Outcome(events=A_TURN[:4]))

    finish(_start(runs, tmp_path))
    finish(runs.carry_on(str(tmp_path), THE_PR, yours=True))

    tail = runs.transcript_tail(THE_PR, 4)
    assert tail == [("✓ done", False), ("", True), ("✻ thinking", False),
                    ("I'll rerun the tests, then fix what fails.", False)]


def test_a_claude_transcript_already_on_disk_still_reads(runs, tmp_path):
    path = _transcript(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(event) + "\n" for event in (
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "On it."}]}},
        {"type": "result", "is_error": False, "duration_ms": 61000},
    )))

    assert runs.transcript_tail(THE_PR, 10) == [("On it.", False), ("✓ done (1m01s)", False)]
