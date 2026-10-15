import json
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.pr_summaries import PrSummaries, SummaryLane
from github_orchestrator.wiring import PrSummariesWiring, SummaryLaneWiring, wire
from tests.builders import a_pr
from tests.conftest import clocks_of, fake_provider, ticking_clock
from tests.pr_summaries.support import HeadsAt, Held, run_now, three_commits

THE_PR = a_pr(7, "acme/widgets")
FAKE_PLUGIN = Path(__file__).with_name("fake_plugin.py")
HEAD = "abc123"


class Lane:
    def __init__(self, tmp_path: Path, behaviour: str, *, run_in: Callable[[Callable[[], None]], None] = run_now,
                 agents_enabled: bool = True, timeout: float = 60, head: str | None = HEAD,
                 plugin: tuple[str, ...] | None = None, clone: Path | None = None, mcp_config: str = "") -> None:
        self.clone = clone or tmp_path / "clone"
        self.clone.mkdir(exist_ok=True)
        self.config = tmp_path / "config.toml"
        self.summaries_dir = tmp_path / "summaries"
        container = wire(
            PrSummariesWiring(self.summaries_dir),
            SummaryLaneWiring(plugin=plugin or (sys.executable, str(FAKE_PLUGIN), "--behaviour", behaviour),
                              config_path=self.config, clones={THE_PR.repo: self.clone}, gh_account="octocat",
                              agents_enabled=agents_enabled, mcp_config=mcp_config, timeout=timeout, run_in=run_in),
            clocks_of(ticking_clock()),
            fake_provider(ChangeDetection, HeadsAt(head)),
        )
        self.summaries: PrSummaries = container.get(PrSummaries)
        self.lane: SummaryLane = container.get(SummaryLane)

    @property
    def folder(self) -> Path:
        return self.summaries_dir / "acme" / "widgets" / "7"

    def call(self) -> dict[str, object]:
        called: dict[str, object] = json.loads((self.folder / "call.json").read_text())
        return called


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
                           "mcp_config": None}
    assert lane.summaries.due(set()) == []


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
    lane = Lane(tmp_path, "hang", timeout=0.5)
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
