import logging
import os

import pytest

from github_orchestrator.pr_manager import ManagedPr
from github_orchestrator.pr_manager import __main__ as manager_main
from github_orchestrator.settings import Process
from github_orchestrator.settings.fake import FakeLogs
from tests.builders import a_pr
from tests.pr_manager.scripted_terminal import ScriptEnded
from tests.pr_manager.support import manager_over
from tests.settings.support import settings_read_from

CONFIGURED = (
    'gh_account = "octocat"\n'
    '[[repos]]\n'
    'repo = "octocat/hello-world"\n'
    'local_path = "/tmp/hello"\n'
)


def _prepared(monkeypatch, tmp_path, *argv, config=CONFIGURED):
    if config is not None:
        (tmp_path / "config.toml").write_text(config)
    logs = FakeLogs()
    manager = manager_over(settings_read_from(tmp_path / "config.toml", tmp_path), logs=logs)
    handed = []

    def container_for(env, home, managed):
        handed.append(managed)
        return manager.container

    monkeypatch.setattr("sys.argv", ["pr_manager", "--repo", "o/n", "--pr", "1", *argv])
    monkeypatch.setattr(manager_main, "make_container", container_for)
    return manager, handed, logs


def _main():
    with pytest.raises(BaseException) as ended:
        manager_main.main()
    return ended.value


def test_main_runs_the_manager_for_the_pr_it_was_started_for(monkeypatch, tmp_path):
    _, handed, _ = _prepared(monkeypatch, tmp_path)
    assert isinstance(_main(), ScriptEnded)
    assert handed == [ManagedPr(pr=a_pr(1, "o/n"), worktree=os.getcwd())]


def test_main_logs_to_the_pr_managers_log_naming_its_pr(monkeypatch, tmp_path):
    _, _, logs = _prepared(monkeypatch, tmp_path)
    _main()
    assert logs.configured == [(Process.PR_MANAGER, "o/n#1")]


def test_a_broken_config_exits_before_the_manager_runs(monkeypatch, tmp_path, capsys):
    _prepared(monkeypatch, tmp_path, config="gh_account = [\n")
    ended = _main()
    assert isinstance(ended, SystemExit) and ended.code == 2
    assert "config.toml" in capsys.readouterr().err


def test_a_broken_config_is_written_to_the_pr_managers_log(monkeypatch, tmp_path, caplog):
    _, _, logs = _prepared(monkeypatch, tmp_path, config="unknown_key = 1\n" + CONFIGURED)

    with caplog.at_level(logging.ERROR):
        _main()

    assert logs.configured == [(Process.PR_MANAGER, "o/n#1")]
    assert "unknown key 'unknown_key'" in caplog.text
    assert "o/n#1" in caplog.text
