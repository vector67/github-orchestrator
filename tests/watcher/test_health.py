import fcntl
import json
import logging
import os
from datetime import timedelta

import pytest

from github_orchestrator.change_detection import CiSucceeded
from github_orchestrator.desktop import Badge, Desktop
from github_orchestrator.desktop.fake import FakeDesktop
from github_orchestrator.domain import Repo
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.notifications import PrStatus, Runs
from github_orchestrator.watcher import Health, Watcher
from tests.builders import a_pr
from tests.watcher.support import (
    NOW,
    health,
    stop_after,
    watcher_container,
    watcher_over,
)


class ErrorThatCannotDescribeItself(RuntimeError):
    def __str__(self):
        raise ValueError("this error cannot describe itself")


class Searches(FakeGitHub):
    def __init__(self, account, repo, error=None):
        super().__init__(account=account)
        self.repos.add(Repo.parse(repo))
        self.cycles = []
        self._error = error

    def search(self, repo, whose):
        if whose == "author":
            self.cycles.append(repo)
        if self._error is not None:
            raise self._error
        return super().search(repo, whose)


def _searches(settings, error=None):
    return Searches(settings.config.gh_account, "octocat/hello-world", error)


def _fail_once(settings, error):
    with pytest.raises(RuntimeError):
        watcher_over(settings, github=_searches(settings, RuntimeError(error))).run_cycle()


def _cannot_search(settings):
    return (f"watcher cannot search octocat/hello-world as "
            f"{settings.config.gh_account} — check [[repos]] and gh_account in "
            f"{settings.config_path}")


def _ci_passed(container):
    container.get(PrStatus).changed(a_pr(84, "o/n"), CiSucceeded(("unit",)))


def _held(settings):
    settings.watcher_lock.write_text("")
    holder = open(settings.watcher_lock, "a")
    fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return holder


def _forever(settings, github, cycles, *, desktop=None, dry_run=False):
    desktop = desktop or FakeDesktop()
    sleep = stop_after(cycles, github.cycles)
    with pytest.raises(KeyboardInterrupt):
        watcher_over(settings, github=github, desktop=desktop, sleep=sleep,
                     dry_run=dry_run).run_forever()
    return desktop, sleep.slept


def test_a_cycle_stamps_the_time_it_polled(settings):
    watcher_over(settings).run_cycle()

    assert settings.watcher_heartbeat.read_text() == NOW.isoformat()


def test_a_dry_run_stamps_nothing(settings):
    watcher_over(settings, dry_run=True).run_cycle()

    assert not settings.watcher_heartbeat.exists()


def test_a_failed_search_repeats_why_gh_refused(settings):
    with pytest.raises(RuntimeError) as excinfo:
        watcher_over(settings, github=FakeGitHub()).run_cycle()

    message = str(excinfo.value)
    assert "cannot be searched" in message
    assert message.index("[[repos]]") < message.index("cannot be searched")


def test_the_daemon_rests_the_poll_interval_between_cycles_two_seconds_at_a_time(settings):
    _, slept = _forever(settings, _searches(settings), 3)

    rest = settings.config.watcher_poll_interval
    assert slept == [2] * (rest // 2) * 2 + [2]


def test_the_daemon_shows_what_was_posted_while_it_rested(settings):
    posted = []

    def sleep(seconds):
        if posted:
            raise KeyboardInterrupt
        _ci_passed(container)
        posted.append(seconds)

    container = watcher_container(settings, github=_searches(settings), sleep=sleep)

    with pytest.raises(KeyboardInterrupt):
        container.get(Watcher).run_forever()

    assert [a.title for a in container.get(Desktop).announcements] == ["CI passed — PR #84"]


def test_a_one_shot_cycle_shows_what_was_posted_before_it(settings):
    container = watcher_container(settings)
    _ci_passed(container)

    container.get(Watcher).run_cycle()

    assert [a.title for a in container.get(Desktop).announcements] == ["CI passed — PR #84"]


def test_a_dry_run_shows_nothing_that_was_posted(settings):
    container = watcher_container(settings, dry_run=True)
    _ci_passed(container)

    container.get(Watcher).run_cycle()

    assert container.get(Desktop).announcements == []


def test_a_batch_that_fell_due_while_the_mac_slept_waits_for_the_first_poll_after(settings):
    now = [NOW]
    github = _searches(settings)
    shown_before_the_second_poll = []

    def sleep(seconds):
        if len(github.cycles) >= 2:
            raise KeyboardInterrupt
        shown_before_the_second_poll.append(len(container.get(Desktop).announcements))
        now[0] += timedelta(hours=2) if len(shown_before_the_second_poll) == 1 else timedelta(seconds=seconds)

    container = watcher_container(settings, github=github, sleep=sleep, clock=lambda: now[0])
    container.get(Runs).agent_skipped(a_pr(1, "o/n"), "thread-activity")

    with pytest.raises(KeyboardInterrupt):
        container.get(Watcher).run_forever()

    assert set(shown_before_the_second_poll) == {0}
    assert [a.title for a in container.get(Desktop).announcements] == [
        "Agents disabled — skipped events on #1 (from 12:00)"]


def test_the_daemon_leaves_its_cycle_summaries_to_the_log_not_stdout(settings, capsys):
    _forever(settings, _searches(settings), 2)

    assert "Polled" not in capsys.readouterr().out


def test_a_cycle_that_cannot_search_notifies_the_user_with_the_fix(settings):
    github = Searches(settings.config.gh_account, "someone/else")

    desktop, _ = _forever(settings, github, 1)

    [notification] = desktop.announcements
    assert "octocat/hello-world" in notification.body
    assert settings.config.gh_account in notification.body
    assert "[[repos]]" in notification.body
    assert "gh_account" in notification.body
    assert str(settings.config_path) in notification.body
    assert "cannot be searched" in notification.body
    assert "cannot be searched" in health(settings).last_error


def test_every_failed_cycle_notifies_not_only_the_first(settings):
    desktop, _ = _forever(settings, _searches(settings, RuntimeError("poll blew up")), 3)

    assert len(desktop.announcements) == 3
    assert health(settings).last_error.endswith("poll blew up")
    assert "3 consecutive failed cycles" in desktop.announcements[-1].body
    assert "poll blew up" in desktop.announcements[-1].body


def test_a_successful_cycle_clears_the_failure_count(settings):
    _fail_once(settings, "poll blew up")
    _fail_once(settings, "poll blew up")

    watcher_over(settings).run_cycle()

    assert health(settings).last_error is None
    _fail_once(settings, "again")
    assert health(settings).last_error.endswith("; again")


def test_a_recovery_leaves_the_run_of_failures_it_ended_in_the_log(settings, caplog):
    _fail_once(settings, "first")
    _fail_once(settings, "gh: Bad credentials")

    with caplog.at_level(logging.INFO):
        watcher_over(settings).run_cycle()

    assert "recovered; failed cycles in a row: 2; last error: watcher cannot search" in caplog.text
    assert "; gh: Bad credentials" in caplog.text


def test_a_cycle_after_a_success_reports_no_recovery(settings, caplog):
    watcher_over(settings).run_cycle()

    with caplog.at_level(logging.INFO):
        watcher_over(settings).run_cycle()

    assert "recovered" not in caplog.text


def test_a_counter_that_cannot_be_cleared_raises_no_false_alarm(settings):
    settings.watcher_failures.mkdir()

    desktop, _ = _forever(settings, _searches(settings), 1)

    assert desktop.announcements == []
    assert settings.watcher_heartbeat.exists()


def test_a_dry_run_neither_counts_the_failure_nor_notifies(settings):
    desktop, _ = _forever(settings, _searches(settings, RuntimeError("poll blew up")), 1,
                          dry_run=True)

    assert desktop.announcements == []
    assert not settings.watcher_failures.exists()


def test_a_counter_that_cannot_be_written_does_not_silence_the_notification(settings):
    settings.watcher_failures.mkdir()

    desktop, _ = _forever(settings, _searches(settings, RuntimeError("poll blew up")), 1)

    assert [(a.badge, a.title, a.body) for a in desktop.announcements] == [
        (Badge.FAILED, "Watcher not polling",
         f"watcher cycle failed: {_cannot_search(settings)}; poll blew up. "
         f"Details in {settings.logs_dir / 'watcher.log'}")]


def test_nothing_the_reporter_hits_can_take_the_daemon_down(settings):
    github = _searches(settings, ErrorThatCannotDescribeItself())

    _forever(settings, github, 3)

    assert len(github.cycles) == 3


def test_a_multi_line_error_reaches_the_notifier_on_one_line(settings):
    github = _searches(settings, RuntimeError("gh: Not Found\nrun gh auth login"))

    desktop, _ = _forever(settings, github, 1)

    assert "\n" not in desktop.announcements[0].body
    assert "run gh auth login" in desktop.announcements[0].body
    assert health(settings).last_error.endswith("; gh: Not Found run gh auth login")


def test_a_one_shot_cycle_that_fails_is_counted_notified_and_raised(settings):
    desktop = FakeDesktop()
    watcher = watcher_over(settings, desktop=desktop,
                           github=_searches(settings, RuntimeError("poll blew up")))

    with pytest.raises(RuntimeError, match="poll blew up"):
        watcher.run_cycle()

    assert [(a.badge, a.title, a.body) for a in desktop.announcements] == [
        (Badge.FAILED, "Watcher not polling",
         f"1 consecutive failed cycle: {_cannot_search(settings)}; poll blew up. "
         f"Details in {settings.logs_dir / 'watcher.log'}")]
    assert health(settings).last_error.endswith("; poll blew up")


def test_a_cycle_under_the_lock_reads_as_alive(settings):
    watcher_over(settings).run_cycle()

    with _held(settings):
        reported = health(settings)
    assert (reported.alive, reported.since_last_poll, reported.last_error) == (
        True, timedelta(0), None)


def test_the_next_poll_is_due_a_poll_interval_after_the_last(settings):
    settings.watcher_heartbeat.write_text((NOW - timedelta(seconds=20)).isoformat())

    reported = health(settings)

    assert reported.next_poll_in == reported.polls_every - timedelta(seconds=20)


def test_a_poll_gap_past_two_intervals_and_the_grace_is_overdue():
    late = Health(alive=True, since_last_poll=timedelta(seconds=241), last_error=None, fix=None,
                  polls_every=timedelta(minutes=1))

    assert late.overdue


def test_the_overdue_threshold_scales_with_the_poll_interval():
    polls_every = timedelta(minutes=5)
    within = Health(alive=True, since_last_poll=timedelta(minutes=11), last_error=None, fix=None,
                    polls_every=polls_every)
    past = Health(alive=True, since_last_poll=timedelta(minutes=13), last_error=None, fix=None,
                  polls_every=polls_every)

    assert (within.overdue, past.overdue) == (False, True)


def test_no_next_poll_is_due_before_the_first(settings):
    assert health(settings).next_poll_in is None


def test_a_half_written_failure_record_reads_as_no_failures(settings):
    settings.watcher_failures.write_text('{"consecutive": 3, "last_er')

    assert health(settings).last_error is None


def test_a_failure_record_in_the_shared_format_is_read(settings):
    settings.watcher_failures.write_text(json.dumps({"consecutive": 4, "last_error": "gone"}))

    assert health(settings).last_error == "gone"


def test_an_interrupted_count_keeps_the_old_record_and_leaves_no_partial_file(
    settings, monkeypatch,
):
    _fail_once(settings, "first")

    def no_fsync(fd):
        raise OSError("disk went away")

    monkeypatch.setattr(os, "fsync", no_fsync)
    _fail_once(settings, "second")

    assert health(settings).last_error.endswith("; first")
    assert list(settings.watcher_failures.parent.glob("*.tmp")) == []


def test_a_cycle_failing_while_gh_has_no_token_for_the_account_says_to_log_in(settings):
    github = _searches(settings, RuntimeError("gh auth token failed"))
    github.tokens.clear()

    _forever(settings, github, 1)

    assert health(settings).fix == "Log in with `gh auth login`, then this page retries."


def test_a_cycle_failing_on_a_repo_the_account_cannot_see_names_the_repo_and_the_account(
    settings,
):
    _forever(settings, Searches(settings.config.gh_account, "someone/else"), 1)

    assert health(settings).fix == (
        f"You can't see octocat/hello-world as {settings.config.gh_account}. "
        "Remove it from your repos, or ask for access.")


def test_a_cycle_failing_for_a_reason_gh_and_github_do_not_explain_has_no_fix(settings):
    _forever(settings, _searches(settings, RuntimeError("poll blew up")), 1)

    assert health(settings).fix is None


def test_a_failure_record_written_before_fixes_were_kept_reads_with_no_fix(settings):
    settings.watcher_failures.write_text(json.dumps({"consecutive": 4, "last_error": "gone"}))

    assert health(settings).fix is None
