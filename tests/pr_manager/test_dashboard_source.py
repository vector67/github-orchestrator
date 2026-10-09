from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from github_orchestrator.agent_runs.fake import FakeAgentRuns, Outcome
from github_orchestrator.board_api.fake import FakeBoardApi
from github_orchestrator.board_api.interface import Dashboards
from github_orchestrator.domain import AuthorKind
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.board_api.support import served_board
from tests.conversation.support import (
    at,
    fake_conversation_managers,
    hear,
    on_github,
    propose,
    repo_at,
    said,
)
from tests.pr_event_queue.support import ci_failed, unmergeable
from tests.pr_manager.polls import (
    BRANCH,
    POLLED,
    REVIEWED,
    REVIEWED_AT,
    WAITING_ON_REVIEW,
    seed,
)
from tests.pr_manager.scripted_terminal import ManualClock
from tests.pr_manager.support import POLLED_AT, THE_PR, manager_over
from tests.settings.support import disk_dismissals, disk_holds


def _windows_at(worktree):
    pr_processes = FakePrProcesses()
    pr_processes.open(THE_PR, worktree)
    return pr_processes


def _both(settings, tmp_path, *events, is_author=True, **modules):
    board = FakeBoardApi()
    modules.setdefault("pr_processes", _windows_at(tmp_path))
    manager = manager_over(settings, None, worktree=tmp_path, is_author=is_author,
                           board=board, **modules)
    for event in events:
        manager.event_queue.add(THE_PR, event)
    manager.run()
    managed = None if board.panel is None else board.panel.dashboard()
    return managed, manager.container.get(Dashboards).dashboard(THE_PR)


@pytest.mark.parametrize(("is_author", "state"), [
    (True, POLLED), (True, WAITING_ON_REVIEW), (False, REVIEWED),
], ids=["fix ci", "awaiting review", "reviewing"])
def test_a_pr_with_no_manager_shows_what_its_manager_would_with_no_run(
        settings, tmp_path, is_author, state):
    seed(settings, state)

    managed, unmanaged = _both(settings, tmp_path, is_author=is_author)

    assert unmanaged == managed


def test_a_pr_on_hold_with_no_manager_says_how_many_events_it_holds(settings, tmp_path):
    seed(settings, POLLED)
    disk_holds(settings.data_dir).set_on_hold(THE_PR, True)

    managed, unmanaged = _both(settings, tmp_path, ci_failed("lint"))

    assert unmanaged == managed
    assert (unmanaged.on_hold, unmanaged.queued_events) == (True, 1)


def test_a_pr_dismissed_until_its_next_event_with_no_manager_says_it_is_hidden(settings, tmp_path):
    seed(settings, POLLED)
    disk_dismissals(settings.data_dir).dismiss_until_next_event(THE_PR)

    managed, unmanaged = _both(settings, tmp_path)

    assert unmanaged == managed
    assert unmanaged.hidden is True


def test_proposed_fixes_are_counted_with_no_manager(settings, tmp_path):
    seed(settings, WAITING_ON_REVIEW)
    fake = fake_conversation_managers()
    repo_at(fake.working_copies, tmp_path, pr=THE_PR)
    fake.watch(THE_PR, is_author=True)
    threads = fake.of(THE_PR)
    on_github(fake.github, "PRRT_1", said(1, "rename this"), pr=THE_PR)
    hear(threads)
    propose(fake, threads, "PRRT_1", pr=THE_PR)
    fake.working_copies.check_out(tmp_path, BRANCH)

    managed, unmanaged = _both(settings, tmp_path, conversation_managers=fake,
                               agent_runs=fake.agent_runs, github=fake.github,
                               working_copies=fake.working_copies)

    assert unmanaged == managed
    assert (unmanaged.threads_proposed, [row.standing for row in unmanaged.thread_rows]) == (
        1, ["ready"])


def test_a_pr_with_no_manager_carries_the_facts_its_move_reads(settings, tmp_path):
    seed(settings, REVIEWED)

    managed, unmanaged = _both(settings, tmp_path, is_author=False)

    assert (unmanaged.polled_at, unmanaged.merge_state, unmanaged.my_review_at) == (
        POLLED_AT, "blocked", REVIEWED_AT)
    assert (unmanaged.ended, unmanaged.draft, unmanaged.viewer_requested,
            unmanaged.mentioned, unmanaged.mentions) == (False, False, False, False, ())
    assert unmanaged == managed


def test_a_pr_with_no_manager_carries_a_row_for_each_thread(settings, tmp_path):
    seed(settings, WAITING_ON_REVIEW)
    fake = fake_conversation_managers()
    repo_at(fake.working_copies, tmp_path, pr=THE_PR)
    fake.watch(THE_PR, is_author=True)
    threads = fake.of(THE_PR)
    on_github(fake.github, "PRRT_1", said(1, "rename this"), pr=THE_PR)
    hear(threads)
    propose(fake, threads, "PRRT_1", pr=THE_PR)
    fake.working_copies.check_out(tmp_path, BRANCH)

    managed, unmanaged = _both(settings, tmp_path, conversation_managers=fake,
                               agent_runs=fake.agent_runs, github=fake.github,
                               working_copies=fake.working_copies)

    assert [(row.key, row.standing, row.state, row.author_kind)
            for row in unmanaged.thread_rows] == [("PRRT_1", "ready", "open", AuthorKind.HUMAN)]
    assert unmanaged.thread_rows[0].updated_at is not None
    assert unmanaged == managed


DRAWN_AT = "2026-10-08T09:00:00Z"
LISTED_AT = "2026-10-08T09:00:05Z"


def test_the_dashboard_and_the_board_list_name_the_same_threads(settings, tmp_path):
    seed(settings, WAITING_ON_REVIEW)
    fake = fake_conversation_managers(clock=at(DRAWN_AT))
    repo_at(fake.working_copies, tmp_path, pr=THE_PR)
    fake.watch(THE_PR, is_author=True)
    threads = fake.of(THE_PR)
    on_github(fake.github, "PRRT_1", said(1, "rename this"), pr=THE_PR)
    hear(threads)
    fake.thread_records.pr(THE_PR).save("json", "PRRT_bad", b"{not json")
    fake.working_copies.check_out(tmp_path, BRANCH)

    board = FakeBoardApi()
    manager = manager_over(settings, None, worktree=tmp_path, is_author=True, board=board,
                           pr_processes=_windows_at(tmp_path),
                           conversation_managers=fake, agent_runs=fake.agent_runs,
                           github=fake.github, working_copies=fake.working_copies)
    manager.run()
    assert board.panel is not None
    real, listening = served_board(fake, fake.working_copies, clock=at(LISTED_AT))
    url = real.start(THE_PR, port=0, manager=board.panel)
    web = TestClient(listening.app, base_url=url)

    drawn = web.get("/api/dashboard").json()
    listed = web.get("/api/conversations").json()

    assert ([row["key"] for row in drawn["threads"]], drawn["unreadable"]) == (
        [conversation["key"] for conversation in listed["conversations"]], listed["unreadable"])
    assert listed["unreadable"] == ["PRRT_bad"]
    assert (drawn["listed_at"], listed["listed_at"]) == (DRAWN_AT, LISTED_AT)


def test_the_flags_say_when_one_last_changed(settings, tmp_path):
    seed(settings, POLLED)
    clock = ManualClock(datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc))
    manager = manager_over(settings, None, worktree=tmp_path, clock=clock,
                           pr_processes=_windows_at(tmp_path))
    dashboards = manager.container.get(Dashboards)

    first = dashboards.dashboard(THE_PR).flags_changed_at
    clock.advance(60)
    unchanged = dashboards.dashboard(THE_PR).flags_changed_at
    disk_holds(settings.data_dir).set_on_hold(THE_PR, True)
    clock.advance(60)
    held = dashboards.dashboard(THE_PR).flags_changed_at

    assert (first, unchanged, held) == (
        "2026-10-08T09:00:00.000000Z", "2026-10-08T09:00:00.000000Z",
        "2026-10-08T09:02:00.000000Z")


def test_a_pr_with_no_manager_says_how_its_last_run_ended(settings, tmp_path):
    seed(settings, POLLED)
    runs = FakeAgentRuns(FakePrProcesses()).script(Outcome(exit_code=1))

    managed, unmanaged = _both(settings, tmp_path, unmergeable(), agent_runs=runs)

    assert (unmanaged.last_run_event, unmanaged.last_run_exit_code) == ("became-unmergeable", 1)
    assert unmanaged.working_on is None
    assert unmanaged == managed


def test_a_frozen_pr_with_no_manager_asks_for_the_worktree_back(settings, tmp_path):
    seed(settings, POLLED)
    working_copies = FakeWorkingCopies()
    working_copies.add_worktree(tmp_path, "another-pr")

    _, unmanaged = _both(settings, tmp_path, working_copies=working_copies)

    assert (unmanaged.frozen_on, unmanaged.expected_branch, unmanaged.worktree) == (
        "another-pr", BRANCH, str(tmp_path))


def test_a_pr_no_poll_has_described_says_so_and_carries_no_poll_stamp(settings, tmp_path):
    _, unmanaged = _both(settings, tmp_path, is_author=None)

    assert (unmanaged.polled, unmanaged.polled_at) == (False, None)


class _AskedCopies(FakeWorkingCopies):
    def __init__(self):
        super().__init__()
        self.asked = []

    def commits_since(self, worktree, sha):
        self.asked.append(worktree)
        return super().commits_since(worktree, sha)


def test_a_pr_with_no_worktree_says_git_cannot_count_its_commits(settings, tmp_path):
    seed(settings, POLLED)
    copies = _AskedCopies()

    _, unmanaged = _both(settings, tmp_path, pr_processes=FakePrProcesses(), working_copies=copies)

    assert (unmanaged.worktree, unmanaged.unpushed_commits) == ("", None)
    assert "" not in copies.asked


def test_a_frozen_pr_dismissed_until_its_next_event_carries_both(
        settings, tmp_path):
    seed(settings, POLLED)
    disk_dismissals(settings.data_dir).dismiss_until_next_event(THE_PR)
    working_copies = FakeWorkingCopies()
    working_copies.add_worktree(tmp_path, "another-pr")

    _, unmanaged = _both(settings, tmp_path, working_copies=working_copies)

    assert (unmanaged.frozen_on, unmanaged.hidden) == ("another-pr", True)
