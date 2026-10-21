import logging
from pathlib import Path

import pytest

from github_orchestrator.desktop.fake import FakeDesktop
from tests.builders import a_pr
from tests.notifications.support import LONG_AWAKE, Clock, opened

LOGGER = "github_orchestrator.notifications"


@pytest.fixture
def desktop():
    return FakeDesktop()


@pytest.fixture
def store(tmp_path, desktop):
    return opened(tmp_path, desktop, Clock())


def _logged(caplog, word):
    return [record for record in caplog.records if f" {word}" in record.getMessage()]


def _watcher_failed(notifications):
    notifications.polling.failed(1, "HTTP 403: secondary rate limit", Path("watcher.log"))


def test_a_posted_notification_is_logged_with_what_it_says_and_the_code_that_posted_it(
        store, caplog):
    notifications, _ = store

    with caplog.at_level(logging.INFO, logger=LOGGER):
        _watcher_failed(notifications)

    [posted] = _logged(caplog, "posted")
    assert "Watcher not polling" in posted.getMessage()
    assert "HTTP 403: secondary rate limit" in posted.getMessage()
    assert "_watcher_failed" in (posted.stack_info or "")


def test_a_shown_notification_is_logged_under_the_key_it_was_posted_with(
        store, desktop, caplog):
    notifications, courier = store

    with caplog.at_level(logging.INFO, logger=LOGGER):
        _watcher_failed(notifications)
        courier.deliver(LONG_AWAKE, None)

    [shown] = _logged(caplog, "shown")
    [posted] = _logged(caplog, "posted")
    key = desktop.announcements[0].key
    assert key in shown.getMessage()
    assert key in posted.getMessage()
    assert "Watcher not polling" in shown.getMessage()


def _fix_ready(notifications):
    notifications.thread_news.fix_ready(a_pr(84, "acme/widgets"), "thread-1", gist="g",
                                        comments=[("octocat", "rename it")],
                                        fix_summary="renamed")


def test_a_notification_gathered_into_a_batch_is_logged_with_its_group_and_the_code(
        store, caplog):
    notifications, _ = store

    with caplog.at_level(logging.INFO, logger=LOGGER):
        _fix_ready(notifications)

    [gathered] = _logged(caplog, "gathered")
    assert "FixReady" in gathered.getMessage()
    assert "_fix_ready" in (gathered.stack_info or "")
