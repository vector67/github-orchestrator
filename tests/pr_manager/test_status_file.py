import dataclasses
import json

import pytest

from github_orchestrator.agent_runs.fake import FakeAgentRuns, Outcome
from github_orchestrator.board_api.fake import FakeBoardApi
from github_orchestrator.board_api.interface import ManagerStanding, ManagerStatuses
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.conversation.support import hear, on_github, said
from tests.pr_event_queue.support import ci_failed
from tests.pr_manager.scripted_terminal import ManualClock
from tests.pr_manager.support import manager_over, seed_state

REPO = "acme/widgets"
THE_PR = a_pr(7, REPO)
WORKING = {"type": "assistant", "message": {"content": [{"type": "text", "text": "reading the diff"}]}}


def _manager(settings, *script, **modules):
    return manager_over(settings, *script, repo=REPO, pr=THE_PR.number, **modules)


def _standing(manager):
    return manager.container.get(ManagerStatuses).standing(THE_PR)


def test_a_manager_that_has_not_ticked_is_starting(settings, tmp_path):
    manager = _manager(settings, worktree=tmp_path)

    assert _standing(manager) is ManagerStanding.STARTING


def test_a_manager_that_ticked_is_answering(settings, tmp_path):
    manager = _manager(settings, worktree=tmp_path).run()

    assert _standing(manager) is ManagerStanding.ANSWERING


@pytest.mark.parametrize(("seconds", "standing"), [
    (9.9, ManagerStanding.ANSWERING),
    (10, ManagerStanding.GONE),
], ids=["just inside the window", "at the window"])
def test_a_manager_is_gone_once_its_file_is_ten_seconds_old(settings, tmp_path, seconds, standing):
    manager = _manager(settings, worktree=tmp_path).run()

    manager.clock.advance(seconds)

    assert _standing(manager) is standing


class _Unready:
    def of(self, pr):
        raise RuntimeError("the threads are not readable yet")


def test_a_new_run_is_starting_until_it_draws_even_after_an_earlier_run_wrote(settings, tmp_path):
    _manager(settings, worktree=tmp_path).run()

    manager = _manager(settings, worktree=tmp_path, conversation_managers=_Unready()).run()

    assert _standing(manager) is ManagerStanding.STARTING


def _status(settings):
    return json.loads((settings.data_dir / "status" / "acme" / "widgets" / "7.json").read_text())


def test_an_idle_manager_writes_that_nothing_is_running_or_frozen(settings, tmp_path):
    _manager(settings, worktree=tmp_path).run()

    assert _status(settings) == {
        "written_at": "2026-09-24T12:00:00.000000Z",
        "active_run": None,
        "notice": None,
        "threads_live": [],
        "frozen_on": None,
        "expected_branch": None,
        "seconds_left": None,
        "run_working": False,
        "release_requested": False,
        "flags_changed_at": "2026-09-24T12:00:00.000000Z",
    }


def test_a_live_run_is_written_with_its_event_its_start_and_its_last_output(settings, tmp_path):
    clock = ManualClock()
    agent_runs = FakeAgentRuns(FakePrProcesses(), clock=clock.monotonic).script(
        Outcome(events=(WORKING,), finishes=False))
    manager = _manager(settings, lambda: clock.advance(5), lambda: clock.advance(5),
                       worktree=tmp_path, clock=clock, agent_runs=agent_runs, is_author=True)
    manager.event_queue.add(THE_PR, ci_failed("tests", "boom"))
    manager.run()

    status = _status(settings)
    assert status["written_at"] == "2026-09-24T12:00:12.000000Z"
    assert status["active_run"] == {
        "event": "ci-failed",
        "started_at": "2026-09-24T12:00:00.000000Z",
        "last_output_at": "2026-09-24T12:00:06.000000Z",
    }


def test_a_frozen_manager_writes_the_branch_it_found_and_the_one_it_expected(settings, tmp_path):
    seed_state(settings, REPO, THE_PR.number, branch="acme-30-add-archiving")
    working_copies = FakeWorkingCopies()
    working_copies.add_worktree(tmp_path, "acme-30-merge-archives")

    _manager(settings, worktree=tmp_path, working_copies=working_copies).run()

    status = _status(settings)
    assert (status["frozen_on"], status["expected_branch"]) == (
        "acme-30-merge-archives", "acme-30-add-archiving")
    assert (status["seconds_left"], status["run_working"], status["release_requested"]) == (
        3600, False, False)


def test_the_keys_of_live_thread_runs_are_written(settings, tmp_path):
    seed_state(settings, REPO, THE_PR.number, title="t", url="u")
    working_copies = FakeWorkingCopies()
    working_copies.add_repo(tmp_path, {"README": "hello"}, "first")
    manager = _manager(settings, None, is_author=True, worktree=tmp_path,
                       working_copies=working_copies,
                       agent_runs=FakeAgentRuns(FakePrProcesses()).script(Outcome(finishes=False)))
    on_github(manager.github, "PRRT_live", said(1, "PRRT_live", author="octocat"), pr=THE_PR)
    hear(manager.conversation_managers.of(THE_PR))

    manager.run()

    assert _status(settings)["threads_live"] == ["PRRT_live"]


def test_the_notice_a_refused_command_leaves_is_written(settings, tmp_path):
    board = FakeBoardApi()
    without_agents = dataclasses.replace(
        settings, config=dataclasses.replace(settings.config, agents_enabled=False))

    _manager(without_agents, lambda: board.panel.carry_on(), worktree=tmp_path, board=board,
             is_author=True).run()

    assert _status(settings)["notice"] == "agents are disabled in config.toml"
