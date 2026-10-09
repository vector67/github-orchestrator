import subprocess

from github_orchestrator.board_api.fake import FakeBoardApi
from tests.pr_manager.support import run_manager


class RecordingRun:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.calls = []
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


def git_repo(tmp_path):
    repo = tmp_path / "wt"
    repo.mkdir()
    for argv in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
         "--allow-empty", "-m", "first"],
    ):
        subprocess.run(argv, cwd=repo, check=True, capture_output=True)
    return repo


def _ran(settings, worktree, *keys, run=None):
    board = FakeBoardApi()
    answers = []

    def ask():
        answers.extend(board.panel.run_git(each) for each in keys)

    modules = {} if run is None else {"run": run}
    run_manager(settings, ask, worktree=worktree, is_author=True, board=board, **modules)
    return answers


def test_the_argv_a_command_ran_with_does_not_leak_into_the_next_run(settings, tmp_path):
    seen = []

    def run(argv, **kwargs):
        seen.append(list(argv))
        argv.append("--force")
        return subprocess.CompletedProcess(argv, 0, "", "")

    _ran(settings, tmp_path, "p", "p", run=run)
    assert seen == [["git", "push"], ["git", "push"]]


def test_a_failing_captured_command_shows_its_exit_code(settings, tmp_path):
    [(exit_code, lines, _)] = _ran(settings, git_repo(tmp_path), "p")
    assert exit_code == 128
    assert any("No configured push destination" in line for line in lines)


def test_a_captured_command_answers_stdout_then_stderr(settings, tmp_path):
    [(_, lines, _)] = _ran(settings, tmp_path, "s",
                           run=RecordingRun(stdout="out1\nout2\n", stderr="oops\n"))
    assert lines == ["out1", "out2", "oops"]


def test_a_captured_command_drops_trailing_blank_lines_but_keeps_interior_ones(settings, tmp_path):
    [(_, lines, _)] = _ran(settings, tmp_path, "s", run=RecordingRun(stdout="a\n\nb\n\n\n"))
    assert lines == ["a", "", "b"]


def test_a_captured_command_is_bounded_and_cannot_prompt(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("SOME_INHERITED_VAR", "kept")
    run = RecordingRun()
    _ran(settings, tmp_path, "p", run=run)
    kwargs = run.calls[0][1]
    assert kwargs["timeout"] == 60
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kwargs["env"]["SOME_INHERITED_VAR"] == "kept"


def test_a_captured_command_that_times_out_says_so(settings, tmp_path):
    def run(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=60)

    [(exit_code, lines, _)] = _ran(settings, tmp_path, "p", run=run)
    assert (exit_code, lines) == (-1, ["timed out after 60s"])
