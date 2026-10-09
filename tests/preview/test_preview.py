import pytest
from fastapi.testclient import TestClient

from github_orchestrator import preview
from github_orchestrator.agent_runs.fake import FakeAgentRuns, HeldVerdicts
from github_orchestrator.board_api import BoardApi
from github_orchestrator.board_api.fake import IDLE
from github_orchestrator.board_api.interface import Dashboards
from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.conversation import ConversationManagerFactory
from github_orchestrator.desktop.fake import FakeDesktop
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.pr_processes import PrProcesses
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import fake_settings
from github_orchestrator.terminal_sessions.fake import FakeTerminalSessions
from github_orchestrator.wiring import dashboard_source_wiring, preview_container
from github_orchestrator.working_copies import WorkingCopies
from tests.board_api.support import PORT, served_board
from tests.conftest import (
    build_container,
    fake_agent_runs_roles,
    fake_github,
    fake_provider,
)
from tests.conversation.support import world
from tests.thread_records.support import disk_thread_records
from tests.working_copies.support import clone_of, real_working_copies

pytestmark = pytest.mark.xdist_group("preview")


@pytest.fixture
def seeded(shared_template):
    return shared_template(client_for_preview, False)


@pytest.fixture
def reviewed(shared_template):
    return shared_template(client_for_preview, True)


def client_for_preview(tmp_path, reviewer):
    settings = fake_settings(tmp_path / "data", agents_enabled=True)
    github = FakeGitHub()
    copies = real_working_copies(settings, github,
                                 clones=clone_of(preview.PR, preview.worktree_in(tmp_path)))
    windows = FakePrProcesses()
    here = world(settings, github=github, working_copies=copies,
                 thread_records=disk_thread_records(tmp_path / "threads"),
                 agent_runs=HeldVerdicts(windows), pr_processes=windows)
    repo = preview.build_repo(preview.worktree_in(tmp_path), reviewer)
    outside = preview.Outside(here.github, here.agent_runs, here.pr_processes,
                              here.change_detection)
    preview.seed(here.conversation_managers, outside, "octocat", repo, reviewer)
    board_api, listening = served_board(here.conversation_managers, here.working_copies)
    dashboards = build_container(
        settings, fake_github(here.github), fake_provider(PrProcesses, here.pr_processes),
        fake_agent_runs_roles(here.agent_runs), fake_provider(WorkingCopies, here.working_copies),
        fake_provider(ChangeDetection, here.change_detection),
        fake_provider(ConversationManagerFactory, here.conversation_managers),
        dashboard_source_wiring(settings)).get(Dashboards)
    url = board_api.start(preview.PR, port=PORT, manager=preview.manager_panel(
        preview.running(dashboards.dashboard(preview.PR))))
    return TestClient(listening.app, base_url=url)


RUN_KINDS = {"first", "rebase", "rework", "retry", "start-session"}


def anchors_of(cards):
    return {(card.path, card.line) for card in cards}


def test_the_reviewer_fixtures_leave_the_author_previews_repo_alone():
    author = anchors_of(preview.AUTHOR_CARDS)
    reviewer = anchors_of(preview.reviewer_cards("octocat"))

    assert author and reviewer
    assert not author & reviewer, (
        "build_repo rewrites every line it is handed, so an anchor a "
        "reviewer card brought would move the author card's own diff")


def test_the_preview_seeds_a_thread_in_every_state_the_author_board_draws(
        seeded):
    threads = seeded.get("/api/conversations").json()["conversations"]

    drawn = {thread["state"] for thread in threads}
    assert drawn == {"ready", "queued", "working", "in-session", "rework",
                     "landing", "waiting", "assumed-done", "deferred", "done"}, (
        "the preview exists to look at every heading at once, and a state "
        "with no thread in it cannot be looked at")
    assert any(thread["reopened"] for thread in threads)


def test_the_preview_seeds_a_reviewer_pr_in_every_state_a_reviewer_draws(
        reviewed):
    threads = reviewed.get("/api/conversations").json()["conversations"]

    assert {thread["state"] for thread in threads} == {
        "ready", "waiting", "assumed-done", "not-mine", "deferred", "done"}, (
        "a reviewed PR has no agent and no fix, so these are the states a "
        "thread of it can be in")
    assert any(thread["reopened"] for thread in threads)
    assert any(thread["unread"] for thread in threads)
    assert any(thread["state"] == "ready" and not thread["unread"] for thread in threads)
    assert any(thread["record_state"] == "confirmed" for thread in threads)


def test_a_reviewer_card_can_read_the_code_its_comment_sits_on(reviewed):
    head = reviewed.get("/api/pull-request").json()["head_sha"]
    anchor = reviewed.get(
        "/api/conversations/PRRT_answered").json()["anchor"]

    answer = reviewed.get("/api/files", params={
        "sha": head, "path": anchor["path"], "from_line": anchor["line"],
        "to_line": anchor["line"]})

    assert answer.status_code == 200
    assert answer.json()["lines"][0]["text"] == "    return sorted(line_items)"


@pytest.mark.parametrize("fixture", ["seeded", "reviewed"])
def test_every_seeded_thread_answers_every_read_its_card_makes(fixture,
                                                               request):
    client = request.getfixturevalue(fixture)

    for thread in client.get("/api/conversations").json()["conversations"]:
        key = thread["key"]
        for read in ("", "/comments", "/operations", "/proposals"):
            answer = client.get(f"/api/conversations/{key}{read}")
            assert answer.status_code == 200, (key, read)


def test_the_previews_own_container_builds_a_board_and_its_threads(tmp_path):
    pr_processes = FakePrProcesses()
    container, _ = preview_container({}, tmp_path, data_dir=tmp_path, repo=preview.PR.repo,
                                     local_path=preview.worktree_in(tmp_path),
                                     github=FakeGitHub(), desktop=FakeDesktop(),
                                     agent_runs=FakeAgentRuns(pr_processes),
                                     pr_processes=pr_processes, agents_enabled=True)

    assert container.get(BoardApi) is not None
    assert container.get(ConversationManagerFactory) is not None


def test_the_previews_terminal_opens_a_shell_in_its_worktree_for_every_launcher(tmp_path):
    sessions = FakeTerminalSessions()
    panel = preview.manager_panel(IDLE, sessions=sessions, worktree=str(tmp_path))

    assert panel.open_terminal("a") is None
    assert panel.open_terminal("new") is None

    [(first, argv), (second, _)] = sessions.started()
    assert first == second == str(tmp_path)
    assert argv[0] == "sh" and argv[-1] == "a"


def test_the_preview_serves_a_manager_panel_with_something_in_every_part(seeded):
    dashboard = seeded.get("/api/dashboard").json()

    assert dashboard["system"]["agent"]["state"] == "working"
    assert dashboard["standing"] == "answering"
    assert dashboard["system"]["last_run"] is not None
    assert dashboard["facts"] is not None
    assert dashboard["threads"]
    assert seeded.get("/api/manager/changes").json()["markdown"]
    assert seeded.get("/api/manager/agent-output").json()["lines"]


@pytest.mark.parametrize("fixture", ["seeded", "reviewed"])
def test_the_previews_dashboard_counts_the_threads_its_board_holds(fixture, request):
    client = request.getfixturevalue(fixture)
    threads = client.get("/api/conversations").json()["conversations"]
    dashboard = client.get("/api/dashboard").json()
    counted = dashboard["system"]["threads"]

    drafts = sum(1 for thread in threads if thread["state"] == "draft")
    proposed = sum(1 for thread in threads
                   if thread["state"] == "ready" and not thread["github_removed"]
                   and thread["operations"]
                   and thread["operations"][-1]["kind"] in RUN_KINDS
                   and thread["operations"][-1]["state"] == "applied")
    assert (counted["proposed"], counted["drafts"]) == (proposed, drafts)
    rows = dashboard["threads"]
    if fixture == "reviewed":
        yours = [row for row in rows if row["author_kind"] == "mine"
                 and row["record_state"] not in ("draft", "enrolled", "discarded")]
        assert (dashboard["facts"]["viewer_requested"], len(yours)) == (True, 7), (
            "a review is asked of you, and you opened seven threads")
    else:
        assert any(row["state"] == "ready" and row["author_kind"] == "human" for row in rows), (
            "a thread row says a human comment waits on you")
    assert (dashboard["pr"]["title"], dashboard["pr"]["branch"]) == (
        preview.PR_TITLE, preview.PR_BRANCH)
    assert dashboard["facts"]["is_author"] is (fixture == "seeded")
    assert fixture == "seeded" or dashboard["pr"]["author"] == "mei"


def test_the_reviewer_preview_seeds_a_mention_in_a_comment_and_in_the_description(reviewed):
    threads = reviewed.get("/api/conversations").json()["conversations"]

    assert sorted(thread["kind"] for thread in threads if thread["mention"]) == [
        "issue", "pr-body"]
