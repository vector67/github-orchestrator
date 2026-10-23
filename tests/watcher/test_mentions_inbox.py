from github_orchestrator.watcher import Watcher
from tests.watcher.support import watcher_container, watcher_over


class CountedSearches:
    def __init__(self, failure: Exception | None = None) -> None:
        self.searches = 0
        self._failure = failure

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


def test_a_dry_run_says_it_would_search_for_mentions_and_writes_nothing(settings, capsys):
    stamped = 'mentions_start = "2026-09-01T00:00:00+00:00"\n'
    settings.config_path.write_text(stamped)

    watcher_container(settings, dry_run=True).get(Watcher).run_cycle()

    assert "would search for mentions" in capsys.readouterr().out
    assert not (settings.data_dir / "mentions.json").exists()
    assert settings.config_path.read_text() == stamped
