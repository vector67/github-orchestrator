import fcntl
import logging

import pytest

from github_orchestrator.board_api.fake import FakeHub
from github_orchestrator.desktop.fake import FakeDesktop
from github_orchestrator.domain import HubState, Repo
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.settings import Process
from github_orchestrator.settings.fake import FakeLogs, fake_settings
from github_orchestrator.watcher import __main__ as watcher_main
from tests.settings.support import settings_read_from
from tests.watcher.support import watcher_container

CONFIGURED = (
    'gh_account = "octocat"\n'
    '[[repos]]\n'
    'repo = "octocat/hello-world"\n'
    'local_path = "/tmp/hello"\n'
)


class Searches(FakeGitHub):
    def __init__(self, repo, error=None):
        super().__init__()
        self.repos.add(Repo.parse(repo))
        self.searched = []
        self._error = error

    def search(self, repo, whose):
        self.searched.append(repo)
        if self._error is not None:
            raise self._error
        return super().search(repo, whose)


def _prepared(monkeypatch, tmp_path, argv, *, config=CONFIGURED, error=None, desktop=None,
              hub=None, sleep=None):
    if config is not None:
        (tmp_path / "config.toml").write_text(config)
    settings = settings_read_from(tmp_path / "config.toml", tmp_path)
    github = Searches("octocat/hello-world", error)
    logs = FakeLogs()
    desktop = desktop or FakeDesktop()
    naps = {} if sleep is None else {"sleep": sleep}

    def container(env, home, *, dry_run):
        return watcher_container(settings, github=github, desktop=desktop, logs=logs,
                                 dry_run=dry_run, hub=hub, **naps)

    monkeypatch.setattr("sys.argv", ["watcher", *argv])
    monkeypatch.setattr(watcher_main, "make_container", container)
    return github, logs


def _held(path):
    lock = open(path, "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return lock


class Edits:
    def __init__(self, path, *bodies):
        self.path = path
        self.bodies = list(bodies)

    def __call__(self, seconds):
        if not self.bodies:
            raise AssertionError("the hub kept waiting after the config was set up")
        body = self.bodies.pop(0)
        if body is None:
            self.path.unlink(missing_ok=True)
        else:
            self.path.write_text(body)


@pytest.mark.parametrize(("config", "state"), [
    (None, HubState.SETUP),
    ('gh_account = "octocat"\n', HubState.SETUP),
    ("unknown_key = 1\n" + CONFIGURED, HubState.BROKEN),
])
def test_a_resident_watcher_without_a_complete_config_serves_the_hub_and_polls_nothing(
    tmp_path, monkeypatch, config, state,
):
    hub = FakeHub()
    github, _ = _prepared(monkeypatch, tmp_path, ["--loop"], config=config, hub=hub,
                          sleep=Edits(tmp_path / "config.toml", config, CONFIGURED))

    watcher_main.main()

    assert hub.states == [state]
    assert github.searched == []


def test_the_hub_stops_when_the_config_is_set_up_so_the_service_starts_the_watcher_again(
    tmp_path, monkeypatch,
):
    hub = FakeHub()
    _prepared(monkeypatch, tmp_path, ["--loop"], config=None, hub=hub,
              sleep=Edits(tmp_path / "config.toml", CONFIGURED))

    watcher_main.main()

    assert hub.port is None


def test_a_broken_config_moved_aside_drops_the_hub_into_setup_by_a_restart(tmp_path, monkeypatch):
    hub = FakeHub()
    _prepared(monkeypatch, tmp_path, ["--loop"], config="unknown_key = 1\n" + CONFIGURED,
              hub=hub, sleep=Edits(tmp_path / "config.toml", None))

    watcher_main.main()

    assert (hub.states, hub.port) == ([HubState.BROKEN], None)


def test_a_resident_watcher_without_a_complete_config_takes_the_lock_first(
    tmp_path, monkeypatch, capsys,
):
    hub = FakeHub()
    _prepared(monkeypatch, tmp_path, ["--loop"], config=None, hub=hub)
    lock = _held(fake_settings(tmp_path).watcher_lock)
    try:
        with pytest.raises(SystemExit) as excinfo:
            watcher_main.main()
    finally:
        lock.close()

    assert excinfo.value.code == 0
    assert hub.states == []


@pytest.mark.parametrize(("config", "said"), [
    (None, "does not exist"),
    ("unknown_key = 1\n" + CONFIGURED, "unknown key 'unknown_key'"),
])
def test_one_cycle_without_a_complete_config_fails_like_a_failed_cycle(
    tmp_path, monkeypatch, capsys, config, said,
):
    github, _ = _prepared(monkeypatch, tmp_path, [], config=config)

    with pytest.raises(SystemExit) as excinfo:
        watcher_main.main()

    assert excinfo.value.code == 1
    assert said in capsys.readouterr().err
    assert github.searched == []


def test_a_config_that_is_not_watching_is_written_to_the_watcher_log(
    tmp_path, monkeypatch, caplog,
):
    _, logs = _prepared(monkeypatch, tmp_path, [],
                        config="unknown_key = 1\n" + CONFIGURED)

    with caplog.at_level(logging.WARNING), pytest.raises(SystemExit):
        watcher_main.main()

    assert logs.configured == [(Process.WATCHER, "")]
    assert "unknown key 'unknown_key'" in caplog.text


def test_failure_prints_the_error_and_the_log_path_to_stderr(tmp_path, monkeypatch, capsys):
    _prepared(monkeypatch, tmp_path, [],
              error=RuntimeError("gh search prs failed (exit 1): gh: Not Found"))

    with pytest.raises(SystemExit) as excinfo:
        watcher_main.main()

    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "gh: Not Found" in err
    assert str(FakeLogs().path(Process.WATCHER)) in err


def test_each_cycle_writes_its_summary_to_the_log(tmp_path, monkeypatch, caplog):
    _prepared(monkeypatch, tmp_path, [])

    with caplog.at_level(logging.INFO):
        watcher_main.main()

    assert "Polled 0 PRs, 0 events queued, 0 torn down" in caplog.text


def test_dry_run_does_not_take_the_watcher_lock(tmp_path, monkeypatch, capsys):
    github, _ = _prepared(monkeypatch, tmp_path, ["--dry-run"])
    lock = _held(fake_settings(tmp_path).watcher_lock)
    try:
        watcher_main.main()
    finally:
        lock.close()

    assert len(github.searched) == 3
    out = capsys.readouterr().out
    assert "[dry-run] found 0 authored, 0 to review, 0 mentioning you" in out
    assert "Polled 0 PRs, 0 events queued, 0 torn down" in out
    assert not (tmp_path / "watcher.heartbeat").exists()


def test_a_real_run_still_refuses_a_second_instance(tmp_path, monkeypatch, capsys):
    github, _ = _prepared(monkeypatch, tmp_path, [])
    lock = _held(fake_settings(tmp_path).watcher_lock)
    try:
        with pytest.raises(SystemExit) as excinfo:
            watcher_main.main()
    finally:
        lock.close()

    assert excinfo.value.code == 0
    assert "Another watcher instance is running" in capsys.readouterr().out
    assert github.searched == []
    assert not (tmp_path / "watcher.heartbeat").exists()


def test_ctrl_c_ends_a_resident_watcher_without_a_traceback(tmp_path, monkeypatch):
    _prepared(monkeypatch, tmp_path, ["--loop"], error=KeyboardInterrupt())

    watcher_main.main()
