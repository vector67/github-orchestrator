from tests.change_detection.support import (
    THE_PR,
    disk_change_detection,
    poll,
    pr_state,
    types,
    would_save_change_detection,
)


def test_a_poll_that_would_be_saved_raises_its_events_and_keeps_the_last_snapshot(tmp_path):
    disk_change_detection(tmp_path).advance(THE_PR, poll(), set())
    before = disk_change_detection(tmp_path).facts(THE_PR)
    said: list[str] = []

    events = would_save_change_detection(tmp_path, said).advance(
        THE_PR, poll(pr_state(mergeable_state="dirty")), set())

    assert types(events) == ["became-unmergeable"]
    assert disk_change_detection(tmp_path).facts(THE_PR) == before
    assert said == [f"would save state for {THE_PR}"]


def test_a_close_that_would_be_saved_leaves_the_pr_open(tmp_path):
    disk_change_detection(tmp_path).advance(THE_PR, poll(), set())
    said: list[str] = []

    would_save_change_detection(tmp_path, said).close(THE_PR)

    assert disk_change_detection(tmp_path).closing(THE_PR) is False
    assert said == [f"would save state for {THE_PR}"]
