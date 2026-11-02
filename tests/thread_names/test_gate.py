import fcntl
import json
import threading

from github_orchestrator.settings.fake import fake_settings
from github_orchestrator.terminal_sessions import Terminals
from github_orchestrator.terminal_sessions.fake import FakeTerminals
from github_orchestrator.thread_names import NameMigration
from github_orchestrator.wiring import thread_names_wiring, wire
from tests.conftest import fake_provider


def _migration(tmp_path, version="0.3.0") -> NameMigration:
    migration: NameMigration = wire(
        thread_names_wiring(fake_settings(tmp_path), version),
        fake_provider(Terminals, FakeTerminals())).get(NameMigration)
    return migration


def _marker(tmp_path):
    return fake_settings(tmp_path).layout_marker


def test_the_first_start_migrates_and_writes_a_marker_naming_the_version_that_wrote_it(tmp_path):
    migration = _migration(tmp_path, "0.3.0")

    assert not migration.migrated()
    migration.migrate()

    assert migration.migrated()
    assert json.loads(_marker(tmp_path).read_text())["written_by"] == "0.3.0"


def test_a_start_that_finds_the_marker_leaves_it_as_the_first_start_wrote_it(tmp_path):
    _migration(tmp_path, "0.3.0").migrate()

    _migration(tmp_path, "0.3.1").migrate()

    assert json.loads(_marker(tmp_path).read_text())["written_by"] == "0.3.0"


def test_a_start_waits_on_the_lock_while_another_process_migrates(tmp_path):
    lock_path = fake_settings(tmp_path).layout_lock
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    held = open(lock_path, "a")
    fcntl.flock(held, fcntl.LOCK_EX)
    waiting = threading.Thread(target=_migration(tmp_path).migrate)
    try:
        waiting.start()
        waiting.join(0.3)
        assert waiting.is_alive() and not _marker(tmp_path).exists()
    finally:
        held.close()
    waiting.join(5)

    assert not waiting.is_alive() and _marker(tmp_path).exists()
