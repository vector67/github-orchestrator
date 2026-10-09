from dataclasses import replace
from datetime import datetime, timedelta, timezone

from github_orchestrator.github import PullRequestState
from github_orchestrator.github.fake import FakeGitHub
from tests.builders import a_pr
from tests.change_detection.support import disk_change_detection, polled_on_disk, seen
from tests.pr_event_queue.support import disk_event_queue, pending_of
from tests.watcher.support import watcher_over

REPO = "octocat/hello-world"
MENTIONED = a_pr(82, REPO)


class CountsMentionSearches(FakeGitHub):
    def __init__(self, account):
        super().__init__(account=account)
        self.mention_searches = 0

    def search(self, repo, whose):
        if whose == "mentions":
            self.mention_searches += 1
        return super().search(repo, whose)


def _github(settings, *, mentioned=True, status="OPEN"):
    github = CountsMentionSearches(settings.config.gh_account)
    github.repos.update(settings.repos)
    github.add_pr(MENTIONED, PullRequestState(author="anna", title="Theirs"), status=status,
                  mentioned=mentioned)
    return github


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def test_a_pr_only_the_mentions_search_finds_is_watched_and_known_as_mentioned(settings):
    watcher_over(settings, github=_github(settings)).run_cycle()

    facts = disk_change_detection(settings.state_dir).facts(MENTIONED)
    assert (facts.title, facts.mentioned) == ("Theirs", True)


def test_the_mentions_search_runs_at_most_once_a_minute_and_keeps_what_it_found(settings):
    github, clock = _github(settings), Clock()
    watcher = watcher_over(settings, github=github, clock=clock)

    watcher.run_cycle()
    github.prs[MENTIONED].mentioned = False
    clock.now += timedelta(seconds=30)
    watcher.run_cycle()
    searched_within_the_minute = github.mention_searches
    clock.now += timedelta(seconds=30)
    watcher.run_cycle()

    assert (searched_within_the_minute, github.mention_searches) == (1, 2)
    assert disk_change_detection(settings.state_dir).closing(MENTIONED) is False
    assert [event.kind for event in pending_of(disk_event_queue(settings.queues_dir), MENTIONED)
            if event.kind == "pr-closed"] == []


def test_a_mentioned_pr_that_left_the_search_stays_watched_while_open(settings):
    polled_on_disk(settings.state_dir, MENTIONED,
                   replace(seen(settings.config.gh_account, is_author=False), mentioned=True))

    watcher_over(settings, github=_github(settings, mentioned=False)).run_cycle()

    detection = disk_change_detection(settings.state_dir)
    assert (detection.facts(MENTIONED).title, detection.closing(MENTIONED)) == ("Theirs", False)


def test_a_mentioned_pr_that_was_merged_is_torn_down(settings, capsys):
    polled_on_disk(settings.state_dir, MENTIONED,
                   replace(seen(settings.config.gh_account, is_author=False), mentioned=True))

    watcher_over(settings, github=_github(settings, status="MERGED")).run_cycle()

    assert "1 torn down" in capsys.readouterr().out
