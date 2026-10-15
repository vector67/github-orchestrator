import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.domain import Pr
from github_orchestrator.pr_summaries import PrSummaries
from github_orchestrator.wiring import Part, PrSummariesWiring, SummaryLaneWiring, wire
from tests.board_api.support import THE_PR, client_for, followed
from tests.conftest import clocks_of, fake_provider
from tests.conversation.support import at

FAKE_PLUGIN = Path(__file__).parents[1] / "pr_summaries" / "fake_plugin.py"
WITNESSES = ["requested", "claimed", "implementation", "tests", "why", "alignment"]
STARTED = "2026-08-28T10:00:00+00:00"


class HeadsAt:
    def __init__(self, head: str | None) -> None:
        self._head = head

    def facts(self, pr: Pr) -> SimpleNamespace:
        return SimpleNamespace(head_sha=self._head)


def run_now(work: Callable[[], None]) -> None:
    work()


class Held:
    def __init__(self) -> None:
        self.work: list[Callable[[], None]] = []

    def __call__(self, work: Callable[[], None]) -> None:
        self.work.append(work)

    def finish(self) -> None:
        while self.work:
            self.work.pop()()


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _three_commits(root: Path) -> tuple[str, str, str]:
    clone = root / "repo"
    clone.mkdir()
    _git(clone, "init", "-q", "-b", "main")
    _git(clone, "config", "user.email", "t@example.com")
    _git(clone, "config", "user.name", "T")
    shas = []
    for message in ("one", "two", "three"):
        _git(clone, "commit", "-q", "--allow-empty", "-m", message)
        shas.append(_git(clone, "rev-parse", "HEAD"))
    return shas[0], shas[1], shas[2]


def summary_parts(tmp_path: Path, behaviour: str = "clean", *, read: str | None = None,
                  run_in: Callable[[Callable[[], None]], None] = run_now,
                  agents_enabled: bool = True) -> list[Part]:
    clone = tmp_path / "repo"
    clone.mkdir(exist_ok=True)
    return [PrSummariesWiring(tmp_path / "summaries"),
            SummaryLaneWiring(tmp_path / "config.toml", {THE_PR.repo: clone}, agents_enabled,
                              plugin=(sys.executable, str(FAKE_PLUGIN), "--behaviour", behaviour),
                              run_in=run_in),
            fake_provider(ChangeDetection, HeadsAt(read))]


def wanted_on(tmp_path: Path) -> None:
    summaries: PrSummaries = wire(PrSummariesWiring(tmp_path / "summaries"),
                                  clocks_of(at("2026-08-28T09:00:00Z"))).get(PrSummaries)
    summaries.want(THE_PR)


def folder(tmp_path: Path) -> Path:
    return tmp_path / "summaries" / "acme" / "widgets" / "54"


def summarised(client: TestClient, verb: str = "summarise", tag: str | None = None):
    etag = tag if tag is not None else client.get("/api/summary").json()["etag"]
    return client.post(f"/api/summary/operations:{verb}", headers={"If-Match": etag})


def test_a_pr_never_summarised_serves_a_summary_with_nothing_stored_and_nothing_running(tmp_path):
    client = client_for(summaries=summary_parts(tmp_path))

    answer = client.get("/api/summary")

    assert answer.status_code == 200
    served = answer.json()
    assert {name: value for name, value in served.items() if name != "etag"} == {
        "repo": "acme/widgets", "number": 54, "head_sha": None, "wanted": None,
        "answered": None, "started": None, "finished": None, "exit_status": None,
        "stderr": None, "markdown": None, "mismatches": None, "running": False,
        "since": None, "witnesses": [], "behind": None}


def test_a_finished_summary_serves_what_was_stored_and_how_many_commits_the_head_has_moved_since(
        tmp_path, git_template):
    first, _, third = git_template(_three_commits)
    wanted_on(tmp_path)
    client = client_for(head_sha=third, summaries=summary_parts(tmp_path, read=first))
    summarised(client)

    served = client.get("/api/summary").json()

    assert {name: value for name, value in served.items() if name != "etag"} == {
        "repo": "acme/widgets", "number": 54, "head_sha": first,
        "wanted": "2026-08-28T09:00:00+00:00", "answered": "2026-08-28T09:00:00+00:00",
        "started": STARTED, "finished": STARTED, "exit_status": 0, "stderr": "",
        "markdown": "# Summary\n\nIt does what it says.\n", "mismatches": 2,
        "running": False, "since": None, "witnesses": [], "behind": 2}


def test_a_run_that_needs_the_github_api_serves_its_exit_status_and_the_plugins_reason(tmp_path):
    client = client_for(summaries=summary_parts(tmp_path, "needs-api"))
    summarised(client)

    served = client.get("/api/summary").json()

    assert served["exit_status"] == 3
    assert "about 31 API calls" in served["stderr"]
    assert (served["markdown"], served["mismatches"]) == (None, None)


def test_a_running_summary_serves_when_it_started_and_a_flag_for_each_witness(tmp_path):
    held = Held()
    client = client_for(summaries=summary_parts(tmp_path, run_in=held))
    summarised(client)
    (folder(tmp_path) / "claimed").mkdir(parents=True)
    (folder(tmp_path) / "claimed" / "output.json").write_text("{}")

    served = client.get("/api/summary").json()

    held.finish()
    assert (served["running"], served["since"]) == (True, STARTED)
    assert served["witnesses"] == [{"witness": witness, "done": witness == "claimed"}
                                   for witness in WITNESSES]


def test_summarise_starts_a_run_and_answers_the_summary_running(tmp_path):
    held = Held()
    client = client_for(summaries=summary_parts(tmp_path, run_in=held))

    answer = summarised(client)

    held.finish()
    assert answer.status_code == 202
    assert answer.json()["running"] is True
    assert answer.headers["Location"] == "/pr/acme/widgets/54/api/summary"
    assert followed(client, answer).json()["running"] is False


def test_each_operation_says_whether_the_run_reads_over_the_github_api(tmp_path):
    client = client_for(summaries=summary_parts(tmp_path))

    summarised(client, "summarise")
    plain = json.loads((folder(tmp_path) / "call.json").read_text())["use_github_api"]
    summarised(client, "summarise-with-github-api")
    over_the_api = json.loads((folder(tmp_path) / "call.json").read_text())["use_github_api"]

    assert (plain, over_the_api) == (False, True)


def test_summarise_while_another_summary_runs_is_refused_with_the_lanes_reason(tmp_path):
    held = Held()
    client = client_for(summaries=summary_parts(tmp_path, run_in=held))
    summarised(client)

    answer = summarised(client)

    held.finish()
    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "summary-refused"
    assert answer.json()["errors"][0]["detail"] == "another summary is running"


def test_summarise_with_agents_disabled_is_refused_and_runs_nothing(tmp_path):
    client = client_for(summaries=summary_parts(tmp_path, agents_enabled=False))

    answer = summarised(client, "summarise-with-github-api")

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "summary-refused"
    assert not folder(tmp_path).exists()


def test_summarise_with_a_tag_from_before_the_summary_moved_is_refused(tmp_path):
    client = client_for(summaries=summary_parts(tmp_path))
    before = client.get("/api/summary").json()["etag"]
    summarised(client)

    answer = summarised(client, tag=before)

    assert answer.status_code == 412
    assert answer.json()["errors"][0]["code"] == "precondition-failed"
    assert client.get("/api/summary").json()["etag"] != before


def test_summarise_without_the_precondition_is_malformed(tmp_path):
    client = client_for(summaries=summary_parts(tmp_path))

    answer = client.post("/api/summary/operations:summarise")

    assert answer.status_code == 400
    assert answer.json()["errors"][0]["code"] == "malformed-request"
    assert not folder(tmp_path).exists()
