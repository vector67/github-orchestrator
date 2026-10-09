from __future__ import annotations

import shutil
from pathlib import Path
from unittest import mock

import pytest

from tests.builders import a_pr
from tests.pr_event_queue.support import (
    ci_failed,
    disk_event_queue,
)
from tests.pr_manager.support import manager_over
from tests.settings.support import disk_holds


def test_dashboard_shows_on_hold_indicator_when_state_is_none(tmp_path, settings):
    disk_holds(settings.data_dir).set_on_hold(a_pr(1, "o/n"), True)
    manager = manager_over(settings, is_author=True, worktree=tmp_path)
    manager.event_queue.add(a_pr(1, "o/n"), ci_failed('tests'))
    manager.run()

    assert manager.board.panel.dashboard().on_hold is True


def test_enqueue_rmtree_race_does_not_leak_tmp(tmp_path):
    queues_dir = tmp_path / "queues"

    real_mkdir = Path.mkdir

    def mkdir_then_remove(self, *args, **kwargs):
        real_mkdir(self, *args, **kwargs)
        if "queues" in str(self):
            shutil.rmtree(self)

    with mock.patch.object(Path, "mkdir", mkdir_then_remove):
        with pytest.raises((OSError, FileNotFoundError)):
            disk_event_queue(queues_dir).add(a_pr(1, "org/repo"), ci_failed())

    if queues_dir.exists():
        leaked = list(queues_dir.rglob(".*.tmp"))
        assert leaked == [], f"tmp files leaked after rmtree race: {leaked}"
