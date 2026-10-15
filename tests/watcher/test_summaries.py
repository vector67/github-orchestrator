from github_orchestrator.pr_summaries import PrSummaries
from github_orchestrator.watcher import Watcher
from tests.builders import a_pr
from tests.watcher.support import watcher_container, watcher_over

THE_PR = a_pr(5, "octocat/hello-world")


class CountedPolls:
    def __init__(self, failure: Exception | None = None) -> None:
        self.polls = 0
        self._failure = failure

    def poll(self) -> None:
        self.polls += 1
        if self._failure is not None:
            raise self._failure


def test_each_cycle_offers_the_summary_lane_its_turn(settings):
    lane = CountedPolls()

    watcher_over(settings, summary_lane=lane).run_cycle()

    assert lane.polls == 1


def test_a_summary_lane_that_fails_does_not_fail_the_cycle(settings, caplog):
    lane = CountedPolls(OSError("summaries folder unreadable"))

    watcher_over(settings, summary_lane=lane).run_cycle()

    assert lane.polls == 1
    assert "summaries folder unreadable" in caplog.text


def test_a_dry_run_says_which_summary_it_would_run_and_runs_none(settings, capsys):
    container = watcher_container(settings, dry_run=True)
    summaries: PrSummaries = container.get(PrSummaries)
    summaries.want(THE_PR)

    container.get(Watcher).run_cycle()

    assert "would summarise octocat/hello-world#5" in capsys.readouterr().out
    assert summaries.due(set()) == [THE_PR]
