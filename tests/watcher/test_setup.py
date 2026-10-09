import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from github_orchestrator.agent_runs import Agent
from github_orchestrator.board_api.fake import FakeHoldings
from github_orchestrator.board_api.interface import SetupDesk, TourMarker
from github_orchestrator.domain import HubState, Repo
from github_orchestrator.github import PullRequestState
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import fake_settings
from github_orchestrator.watcher import Watcher
from tests.board_api.support import HUB_PORT, InProcess, hub_on
from tests.builders import a_pr
from tests.settings.support import disk_holds
from tests.watcher.support import watcher_container

ME = "octocat"
WIDGETS = Repo.parse("acme/widgets")
GADGETS = Repo.parse("acme/gadgets")
HELLO = Repo.parse("octocat/hello-world")
NOW = datetime(2026, 10, 9, 8, 30, 5, tzinfo=timezone.utc)
OPTIONS = {"agent_model": "opus", "agents_enabled": False, "max_thread_runs": 2}


@dataclass
class Clock:
    now: datetime = NOW

    def __call__(self) -> datetime:
        return self.now


@dataclass
class World:
    tmp_path: Path
    github: FakeGitHub
    processes: FakePrProcesses
    clock: Clock
    clones: dict[Path, Repo] = field(default_factory=dict)
    client: TestClient | None = None
    watcher: Watcher | None = None

    @property
    def config(self) -> Path:
        return self.tmp_path / "config.toml"

    @property
    def home(self) -> Path:
        return self.tmp_path / "home"

    @property
    def web(self) -> TestClient:
        assert self.client is not None
        return self.client

    def clone_problem(self, repo: Repo, path: Path) -> str | None:
        found = self.clones.get(path)
        if found == repo:
            return None
        return f"{path} is not a git repository" if found is None else (
            f"{path}'s origin is {found}, not {repo}")

    def left(self) -> bool:
        assert self.watcher is not None
        try:
            self.watcher.wait_in(HubState.SETUP, lambda: HubState.SETUP)
        except AssertionError:
            return False
        return True

    def read(self) -> dict:
        return tomllib.loads(self.config.read_text())

    def put(self, body, *, etag=None, **headers):
        tag = etag if etag is not None else self.web.get("/api/setup").json()["etag"]
        return self.web.put("/api/setup", json=body, headers={"If-Match": tag, **headers})


WATCHING = (f'gh_account = "{ME}"\n\n[[repos]]\nrepo = "acme/widgets"\n'
            'local_path = "~/repositories/widgets"\nnew_worktree_command = "cp .env ."\n')


@pytest.fixture
def world(tmp_path):
    github = FakeGitHub(account=ME)
    github.listed = [GADGETS, WIDGETS, HELLO]
    github.read_only.add(HELLO)
    github.repos.update({WIDGETS, GADGETS, HELLO})
    built = World(tmp_path, github, FakePrProcesses(), Clock())
    built.home.mkdir()
    return built


def serve(world: World, config: str | None = None, *, state=HubState.SETUP,
          agent: Agent = Agent.CLAUDE) -> World:
    if config is not None:
        world.config.write_text(config)
    settings = fake_settings(world.tmp_path, agent=agent)
    container = watcher_container(
        settings, github=world.github, pr_processes=world.processes, clock=world.clock,
        home=world.home, clone_problem=world.clone_problem,
        requirements=lambda: [("gh", None), ("claude", "install claude")])
    world.watcher = container.get(Watcher)
    listening = InProcess()
    hub = hub_on(listening, setup=container.get(SetupDesk), tour=container.get(TourMarker))
    url = hub.start(HUB_PORT, FakeHoldings(), state)
    world.client = TestClient(listening.app, base_url=url)
    return world


def request(*repos, account=ME, **options):
    return {"gh_account": account,
            "repos": [{"repo": repo, "local_path": path, "new_worktree_command": command}
                      for repo, path, command in repos],
            "options": {**OPTIONS, **options}}


def test_setup_from_no_config_says_setup_with_nothing_chosen_and_gh_s_active_account(world):
    answer = serve(world).web.get("/api/setup")

    body = answer.json()
    assert answer.status_code == 200
    assert answer.headers["ETag"]
    assert (body["state"], body["gh_account"], body["repos"], body["active_account"]) == (
        "setup", None, [], ME)
    assert body["config_path"] == str(world.config)
    assert body["agent_name"] == "Claude"
    assert body["options"] == {"agent_model": "opus", "agents_enabled": True,
                               "max_thread_runs": 4}
    assert body["requirements"] == [{"program": "gh", "fix": None},
                                    {"program": "claude", "fix": "install claude"}]


def test_setup_for_a_codex_instance_offers_codexs_model_under_its_name(world):
    body = serve(world, 'agent = "codex"\n', agent=Agent.CODEX).web.get("/api/setup").json()

    assert (body["agent_name"], body["options"]["agent_model"]) == ("Codex", "gpt-6-luna")


def test_setup_of_a_watched_config_lists_its_account_and_repos_and_writes_nothing(world):
    serve(world, WATCHING, state=HubState.WATCHING)
    before = (world.config.read_bytes(), world.config.stat().st_mtime_ns)

    body = world.web.get("/api/setup").json()

    assert (body["state"], body["gh_account"]) == ("watching", ME)
    assert body["repos"] == [{"repo": "acme/widgets", "local_path": "~/repositories/widgets",
                              "new_worktree_command": "cp .env ."}]
    assert (world.config.read_bytes(), world.config.stat().st_mtime_ns) == before


def test_an_account_gh_holds_a_token_for_answers_its_scopes(world):
    world.github.granted[ME] = ("read:org", "repo")

    answer = serve(world).web.get(f"/api/setup/accounts/{ME}")

    assert answer.json() == {"login": ME, "scopes": ["read:org", "repo"]}


def test_an_account_gh_holds_no_token_for_is_refused_with_the_login_to_run(world):
    answer = serve(world).web.get("/api/setup/accounts/nobody")

    assert answer.status_code == 404
    [error] = answer.json()["errors"]
    assert error["code"] == "no-gh-token"
    assert "gh auth login" in error["detail"]


def test_the_account_s_repos_come_with_what_it_may_do_and_whether_it_has_prs_there(world):
    world.github.add_pr(a_pr(1, "acme/widgets"), PullRequestState(author=ME))

    answer = serve(world).web.get(f"/api/setup/accounts/{ME}/repos")

    assert answer.json() == {"login": ME, "repos": [
        {"repo": "acme/gadgets", "can_push": True, "has_my_prs": False, "default_branch": "main"},
        {"repo": "acme/widgets", "can_push": True, "has_my_prs": True, "default_branch": "main"},
        {"repo": "octocat/hello-world", "can_push": False, "has_my_prs": False,
         "default_branch": "main"}]}


def test_the_account_s_repos_are_kept_for_a_minute(world):
    serve(world)
    world.web.get(f"/api/setup/accounts/{ME}/repos")
    world.github.listed = [HELLO]

    within = world.web.get(f"/api/setup/accounts/{ME}/repos").json()["repos"]
    world.clock.now += timedelta(seconds=61)
    after = world.web.get(f"/api/setup/accounts/{ME}/repos").json()["repos"]

    assert [one["repo"] for one in within] == ["acme/gadgets", "acme/widgets",
                                               "octocat/hello-world"]
    assert [one["repo"] for one in after] == ["octocat/hello-world"]


def test_a_repo_typed_by_name_is_looked_up_for_the_login(world):
    answer = serve(world).web.get("/api/setup/repos/octocat/hello-world", params={"login": ME})

    assert answer.json() == {"repo": "octocat/hello-world", "can_push": False,
                             "has_my_prs": False, "default_branch": "main"}


def test_a_repo_typed_by_name_the_login_cannot_see_is_refused(world):
    answer = serve(world).web.get("/api/setup/repos/acme/typo", params={"login": ME})

    assert answer.status_code == 404
    [error] = answer.json()["errors"]
    assert error["code"] == "repo-not-visible"
    assert "acme/typo" in error["detail"]


def test_a_clone_is_suggested_under_the_repositories_folder_until_one_is_there(world):
    serve(world)

    nothing = world.web.get("/api/setup/clones/acme/gadgets").json()
    (world.home / "repositories" / "gadgets").mkdir(parents=True)
    something = world.web.get("/api/setup/clones/acme/gadgets").json()
    world.clones[world.home / "repositories" / "gadgets"] = GADGETS
    a_clone = world.web.get("/api/setup/clones/acme/gadgets").json()

    assert nothing == {"repo": "acme/gadgets", "path": "~/repositories/gadgets",
                       "exists": False, "is_clone": False}
    assert (something["exists"], something["is_clone"]) == (True, False)
    assert (a_clone["exists"], a_clone["is_clone"]) == (True, True)


def test_a_watched_repo_s_clone_is_where_the_config_says(world):
    serve(world, 'gh_account = "octocat"\n\n[[repos]]\nrepo = "acme/widgets"\n'
                 'local_path = "/src/widgets"\n', state=HubState.WATCHING)

    assert world.web.get("/api/setup/clones/acme/widgets").json()["path"] == "/src/widgets"


def test_starting_to_watch_clones_what_is_missing_writes_the_config_and_restarts(world):
    serve(world)

    answer = world.put(request(("acme/widgets", "~/repositories/widgets", "cp .env .")))

    assert answer.status_code == 202
    operation = answer.json()
    assert answer.headers["Location"] == f"/api/setup/operations/{operation['id']}"
    assert world.github.cloned == [(WIDGETS, world.home / "repositories" / "widgets")]
    assert world.read() == {"gh_account": ME, **OPTIONS, "repos": [
        {"repo": "acme/widgets", "local_path": "~/repositories/widgets",
         "new_worktree_command": "cp .env ."}]}
    read = world.web.get(f"/api/setup/operations/{operation['id']}").json()
    assert read["state"] == "restarting"
    assert read["clones"] == [{"repo": "acme/widgets",
                               "path": str(world.home / "repositories" / "widgets"),
                               "state": "cloned", "error": None}]
    assert world.left()


def test_the_first_setup_that_starts_watching_makes_the_board_s_tour_due_until_seen(world):
    serve(world)

    world.put(request(("acme/widgets", "~/repositories/widgets", "")))
    due = world.web.get("/api/tour").json()
    world.web.post("/api/tour:seen")

    assert (due, world.web.get("/api/tour").json()) == ({"due": True}, {"due": False})


def test_changing_the_repos_of_a_watched_config_leaves_the_tour_as_it_was(world):
    serve(world, WATCHING, state=HubState.WATCHING)

    world.put(request(("acme/gadgets", "~/repositories/gadgets", "")))

    assert world.web.get("/api/tour").json() == {"due": False}


def test_a_clone_already_there_is_kept_and_not_cloned_again(world):
    there = world.home / "repositories" / "widgets"
    there.mkdir(parents=True)
    world.clones[there] = WIDGETS
    serve(world)

    operation = world.put(request(("acme/widgets", str(there), ""))).json()

    assert world.github.cloned == []
    assert [clone["state"] for clone in operation["clones"]] == ["found"]


def test_a_clone_that_fails_leaves_the_config_alone_and_the_watcher_running(world):
    blocked = world.tmp_path / "blocked"
    blocked.write_text("a file where a folder should be")
    serve(world)

    operation = world.put(request(("acme/widgets", str(blocked / "widgets"), ""))).json()

    assert operation["state"] == "failed"
    assert operation["clones"][0]["state"] == "failed"
    assert not world.config.exists()
    assert not world.left()


def test_a_write_against_a_setup_read_since_changed_is_refused_and_writes_nothing(world):
    serve(world)

    answer = world.put(request(("acme/widgets", "~/repositories/widgets", "")), etag='"stale"')

    assert answer.status_code == 412
    assert answer.json()["errors"][0]["code"] == "precondition-failed"
    assert not world.config.exists()


def test_a_write_names_each_field_it_refuses_and_writes_and_clones_nothing(world):
    there = world.home / "repositories" / "gadgets"
    there.mkdir(parents=True)
    serve(world)

    answer = world.put({**request(("acme/typo", "~/repositories/typo", ""),
                                  ("acme/gadgets", str(there), ""),
                                  ("not-a-repo", "~/repositories/x", "")),
                        "hub_port": 8731})

    assert answer.status_code == 422
    refused = {error["field"]: error["detail"] for error in answer.json()["errors"]}
    assert set(refused) == {"repos[0].repo", "repos[1].local_path", "repos[2].repo", "config"}
    assert "acme/typo" in refused["repos[0].repo"]
    assert "not a git repository" in refused["repos[1].local_path"]
    assert "8730-8829" in refused["config"]
    assert {error["code"] for error in answer.json()["errors"]} == {"setup-refused"}
    assert (world.config.exists(), world.github.cloned) == (False, [])


def test_a_write_for_an_account_gh_holds_no_token_for_is_refused_on_the_account(world):
    serve(world)

    answer = world.put(request(("acme/widgets", "~/repositories/widgets", ""),
                               account="nobody"))

    assert answer.status_code == 422
    assert [error["field"] for error in answer.json()["errors"]] == ["gh_account"]


def test_removing_a_repo_archives_its_state_closes_its_managers_and_lists_its_worktrees(world):
    widgets_clone = world.tmp_path / "widgets"
    gadgets_clone = world.tmp_path / "gadgets"
    for clone, repo in ((widgets_clone, WIDGETS), (gadgets_clone, GADGETS)):
        clone.mkdir()
        world.clones[clone] = repo
    serve(world, f'gh_account = "{ME}"\n\n[[repos]]\nrepo = "acme/widgets"\n'
                 f'local_path = "{widgets_clone}"\n\n[[repos]]\nrepo = "acme/gadgets"\n'
                 f'local_path = "{gadgets_clone}"\n', state=HubState.WATCHING)
    worktree = world.tmp_path / "gadgets-pr-5"
    worktree.mkdir()
    world.processes.open(a_pr(5, "acme/gadgets"), worktree)
    world.processes.open(a_pr(7, "acme/widgets"), widgets_clone)
    disk_holds(world.tmp_path).set_on_hold(a_pr(5, "acme/gadgets"), True)

    operation = world.put(request(("acme/widgets", str(widgets_clone), ""))).json()

    archive = world.tmp_path / "archive" / "20261009-083005"
    assert operation["state"] == "restarting"
    assert str(archive / "on_hold" / "acme" / "gadgets") in operation["archived"]
    assert (archive / "on_hold" / "acme" / "gadgets" / "5.flag").exists()
    assert operation["kept_worktrees"] == [str(worktree)]
    assert set(world.processes.managers) == {a_pr(7, "acme/widgets")}
    assert [entry["repo"] for entry in world.read()["repos"]] == ["acme/widgets"]


def test_a_setup_write_from_another_site_s_page_is_refused_and_writes_nothing(world):
    serve(world)

    answer = world.put(request(("acme/widgets", "~/repositories/widgets", "")),
                       Origin="https://evil.example")

    assert answer.status_code == 403
    assert answer.json()["errors"][0]["code"] == "foreign-origin"
    assert (world.config.exists(), world.github.cloned) == (False, [])


def test_a_broken_config_is_moved_aside_and_the_watcher_restarts_into_setup(world):
    serve(world, "gh_account = \n", state=HubState.BROKEN)

    answer = world.web.post("/api/setup:move-aside")

    assert answer.status_code == 202
    moved = Path(answer.json()["moved_to"])
    assert moved.name == "config.toml.broken-20261009-083005"
    assert (moved.exists(), world.config.exists()) == (True, False)
    assert world.left()


def test_a_config_that_parses_is_not_moved_aside(world):
    serve(world, WATCHING, state=HubState.WATCHING)

    answer = world.web.post("/api/setup:move-aside")

    assert answer.status_code == 409
    assert answer.json()["errors"][0]["code"] == "not-broken"
    assert world.config.exists()


def test_a_broken_config_is_not_written_over(world):
    serve(world, "gh_account = \n", state=HubState.BROKEN)

    answer = world.put(request(("acme/widgets", "~/repositories/widgets", "")))

    assert answer.status_code == 422
    assert [error["field"] for error in answer.json()["errors"]] == ["config"]
    assert world.config.read_text() == "gh_account = \n"
