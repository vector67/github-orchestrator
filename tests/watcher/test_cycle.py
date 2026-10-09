import os

import pytest

from github_orchestrator.change_detection import Poll
from github_orchestrator.desktop import Badge
from github_orchestrator.domain import Repo
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    Thread,
    ThreadComment,
)
from github_orchestrator.github.fake import Check, FakeGitHub, GhError
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.pr_processes import ManagerPane
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import RepoEntry, fake_settings
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.change_detection.support import disk_change_detection, types
from tests.pr_event_queue.support import ci_failed, disk_event_queue, pending_of
from tests.pr_processes.support import checked_out
from tests.settings.support import disk_dismissals
from tests.watcher.support import the_clone, watcher_over, watching

REPO = "octocat/hello-world"
GADGETS = "acme/gadgets"
POLLED_AT = "2026-07-07T08:00:00Z"


def _checks(conclusion="success"):
    return (Check("tests", "completed", conclusion),)


def _state(author, **fields):
    return PullRequestState(**{"author": author, "head_sha": "sha1", "mergeable": True,
                               "mergeable_state": "clean", "checks": _checks(), **fields})


def _mine(github, number, **fields):
    github.add_pr(a_pr(number, REPO), _state(github.account, **fields))


def _theirs(github, number, **fields):
    github.add_pr(a_pr(number, REPO), _state("alice", **fields), review_requested=True)


def _seen(settings, number, state, polled_at=POLLED_AT):
    disk_change_detection(settings.state_dir).advance(
        a_pr(number, REPO), Poll(state, polled_at), set())


def _dry_run(settings, capsys, github, **modules):
    watcher_over(settings, github=github, dry_run=True, **modules).run_cycle()
    return capsys.readouterr().out


class _Recording(FakePrProcesses):
    def __init__(self):
        super().__init__()
        self.calls = []

    def manager(self, pr):
        self.calls.append(("manager", pr.number))
        return super().manager(pr)

    def close(self, pr):
        self.calls.append(("close", pr.number))
        return super().close(pr)


def test_a_pr_dismissed_forever_is_neither_polled_nor_given_a_window(settings, pr_processes):
    github = watching(settings)
    _mine(github, 61)
    disk_dismissals(settings.data_dir).dismiss_forever(a_pr(61, REPO))

    watcher_over(settings, github=github, pr_processes=pr_processes).run_cycle()

    assert pr_processes.managers == {}
    assert disk_change_detection(settings.state_dir).facts(a_pr(61, REPO)) is None


def _fetched_by_cycle(settings, tmp_path, head_sha):
    world = FakePrProcesses()
    notifications = FakeNotifications()
    copies = FakeWorkingCopies(notifications=notifications)
    _seen(settings, 61, _state("alice", branch="PROJ-1-thing"))
    worktree = checked_out(copies, tmp_path / "PROJ-1-thing", "PROJ-1-thing")
    world.open(a_pr(61, REPO), worktree)
    github = watching(settings)
    _theirs(github, 61, head_sha=head_sha, branch="PROJ-1-thing")

    watcher_over(settings, github=github, notifications=notifications, working_copies=copies,
                 pr_processes=world).run_cycle()

    return [(n.badge, n.title) for n in notifications.posted if "fetch" in n.title]


def test_a_moved_head_makes_the_cycle_fetch_that_prs_worktree(tmp_path, settings):
    assert _fetched_by_cycle(settings, tmp_path, "sha2") == [
        (Badge.FAILED, "PR #61 fetch failed")]


def test_an_unmoved_head_leaves_the_cycles_worktree_unfetched(tmp_path, settings):
    assert _fetched_by_cycle(settings, tmp_path, "sha1") == []


def test_a_moved_head_fetches_the_worktree_a_new_window_reuses(tmp_path, settings):
    notifications = FakeNotifications()
    copies = FakeWorkingCopies(notifications=notifications)
    _seen(settings, 61, _state("alice", branch="PROJ-1-thing"))
    checked_out(copies, tmp_path / "PROJ-1-thing", "PROJ-1-thing")
    github = watching(settings)
    _theirs(github, 61, head_sha="sha2", branch="PROJ-1-thing")
    world = FakePrProcesses()

    watcher_over(settings, github=github, notifications=notifications, working_copies=copies,
                 pr_processes=world).run_cycle()

    assert [(n.badge, n.title) for n in notifications.posted] == [
        (Badge.FAILED, "PR #61 fetch failed")]
    assert world.manager(a_pr(61, REPO)) is ManagerPane.RUNNING


def test_a_moved_head_fetches_the_prs_base_beside_it(tmp_path, settings):
    copies = FakeWorkingCopies()
    base = copies.publish("release", "", {"f": "1\n"}, "the release")
    copies.publish("PROJ-1-thing", base, {"g": "2\n"}, "the thing")
    _seen(settings, 61, _state("alice", branch="PROJ-1-thing"))
    checked_out(copies, tmp_path / "PROJ-1-thing", "PROJ-1-thing")
    github = watching(settings)
    _theirs(github, 61, head_sha="sha2", branch="PROJ-1-thing", base_branch="release")

    watcher_over(settings, github=github, working_copies=copies,
                 pr_processes=FakePrProcesses()).run_cycle()

    assert copies.fetched == {"PROJ-1-thing": copies.origin["PROJ-1-thing"], "release": base}


def test_a_poll_does_not_raise_a_check_the_queue_already_holds(settings):
    _seen(settings, 61, _state(settings.config.gh_account, head_sha="sha0"))
    disk_event_queue(settings.queues_dir).add(a_pr(61, REPO), ci_failed('tests'))
    github = watching(settings)
    _mine(github, 61, checks=_checks("failure"))

    watcher_over(settings, github=github).run_cycle()

    pending = pending_of(disk_event_queue(settings.queues_dir), a_pr(61, REPO))
    assert sum(e.kind == "ci-failed" for e in pending) == 1
    polled_again = Poll(_state(settings.config.gh_account, checks=_checks("failure")),
                        POLLED_AT)
    assert "ci-failed" not in types(disk_change_detection(settings.state_dir).advance(
        a_pr(61, REPO), polled_again, set()))


def test_one_pr_that_cannot_be_polled_does_not_stop_the_rest(settings, pr_processes):
    class _OneBroken(FakeGitHub):
        def pr_state(self, pr):
            if pr.number == 1:
                raise RuntimeError("gh pr view failed")
            return super().pr_state(pr)

    github = _OneBroken(account=settings.config.gh_account)
    github.repos.add(Repo.parse(REPO))
    _mine(github, 1, branch="b1")
    _mine(github, 2, branch="b2")
    copies = FakeWorkingCopies(github)
    main = copies.add_repo(the_clone(settings), {"f": "1\n"}, "first")
    copies.publish("b1", main, {}, "one")
    copies.publish("b2", main, {}, "two")

    watcher_over(settings, github=github, pr_processes=pr_processes,
                 working_copies=copies).run_cycle()

    detection = disk_change_detection(settings.state_dir)
    assert detection.facts(a_pr(1, REPO)) is None
    assert detection.facts(a_pr(2, REPO)) is not None
    assert list(pr_processes.managers) == [a_pr(2, REPO)]


def test_a_cycle_polls_then_reaps_then_revives(settings):
    github = watching(settings)
    _mine(github, 1)
    disk_change_detection(settings.state_dir).close(a_pr(7, REPO))
    disk_event_queue(settings.queues_dir).add(a_pr(9, REPO), ci_failed())
    windows = _Recording()

    watcher_over(settings, github=github, pr_processes=windows).run_cycle()

    assert windows.calls == [("manager", 1), ("manager", 7), ("close", 7), ("manager", 9)]


def test_a_save_that_fails_raises_nothing_until_the_next_poll_saves(monkeypatch, settings):
    _seen(settings, 7, _state(settings.config.gh_account, review_decision="APPROVED"),
          "2025-01-01T00:00:00Z")
    github = watching(settings)
    github.add_pr(a_pr(7, REPO), PullRequestState(author=github.account, mergeable_state="dirty",
                                            review_decision="APPROVED"))
    real_fsync = os.fsync
    failures = ["simulated disk full"]

    def fsync_that_fails_once(fd):
        if failures:
            raise OSError(failures.pop())
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync_that_fails_once)

    def unmergeable_after_a_cycle():
        watcher_over(settings, github=github).run_cycle()
        return [e for e in pending_of(disk_event_queue(settings.queues_dir), a_pr(7, REPO))
                if e.kind == "became-unmergeable"]

    assert unmergeable_after_a_cycle() == []
    assert len(unmergeable_after_a_cycle()) == 1


def test_dry_run_counts_the_review_request_and_names_the_window_it_would_open(settings, capsys):
    github = watching(settings)
    _theirs(github, 23)

    out = _dry_run(settings, capsys, github)

    assert f"[dry-run] would enqueue review-requested for {REPO}#23" in out
    assert "would open or revive PR 23's window" in out
    assert "worktree" in out
    assert "agent manager" in out
    assert "Polled 1 PRs, 1 events queued, 0 torn down" in out
    assert disk_event_queue(settings.queues_dir).queues() == []


def test_dry_run_names_the_new_worktree_command_it_would_run(capsys, tmp_path):
    settings = fake_settings(tmp_path, new_worktree_command="make setup")
    github = watching(settings)
    _theirs(github, 23)

    out = _dry_run(settings, capsys, github)

    assert "new_worktree_command" in out
    assert "make setup" in out


def test_dry_run_stays_quiet_about_an_unconfigured_new_worktree_command(capsys, tmp_path):
    settings = fake_settings(tmp_path, new_worktree_command="")
    github = watching(settings)
    _theirs(github, 23)

    assert "new_worktree_command" not in _dry_run(settings, capsys, github)


def _two_repos(tmp_path):
    return fake_settings(tmp_path, repos=(
        RepoEntry(Repo.parse(REPO), str(tmp_path / "hello" / "clone")),
        RepoEntry(Repo.parse(GADGETS), str(tmp_path / "gadgets" / "clone"), "make gadgets"),
    ))


class _CountsSearches(FakeGitHub):
    def __init__(self, account):
        super().__init__(account=account)
        self.searched = []
        self.asked = []

    def search(self, repos, whose):
        self.searched.append((sorted(str(repo) for repo in repos), whose))
        return super().search(repos, whose)

    def relevance(self, pr):
        self.asked.append(pr)
        return super().relevance(pr)


def test_one_cycle_searches_every_watched_repo_at_once_and_cuts_each_worktree_by_its_clone(
        tmp_path):
    settings = _two_repos(tmp_path)
    github = _CountsSearches(settings.config.gh_account)
    _mine(github, 1, branch="b1")
    github.add_pr(a_pr(2, GADGETS), _state("alice", branch="b2"), review_requested=True)
    copies = FakeWorkingCopies(github)
    copies.publish("b1", "", {"f": "1\n"}, "one")
    copies.publish("b2", "", {"g": "2\n"}, "two")
    windows = FakePrProcesses()

    watcher_over(settings, github=github, working_copies=copies, pr_processes=windows).run_cycle()

    both = [GADGETS, REPO]
    assert sorted(github.searched) == [(both, "author"), (both, "mentions"), (both, "review-requested")]
    assert set(windows.changes) == {tmp_path / "hello" / "b1", tmp_path / "gadgets" / "b2"}


def test_a_tracked_pr_of_a_repo_no_longer_watched_is_not_asked_about(settings):
    github = _CountsSearches(settings.config.gh_account)
    github.repos.update(settings.repos)
    dropped = a_pr(5, "acme/dropped")
    disk_change_detection(settings.state_dir).advance(
        dropped, Poll(_state(settings.config.gh_account), POLLED_AT), set())

    watcher_over(settings, github=github).run_cycle()

    assert github.asked == []
    assert disk_change_detection(settings.state_dir).facts(dropped) is not None


def test_a_closing_pr_of_a_repo_no_longer_watched_is_left_for_the_archive(settings, caplog):
    dropped = a_pr(5, "acme/dropped")
    detection = disk_change_detection(settings.state_dir)
    detection.advance(dropped, Poll(_state(settings.config.gh_account), POLLED_AT), set())
    detection.close(dropped)

    watcher_over(settings, github=watching(settings)).run_cycle()

    assert "Failed to reap" not in caplog.text
    assert disk_change_detection(settings.state_dir).tracked() == [dropped]


def test_a_dead_manager_of_a_repo_no_longer_watched_is_not_revived(settings, tmp_path):
    dropped = a_pr(5, "acme/dropped")
    windows = FakePrProcesses()
    windows.open(dropped, tmp_path / "wt")
    windows.stop_managers()
    disk_event_queue(settings.queues_dir).add(dropped, ci_failed())
    disk_change_detection(settings.state_dir).advance(
        dropped, Poll(_state(settings.config.gh_account, branch="b"), POLLED_AT), set())

    watcher_over(settings, github=watching(settings), pr_processes=windows).run_cycle()

    assert windows.manager(dropped) is ManagerPane.EXITED


def test_dry_run_names_each_prs_own_clone_and_new_worktree_command(capsys, tmp_path):
    settings = _two_repos(tmp_path)
    github = watching(settings)
    github.add_pr(a_pr(2, GADGETS), _state("alice"), review_requested=True)

    out = _dry_run(settings, capsys, github)

    assert f"beside {tmp_path / 'gadgets' / 'clone'}" in out
    assert "make gadgets" in out


def test_dry_run_says_which_events_would_launch_claude(settings, capsys):
    github = watching(settings)
    _mine(github, 3, checks=_checks("failure"))
    _theirs(github, 4, checks=_checks("failure"))
    _seen(settings, 3, _state(github.account))
    _seen(settings, 4, _state("alice"))

    out = _dry_run(settings, capsys, github)

    assert f"[dry-run] would enqueue ci-failed for {REPO}#3 — would launch an agent run" in out
    assert f"[dry-run] would enqueue ci-failed for {REPO}#4" in out.splitlines()


def test_dry_run_says_nothing_launches_when_claude_is_disabled(capsys, tmp_path):
    settings = fake_settings(tmp_path, agents_enabled=False)
    github = watching(settings)
    _mine(github, 3, checks=_checks("failure"))
    _seen(settings, 3, _state(github.account))

    out = _dry_run(settings, capsys, github)

    assert (f"[dry-run] would enqueue ci-failed for {REPO}#3 — would start no run: agents are "
            f"disabled") in out
    assert "an agent run" not in out


def _commented(github, number, *keys):
    for comment_id, key in enumerate(keys, start=1):
        github.add_thread(a_pr(number, REPO), Thread(
            key=key, kind=CommentKind.REVIEW, path="src/w.py", line=3,
            comments=(ThreadComment(id=comment_id, author="bob", body="rename",
                                    created_at="2026-01-01T00:00:00Z"),)))


def test_dry_run_counts_the_threads_and_stale_records_new_comments_would_enqueue(settings, capsys):
    github = watching(settings)
    _mine(github, 3)
    _commented(github, 3, "PRRT_one", "PRRT_two")
    _seen(settings, 3, _state(github.account))

    out = _dry_run(settings, capsys, github)

    assert (f"[dry-run] would enqueue thread-activity (2 thread(s), 0 stale record(s)) for "
            f"{REPO}#3") in out.splitlines()


def test_dry_run_prints_each_prs_lines_as_one_block(settings, capsys):
    github = watching(settings)
    for number in (3, 4):
        _mine(github, number, mergeable=False, mergeable_state="dirty",
              checks=_checks("failure"))
        _seen(settings, number, _state(github.account))

    lines = _dry_run(settings, capsys, github).splitlines()

    for number in (3, 4):
        block = [i for i, line in enumerate(lines) if f"{REPO}#{number}" in line]
        assert lines[block[0]] == f"[dry-run] would save state for {REPO}#{number}"
        assert len(block) == 3
        assert block == list(range(block[0], block[0] + len(block)))


def test_dry_run_saves_and_queues_nothing(settings, capsys):
    github = watching(settings)
    _mine(github, 3, checks=_checks("failure"))
    _seen(settings, 3, _state(github.account))
    before = disk_change_detection(settings.state_dir).facts(a_pr(3, REPO))

    _dry_run(settings, capsys, github)

    assert disk_change_detection(settings.state_dir).facts(a_pr(3, REPO)) == before
    assert disk_event_queue(settings.queues_dir).queues() == []


@pytest.fixture
def dismissed_until_event(settings):
    github = watching(settings)
    _mine(github, 23)
    watcher_over(settings, github=github).run_cycle()
    disk_dismissals(settings.data_dir).dismiss_until_next_event(a_pr(23, REPO))
    return github


def test_dry_run_does_not_promise_a_window_for_a_pr_dismissed_until_event(
    settings, capsys, dismissed_until_event,
):
    capsys.readouterr()
    out = _dry_run(settings, capsys, dismissed_until_event)

    assert "would leave PR 23 alone (dismissed until the next event)" in out
    assert "would open or revive PR 23's window" not in out


def test_dry_run_promises_the_window_when_a_queued_event_would_clear_it(
    settings, capsys, dismissed_until_event,
):
    disk_event_queue(settings.queues_dir).add(a_pr(23, REPO), ci_failed())
    capsys.readouterr()

    out = _dry_run(settings, capsys, dismissed_until_event)

    assert "would open or revive PR 23's window" in out
    assert "dismissed until the next event" not in out


def test_dry_run_promises_the_window_when_this_cycle_would_enqueue(
    settings, capsys, dismissed_until_event,
):
    _mine(dismissed_until_event, 23, checks=_checks("failure"))
    capsys.readouterr()

    out = _dry_run(settings, capsys, dismissed_until_event)

    assert "would open or revive PR 23's window" in out
    assert "dismissed until the next event" not in out


def test_dry_run_summary_counts_the_prs_the_events_and_the_teardowns(settings, capsys):
    github = watching(settings)
    _theirs(github, 1)
    _mine(github, 2)
    disk_change_detection(settings.state_dir).close(a_pr(7, REPO))

    out = _dry_run(settings, capsys, github)

    assert "Polled 2 PRs, 1 events queued, 1 torn down" in out


class _UnreadableOnce(FakeGitHub):
    def __init__(self, account):
        super().__init__(account=account)
        self.refused = False

    def pr_state(self, pr):
        if not self.refused:
            self.refused = True
            raise GhError("gh api /repos/octocat/hello-world/pulls/23 failed (exit 1): timeout")
        return super().pr_state(pr)


def test_a_review_request_whose_pr_cannot_be_read_yet_is_queued_once_it_can_be(settings):
    github = _UnreadableOnce(settings.config.gh_account)
    github.repos.add(Repo.parse(REPO))
    _theirs(github, 23, title="Rework the writer")
    watcher = watcher_over(settings, github=github)

    def requested():
        return [event.title
                for event in pending_of(disk_event_queue(settings.queues_dir), a_pr(23, REPO))
                if event.kind == "review-requested"]

    watcher.run_cycle()
    first = requested()
    watcher.run_cycle()

    assert (first, requested()) == ([], ["Rework the writer"])
