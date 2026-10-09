import subprocess

from github_orchestrator.agent_runs.fake import FakeAgentRuns
from github_orchestrator.board_api.interface import ManagerPanels
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.pr_processes import AgentChanges, PrProcesses
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.wiring import ManagerPanelsWiring, dashboard_source_wiring
from github_orchestrator.working_copies import WorkingCopies
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.conftest import (
    build_container,
    fake_agent_runs_roles,
    fake_github,
    fake_provider,
)

THE_PR = a_pr(54, "acme/widgets")


def panels_over(settings, windows):
    github = FakeGitHub()
    container = build_container(
        settings,
        fake_provider(PrProcesses, windows),
        fake_provider(AgentChanges, windows),
        fake_agent_runs_roles(FakeAgentRuns(windows)),
        fake_github(github),
        fake_provider(WorkingCopies, FakeWorkingCopies(github)),
        dashboard_source_wiring(settings),
        ManagerPanelsWiring(subprocess.run))
    panels: ManagerPanels = container.get(ManagerPanels)
    return panels


def test_a_panel_reads_the_notes_in_the_worktree_its_manager_was_started_in(settings, tmp_path):
    windows = FakePrProcesses()
    panel = panels_over(settings, windows).of(THE_PR)
    windows.open(THE_PR, tmp_path)
    windows.changes[tmp_path] = "# What changed\n"

    assert panel.changes() == "# What changed\n"

