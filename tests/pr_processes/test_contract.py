import importlib.util
import re
import sys
from datetime import datetime

import pytest

from github_orchestrator.domain import Repo
from github_orchestrator.pr_processes import ManagerPane
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.terminal_sessions.fake import FakeTerminals
from tests.builders import a_pr
from tests.pr_processes.scripted_processes import ScriptedProcesses
from tests.pr_processes.support import background_pr_processes, real_agent_changes

REPO = "octocat/hello-world"
PR = 7
THE_PR = a_pr(PR, REPO)
BRANCH = "feature-7"
MANAGER = (f"{sys.executable} -m github_orchestrator.pr_manager "
           f"--repo {REPO} --pr {PR}")


@pytest.fixture(params=["fake", "background"])
def any_windows(request, settings):
    if request.param == "fake":
        return FakePrProcesses()
    return background_pr_processes(settings, ScriptedProcesses(), FakeTerminals())


@pytest.fixture
def changes(any_windows):
    return any_windows if isinstance(any_windows, FakePrProcesses) else real_agent_changes()


@pytest.fixture
def worktree(tmp_path):
    path = tmp_path / BRANCH
    path.mkdir()
    return path


@pytest.fixture
def any_opened(any_windows, worktree):
    def open_window(is_author=False):
        any_windows.open(THE_PR, worktree)
    return open_window


def test_the_manager_starts_a_module_that_can_run():
    [module] = re.findall(r"-m ([\w.]+)", MANAGER)
    assert importlib.util.find_spec(f"{module}.__main__") is not None


def test_reviving_a_pr_without_a_window_opens_nothing(any_windows):
    any_windows.revive(THE_PR)

    assert any_windows.manager(THE_PR) is ManagerPane.NO_WINDOW


def test_an_opened_pr_has_a_running_manager(any_windows, any_opened):
    assert any_windows.manager(THE_PR) is ManagerPane.NO_WINDOW

    any_opened()

    assert any_windows.manager(THE_PR) is ManagerPane.RUNNING


def test_the_manager_pane_says_where_it_runs(any_windows, any_opened, worktree):
    assert any_windows.manager_path(THE_PR) is None

    any_opened()

    assert any_windows.manager_path(THE_PR) == str(worktree)


def test_a_detached_pr_is_named_defunct_and_has_no_manager(any_windows, any_opened):
    any_opened()

    assert any_windows.detach(THE_PR) == "hello-world/#7-defunct"

    assert any_windows.manager(THE_PR) is ManagerPane.NO_WINDOW
    assert any_windows.manager_path(THE_PR) is None


def test_detaching_a_pr_without_a_window_does_nothing(any_windows):
    assert any_windows.detach(THE_PR) is None

    assert any_windows.manager(THE_PR) is ManagerPane.NO_WINDOW


def test_a_closed_pr_has_no_manager(any_windows, any_opened):
    any_opened()

    assert any_windows.close(THE_PR) is True

    assert any_windows.manager(THE_PR) is ManagerPane.NO_WINDOW
    assert any_windows.manager_path(THE_PR) is None


def test_closing_a_pr_without_a_window_does_nothing(any_windows):
    assert any_windows.close(THE_PR) is True

    assert any_windows.manager(THE_PR) is ManagerPane.NO_WINDOW


def test_closing_other_repos_keeps_the_kept_repos_managers_and_names_each_pr_closed_with_its_worktree(
        any_windows, any_opened, tmp_path):
    any_opened()
    for name in ("spoon-3", "spoon-4", "linguist-5"):
        (tmp_path / name).mkdir()
    any_windows.open(a_pr(3, "octocat/spoon-knife"), tmp_path / "spoon-3")
    any_windows.open(a_pr(4, "octocat/spoon-knife"), tmp_path / "spoon-4")
    any_windows.open(a_pr(5, "octocat/linguist"), tmp_path / "linguist-5")

    closed = any_windows.close_other_repos(
        {Repo.parse("octocat/hello-world"), Repo.parse("octocat/linguist")})

    assert closed == {a_pr(3, "octocat/spoon-knife"): str(tmp_path / "spoon-3"),
                      a_pr(4, "octocat/spoon-knife"): str(tmp_path / "spoon-4")}
    assert [any_windows.manager(pr) for pr in (THE_PR, a_pr(5, "octocat/linguist"), *closed)] == [
        ManagerPane.RUNNING, ManagerPane.RUNNING, ManagerPane.NO_WINDOW, ManagerPane.NO_WINDOW]


def test_an_any_opened_window_starts_the_prs_changes_under_its_title(changes, any_opened, worktree):
    any_opened()

    assert changes.read(worktree) == "# Agent Changes -- octocat/hello-world#7\n\n"


def test_a_note_is_added_under_a_header_stamped_with_its_minute(changes, any_opened, worktree):
    any_opened()

    changes.note(worktree, "CI passed.", datetime(2026, 9, 26, 10, 30, 59))

    assert changes.read(worktree) == (
        "# Agent Changes -- octocat/hello-world#7\n\n## [2026-09-26 10:30]\n\nCI passed.\n")


def test_notes_follow_one_another_in_the_order_they_were_written(changes, any_opened, worktree):
    any_opened()

    changes.note(worktree, "first", datetime(2026, 9, 26, 10, 30))
    changes.note(worktree, "second", datetime(2026, 9, 26, 10, 31))

    assert changes.read(worktree).endswith(
        "## [2026-09-26 10:30]\n\nfirst\n## [2026-09-26 10:31]\n\nsecond\n")


def test_a_note_keeps_its_newlines_and_tabs_but_no_other_control_characters(changes, worktree):
    changes.note(worktree, "\x1b[31mred\x1b[0m\n\x1b]8;;file:///etc/passwd\x07link\x1b]8;;\x1b\\"
                           "\tbell\x07\x9b2Jgone\x1bcreset\r\x00",
                 datetime(2026, 9, 26, 10, 30))

    assert changes.read(worktree) == "## [2026-09-26 10:30]\n\nred\nlink\tbell2Jgonereset\n"


def test_a_worktree_no_window_opened_in_has_no_changes(changes, worktree):
    assert changes.read(worktree) is None


def test_a_note_where_no_window_opened_starts_the_changes_with_it(changes, worktree):
    changes.note(worktree, "first", datetime(2026, 9, 26, 10, 30))

    assert changes.read(worktree) == "## [2026-09-26 10:30]\n\nfirst\n"


def test_reopening_a_window_keeps_the_changes_written_so_far(any_windows, changes, any_opened,
                                                            worktree):
    any_opened()
    changes.note(worktree, "first", datetime(2026, 9, 26, 10, 30))
    any_windows.close(THE_PR)

    any_opened()

    assert changes.read(worktree).endswith("## [2026-09-26 10:30]\n\nfirst\n")


def test_a_note_in_a_worktree_that_is_gone_is_refused(changes, tmp_path):
    with pytest.raises(OSError):
        changes.note(tmp_path / "gone", "first", datetime(2026, 9, 26, 10, 30))

    assert changes.read(tmp_path / "gone") is None


def test_stopping_the_managers_stops_every_running_one_and_names_its_pr(any_windows,
                                                                          any_opened, tmp_path):
    other = a_pr(8, REPO)
    any_opened()
    any_windows.open(other, tmp_path)

    assert any_windows.stop_managers() == [THE_PR, other]

    assert any_windows.manager(THE_PR) is ManagerPane.EXITED
    assert any_windows.manager(other) is ManagerPane.EXITED


def test_a_manager_that_had_already_exited_is_not_named_as_stopped(any_windows, any_opened,
                                                                   tmp_path):
    other = a_pr(8, REPO)
    any_opened()
    any_windows.open(other, tmp_path)
    any_windows.stop_managers()
    any_windows.revive(other)

    assert any_windows.stop_managers() == [other]


def test_with_no_windows_no_manager_is_stopped(any_windows):
    assert any_windows.stop_managers() == []


def test_a_stopped_manager_is_started_again_by_a_revive(any_windows, any_opened, worktree):
    any_opened()
    any_windows.stop_managers()

    any_windows.revive(THE_PR)

    assert any_windows.manager(THE_PR) is ManagerPane.RUNNING
    assert any_windows.manager_path(THE_PR) == str(worktree)
