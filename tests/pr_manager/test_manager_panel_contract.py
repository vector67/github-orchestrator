import shlex
import subprocess

import pytest

from github_orchestrator.agent_runs.fake import FakeAgentRuns, Outcome
from github_orchestrator.board_api.fake import FakeBoardApi, FakeManagerPanel
from github_orchestrator.pr_processes.fake import FakePrProcesses
from tests.builders import a_pr
from tests.pr_manager.support import PR, REPO, run_manager

THE_PR = a_pr(PR, REPO)


def _said(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


class FakeSide:
    def __init__(self):
        self.panel = FakeManagerPanel()

    def notes(self, text):
        self.panel.changes_text = text

    def said(self, *texts):
        self.panel.output.extend((text, False) for text in texts)

    def git_prints(self, exit_code, *lines):
        self.panel.git_answer = (exit_code, list(lines), 0.2)

    def has_nowhere_to_open(self, reason):
        self.panel.terminal_refusal = reason

    def settle(self, *commands):
        for command in commands:
            command(self.panel)
        return self.panel


class ManagerSide:
    def __init__(self, settings, worktree):
        self.settings, self.worktree = settings, worktree
        self.windows = FakePrProcesses()
        self.runs = FakeAgentRuns(self.windows)
        self.git = (0, "", "")
        self.ran = []
        self.windows.open(THE_PR, worktree)
        self.windows.changes.pop(worktree)

    def notes(self, text):
        self.windows.changes[self.worktree] = text

    def said(self, *texts):
        self.runs.script(Outcome(events=tuple(_said(text) for text in texts)))
        self.runs.fix_check(str(self.worktree), THE_PR, "ci-failed", check="tests", summary=None,
                            push=True).pump()

    def git_prints(self, exit_code, *lines):
        self.git = (exit_code, "\n".join(lines) + "\n", "")

    def has_nowhere_to_open(self, reason):
        self.windows.refusal = reason

    def opened(self):
        return [(session.worktree, shlex.join(session.argv))
                for sessions in self.windows.sessions.values() for session in sessions]

    def run(self, argv, **kwargs):
        self.ran.append((list(argv), kwargs["cwd"]))
        exit_code, stdout, stderr = self.git
        return subprocess.CompletedProcess(argv, exit_code, stdout, stderr)

    def settle(self, *commands):
        board = FakeBoardApi()

        def ask():
            for command in commands:
                command(board.panel)

        run_manager(self.settings, ask, None, worktree=self.worktree, is_author=True,
                    board=board, pr_processes=self.windows, agent_runs=self.runs,
                    run=self.run)
        return board.panel


@pytest.fixture(params=["fake", "manager"])
def side(request, settings, tmp_path):
    return FakeSide() if request.param == "fake" else ManagerSide(settings, tmp_path)


def test_a_panel_left_alone_answers_a_dashboard_not_on_hold(side):
    assert side.settle().dashboard().on_hold is False


def test_a_panel_on_hold_answers_a_dashboard_on_hold(side):
    assert side.settle(lambda panel: panel.set_on_hold(True)).dashboard().on_hold is True


def test_a_panel_on_hold_and_resumed_answers_a_dashboard_not_on_hold(side):
    panel = side.settle(lambda panel: panel.set_on_hold(True), lambda panel: panel.set_on_hold(False))

    assert panel.dashboard().on_hold is False


def test_a_panel_answers_the_agents_notes(side):
    side.notes("# What changed\n")

    assert side.settle().changes() == "# What changed\n"


def test_a_panel_with_no_notes_answers_none(side):
    assert side.settle().changes() is None


def test_a_panel_answers_the_tail_of_what_claude_said(side):
    side.said("reading the code", "running the tests", "all green")

    tail = side.settle().agent_output(2)

    assert [text for text, _ in tail] == ["running the tests", "all green"]


def test_a_panel_runs_git_and_answers_its_exit_code_and_what_it_printed(side):
    side.git_prints(1, "error: failed to push some refs", "hint: pull first")

    exit_code, lines, _ = side.settle().run_git("p")

    assert (exit_code, lines) == (1, ["error: failed to push some refs", "hint: pull first"])


def test_a_panel_opens_a_terminal_command_and_answers_no_refusal(side):
    assert side.settle().open_terminal("a") is None


def test_a_panel_with_nowhere_to_open_a_terminal_says_why(side):
    side.has_nowhere_to_open("[Errno 2] No such file or directory: 'git'")

    assert side.settle().open_terminal("c") == "[Errno 2] No such file or directory: 'git'"


def test_the_manager_opens_each_terminal_command_in_the_prs_worktree(
        settings, tmp_path, monkeypatch):
    monkeypatch.setenv("SHELL", "/bin/zsh")
    side = ManagerSide(settings, tmp_path)

    panel = side.settle()
    for keys in ("l", "d", "a", "c", "i3", "r", "new"):
        assert panel.open_terminal(keys) is None

    assert sorted(side.opened()) == sorted([
        (str(tmp_path), "git log"),
        (str(tmp_path), "git diff HEAD"),
        (str(tmp_path), "git add -p"),
        (str(tmp_path), "git commit"),
        (str(tmp_path), "git rebase -i 'HEAD~3'"),
        (str(tmp_path), "claude /rebase-on-main"),
        (str(tmp_path), "/bin/zsh -l"),
    ])


def test_the_manager_refuses_to_open_what_needs_no_terminal(settings, tmp_path):
    side = ManagerSide(settings, tmp_path)
    panel = side.settle()

    for keys in ("f", "p", "pra", "s", "i", "zz", ""):
        with pytest.raises(ValueError):
            panel.open_terminal(keys)

    assert side.opened() == []


def test_the_manager_runs_each_captured_git_command_in_the_prs_worktree(settings, tmp_path):
    side = ManagerSide(settings, tmp_path)

    panel = side.settle()
    for keys in ("f", "p", "pra", "s", "l", "d"):
        panel.run_git(keys)

    assert side.ran == [
        (["git", "push", "--force-with-lease"], str(tmp_path)),
        (["git", "push"], str(tmp_path)),
        (["git", "pull", "--rebase", "--autostash"], str(tmp_path)),
        (["git", "status"], str(tmp_path)),
        (["git", "log"], str(tmp_path)),
        (["git", "diff", "HEAD"], str(tmp_path)),
    ]


def test_the_manager_refuses_git_the_palette_opens_in_a_terminal(settings, tmp_path):
    side = ManagerSide(settings, tmp_path)
    panel = side.settle()

    for keys in ("a", "c", "i3", "r", "zz"):
        with pytest.raises(ValueError):
            panel.run_git(keys)

    assert side.ran == []
