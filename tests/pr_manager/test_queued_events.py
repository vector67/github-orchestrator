import logging
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from github_orchestrator.agent_runs import FixComment
from github_orchestrator.agent_runs.fake import (
    FixingCheck,
    HeldVerdicts,
    Outcome,
    Rebasing,
    Rereviewing,
    Reviewing,
)
from github_orchestrator.change_detection.fake import (
    MergeableReason,
    ReviewDecision,
    UnmergeableReason,
)
from github_orchestrator.conversation import ConversationState
from github_orchestrator.desktop import Badge
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    ReviewState,
    ThreadComment,
)
from github_orchestrator.github.fake import Review
from github_orchestrator.notifications.fake import AgentSkipped, FakeNotifications
from github_orchestrator.pr_event_queue import Worklist
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import fake_settings
from tests.builders import a_pr
from tests.conversation.support import (
    Moment,
    fake_conversation_managers,
    hear,
    on_github,
    said,
    without_runs,
)
from tests.pr_event_queue.support import (
    activity as found,
)
from tests.pr_event_queue.support import (
    ci_failed,
    ci_succeeded,
    closed,
    decision_changed,
    head_moved,
    mergeable,
    pushed,
    review_requested,
    unmergeable,
)
from tests.pr_manager.support import PR, REPO, manager_over, seed_state

THE_PR = a_pr(PR, REPO)

STAMP = "## [2026-09-24 12:00]"
RESOLVED_AT = "2026-09-21T10:00:00Z"


def _worktree(tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    return worktree


def _manager(settings, worktree, *events, is_author=True, **modules):
    manager = manager_over(settings, worktree=worktree, is_author=is_author, **modules)
    for event in events:
        if event.kind == "thread-activity":
            manager.event_queue.add_thread_activity(THE_PR, event)
        else:
            manager.event_queue.add(THE_PR, event)
    return manager


def _carried_out(settings, worktree, *events, **modules):
    return _manager(settings, worktree, *events, **modules).run()


def _changes(manager, worktree):
    return manager.pr_processes.read(worktree) or ""


def _work(manager):
    [started] = manager.agent_runs.started
    return started.work


def _on_github(github, key, *comments, **fields):
    on_github(github, key, *comments, pr=THE_PR, **fields)


def _edited(github, key, comment_id, body):
    record = github.prs[THE_PR]
    record.threads = [replace(thread, comments=tuple(
        replace(comment, body=body) if comment.id == comment_id else comment
        for comment in thread.comments)) if thread.key == key else thread
        for thread in record.threads]


def _polled(threads):
    polled = threads.poll(PullRequestState())
    polled.commit()
    return polled.activity


def _threads_ticked(manager):
    manager.event_queue.add_thread_activity(THE_PR, _polled(manager.conversation_managers.of(THE_PR)))
    return manager.run()


def _conversations(manager):
    return {conversation.key: conversation
            for conversation in manager.conversation_managers.of(THE_PR).all()}


def _checked_out(working_copies, tmp_path):
    worktree = _worktree(tmp_path)
    working_copies.add_repo(worktree, {"README": "hello"}, "first")
    return worktree


def test_a_failed_check_on_an_authored_pr_starts_a_fix_run(settings, tmp_path, desktop,
                                                          agent_runs):
    worktree = _worktree(tmp_path)
    seed_state(settings, title="Fix the frobnicator")
    agent_runs.script(Outcome(finishes=False))
    manager = manager_over(settings, None, is_author=True, worktree=worktree, agent_runs=agent_runs,
                           desktop=desktop)
    manager.event_queue.add(THE_PR, ci_failed('tests', 'boom'))
    manager.run()
    [started] = manager.agent_runs.started
    assert started.worktree == str(worktree)
    assert started.work == FixingCheck("tests", "boom", True)
    assert manager.board.panel.dashboard().working_on == "ci-failed"
    assert f"{STAMP}\n\nCI check 'tests' failed. See diagnosis output below.\n" in _changes(manager, worktree)


def test_a_fix_run_claude_will_not_start_for_fails_its_event_and_says_why(
        settings, tmp_path, agent_runs):
    worktree = _worktree(tmp_path)
    agent_runs.script(Outcome(starts=False))
    manager = manager_over(settings, None, is_author=True, worktree=worktree,
                           agent_runs=agent_runs)
    manager.event_queue.add(THE_PR, ci_failed('tests', 'boom'))
    manager.run()
    assert manager.agent_runs.started == []
    assert [entry.event.kind for entry in manager.event_queue.failed_since(
        datetime(1970, 1, 1, tzinfo=timezone.utc))] == ["ci-failed"]
    assert "could not start the agent" in manager.board.panel.dashboard().notice


def test_nothing_is_taken_from_the_queue_while_the_prs_role_is_unknown(settings, tmp_path):
    manager = _carried_out(settings, _worktree(tmp_path), ci_failed("tests"), is_author=None)

    assert manager.agent_runs.started == []
    assert manager.container.get(Worklist).waiting(THE_PR).count == 1


def test_queued_work_is_taken_once_the_prs_role_is_known(settings, tmp_path):
    worktree = _worktree(tmp_path)
    _carried_out(settings, worktree, ci_failed("tests"), is_author=None)
    seed_state(settings, is_author=True)

    manager = manager_over(settings, worktree=worktree, is_author=None).run()

    assert _work(manager) == FixingCheck("tests", None, True)


def test_a_fix_run_with_more_failures_queued_is_told_not_to_push(settings, tmp_path):
    manager = _carried_out(settings, _worktree(tmp_path),
                           ci_failed("tests", "boom"), ci_failed("lint"))
    assert _work(manager) == FixingCheck("tests", "boom", False)


def test_conflicts_on_an_authored_pr_start_a_rebase_run(settings, tmp_path):
    manager = _carried_out(settings, _worktree(tmp_path),
                           unmergeable(UnmergeableReason.CONFLICTS))
    assert _work(manager) == Rebasing("conflicts")


def test_a_head_change_is_only_logged(settings, tmp_path, caplog):
    worktree = _worktree(tmp_path)
    with caplog.at_level(logging.DEBUG, logger="github_orchestrator.pr_manager._carry_out"):
        manager = _carried_out(settings, worktree, head_moved("sha1", "sha2"), is_author=False)
    assert manager.agent_runs.started == []
    assert manager.notifications.posted == []
    assert _changes(manager, worktree) == ""
    assert "sha1" in caplog.text
    assert "sha2" in caplog.text


def test_a_review_request_starts_a_review_run_on_its_branch(settings, tmp_path):
    seed_state(settings, branch="PROJ-123-fix", is_author=False)
    manager = _carried_out(settings, _worktree(tmp_path),
                           review_requested("Fix bug", "https://example.com"), is_author=False)
    assert _work(manager) == Reviewing("Fix bug", "https://example.com", "PROJ-123-fix", 0, 0)


def test_a_review_run_is_told_how_large_the_change_is(settings, tmp_path):
    seed_state(settings, branch="PROJ-456-pr", additions=300, deletions=200,
               is_author=False)
    manager = _carried_out(settings, _worktree(tmp_path),
                           review_requested("PR", "https://example.com"), is_author=False)
    assert _work(manager) == Reviewing("PR", "https://example.com", "PROJ-456-pr", 300, 200)


def test_a_review_of_a_pr_with_no_title_or_facts_is_of_the_pr_by_number(settings, tmp_path):
    manager = _carried_out(settings, _worktree(tmp_path), review_requested(None, None),
                           is_author=False)
    assert _work(manager) == Reviewing("PR #1", "", "", 0, 0)


REVIEWED_AT = "2026-08-20T09:00:00Z"
REPLIED_AT = "2026-08-21T12:00:00Z"


def _reviewed_before(settings, tmp_path, working_copies, verdict):
    worktree = _worktree(tmp_path)
    reviewed = working_copies.add_repo(tmp_path / "repo", {"README": "hello"}, "first")
    working_copies.add_worktree(worktree, "PROJ-123-fix")
    working_copies.branches["PROJ-123-fix"] = reviewed
    pushed = working_copies.commit(worktree, {"README": "hello again"}, "Retry the upload once")
    me = settings.config.gh_account
    seed_state(settings, is_author=False, author="alice", branch="PROJ-123-fix", head_sha=pushed,
               reviews=(Review(author=me, state=verdict, submitted_at=REVIEWED_AT,
                               commit_id=reviewed),))
    windows = FakePrProcesses()
    verdicts = HeldVerdicts(windows)
    manager = manager_over(settings, worktree=worktree, is_author=False,
                           working_copies=working_copies, pr_processes=windows,
                           agent_runs=verdicts)
    hear(manager.conversation_managers.of(THE_PR))
    _on_github(manager.github, "PRR_mine", ThreadComment(
        id=301, author=me, body="Two things before this can go in.", created_at=REVIEWED_AT,
        review_state=verdict), kind=CommentKind.REVIEW_SUMMARY, path=None, line=None,
        state=verdict)
    _on_github(manager.github, "PRRT_mine", said(302, "This retries forever.", author=me,
                                                created_at=REVIEWED_AT),
               said(303, "Now it retries once.", author="alice", created_at=REPLIED_AT),
               path="src/upload.py", line=42)
    _on_github(manager.github, "PRRT_frank", said(304, "Rename this.", author="frank"),
               said(305, "Done.", author="alice", created_at=REPLIED_AT))
    hear(manager.conversation_managers.of(THE_PR))
    verdicts.give("their-move", key="PRR_mine")
    return manager, reviewed[:7]


def test_a_review_request_after_your_review_starts_a_re_review_of_what_changed_since(
        settings, tmp_path, working_copies):
    manager, reviewed = _reviewed_before(settings, tmp_path, working_copies,
                                         ReviewState.CHANGES_REQUESTED)
    manager.event_queue.add(THE_PR, review_requested("Fix bug", "https://example.com"))

    manager.run()

    work = _work(manager)
    assert isinstance(work, Rereviewing)
    assert (work.title, work.url, work.branch, work.verdict) == (
        "Fix bug", "https://example.com", "PROJ-123-fix", "changes-requested")
    assert work.said == FixComment(settings.config.gh_account,
                                   "Two things before this can go in.", REVIEWED_AT)
    assert work.since is not None and work.since.startswith(reviewed)
    assert [line.split(" ", 1)[1] for line in work.commits or ()] == ["Retry the upload once"]
    assert work.replied == (("src/upload.py", 42, (
        FixComment(settings.config.gh_account, "This retries forever.", REVIEWED_AT),
        FixComment("alice", "Now it retries once.", REPLIED_AT))),)


def test_a_review_request_after_only_a_pending_review_starts_a_first_review(
        settings, tmp_path, working_copies):
    manager, _ = _reviewed_before(settings, tmp_path, working_copies, ReviewState.PENDING)
    manager.event_queue.add(THE_PR, review_requested("Fix bug", "https://example.com"))

    manager.run()

    assert isinstance(_work(manager), Reviewing)


def test_new_threads_on_an_authored_pr_become_author_records(settings, tmp_path, working_copies):
    worktree = _checked_out(working_copies, tmp_path)
    manager = manager_over(settings, worktree=worktree, is_author=True,
                           working_copies=working_copies)
    _polled(manager.conversation_managers.of(THE_PR))
    _on_github(manager.github, "PRRT_one", said(101, "fix this", author="alice"),
               path="src/x.py", line=3)
    _on_github(manager.github, "IC_one", said(202, "ship it", author="bob"),
               kind=CommentKind.ISSUE, path=None, line=None)

    _threads_ticked(manager)

    assert manager.agent_runs.started == []
    stored = _conversations(manager)
    assert set(stored) == {"PRRT_one", "IC_one"}
    assert stored["PRRT_one"].body == "fix this"
    assert stored["PRRT_one"].standing is ConversationState.QUEUED


def test_new_threads_on_an_authored_pr_are_counted_with_a_board_hint(settings, tmp_path,
                                                                    working_copies):
    worktree = _checked_out(working_copies, tmp_path)
    manager = manager_over(settings, worktree=worktree, is_author=True,
                           working_copies=working_copies)
    for cid in (1, 2, 3):
        _on_github(manager.github, f"t{cid}", said(cid, "x"))

    _threads_ticked(manager)

    changes = _changes(manager, worktree)
    assert STAMP in changes
    assert "Thread activity (3)" in changes
    assert "on the review board" in changes


def test_with_claude_disabled_an_authored_prs_threads_drain_without_records(tmp_path):
    settings = fake_settings(tmp_path / "data", agents_enabled=False)
    worktree = _worktree(tmp_path)
    manager = manager_over(settings, worktree=worktree, is_author=True)
    _on_github(manager.github, "t1", said(101, "fix this"))

    _threads_ticked(manager)

    assert _conversations(manager) == {}
    assert manager.agent_runs.started == []
    assert manager.notifications.gathered == [AgentSkipped(THE_PR, "thread-activity")]
    assert manager.notifications.posted == []
    assert "disabled" in _changes(manager, worktree)
    assert "thread-activity" in _changes(manager, worktree)


def _reviewed(settings, worktree):
    manager = manager_over(settings, worktree=worktree, is_author=False)
    _on_github(manager.github, "t1", said(101, "looks good", author="alice"))
    return _threads_ticked(manager)


def test_with_claude_disabled_a_reviewed_prs_threads_still_become_records(tmp_path):
    settings = fake_settings(tmp_path / "data", agents_enabled=False)
    worktree = _worktree(tmp_path)

    manager = _reviewed(settings, worktree)

    assert _conversations(manager)["t1"].standing is ConversationState.READY
    assert _changes(manager, worktree) == ""


def test_new_threads_on_a_reviewed_pr_become_reviewer_records_quietly(settings, tmp_path):
    worktree = _worktree(tmp_path)

    manager = _reviewed(settings, worktree)

    assert manager.agent_runs.started == []
    assert _conversations(manager)["t1"].standing is ConversationState.READY
    assert _changes(manager, worktree) == ""


@pytest.mark.parametrize("is_author", [True, False])
def test_stale_threads_refresh_their_records_without_adding_any(settings, tmp_path,
                                                                working_copies, is_author):
    worktree = _checked_out(working_copies, tmp_path)
    manager = manager_over(without_runs(settings), worktree=worktree, is_author=is_author,
                           working_copies=working_copies)
    _on_github(manager.github, "t1", said(1, "original", author="alice"),
               said(2, "and this", author="alice"))
    hear(manager.conversation_managers.of(THE_PR))
    _edited(manager.github, "t1", 2, "edited")

    _threads_ticked(manager)

    assert manager.agent_runs.started == []
    assert list(_conversations(manager)) == ["t1"]
    assert [c.body for c in _conversations(manager)["t1"].comments] == ["original", "edited"]
    assert _changes(manager, worktree) == ""


BEFORE_THE_RESOLVE = "2026-09-21T10:00:00Z"
RESOLVED_AT = "2026-09-21T10:00:30Z"
AFTER_THE_RESOLVE = "2026-09-21T10:05:05Z"


def _unresolved_ticked(settings, tmp_path, polled_at):
    moment = Moment("2026-09-21T09:00:00Z")
    fake = fake_conversation_managers(clock=moment)
    fake.watch(THE_PR, is_author=False)
    threads = fake.of(THE_PR)
    _on_github(fake.github, "PRRT_one", said(1, "rename this", author=fake.github.account))
    hear(threads)
    fake.github.resolve_thread("PRRT_one")
    moment.iso = "2026-09-21T09:30:00Z"
    _polled(threads)
    fake.github.unresolve_thread("PRRT_one")

    def resolved_by_the_board():
        moment.iso = RESOLVED_AT
        with threads.editing("PRRT_one") as editable:
            editable.resolve(resolve=True)
        threads.tick(FakeNotifications(), on_hold=False)

    if polled_at > RESOLVED_AT:
        resolved_by_the_board()
        fake.github.unresolve_thread("PRRT_one")
    moment.iso = polled_at
    found = _polled(threads)
    if polled_at < RESOLVED_AT:
        resolved_by_the_board()
    manager = manager_over(settings, worktree=_worktree(tmp_path), is_author=False,
                           github=fake.github, agent_runs=fake.agent_runs,
                           working_copies=fake.working_copies, conversation_managers=fake)
    manager.event_queue.add_thread_activity(THE_PR, found)
    manager.run()
    return threads.get("PRRT_one")


def test_an_unresolve_polled_before_the_boards_resolve_is_ignored(settings, tmp_path):
    stored = _unresolved_ticked(settings, tmp_path, BEFORE_THE_RESOLVE)
    assert stored.standing is ConversationState.DONE
    assert stored.github_resolved is True


def test_an_unresolve_polled_after_the_boards_resolve_reopens_the_thread(settings, tmp_path):
    stored = _unresolved_ticked(settings, tmp_path, AFTER_THE_RESOLVE)
    assert (stored.standing, stored.unread) == (ConversationState.READY, True)
    assert stored.github_resolved is False


@pytest.mark.parametrize(("event", "is_author"), [
    (ci_failed("build"), True),
    (review_requested("T", "u"), False),
])
def test_with_claude_disabled_a_launch_is_drained_with_a_note(tmp_path, event, is_author):
    settings = fake_settings(tmp_path / "data", agents_enabled=False)
    worktree = _worktree(tmp_path)
    manager = _carried_out(settings, worktree, event, is_author=is_author)
    assert manager.agent_runs.started == []
    assert manager.notifications.gathered == [AgentSkipped(THE_PR, event.kind)]
    assert manager.notifications.posted == []
    assert "Agents are disabled" in _changes(manager, worktree)


def test_pr_closed_stops_the_run_then_notifies_and_ends(settings, tmp_path, notifications,
                                                        agent_runs):
    agent_runs.script(Outcome(finishes=False))
    run_ended_before_notice = []
    announce = notifications.changed

    def watching(pr, change):
        run_ended_before_notice.append(bool(agent_runs.ledger))
        announce(pr, change)

    notifications.changed = watching
    worktree = _worktree(tmp_path)
    reached = []
    manager = manager_over(
        settings,
        lambda: manager.event_queue.add(THE_PR, closed(merged=True)),
        lambda: reached.append(True), lambda: reached.append(True),
        is_author=True, worktree=worktree, notifications=notifications, agent_runs=agent_runs)
    manager.event_queue.add(THE_PR, ci_failed('tests'))
    manager.run()
    assert run_ended_before_notice == [True]
    assert agent_runs.last_run(THE_PR).exit_code == -15
    assert notifications.posted[-1].title == "PR #1 closed"
    assert reached == []


@pytest.mark.parametrize(("merged", "said"), [
    (True, "PR was merged."), (False, "PR was closed without merging."),
])
def test_pr_closed_tears_down_the_queue_and_leaves_the_worktree(settings, tmp_path, merged,
                                                                said):
    worktree = _worktree(tmp_path)
    manager = _carried_out(settings, worktree, closed(merged=merged))
    assert manager.event_queue.is_torn_down(THE_PR)
    assert manager.notifications.posted[-1].body == said
    assert worktree.exists()
    assert manager.pr_processes.managers == {}


@pytest.mark.parametrize(("event", "is_author", "posted"), [
    (ci_succeeded("lint", "unit"), True,
     (Badge.INFO, "CI passed — PR #1", "Checks passed: lint, unit (success)")),
    (unmergeable(UnmergeableReason.BLOCKED), True,
     (Badge.FAILED, "PR #1 unmergeable", "Reason: blocked")),
    (mergeable(MergeableReason.CI_PASSED), True,
     (Badge.INFO, "PR #1 is now mergeable", "Reason: ci-passed")),
    (decision_changed(ReviewDecision.REVIEW_REQUIRED, ReviewDecision.APPROVED, "alice"), True,
     (Badge.INFO, "Review decision changed — PR #1",
      "alice changed review from review-required to approved")),
    (pushed(1, False), False, (Badge.INFO, "PR #1 updated", "Author pushed 1 commit since your review")),
    (pushed(3, False), False, (Badge.INFO, "PR #1 updated", "Author pushed 3 commits since your review")),
    (pushed(2, True), False, (Badge.INFO, "PR #1 updated", "Author force-pushed since your review")),
    (closed(merged=False, no_longer_relevant=True), False,
     (Badge.INFO, "PR #1 no longer relevant",
      "Removed from your watch list (not authored, not reviewed, not requested).")),
])
def test_each_change_of_a_prs_status_is_announced_in_its_words(settings, tmp_path, event,
                                                                is_author, posted):
    manager = _carried_out(settings, _worktree(tmp_path), event, is_author=is_author)
    assert [(p.badge, p.title, p.body) for p in manager.notifications.posted] == [posted]


@pytest.mark.parametrize(("event", "is_author", "agents_enabled", "notes"), [
    (ci_succeeded("lint", "unit"), True, True, ["CI passed: lint, unit — all checks success."]),
    (ci_failed("lint", "E501"), False, True, ["CI check \x27lint\x27 failed. Summary: E501"]),
    (ci_failed("lint"), False, True, ["CI check \x27lint\x27 failed. Summary: "]),
    (unmergeable(UnmergeableReason.BLOCKED), True, True, ["PR became unmergeable: blocked."]),
    (mergeable(MergeableReason.CI_PASSED), True, True, ["PR became mergeable: ci-passed."]),
    (decision_changed(), True, True, []),
    (pushed(1, False), False, True, ["Author pushed 1 commit since your review."]),
    (unmergeable(UnmergeableReason.CONFLICTS), True, True,
     ["PR became unmergeable (conflicts). See rebase output below."]),
    (review_requested("Fix bug", "https://x/1"), False, True,
     ["Review requested: \"Fix bug\". See review findings below."]),
    (review_requested(None, None), False, True,
     ["Review requested: \"PR #1\". See review findings below."]),
    (ci_failed("tests"), True, False,
     ["CI check \x27tests\x27 failed. See diagnosis output below.",
      "Agents are disabled (agents_enabled=false) — skipped ci-failed; no agent run."]),
    (found(stale=("PRRT_one",)), True, False,
     ["Agents are disabled (agents_enabled=false) — skipped thread-activity; no agent run."]),
])
def test_each_event_carried_out_leaves_its_note_in_agent_changes(tmp_path, event, is_author,
                                                                 agents_enabled, notes):
    settings = fake_settings(tmp_path / "data", agents_enabled=agents_enabled)
    worktree = _worktree(tmp_path)
    manager = _carried_out(settings, worktree, event, is_author=is_author)
    assert _changes(manager, worktree) == "".join(f"{STAMP}\n\n{note}\n" for note in notes)
