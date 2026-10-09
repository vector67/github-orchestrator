import logging
import os
import sys
import tempfile
from pathlib import Path

import pytest

from github_orchestrator.domain import Repo
from github_orchestrator.pr_manager import __main__ as manager_main
from github_orchestrator.settings.fake import Settings
from github_orchestrator.wiring import make_container
from tests.pr_manager.scripted_terminal import ScriptEnded
from tests.pr_manager.support import manager_over

TEMP_ROOT = Path(tempfile.gettempdir())


def _process_settings():
    return make_container(os.environ, Path.home()).get(Settings)


def test_the_suite_isolates_the_orchestrator_data_dir():
    data_dir = _process_settings().data_dir
    assert data_dir.is_relative_to(TEMP_ROOT), data_dir


def test_the_suite_never_inherits_the_operators_config_file():
    settings = _process_settings()
    assert settings.config_path.is_relative_to(TEMP_ROOT), settings.config_path
    assert settings.config.gh_account == "octocat"
    assert set(settings.repos) == {Repo("octocat", "hello-world")}


def test_the_manager_entry_point_logs_inside_the_isolated_data_dir(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["m", "--repo", "o/n", "--pr", "1"])

    def isolated(env, home, managed):
        return manager_over(make_container(env, home).get(Settings)).container

    monkeypatch.setattr(manager_main, "make_container", isolated)
    with pytest.raises(ScriptEnded):
        manager_main.main()

    [log_file] = [
        Path(handler.baseFilename)
        for handler in logging.getLogger().handlers
        if hasattr(handler, "baseFilename")
    ]
    assert log_file.is_relative_to(TEMP_ROOT), log_file
