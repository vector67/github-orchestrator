from dataclasses import replace

import pytest

from github_orchestrator.board_api.interface import Told
from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    Thread,
    ThreadComment,
)
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.mentions import PrNow, StartUnread
from github_orchestrator.pr_processes import ManagerPane
from github_orchestrator.watcher import Watcher
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.change_detection.support import disk_change_detection, polled_on_disk, seen
from tests.pr_event_queue.support import disk_event_queue, pending_of
from tests.pr_processes.support import checked_out
from tests.settings.support import disk_dismissals
from tests.watcher.support import health, watcher_container, watcher_over, watching

UNBUILT = a_pr(82, "octocat/hello-world")


class CountedSearches:
    def __init__(self, failure: Exception | None = None) -> None:
        self.searches = 0
        self._failure = failure
        self.unbuilt_cards: list = []
        self.opened_prs: list = []
        self.settled: list = []

    def unbuilt(self):
        return self.unbuilt_cards

    def opened(self):
        return self.opened_prs

    def settle_deferrals(self, prs) -> None:
        self.settled.append(dict(prs))

    def search_if_due(self) -> None:
        self.searches += 1
        if self._failure is not None:
            raise self._failure


def test_each_cycle_offers_the_mentions_inbox_its_search(settings):
    inbox = CountedSearches()

    watcher_over(settings, mentions_inbox=inbox).run_cycle()

    assert inbox.searches == 1


def test_a_mentions_inbox_that_fails_does_not_fail_the_cycle(settings, caplog):
    inbox = CountedSearches(OSError("mentions.json unwritable"))

    watcher_over(settings, mentions_inbox=inbox).run_cycle()

    assert inbox.searches == 1
    assert "mentions.json unwritable" in caplog.text


def test_a_config_the_mentions_inbox_cannot_read_fails_the_cycle_and_says_why(settings):
    inbox = CountedSearches(StartUnread("config.toml: mentions_start must be in quotes"))

    with pytest.raises(StartUnread):
        watcher_over(settings, mentions_inbox=inbox).run_cycle()

    assert health(settings).last_error.endswith("mentions_start must be in quotes")


def test_a_dry_run_says_it_would_search_for_mentions_and_writes_nothing(settings, capsys):
    stamped = 'mentions_start = "2026-09-01T00:00:00+00:00"\n'
    settings.config_path.write_text(stamped)

    watcher_container(settings, dry_run=True).get(Watcher).run_cycle()

    assert "would search for mentions" in capsys.readouterr().out
    assert not (settings.data_dir / "mentions.json").exists()
    assert settings.config_path.read_text() == stamped


def _off_the_search(settings):
    github = FakeGitHub(account=settings.config.gh_account)
    github.repos.update(settings.repos)
    github.add_pr(UNBUILT, PullRequestState(author="anna", title="Theirs"), mentioned=False)
    github.add_thread(UNBUILT, Thread(key="IC_1", kind=CommentKind.ISSUE, comments=(
        ThreadComment(id=1, author="anna", body="@octocat ping",
                      created_at="2026-10-22T10:00:00Z"),)))
    return github


def test_a_pr_whose_mention_the_inbox_has_no_card_for_is_tracked_as_mentioned(settings):
    inbox = CountedSearches()
    inbox.unbuilt_cards = [UNBUILT]

    watcher_over(settings, github=_off_the_search(settings), mentions_inbox=inbox).run_cycle()

    facts = disk_change_detection(settings.state_dir).facts(UNBUILT)
    assert (facts.title, facts.mentioned) == ("Theirs", True)


def test_the_mention_thread_of_a_pr_the_inbox_repairs_is_queued_to_become_a_card(settings):
    inbox = CountedSearches()
    inbox.unbuilt_cards = [UNBUILT]

    watcher_over(settings, github=_off_the_search(settings), mentions_inbox=inbox).run_cycle()

    [queued] = [event for event in pending_of(disk_event_queue(settings.queues_dir), UNBUILT)
                if event.kind == "thread-activity"]
    assert [thread.key for thread in queued.threads] == ["IC_1"]


def test_a_pr_opened_for_a_mention_is_tracked_and_its_mention_queued_to_become_a_card(settings):
    inbox = CountedSearches()
    inbox.opened_prs = [UNBUILT]

    watcher_over(settings, github=_off_the_search(settings), mentions_inbox=inbox).run_cycle()

    [queued] = [event for event in pending_of(disk_event_queue(settings.queues_dir), UNBUILT)
                if event.kind == "thread-activity"]
    assert ([thread.key for thread in queued.threads],
            disk_change_detection(settings.state_dir).facts(UNBUILT).mentioned) == (["IC_1"], True)


def test_a_merged_pr_opened_for_a_mention_is_kept_and_not_closed(settings, capsys):
    polled_on_disk(settings.state_dir, UNBUILT, seen(settings.config.gh_account))
    github = _off_the_search(settings)
    github.prs[UNBUILT].status = "MERGED"
    inbox = CountedSearches()
    inbox.opened_prs = [UNBUILT]

    watcher_over(settings, github=github, mentions_inbox=inbox).run_cycle()

    assert "0 torn down" in capsys.readouterr().out
    detection = disk_change_detection(settings.state_dir)
    assert detection.closing(UNBUILT) is False
    assert (detection.facts(UNBUILT).ended, detection.facts(UNBUILT).merged) == (True, True)
    assert [event.kind for event in pending_of(disk_event_queue(settings.queues_dir), UNBUILT)
            if event.kind == "pr-closed"] == []


def _dismissed_forever_and_opened(settings, tmp_path, pr_processes):
    github = _off_the_search(settings)
    github.prs[UNBUILT].state = replace(github.prs[UNBUILT].state, branch="theirs")
    copies = FakeWorkingCopies()
    checked_out(copies, tmp_path / "theirs", "theirs")
    disk_dismissals(settings.data_dir).dismiss_forever(UNBUILT)
    inbox = CountedSearches()
    inbox.opened_prs = [UNBUILT]
    return watcher_over(settings, github=github, mentions_inbox=inbox,
                        pr_processes=pr_processes, working_copies=copies)


def test_a_pr_dismissed_forever_opened_for_a_mention_gets_its_mention_queued_and_a_manager(
        settings, tmp_path, pr_processes):
    watcher = _dismissed_forever_and_opened(settings, tmp_path, pr_processes)

    watcher.run_cycle()

    [queued] = [event for event in pending_of(disk_event_queue(settings.queues_dir), UNBUILT)
                if event.kind == "thread-activity"]
    assert [thread.key for thread in queued.threads] == ["IC_1"]
    assert pr_processes.manager(UNBUILT) is ManagerPane.RUNNING


def test_a_pr_dismissed_forever_opened_for_a_mention_stays_dismissed_and_held(
        settings, tmp_path, pr_processes, capsys):
    watcher = _dismissed_forever_and_opened(settings, tmp_path, pr_processes)

    watcher.run_cycle()
    watcher.run_cycle()

    assert disk_dismissals(settings.data_dir).is_dismissed_forever(UNBUILT)
    assert "0 torn down" in capsys.readouterr().out.splitlines()[-1]
    assert UNBUILT in watcher_container(settings).get(Told).held().managers


def test_each_cycle_hands_the_inbox_what_it_polled_of_each_pr_to_settle_deferrals(settings):
    github = _off_the_search(settings)
    github.prs[UNBUILT].state = PullRequestState(author="anna", title="Theirs", head_sha="abc",
                                                 review_decision="APPROVED")
    inbox = CountedSearches()
    inbox.unbuilt_cards = [UNBUILT]

    watcher_over(settings, github=github, mentions_inbox=inbox).run_cycle()

    assert inbox.settled == [{UNBUILT: PrNow(head_sha="abc", approved=True, last_event_at=None,
                                             closed=False, merged=False)}]


@pytest.mark.parametrize(("status", "said"), [("MERGED", (True, True)),
                                              ("CLOSED", (True, False))])
def test_a_pr_that_ends_reaches_the_inbox_closed_and_whether_merged(settings, status, said):
    polled_on_disk(settings.state_dir, UNBUILT, seen(settings.config.gh_account))
    github = watching(settings)
    github.add_pr(UNBUILT, PullRequestState(author=settings.config.gh_account), status=status)
    inbox = CountedSearches()

    watcher_over(settings, github=github, mentions_inbox=inbox).run_cycle()

    assert [(now.closed, now.merged) for now in inbox.settled[0].values()] == [said]


def test_an_inbox_that_fails_to_settle_deferrals_does_not_fail_the_cycle(settings, caplog):
    class Failing(CountedSearches):
        def settle_deferrals(self, prs) -> None:
            raise OSError("mentions-deferred.json unwritable")

    watcher_over(settings, mentions_inbox=Failing()).run_cycle()

    assert "mentions-deferred.json unwritable" in caplog.text
