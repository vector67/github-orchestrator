import pytest

from github_orchestrator.github import (
    CommentKind,
    PullRequestState,
    Thread,
    ThreadComment,
)
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.mentions import PrNow, StartUnread
from github_orchestrator.watcher import Watcher
from tests.builders import a_pr
from tests.change_detection.support import disk_change_detection
from tests.pr_event_queue.support import disk_event_queue, pending_of
from tests.watcher.support import health, watcher_container, watcher_over

UNBUILT = a_pr(82, "octocat/hello-world")


class CountedSearches:
    def __init__(self, failure: Exception | None = None) -> None:
        self.searches = 0
        self._failure = failure
        self.unbuilt_cards: list = []
        self.settled: list = []

    def unbuilt(self):
        return self.unbuilt_cards

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


def test_each_cycle_hands_the_inbox_what_it_polled_of_each_pr_to_settle_deferrals(settings):
    github = _off_the_search(settings)
    github.prs[UNBUILT].state = PullRequestState(author="anna", title="Theirs", head_sha="abc",
                                                 review_decision="APPROVED")
    inbox = CountedSearches()
    inbox.unbuilt_cards = [UNBUILT]

    watcher_over(settings, github=github, mentions_inbox=inbox).run_cycle()

    assert inbox.settled == [{UNBUILT: PrNow(head_sha="abc", approved=True, last_event_at=None,
                                             ended=False)}]


def test_an_inbox_that_fails_to_settle_deferrals_does_not_fail_the_cycle(settings, caplog):
    class Failing(CountedSearches):
        def settle_deferrals(self, prs) -> None:
            raise OSError("mentions-deferred.json unwritable")

    watcher_over(settings, mentions_inbox=Failing()).run_cycle()

    assert "mentions-deferred.json unwritable" in caplog.text
