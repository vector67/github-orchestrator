import pytest

from github_orchestrator.agent_runs import Agent, ThreadFix
from github_orchestrator.agent_runs.fake import FakeAgentRuns
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.agent_runs.scripted_claude import ScriptedClaude
from tests.agent_runs.support import finish, real_agent_runs
from tests.builders import a_pr

THE_PR = a_pr(12, "acme/widgets")
CHANGED = {"CLAUDE.md": "be bold\n", ".mcp.json": "{}\n"}


@pytest.fixture(autouse=True)
def codex_home(tmp_path, monkeypatch):
    home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))


@pytest.fixture
def world():
    return FakeAgentRuns(FakePrProcesses())


@pytest.fixture
def copies():
    return FakeWorkingCopies()


@pytest.fixture(params=[Agent.CLAUDE, Agent.CODEX], ids=["claude", "codex"])
def agent(request):
    return request.param


@pytest.fixture
def program(world, agent):
    stand_in = ScriptedClaude(world, program=agent.value)
    yield stand_in
    stand_in.reap()


@pytest.fixture
def worktree(tmp_path):
    made = tmp_path / "wt"
    made.mkdir()
    return made


@pytest.fixture
def runs(world, program, tmp_path, copies, agent):
    return real_agent_runs(world, program, tmp_path, agent=agent, command=agent.value,
                           working_copies=copies)


def _loads_only_user_settings(argv, worktree):
    return ("--setting-sources" in argv
            or f'projects={{"{worktree.resolve()}"={{trust_level="untrusted"}}}}' in argv)


def _fix(worktree):
    return ThreadFix(pr=THE_PR, key="2313088871", worktree=str(worktree), author="octocat",
                     path="src/widgets.py", line=4, body="rename this", reviewing=True)


SOMEONE_ELSES_RUNS = [
    pytest.param(lambda runs, worktree: runs.review(
        str(worktree), THE_PR, "review-requested", title="Fix bug", url="", branch="fix",
        additions=1, deletions=1), id="review"),
    pytest.param(lambda runs, worktree: runs.rereview(
        str(worktree), THE_PR, "review-requested", title="Fix bug", url="", branch="fix",
        verdict="commented", said=None, since=None, commits=None, replied=()), id="rereview"),
    pytest.param(lambda runs, worktree: runs.carry_on(str(worktree), THE_PR, yours=False),
                 id="carry-on"),
    pytest.param(lambda runs, worktree: runs.fix(_fix(worktree)), id="thread-fix"),
    pytest.param(lambda runs, worktree: runs.carry_on_thread(_fix(worktree)),
                 id="thread-carry-on"),
    pytest.param(lambda runs, worktree: runs.answer_thread(_fix(worktree)), id="thread-answer"),
]

SOMEONE_ELSES_SESSIONS = [
    pytest.param(lambda runs, worktree: runs.rebase_in_session(THE_PR, str(worktree),
                                                               yours=False), id="rebase"),
    pytest.param(lambda runs, worktree: runs.ask_in_session(THE_PR, str(worktree), "Why?",
                                                            yours=False), id="question"),
    pytest.param(lambda runs, worktree: runs.open_session(_fix(worktree), None),
                 id="thread-session"),
    pytest.param(lambda runs, worktree: runs.fix_in_session(_fix(worktree)),
                 id="thread-first-fix"),
    pytest.param(lambda runs, worktree: runs.answer_in_session(_fix(worktree), "widen it"),
                 id="thread-answer"),
]


def _answered(copies, worktree, *, allowed):
    copies.change_agent_config(worktree, CHANGED)
    config = copies.agent_config(THE_PR, str(worktree))
    assert config is not None
    copies.answer_agent_config(THE_PR, config.digest, allowed=allowed)


def _run_argv(runs, program, worktree, started):
    finish(started(runs, worktree))
    [spawned] = program.spawned
    return spawned.argv


def _session_argv(runs, world, worktree, opened):
    assert opened(runs, worktree) is None
    [session] = world.pr_processes.sessions[THE_PR]
    return session.argv


@pytest.mark.parametrize("started", SOMEONE_ELSES_RUNS)
def test_a_run_on_someone_else_s_pr_that_changes_no_agent_configuration_loads_project_settings(
        runs, program, copies, worktree, started):
    copies.change_agent_config(worktree, {})

    assert not _loads_only_user_settings(_run_argv(runs, program, worktree, started), worktree)


@pytest.mark.parametrize("started", SOMEONE_ELSES_RUNS)
def test_a_run_on_someone_else_s_pr_whose_changes_you_allowed_loads_project_settings(
        runs, program, copies, worktree, started):
    _answered(copies, worktree, allowed=True)

    assert not _loads_only_user_settings(_run_argv(runs, program, worktree, started), worktree)


@pytest.mark.parametrize("started", SOMEONE_ELSES_RUNS)
def test_a_run_on_someone_else_s_pr_whose_changes_you_turned_down_loads_user_settings_only(
        runs, program, copies, worktree, started):
    _answered(copies, worktree, allowed=False)

    assert _loads_only_user_settings(_run_argv(runs, program, worktree, started), worktree)


@pytest.mark.parametrize("started", SOMEONE_ELSES_RUNS)
def test_a_run_on_someone_else_s_pr_whose_changes_wait_for_an_answer_loads_user_settings_only(
        runs, program, copies, worktree, started):
    copies.change_agent_config(worktree, CHANGED)

    assert _loads_only_user_settings(_run_argv(runs, program, worktree, started), worktree)


@pytest.mark.parametrize("started", SOMEONE_ELSES_RUNS)
def test_a_run_where_git_cannot_say_loads_user_settings_only(
        runs, program, worktree, started):
    assert _loads_only_user_settings(_run_argv(runs, program, worktree, started), worktree)


@pytest.mark.parametrize("opened", SOMEONE_ELSES_SESSIONS)
def test_a_session_on_someone_else_s_pr_that_changes_no_agent_configuration_loads_project_settings(
        runs, world, copies, worktree, opened):
    copies.change_agent_config(worktree, {})

    assert not _loads_only_user_settings(_session_argv(runs, world, worktree, opened), worktree)


@pytest.mark.parametrize("opened", SOMEONE_ELSES_SESSIONS)
def test_a_session_on_someone_else_s_pr_whose_changes_you_allowed_loads_project_settings(
        runs, world, copies, worktree, opened):
    _answered(copies, worktree, allowed=True)

    assert not _loads_only_user_settings(_session_argv(runs, world, worktree, opened), worktree)


@pytest.mark.parametrize("opened", SOMEONE_ELSES_SESSIONS)
def test_a_session_on_someone_else_s_pr_whose_changes_you_turned_down_loads_user_settings_only(
        runs, world, copies, worktree, opened):
    _answered(copies, worktree, allowed=False)

    assert _loads_only_user_settings(_session_argv(runs, world, worktree, opened), worktree)


@pytest.mark.parametrize("opened", SOMEONE_ELSES_SESSIONS)
def test_a_session_on_someone_else_s_pr_whose_changes_wait_for_an_answer_loads_user_settings_only(
        runs, world, copies, worktree, opened):
    copies.change_agent_config(worktree, CHANGED)

    assert _loads_only_user_settings(_session_argv(runs, world, worktree, opened), worktree)
