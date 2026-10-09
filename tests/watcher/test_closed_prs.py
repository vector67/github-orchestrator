from pathlib import Path

import pytest

from github_orchestrator.domain import Repo
from github_orchestrator.github import PullRequestState
from github_orchestrator.github.fake import Check
from github_orchestrator.pr_event_queue.fake import FakePrEventQueue
from github_orchestrator.pr_processes import ManagerPane
from github_orchestrator.settings.fake import RepoEntry, fake_settings
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.change_detection.support import (
    disk_change_detection,
    passing,
    polled_on_disk,
    seen,
)
from tests.pr_event_queue.support import closed, disk_event_queue, pending_of
from tests.pr_processes.support import checked_out
from tests.settings.support import disk_dismissals
from tests.watcher.support import watcher_over, watching

REPO = "octocat/hello-world"
OTHER = "octocat/other"


@pytest.fixture
def settings(tmp_path):
    return fake_settings(tmp_path, repos=tuple(
        RepoEntry(Repo.parse(repo), str(tmp_path / repo / "clone"))
        for repo in (REPO, OTHER, "org/repo")))


def _polled(settings, repo, number, *, is_author=False, **state):
    polled_on_disk(settings.state_dir, a_pr(number, repo),
                   seen(settings.config.gh_account, is_author=is_author, **state))


def _github(settings, *prs):
    github = watching(settings)
    for repo, number, status, authored, reviewed, *state in prs:
        author = github.account if authored else "someone-else"
        github.add_pr(a_pr(number, repo), PullRequestState(author=author, **(state[0] if state else {})),
                      status=status, viewer_reviewed=reviewed)
    return github


def _cycle(settings, capsys, github, *, dry_run=False, **modules):
    watcher_over(settings, github=github, dry_run=dry_run, **modules).run_cycle()
    return capsys.readouterr().out


def _closed(settings, repo, number):
    return [e for e in pending_of(disk_event_queue(settings.queues_dir), a_pr(number, repo))
            if e.kind == "pr-closed"]


def test_an_open_pr_i_wrote_that_left_the_search_is_kept_and_refreshed(
    settings, capsys, pr_processes, tmp_path,
):
    _polled(settings, OTHER, 55, is_author=True)
    github = _github(settings, (OTHER, 55, "OPEN", True, False, {"title": "Fresh", "branch": "b"}))
    copies = FakeWorkingCopies()
    checked_out(copies, tmp_path / "b", "b")

    out = _cycle(settings, capsys, github, pr_processes=pr_processes, working_copies=copies)

    assert "0 torn down" in out
    detection = disk_change_detection(settings.state_dir)
    assert detection.facts(a_pr(55, OTHER)).title == "Fresh"
    assert detection.closing(a_pr(55, OTHER)) is False
    assert _closed(settings, OTHER, 55) == []
    assert pr_processes.manager(a_pr(55, OTHER)) is ManagerPane.RUNNING


def test_an_open_pr_i_reviewed_that_left_the_search_is_kept_and_refreshed(
    settings, capsys, pr_processes, tmp_path,
):
    _polled(settings, OTHER, 63)
    github = _github(settings, (OTHER, 63, "OPEN", False, True, {"title": "Fresh", "branch": "b"}))
    copies = FakeWorkingCopies()
    checked_out(copies, tmp_path / "b", "b")

    out = _cycle(settings, capsys, github, pr_processes=pr_processes, working_copies=copies)

    assert "0 torn down" in out
    assert disk_change_detection(settings.state_dir).facts(a_pr(63, OTHER)).title == "Fresh"
    assert _closed(settings, OTHER, 63) == []
    assert pr_processes.manager(a_pr(63, OTHER)) is ManagerPane.RUNNING


def test_a_kept_pr_is_repolled_in_the_role_its_snapshot_holds(settings, capsys):
    failing = {"head_sha": "sha1", "mergeable": True, "mergeable_state": "clean",
               "checks": (Check("tests", "completed", "failure"),)}
    passed = {"head_sha": "sha1", "mergeable": True, "mergeable_state": "clean",
              "checks": (passing(),)}
    _polled(settings, OTHER, 65, **passed)
    _polled(settings, OTHER, 55, is_author=True, **passed)
    github = _github(settings, (OTHER, 65, "OPEN", False, True, failing),
                     (OTHER, 55, "OPEN", True, False, failing))

    out = _cycle(settings, capsys, github, dry_run=True)

    assert f"[dry-run] would enqueue ci-failed for {OTHER}#65" in out.splitlines()
    assert f"[dry-run] would enqueue ci-failed for {OTHER}#55 — would launch an agent run" in out


def test_an_open_pr_i_am_not_engaged_in_is_torn_down_as_no_longer_relevant(settings, capsys):
    _polled(settings, REPO, 64)
    github = _github(settings, (REPO, 64, "OPEN", False, False))

    out = _cycle(settings, capsys, github)

    assert "1 torn down" in out
    assert disk_change_detection(settings.state_dir).closing(a_pr(64, REPO)) is True
    [event] = _closed(settings, REPO, 64)
    assert event == closed(merged=False, no_longer_relevant=True)


def test_a_closed_pr_is_queued_for_teardown(settings, capsys):
    _polled(settings, REPO, 59)
    github = _github(settings, (REPO, 59, "CLOSED", False, False))

    out = _cycle(settings, capsys, github)

    assert "1 torn down" in out
    assert disk_change_detection(settings.state_dir).closing(a_pr(59, REPO)) is True
    [event] = _closed(settings, REPO, 59)
    assert event == closed(merged=False)


def test_a_closed_pr_dismissed_forever_is_forgotten_not_queued(settings, capsys):
    _polled(settings, REPO, 57)
    disk_dismissals(settings.data_dir).dismiss_forever(a_pr(57, REPO))
    github = _github(settings, (REPO, 57, "CLOSED", False, False))

    out = _cycle(settings, capsys, github)

    assert "1 torn down" in out
    assert disk_event_queue(settings.queues_dir).queues() == []
    assert disk_change_detection(settings.state_dir).facts(a_pr(57, REPO)) is None
    assert disk_dismissals(settings.data_dir).dismissal(a_pr(57, REPO)) is None


def test_a_pr_waiting_for_teardown_is_reaped_without_queueing_again(settings, capsys):
    _polled(settings, REPO, 58)
    disk_change_detection(settings.state_dir).close(a_pr(58, REPO))
    github = _github(settings, (REPO, 58, "CLOSED", False, False))

    out = _cycle(settings, capsys, github)

    assert "1 torn down" in out
    assert disk_event_queue(settings.queues_dir).queues() == []


def test_dry_run_names_the_teardown_a_closed_pr_would_get(settings, capsys):
    _polled(settings, REPO, 59, is_author=True)
    github = _github(settings, (REPO, 59, "MERGED", False, False))

    out = _cycle(settings, capsys, github, dry_run=True)

    assert f"[dry-run] would enqueue pr-closed for {REPO}#59" in out.splitlines()
    assert "1 torn down" in out
    assert disk_event_queue(settings.queues_dir).queues() == []
    assert disk_change_detection(settings.state_dir).closing(a_pr(59, REPO)) is False


def test_dry_run_counts_the_reap_it_reports(settings, capsys):
    _polled(settings, REPO, 7)
    disk_change_detection(settings.state_dir).close(a_pr(7, REPO))

    out = _cycle(settings, capsys, watching(settings), dry_run=True)

    assert f"[dry-run] would reap {REPO}#7" in out
    assert "1 torn down" in out
    assert disk_change_detection(settings.state_dir).facts(a_pr(7, REPO)) is not None


def test_a_closed_pr_is_queued_once_across_cycles(settings, capsys, pr_processes):
    pr_processes.open(a_pr(5, "org/repo"), Path("/wt"))
    _polled(settings, "org/repo", 5)
    github = _github(settings, ("org/repo", 5, "MERGED", False, False))

    _cycle(settings, capsys, github, pr_processes=pr_processes)
    _cycle(settings, capsys, github, pr_processes=pr_processes)

    assert len(_closed(settings, "org/repo", 5)) == 1


def test_one_closed_pr_that_fails_does_not_stop_the_rest(settings, capsys):
    attempts = []

    class FlakyEventQueue(FakePrEventQueue):
        def add(self, *args, **kwargs):
            attempts.append(args[0])
            if len(attempts) == 1:
                raise OSError("simulated FS error on first PR")
            super().add(*args, **kwargs)

    _polled(settings, REPO, 1)
    _polled(settings, REPO, 2)
    github = _github(settings, (REPO, 1, "CLOSED", False, False),
                     (REPO, 2, "CLOSED", False, False))
    event_queue = FlakyEventQueue()

    out = _cycle(settings, capsys, github, event_queue=event_queue)

    assert len(attempts) == 2
    assert "1 torn down" in out
    assert [q.pr for q in event_queue.queues()] == [attempts[1]]
