from tests.watcher.support import watcher_over


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
