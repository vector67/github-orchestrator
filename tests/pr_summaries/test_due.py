import os
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from github_orchestrator.domain import Pr
from github_orchestrator.pr_summaries import PrSummaries, Summary
from github_orchestrator.wiring import PrSummariesWiring, wire
from tests.builders import a_pr
from tests.conftest import clocks_of, ticking_clock

THE_PR = a_pr(1, "o/n")


def summaries_in(summaries_dir: Path,
                 now: Callable[[], datetime] | None = None) -> PrSummaries:
    summaries: PrSummaries = wire(PrSummariesWiring(summaries_dir),
                                  clocks_of(now or ticking_clock())).get(PrSummaries)
    return summaries


def test_a_first_review_request_makes_the_summary_due(tmp_path):
    summaries = summaries_in(tmp_path)

    summaries.want(THE_PR)

    assert summaries.due(set()) == [THE_PR]


def _answered(summaries: PrSummaries, pr: Pr) -> None:
    stored = summaries.load(pr)
    assert stored is not None
    summaries.save(pr, replace(stored, answered=stored.wanted))


def test_a_summary_run_for_the_request_is_no_longer_due(tmp_path):
    summaries = summaries_in(tmp_path)
    summaries.want(THE_PR)

    _answered(summaries, THE_PR)

    assert summaries.due(set()) == []


def test_a_re_request_after_a_review_makes_the_summary_due_again(tmp_path):
    summaries = summaries_in(tmp_path)
    summaries.want(THE_PR)
    _answered(summaries, THE_PR)

    summaries.want(THE_PR)

    assert summaries.due(set()) == [THE_PR]


def test_an_unwanted_summary_is_no_longer_due_and_keeps_its_last_report(tmp_path):
    summaries = summaries_in(tmp_path)
    summaries.want(THE_PR)
    stored = summaries.load(THE_PR)
    assert stored is not None
    summaries.save(THE_PR, replace(stored, markdown="# Earlier\n"))

    assert summaries.unwant(THE_PR) is True

    assert summaries.due(set()) == []
    assert summaries.load(THE_PR) == Summary(markdown="# Earlier\n")


def test_a_summary_that_cannot_be_rewritten_is_not_unwanted(tmp_path):
    summaries = summaries_in(tmp_path)
    summaries.want(THE_PR)
    folder = tmp_path / "o" / "n"
    folder.chmod(0o500)
    try:
        assert summaries.unwant(THE_PR) is False
    finally:
        folder.chmod(0o700)

    assert summaries.due(set()) == [THE_PR]


def test_unwanting_a_pr_with_no_summary_leaves_nothing_behind(tmp_path):
    summaries = summaries_in(tmp_path)

    assert summaries.unwant(THE_PR) is True

    assert summaries.load(THE_PR) is None


def test_a_summary_with_its_run_in_flight_is_not_due(tmp_path):
    summaries = summaries_in(tmp_path)
    summaries.want(THE_PR)

    assert summaries.due({THE_PR}) == []


def test_a_run_lost_with_the_process_is_due_again_after_a_restart(tmp_path):
    summaries_in(tmp_path).want(THE_PR)

    restarted = summaries_in(tmp_path)

    assert restarted.due(set()) == [THE_PR]


def test_the_oldest_request_is_due_first(tmp_path):
    summaries = summaries_in(tmp_path)
    later, earlier, middle = a_pr(1, "a/z"), a_pr(9, "z/a"), a_pr(10, "m/m")

    for pr in (earlier, middle, later):
        summaries.want(pr)

    assert summaries.due(set()) == [earlier, middle, later]


def test_a_request_made_during_a_run_stays_due_after_the_run_saves(tmp_path):
    summaries = summaries_in(tmp_path)
    summaries.want(THE_PR)
    started_for = summaries.load(THE_PR)
    assert started_for is not None

    summaries.want(THE_PR)
    summaries.save(THE_PR, replace(started_for, answered=started_for.wanted))

    assert summaries.due(set()) == [THE_PR]


def test_a_corrupt_summary_file_leaves_the_other_summaries_due(tmp_path):
    summaries = summaries_in(tmp_path)
    corrupt = a_pr(2, "o/n")
    summaries.want(THE_PR)
    summaries.want(corrupt)
    (tmp_path / "o" / "n" / "2.json").write_text("{not json")

    assert summaries.due(set()) == [THE_PR]


def test_a_save_reaches_the_disk_before_it_replaces_the_stored_summary(tmp_path, monkeypatch):
    summaries = summaries_in(tmp_path)
    summaries.want(THE_PR)
    stored_file = tmp_path / "o" / "n" / "1.json"
    before = stored_file.read_bytes()
    synced = []
    monkeypatch.setattr(os, "fsync", lambda fd: synced.append((os.pread(fd, 1 << 20, 0), stored_file.read_bytes())))

    summaries.save(THE_PR, Summary(head_sha="abc1234"))

    assert synced == [(stored_file.read_bytes(), before)]


STARTED =datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
FINISHED = datetime(2026, 10, 15, 9, 7, tzinfo=timezone.utc)


def test_a_saved_run_reads_back_with_every_stored_field(tmp_path):
    summaries = summaries_in(tmp_path)
    summaries.want(THE_PR)
    wanted = summaries.load(THE_PR)
    assert wanted is not None
    ran = replace(wanted, answered=wanted.wanted, head_sha="abc1234", started=STARTED,
                  finished=FINISHED, exit_status=3, stderr="needs the api\n",
                  markdown="# Summary\n", mismatches=2)

    summaries.save(THE_PR, ran)

    assert summaries_in(tmp_path).load(THE_PR) == ran


def test_a_summary_is_kept_per_pr_under_owner_and_repo(tmp_path):
    summaries_in(tmp_path).want(a_pr(7, "acme/widgets"))

    assert (tmp_path / "acme" / "widgets" / "7.json").is_file()
