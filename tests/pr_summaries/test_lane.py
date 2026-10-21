import json
import os
import signal
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from tests.builders import a_pr
from tests.pr_summaries.support import HEAD, THE_PR, Held, Lane, three_commits


def test_a_due_summary_runs_the_plugin_on_the_next_poll_and_stores_its_report(tmp_path):
    lane = Lane(tmp_path, "clean")
    lane.summaries.want(THE_PR)
    wanted = lane.summaries.load(THE_PR).wanted

    lane.lane.poll()

    stored = lane.summaries.load(THE_PR)
    assert stored.markdown == "# Summary\n\nIt does what it says.\n"
    assert (stored.exit_status, stored.stderr, stored.head_sha, stored.mismatches) == (0, "", HEAD, 2)
    assert stored.answered == wanted
    assert wanted < stored.started < stored.finished
    assert lane.call() == {"pr": "https://github.com/acme/widgets/pull/7", "config": str(lane.config),
                           "cwd": str(lane.clone.resolve()), "use_github_api": False, "gh_account": "octocat",
                           "mcp_config": None, "earlier_primer": None}
    assert lane.summaries.due(set()) == []


def test_a_rerun_hands_the_plugin_the_primer_the_last_run_wrote(tmp_path):
    lane = Lane(tmp_path, "clean")
    lane.lane.start(THE_PR, use_github_api=False)
    written = json.loads((lane.folder / "primer" / "output.json").read_text())

    lane.lane.start(THE_PR, use_github_api=False)

    assert lane.call()["earlier_primer"] == written


def test_a_run_that_wrote_no_primer_leaves_the_one_before_for_the_next(tmp_path):
    Lane(tmp_path, "clean").lane.start(THE_PR, use_github_api=False)
    Lane(tmp_path, "crash").lane.start(THE_PR, use_github_api=False)
    lane = Lane(tmp_path, "clean")

    lane.lane.start(THE_PR, use_github_api=False)

    assert lane.call()["earlier_primer"]["concepts"][0]["name"] == "Toolbar"


def test_a_pr_whose_last_run_kept_a_primer_is_due_again_once_wanted(tmp_path):
    lane = Lane(tmp_path, "clean")
    lane.lane.start(THE_PR, use_github_api=False)
    lane.lane.start(THE_PR, use_github_api=False)

    lane.summaries.want(THE_PR)

    assert lane.summaries.due(set()) == [THE_PR]


RECORDING_CLAMP = "import os, sys; open(sys.argv[1], 'w').write(sys.argv[2]); os.execv(sys.argv[2], sys.argv[2:])"


def test_a_run_starts_the_plugin_under_the_clamp(tmp_path):
    clamped = tmp_path / "clamped"
    lane = Lane(tmp_path, "clean", clamp=(sys.executable, "-c", RECORDING_CLAMP, str(clamped)))
    lane.summaries.want(THE_PR)

    lane.lane.poll()

    assert clamped.read_text() == sys.executable
    assert lane.summaries.load(THE_PR).exit_status == 0


def test_a_run_empties_the_working_folder_before_the_plugin_writes_into_it(tmp_path):
    lane = Lane(tmp_path, "clean")
    lane.summaries.want(THE_PR)
    (lane.folder / "why").mkdir(parents=True)
    (lane.folder / "why" / "output.json").write_text("{}")

    lane.lane.poll()

    assert lane.summaries.load(THE_PR).exit_status == 0
    assert (lane.folder / "alignment" / "output.json").exists()


def _with_an_earlier_summary(lane: Lane) -> None:
    lane.summaries.want(THE_PR)
    lane.summaries.save(THE_PR, replace(lane.summaries.load(THE_PR), head_sha="old", markdown="# Earlier\n",
                                        mismatches=1, exit_status=0))


def test_a_run_that_needs_the_github_api_keeps_the_earlier_summary_and_stores_the_plugins_reason(tmp_path):
    lane = Lane(tmp_path, "needs-api")
    _with_an_earlier_summary(lane)
    wanted = lane.summaries.load(THE_PR).wanted

    lane.lane.poll()

    stored = lane.summaries.load(THE_PR)
    assert stored.exit_status == 3
    assert "about 31 API calls" in stored.stderr
    assert (stored.head_sha, stored.markdown, stored.mismatches) == ("old", "# Earlier\n", 1)
    assert stored.answered == wanted


def test_a_run_that_fails_otherwise_keeps_the_earlier_summary_and_stores_its_exit_status(tmp_path):
    lane = Lane(tmp_path, "crash")
    _with_an_earlier_summary(lane)

    lane.lane.poll()

    stored = lane.summaries.load(THE_PR)
    assert (stored.exit_status, stored.stderr) == (1, "GhFailed: gh pr view failed\n")
    assert (stored.head_sha, stored.markdown, stored.mismatches) == ("old", "# Earlier\n", 1)
    assert lane.summaries.due(set()) == []


def test_a_run_past_its_time_is_killed_and_stored_as_failed(tmp_path):
    lane = Lane(tmp_path, "hang", timeout=0.2)
    _with_an_earlier_summary(lane)

    lane.lane.poll()

    stored = lane.summaries.load(THE_PR)
    assert stored.exit_status != 0
    assert "stopped the run after" in stored.stderr
    assert stored.markdown == "# Earlier\n"
    assert lane.summaries.due(set()) == []


def test_without_the_judges_output_the_mismatch_count_is_unknown(tmp_path):
    lane = Lane(tmp_path, "no-alignment")
    lane.summaries.want(THE_PR)

    lane.lane.poll()

    stored = lane.summaries.load(THE_PR)
    assert (stored.exit_status, stored.markdown, stored.mismatches) == (0, "# Summary\n\nIt does what it says.\n", None)


def test_a_malformed_judges_output_leaves_the_mismatch_count_unknown(tmp_path):
    lane = Lane(tmp_path, "malformed-alignment")
    lane.summaries.want(THE_PR)

    lane.lane.poll()

    assert lane.summaries.load(THE_PR).mismatches is None


def test_a_plugin_that_cannot_be_started_is_stored_as_failed(tmp_path):
    lane = Lane(tmp_path, "clean", plugin=(str(tmp_path / "no-such-uv"),))
    _with_an_earlier_summary(lane)

    lane.lane.poll()

    stored = lane.summaries.load(THE_PR)
    assert stored.exit_status is None
    assert "no-such-uv" in stored.stderr
    assert stored.finished is not None
    assert lane.summaries.due(set()) == []


class InAThread:
    def __init__(self) -> None:
        self.threads: list[threading.Thread] = []

    def __call__(self, work: Callable[[], None]) -> None:
        thread = threading.Thread(target=work)
        self.threads.append(thread)
        thread.start()

    def finish(self, lane: Lane) -> None:
        (lane.folder / "go-on").write_text("")
        for thread in self.threads:
            thread.join(timeout=10)


def _partway(lane: Lane) -> None:
    deadline = time.monotonic() + 10
    while not (lane.folder / "implementation").is_dir():
        assert time.monotonic() < deadline, "the fake plugin never got partway"
        time.sleep(0.01)


def test_while_a_run_is_in_flight_its_progress_names_the_witnesses_that_have_finished(tmp_path):
    threads = InAThread()
    lane = Lane(tmp_path, "partway", run_in=threads)
    lane.summaries.want(THE_PR)
    lane.lane.poll()
    _partway(lane)

    progress = lane.lane.progress(THE_PR)

    threads.finish(lane)
    assert progress is not None
    assert dict(progress.done) == {"claimed": True, "implementation": False}
    assert progress.since == lane.summaries.load(THE_PR).started
    assert lane.lane.progress(THE_PR) is None


def test_a_run_in_flight_counts_the_critic_and_the_final_judge_among_its_agents(tmp_path):
    threads = InAThread()
    lane = Lane(tmp_path, "partway", run_in=threads)
    lane.summaries.want(THE_PR)
    lane.lane.poll()
    _partway(lane)
    (lane.folder / "critic").mkdir()
    (lane.folder / "critic" / "output.json").write_text("{}")
    (lane.folder / "verdict").mkdir()

    progress = lane.lane.progress(THE_PR)

    threads.finish(lane)
    assert progress is not None
    assert dict(progress.done) == {"claimed": True, "implementation": False, "critic": True, "verdict": False}


def test_a_run_in_flight_counts_the_primer_among_its_agents(tmp_path):
    threads = InAThread()
    lane = Lane(tmp_path, "partway", run_in=threads)
    lane.summaries.want(THE_PR)
    lane.lane.poll()
    _partway(lane)
    (lane.folder / "primer").mkdir()

    progress = lane.lane.progress(THE_PR)

    threads.finish(lane)
    assert progress is not None
    assert dict(progress.done) == {"claimed": True, "implementation": False, "primer": False}


def test_a_pr_with_no_run_in_flight_has_no_progress(tmp_path):
    lane = Lane(tmp_path, "clean")
    lane.summaries.want(THE_PR)
    lane.lane.poll()

    assert lane.lane.progress(THE_PR) is None
    assert lane.lane.progress(a_pr(8, "acme/widgets")) is None


def test_a_request_made_while_its_summary_runs_leaves_the_summary_due(tmp_path):
    threads = InAThread()
    lane = Lane(tmp_path, "partway", run_in=threads)
    lane.summaries.want(THE_PR)
    lane.lane.poll()
    _partway(lane)

    lane.summaries.want(THE_PR)
    threads.finish(lane)

    assert lane.summaries.due(set()) == [THE_PR]


def test_the_lane_runs_one_summary_at_a_time(tmp_path):
    threads = InAThread()
    lane = Lane(tmp_path, "partway", run_in=threads)
    other = a_pr(8, "acme/widgets")
    lane.summaries.want(THE_PR)
    lane.summaries.want(other)
    lane.lane.poll()
    _partway(lane)

    lane.lane.poll()
    refused = lane.lane.start(other, use_github_api=False)

    threads.finish(lane)
    assert len(threads.threads) == 1
    assert refused == "another summary is running"
    assert lane.summaries.due(set()) == [other]


def test_a_started_run_reads_over_the_github_api_when_asked_and_answers_the_request_it_saw(tmp_path):
    lane = Lane(tmp_path, "clean")
    lane.summaries.want(THE_PR)
    wanted = lane.summaries.load(THE_PR).wanted

    refused = lane.lane.start(THE_PR, use_github_api=True)

    assert refused is None
    assert lane.call()["use_github_api"] is True
    stored = lane.summaries.load(THE_PR)
    assert (stored.wanted, stored.answered, stored.exit_status) == (wanted, wanted, 0)


def test_a_started_run_on_a_pr_never_requested_leaves_it_not_due(tmp_path):
    lane = Lane(tmp_path, "clean")

    lane.lane.start(THE_PR, use_github_api=False)

    stored = lane.summaries.load(THE_PR)
    assert (stored.wanted, stored.answered, stored.markdown) == (None, None, "# Summary\n\nIt does what it says.\n")
    assert lane.summaries.due(set()) == []


def test_with_agents_disabled_the_lane_runs_nothing(tmp_path):
    lane = Lane(tmp_path, "clean", agents_enabled=False)
    lane.summaries.want(THE_PR)

    lane.lane.poll()
    refused = lane.lane.start(THE_PR, use_github_api=False)

    assert refused == "agents are disabled (agents_enabled=false)"
    assert not lane.folder.exists()
    assert lane.summaries.due(set()) == [THE_PR]


def test_a_pr_in_a_repository_no_longer_watched_is_not_summarised(tmp_path):
    lane = Lane(tmp_path, "clean")
    elsewhere = a_pr(3, "acme/gadgets")
    lane.summaries.want(elsewhere)

    lane.lane.poll()
    refused = lane.lane.start(elsewhere, use_github_api=False)

    assert refused == "acme/gadgets is not a watched repository"
    assert lane.summaries.due(set()) == [elsewhere]


def test_a_run_shows_as_in_flight_from_the_moment_it_takes_the_slot(tmp_path):
    held = Held()
    lane = Lane(tmp_path, "clean", run_in=held)
    earlier = a_pr(8, "acme/widgets")
    lane.lane.start(earlier, use_github_api=False)
    held.work.pop()()

    lane.lane.start(THE_PR, use_github_api=False)

    assert lane.lane.progress(earlier) is None
    assert lane.lane.progress(THE_PR) is not None
    held.work.pop()()


def _a_server_that_dies_partway(tmp_path: Path, lane: Lane, behaviour: str) -> None:
    server = os.fork()
    if server == 0:
        try:
            Lane(tmp_path, behaviour).lane.start(THE_PR, use_github_api=False)
        finally:
            os._exit(0)
    _partway(lane)
    os.kill(server, signal.SIGKILL)
    os.waitpid(server, 0)


def _until_it_stops_running(lane: Lane) -> None:
    deadline = time.monotonic() + 10
    while lane.lane.progress(THE_PR) is not None:
        assert time.monotonic() < deadline, "the run never stopped"
        time.sleep(0.02)


def test_a_run_whose_server_died_still_shows_as_running_and_cannot_be_started_twice(tmp_path):
    lane = Lane(tmp_path, "partway", head="moved-on")
    lane.summaries.want(THE_PR)
    _a_server_that_dies_partway(tmp_path, lane, "partway")

    progress = lane.lane.progress(THE_PR)
    refused = lane.lane.start(THE_PR, use_github_api=False)

    (lane.folder / "go-on").write_text("")
    _until_it_stops_running(lane)
    assert progress is not None
    assert dict(progress.done) == {"claimed": True, "implementation": False}
    assert refused == "another summary is running"


def test_a_run_whose_server_died_is_stored_by_the_next_lane_to_see_it_finish(tmp_path):
    lane = Lane(tmp_path, "partway", head="moved-on")
    lane.summaries.want(THE_PR)
    wanted = lane.summaries.load(THE_PR).wanted
    _a_server_that_dies_partway(tmp_path, lane, "partway")
    since = lane.lane.progress(THE_PR).since

    (lane.folder / "go-on").write_text("")
    _until_it_stops_running(lane)

    stored = lane.summaries.load(THE_PR)
    assert stored.markdown == "# Summary\n\nIt does what it says.\n"
    assert (stored.exit_status, stored.stderr, stored.head_sha, stored.mismatches) == (0, "", HEAD, None)
    assert (stored.answered, stored.started) == (wanted, since)
    assert stored.finished is not None
    assert lane.summaries.due(set()) == []


def test_a_run_whose_server_died_and_whose_witness_failed_keeps_the_earlier_summary(tmp_path):
    lane = Lane(tmp_path, "partway-then-a-witness-fails")
    _with_an_earlier_summary(lane)
    _a_server_that_dies_partway(tmp_path, lane, "partway-then-a-witness-fails")

    (lane.folder / "go-on").write_text("")
    _until_it_stops_running(lane)

    stored = lane.summaries.load(THE_PR)
    assert (stored.exit_status, stored.stderr) == (1, "Witnesses failed: why: timed out\n")
    assert (stored.head_sha, stored.markdown, stored.mismatches) == ("old", "# Earlier\n", 1)
    assert lane.summaries.due(set()) == []


def test_a_run_that_died_with_no_server_waiting_is_stored_as_lost_and_left_due(tmp_path):
    lane = Lane(tmp_path, "partway")
    _with_an_earlier_summary(lane)
    _a_server_that_dies_partway(tmp_path, lane, "partway")

    (lane.folder / "die").write_text("")
    _until_it_stops_running(lane)

    stored = lane.summaries.load(THE_PR)
    assert stored.exit_status is None
    assert "ended without an exit status" in stored.stderr
    assert (stored.head_sha, stored.markdown) == ("old", "# Earlier\n")
    assert lane.summaries.due(set()) == [THE_PR]


def test_a_summary_is_behind_by_the_commits_between_the_head_it_read_and_the_head_now(tmp_path, git_template):
    first, _, third = git_template(three_commits)
    lane = Lane(tmp_path, "clean", head=first, clone=tmp_path / "repo")
    lane.lane.start(THE_PR, use_github_api=False)

    assert lane.lane.behind(THE_PR, third) == 2
    assert lane.lane.behind(THE_PR, first) == 0


def test_a_summary_has_no_count_behind_without_both_heads_or_a_commit_the_clone_holds(tmp_path, git_template):
    first, _, third = git_template(three_commits)
    lane = Lane(tmp_path, "clean", head=first, clone=tmp_path / "repo")

    never_run = lane.lane.behind(THE_PR, third)
    lane.lane.start(THE_PR, use_github_api=False)

    assert never_run is None
    assert lane.lane.behind(THE_PR, None) is None
    assert lane.lane.behind(THE_PR, "0" * 40) is None
    assert lane.lane.behind(a_pr(3, "acme/gadgets"), third) is None


def test_a_configured_mcp_config_is_handed_to_the_plugin(tmp_path):
    lane = Lane(tmp_path, "clean", mcp_config="/etc/acme/mcp.json")
    lane.summaries.want(THE_PR)

    lane.lane.poll()

    assert lane.call()["mcp_config"] == "/etc/acme/mcp.json"
