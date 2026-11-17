import fcntl
import json
import logging
import os
from datetime import timedelta

import pytest

from github_orchestrator.desktop import Badge, Desktop
from github_orchestrator.desktop.fake import FakeDesktop
from github_orchestrator.domain import Fault, Repo
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.notifications import Runs
from github_orchestrator.settings.fake import RepoEntry, fake_settings
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


def _fail_once(settings, error, desktop=None):
    with pytest.raises(RuntimeError):
        watcher_over(settings, github=_searches(settings, RuntimeError(error)),
                     desktop=desktop).run_cycle()


def _cannot_search(settings):
    return f"watcher cannot search octocat/hello-world as {settings.config.gh_account}"


NO_SUCH_HOST = 'Post "https://api.github.com/graphql": dial tcp: lookup api.github.com: no such host'
NO_TOKEN = ("gh auth token --user octocat failed (exit 1): no oauth token found for "
            "github.com account octocat")
DISK_FULL = "[Errno 28] No space left on device: '/data/github-orchestrator/state.json'"


def _run_failed(container):
    container.get(Runs).run_failed(a_pr(84, "o/n"), "ci-failed", 1)


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
    assert message.startswith(f"{_cannot_search(settings)}: ")
    assert "cannot be searched" in message


def test_the_daemon_rests_the_poll_interval_between_cycles_two_seconds_at_a_time(settings):
    _, slept = _forever(settings, _searches(settings), 3)

    rest = settings.config.watcher_poll_interval
    assert slept == [2] * (rest // 2) * 2 + [2]


def test_the_daemon_shows_what_was_posted_while_it_rested(settings):
    posted = []

    def sleep(seconds):
        if posted:
            raise KeyboardInterrupt
        _run_failed(container)
        posted.append(seconds)

    container = watcher_container(settings, github=_searches(settings), sleep=sleep)

    with pytest.raises(KeyboardInterrupt):
        container.get(Watcher).run_forever()

    assert [a.title for a in container.get(Desktop).announcements] == ["Run failed on n#84"]


def test_a_one_shot_cycle_shows_what_was_posted_before_it(settings):
    container = watcher_container(settings)
    _run_failed(container)

    container.get(Watcher).run_cycle()

    assert [a.title for a in container.get(Desktop).announcements] == ["Run failed on n#84"]


def test_a_dry_run_shows_nothing_that_was_posted(settings):
    container = watcher_container(settings, dry_run=True)
    _run_failed(container)

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
        "Agents disabled, skipped events on n#1 (from 12:00)"]


def test_the_daemon_leaves_its_cycle_summaries_to_the_log_not_stdout(settings, capsys):
    _forever(settings, _searches(settings), 2)

    assert "Polled" not in capsys.readouterr().out


def test_a_cycle_that_cannot_search_notifies_the_user_with_the_fix(settings):
    github = Searches(settings.config.gh_account, "someone/else")

    desktop, _ = _forever(settings, github, 3)

    [notification] = desktop.announcements
    assert "octocat/hello-world" in notification.body
    assert settings.config.gh_account in notification.body
    assert "[[repos]]" in notification.body
    assert str(settings.config_path) in notification.body
    assert "cannot be searched" in notification.body
    assert "cannot be searched" in health(settings).last_error


def test_a_fault_to_fix_notifies_once_when_the_third_cycle_in_a_row_fails(settings):
    desktop, _ = _forever(settings, _searches(settings, RuntimeError("poll blew up")), 5)

    [notification] = desktop.announcements
    assert health(settings).last_error.endswith("poll blew up")
    assert "3 cycles in a row failed" in notification.body
    assert "poll blew up" in notification.body


def test_a_fault_to_fix_notifies_again_after_a_good_cycle_ends_the_streak(settings):
    desktop = FakeDesktop()
    for _ in range(3):
        _fail_once(settings, "poll blew up", desktop)
    watcher_over(settings).run_cycle()
    for _ in range(3):
        _fail_once(settings, "poll blew up", desktop)

    assert len(desktop.announcements) == 2


def test_a_streak_that_turns_into_a_fault_to_fix_past_the_third_cycle_notifies_once(settings):
    desktop = FakeDesktop()
    for _ in range(3):
        _fail_once(settings, NO_SUCH_HOST, desktop)
    for _ in range(2):
        _fail_once(settings, NO_TOKEN, desktop)

    [notification] = desktop.announcements
    assert "4 cycles in a row failed" in notification.body


def test_a_streak_carried_over_past_three_notifies_once_at_its_next_fault_to_fix(settings):
    settings.watcher_failures.write_text(
        json.dumps({"consecutive": 5, "last_error": "poll blew up", "fix": None}))
    desktop = FakeDesktop()

    for _ in range(2):
        _fail_once(settings, "poll blew up", desktop)

    [notification] = desktop.announcements
    assert "6 cycles in a row failed" in notification.body


def test_a_network_fault_never_notifies(settings):
    desktop, _ = _forever(settings, _searches(settings, RuntimeError(NO_SUCH_HOST)), 4)

    assert desktop.announcements == []
    assert health(settings).last_error.endswith(NO_SUCH_HOST)


def test_a_login_fault_notifies_though_a_watched_repo_is_named_like_a_network_fault(tmp_path):
    named = fake_settings(tmp_path, repos=(
        RepoEntry(Repo("acme", "request-timeout"), "/code/request-timeout"),))
    github = Searches(named.config.gh_account, "acme/request-timeout",
                      RuntimeError("HTTP 401: Bad credentials"))

    desktop, _ = _forever(named, github, 3)

    assert len(desktop.announcements) == 1


@pytest.mark.parametrize(("error", "fix"), [
    (NO_TOKEN, "GitHub turned down the login for {account}. "
               "Run `gh auth login` as {account}."),
    (DISK_FULL, "The disk is full. Free some space and the watcher carries on."),
])
def test_a_fault_to_fix_notifies_what_to_do_about_it(settings, error, fix):
    desktop, _ = _forever(settings, _searches(settings, RuntimeError(error)), 3)

    [notification] = desktop.announcements
    assert notification.body.startswith(fix.format(account=settings.config.gh_account))
    assert "[[repos]]" not in notification.body


def test_a_successful_cycle_clears_the_failure_count(settings):
    _fail_once(settings, "poll blew up")
    _fail_once(settings, "poll blew up")

    watcher_over(settings).run_cycle()

    assert health(settings).last_error is None
    _fail_once(settings, "again")
    assert health(settings).last_error.endswith(": again")


def test_a_recovery_leaves_the_run_of_failures_it_ended_in_the_log(settings, caplog):
    _fail_once(settings, "first")
    _fail_once(settings, "gh: Bad credentials")

    with caplog.at_level(logging.INFO):
        watcher_over(settings).run_cycle()

    assert "recovered; failed cycles in a row: 2; last error: watcher cannot search" in caplog.text
    assert ": gh: Bad credentials" in caplog.text


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

    desktop, _ = _forever(settings, _searches(settings, RuntimeError("poll blew up")), 4)

    assert [(a.badge, a.title, a.body) for a in desktop.announcements] == [
        (Badge.FAILED, "Watcher not polling",
         f"3 cycles in a row failed: {_cannot_search(settings)}: poll blew up. "
         f"Details in {settings.logs_dir / 'watcher.log'}")]


def test_nothing_the_reporter_hits_can_take_the_daemon_down(settings):
    github = _searches(settings, ErrorThatCannotDescribeItself())

    _forever(settings, github, 3)

    assert len(github.cycles) == 3


def test_a_multi_line_error_reaches_the_notifier_on_one_line(settings):
    github = _searches(settings, RuntimeError("gh: Not Found\nrun gh auth login"))

    desktop, _ = _forever(settings, github, 3)

    assert "\n" not in desktop.announcements[0].body
    assert "run gh auth login" in desktop.announcements[0].body
    assert health(settings).last_error.endswith(": gh: Not Found run gh auth login")


def test_one_shot_cycles_that_fail_are_counted_notified_and_raised(settings):
    desktop = FakeDesktop()
    watcher = watcher_over(settings, desktop=desktop,
                           github=_searches(settings, RuntimeError("poll blew up")))

    for _ in range(3):
        with pytest.raises(RuntimeError, match="poll blew up"):
            watcher.run_cycle()

    assert [(a.badge, a.title, a.body) for a in desktop.announcements] == [
        (Badge.FAILED, "Watcher not polling",
         f"3 cycles in a row failed: {_cannot_search(settings)}: poll blew up. "
         f"Details in {settings.logs_dir / 'watcher.log'}")]
    assert health(settings).last_error.endswith(": poll blew up")


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
    late = Health(alive=True, polled_at=NOW - timedelta(seconds=241), read_at=NOW,
                  last_error=None, polls_every=timedelta(minutes=1))

    assert late.overdue


def test_the_overdue_threshold_scales_with_the_poll_interval():
    polls_every = timedelta(minutes=5)
    within = Health(alive=True, polled_at=NOW - timedelta(minutes=11), read_at=NOW,
                    last_error=None, polls_every=polls_every)
    past = Health(alive=True, polled_at=NOW - timedelta(minutes=13), read_at=NOW,
                  last_error=None, polls_every=polls_every)

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

    assert health(settings).last_error.endswith(": first")
    assert list(settings.watcher_failures.parent.glob("*.writing")) == []


def _fault(settings):
    reported = health(settings)
    return reported.last_error_fault, reported.hidden_repo


def test_a_cycle_failing_while_gh_has_no_token_for_the_account_is_a_login_fault(settings):
    _forever(settings, _searches(settings, RuntimeError(NO_TOKEN)), 1)

    assert _fault(settings) == (Fault.LOGIN, None)


def test_a_cycle_failing_on_a_repo_the_account_cannot_see_names_the_repo(settings):
    _forever(settings, Searches(settings.config.gh_account, "someone/else"), 1)

    assert _fault(settings) == (Fault.ACCESS, Repo("octocat", "hello-world"))


def test_a_refusal_naming_no_repo_the_account_cannot_see_names_none(settings):
    _forever(settings, _searches(settings, RuntimeError("gh: Not Found (HTTP 404)")), 1)

    assert _fault(settings) == (Fault.ACCESS, None)


def test_a_cycle_failing_for_a_reason_gh_and_github_do_not_explain_is_unknown(settings):
    _forever(settings, _searches(settings, RuntimeError("poll blew up")), 1)

    assert _fault(settings) == (Fault.UNKNOWN, None)


def test_a_failure_record_written_before_faults_were_kept_is_diagnosed_from_its_error(settings):
    settings.watcher_failures.write_text(json.dumps(
        {"consecutive": 4, "last_error": "HTTP 401: Bad credentials", "fix": "log in"}))

    assert _fault(settings) == (Fault.LOGIN, None)


def test_the_health_names_the_account_and_the_config_a_fix_is_worded_from(settings):
    reported = health(settings)

    assert (reported.account, reported.config_path) == (
        settings.config.gh_account, str(settings.config_path))
