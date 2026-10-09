import logging
import os

import pytest

from github_orchestrator.settings import Logs, Process
from github_orchestrator.wiring import LogsWiring, wire
from tests.settings.support import settings_read_from

LINE = "x" * 60


@pytest.fixture(autouse=True)
def _root_logger_restored():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
        if handler not in handlers:
            handler.close()
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)


def _logs(logs_dir, level="INFO", **limits) -> Logs:
    return wire(LogsWiring(logs_dir, level, **limits)).get(Logs)


def _record(message):
    return logging.LogRecord("t", logging.WARNING, __file__, 1, message, None, None)


def _handler():
    [handler] = logging.getLogger().handlers
    return handler


def test_each_process_writes_its_own_file_under_the_logs_dir(tmp_path):
    logs = _logs(tmp_path / "logs")
    paths = {process: logs.path(process) for process in Process}
    assert {path.parent for path in paths.values()} == {tmp_path / "logs"}
    assert len(set(paths.values())) == len(Process)


def test_configuring_a_process_logs_to_its_file_and_creates_the_folder(tmp_path):
    logs = _logs(tmp_path / "logs")
    logs.configure_logging(Process.PR_MANAGER)
    logging.getLogger("t").warning("hello")
    assert "hello" in logs.path(Process.PR_MANAGER).read_text()
    assert not logs.path(Process.WATCHER).exists()


def test_the_configured_level_comes_from_the_config(tmp_path):
    (tmp_path / "config.toml").write_text(
        'gh_account = "octocat"\nlog_level = "debug"\n'
        '[[repos]]\nrepo = "o/n"\nlocal_path = "/tmp/n"\n')
    settings = settings_read_from(tmp_path / "config.toml", tmp_path)
    _logs(settings.logs_dir, settings.config.log_level).configure_logging(Process.WATCHER)
    assert logging.getLogger().level == logging.DEBUG


def test_an_unknown_level_falls_back_to_info(tmp_path):
    _logs(tmp_path, "chatty").configure_logging(Process.WATCHER)
    assert logging.getLogger().level == logging.INFO


def test_configuring_again_replaces_the_handler(tmp_path):
    logs = _logs(tmp_path)
    logs.configure_logging(Process.WATCHER)
    first = _handler()
    logs.configure_logging(Process.PR_MANAGER)
    assert _handler() is not first
    first.close()


def test_a_log_over_its_limit_rotates_and_keeps_only_its_backups(tmp_path):
    logs = _logs(tmp_path, max_bytes=500, backup_count=2)
    logs.configure_logging(Process.WATCHER)
    for n in range(100):
        _handler().handle(_record(f"{n} {LINE}"))

    path = logs.path(Process.WATCHER)
    assert sorted(p.name for p in tmp_path.iterdir() if not p.name.endswith(".lock")) == [
        path.name, f"{path.name}.1", f"{path.name}.2"]
    assert "99 " in path.read_text()


def test_a_second_process_keeps_writing_the_live_file_after_the_first_rotates(tmp_path):
    first_logs = _logs(tmp_path, max_bytes=500, backup_count=3)
    first_logs.configure_logging(Process.PR_MANAGER)
    first = _handler()
    _logs(tmp_path, max_bytes=500, backup_count=3).configure_logging(Process.PR_MANAGER)
    second = _handler()
    try:
        second.handle(_record("second is open"))
        for n in range(20):
            first.handle(_record(f"{n} {LINE}"))
        second.handle(_record("second after the rotation"))
    finally:
        first.close()

    assert "second after the rotation" in first_logs.path(Process.PR_MANAGER).read_text()


def test_each_line_names_the_process_and_what_it_manages(tmp_path):
    logs = _logs(tmp_path)
    logs.configure_logging(Process.PR_MANAGER, context="acme/widgets#7")
    logging.getLogger("t").warning("hello")

    line = logs.path(Process.PR_MANAGER).read_text()
    assert f"[{os.getpid()} acme/widgets#7]" in line
    assert "hello" in line


def test_a_process_with_no_context_is_named_by_its_pid_alone(tmp_path):
    logs = _logs(tmp_path)
    logs.configure_logging(Process.WATCHER)
    logging.getLogger("t").warning("hello")

    assert f"[{os.getpid()}]" in logs.path(Process.WATCHER).read_text()


@pytest.mark.parametrize("scheduler", [Process.LAUNCHD])
def test_the_watcher_trims_an_oversized_scheduler_log_in_place_as_it_starts(
    scheduler, tmp_path,
):
    logs = _logs(tmp_path, max_bytes=500)
    path = logs.path(scheduler)
    path.write_text("old line\n" * 100)

    with open(path, "a") as held_by_the_scheduler:
        logs.configure_logging(Process.WATCHER)
        held_by_the_scheduler.write("written after the trim\n")

    assert path.read_text() == "written after the trim\n"
    assert path.with_name(f"{path.name}.1").read_text() == "old line\n" * 100


def test_a_scheduler_log_under_its_limit_is_left_alone(tmp_path):
    logs = _logs(tmp_path)
    path = logs.path(Process.LAUNCHD)
    path.write_text("short\n")

    logs.configure_logging(Process.WATCHER)

    assert path.read_text() == "short\n"
    assert not path.with_name(f"{path.name}.1").exists()


def test_only_the_watcher_trims_the_scheduler_logs(tmp_path):
    logs = _logs(tmp_path, max_bytes=500)
    path = logs.path(Process.LAUNCHD)
    path.write_text("old line\n" * 100)

    logs.configure_logging(Process.PR_MANAGER)

    assert path.read_text() == "old line\n" * 100
