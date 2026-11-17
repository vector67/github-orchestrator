import errno

import pytest

from github_orchestrator.desktop.fake import FakeDesktop
from tests.builders import a_pr
from tests.notifications.support import LONG_AWAKE, Clock, opened


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def desktop():
    return FakeDesktop()


def _titles(desktop):
    return [a.title for a in desktop.announcements]


def test_a_run_that_fails_again_the_same_day_is_shown_once(tmp_path, desktop, clock):
    notifications, courier = opened(tmp_path, desktop, clock)

    notifications.runs.run_failed(a_pr(84, "acme/widgets"), "ci-failed", 1)
    courier.deliver(LONG_AWAKE, None)
    clock.advance(hours=2)
    notifications.runs.run_failed(a_pr(84, "acme/widgets"), "ci-failed", 1)
    courier.deliver(LONG_AWAKE, None)

    assert _titles(desktop) == ["Run failed on widgets#84"]


def test_a_run_that_fails_again_the_next_day_is_shown_again(tmp_path, desktop, clock):
    notifications, courier = opened(tmp_path, desktop, clock)

    notifications.runs.run_failed(a_pr(84, "acme/widgets"), "ci-failed", 1)
    courier.deliver(LONG_AWAKE, None)
    clock.advance(hours=7)
    notifications.runs.run_failed(a_pr(84, "acme/widgets"), "ci-failed", 1)
    courier.deliver(LONG_AWAKE, None)

    assert _titles(desktop) == ["Run failed on widgets#84", "Run failed on widgets#84"]


def test_a_run_failed_before_a_restart_is_not_shown_again_after_it(tmp_path, desktop, clock):
    before, courier = opened(tmp_path, desktop, clock)
    before.runs.run_failed(a_pr(84, "acme/widgets"), "ci-failed", 1)
    courier.deliver(LONG_AWAKE, None)

    after, courier = opened(tmp_path, desktop, clock)
    after.runs.run_failed(a_pr(84, "acme/widgets"), "ci-failed", 1)
    courier.deliver(LONG_AWAKE, None)

    assert _titles(desktop) == ["Run failed on widgets#84"]


def test_a_fix_that_fails_again_the_same_day_is_shown_once(tmp_path, desktop, clock):
    notifications, courier = opened(tmp_path, desktop, clock)

    notifications.thread_news.fix_failed(a_pr(84, "acme/widgets"), gist="rename it",
                                         author="octocat", reason="tests failed")
    courier.deliver(LONG_AWAKE, None)
    notifications.thread_news.fix_failed(a_pr(84, "acme/widgets"), gist="drop the flag",
                                         author="octocat", reason="no change")
    courier.deliver(LONG_AWAKE, None)

    assert _titles(desktop) == ["Fix failed on widgets#84"]


def test_an_agent_question_asked_again_is_shown_once(tmp_path, desktop, clock):
    notifications, courier = opened(tmp_path, desktop, clock)

    for _ in range(2):
        notifications.thread_news.agent_asked(a_pr(84, "acme/widgets"), "thread-a",
                                              question="Rename it everywhere?")
        courier.deliver(LONG_AWAKE, None)
        clock.advance(days=1)

    assert [a.body for a in desktop.announcements] == ["Rename it everywhere?"]


def test_a_new_question_in_the_same_thread_is_shown(tmp_path, desktop, clock):
    notifications, courier = opened(tmp_path, desktop, clock)

    notifications.thread_news.agent_asked(a_pr(84, "acme/widgets"), "thread-a",
                                          question="Rename it everywhere?")
    notifications.thread_news.agent_asked(a_pr(84, "acme/widgets"), "thread-a",
                                          question="Keep the old name as an alias?")
    courier.deliver(LONG_AWAKE, None)

    assert [a.body for a in desktop.announcements] == [
        "Rename it everywhere?", "Keep the old name as an alias?"]


def test_the_same_question_in_another_thread_is_shown(tmp_path, desktop, clock):
    notifications, courier = opened(tmp_path, desktop, clock)

    for thread in ("thread-a", "thread-b"):
        notifications.thread_news.agent_asked(a_pr(84, "acme/widgets"), thread,
                                              question="Rename it everywhere?")
    courier.deliver(LONG_AWAKE, None)

    assert len(desktop.announcements) == 2


@pytest.mark.parametrize("damage", ["{not json", "[]", '{"run failed": 7}', ""])
def test_a_damaged_record_of_what_was_sent_stops_no_notification(tmp_path, desktop, clock, damage):
    notifications, courier = opened(tmp_path, desktop, clock)
    (tmp_path / "sent.json").write_text(damage)

    notifications.runs.run_failed(a_pr(84, "acme/widgets"), "ci-failed", 1)
    courier.deliver(LONG_AWAKE, None)
    notifications.runs.run_failed(a_pr(84, "acme/widgets"), "ci-failed", 1)
    courier.deliver(LONG_AWAKE, None)

    assert _titles(desktop) == ["Run failed on widgets#84"]


def test_the_record_forgets_what_was_sent_more_than_three_days_ago(tmp_path, desktop, clock):
    notifications, courier = opened(tmp_path, desktop, clock)
    question = "Rename it everywhere?"

    notifications.thread_news.agent_asked(a_pr(84, "acme/widgets"), "thread-a", question=question)
    clock.advance(days=3, minutes=1)
    notifications.runs.run_failed(a_pr(84, "acme/widgets"), "ci-failed", 1)
    notifications.thread_news.agent_asked(a_pr(84, "acme/widgets"), "thread-a", question=question)
    courier.deliver(LONG_AWAKE, None)

    assert [a.body for a in desktop.announcements].count(question) == 2


def test_a_record_that_cannot_be_read_or_written_stops_no_notification(tmp_path, desktop, clock):
    notifications, courier = opened(tmp_path, desktop, clock)
    (tmp_path / "sent.json").mkdir(parents=True)

    notifications.runs.run_failed(a_pr(84, "acme/widgets"), "ci-failed", 1)
    courier.deliver(LONG_AWAKE, None)

    assert _titles(desktop) == ["Run failed on widgets#84"]


_ONCE_ONLY = {
    "run failed": lambda n: n.runs.run_failed(a_pr(84, "acme/widgets"), "ci-failed", 1),
    "fix failed": lambda n: n.thread_news.fix_failed(a_pr(84, "acme/widgets"), gist="rename it",
                                                     author="octocat", reason="tests failed"),
    "agent asked": lambda n: n.thread_news.agent_asked(a_pr(84, "acme/widgets"), "thread-a",
                                                       question="Rename it everywhere?"),
}


@pytest.mark.parametrize("notice", _ONCE_ONLY.values(), ids=_ONCE_ONLY.keys())
def test_a_notice_whose_post_failed_is_posted_when_it_comes_again(tmp_path, desktop, clock,
                                                                  monkeypatch, notice):
    notifications, courier = opened(tmp_path, desktop, clock)

    def full(path, data):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr("github_orchestrator.notifications._disk.write_atomically", full)
    with pytest.raises(OSError):
        notice(notifications)
    monkeypatch.undo()
    notice(notifications)
    courier.deliver(LONG_AWAKE, None)

    assert len(desktop.announcements) == 1
