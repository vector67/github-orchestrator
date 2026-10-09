import os
import pickle
import selectors
import shutil
import signal
import struct
import tempfile
import threading
import traceback
import warnings
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from _pytest._io import TerminalWriter
from _pytest.terminal import TerminalReporter

_FRAME = struct.Struct("!I")
_SPAN = struct.Struct("!II")
_SECONDS = "forked_run/seconds"
_UNTIMED = 0.01


def _spans(seconds: list[float], forks: int) -> Iterator[tuple[int, int]]:
    start = 0
    left = sum(seconds)
    while start < len(seconds):
        share = left / (forks * 3)
        end = start + 1
        taken = seconds[start]
        while end < len(seconds) and taken + seconds[end] <= share:
            taken += seconds[end]
            end += 1
        yield start, end
        left -= taken
        start = end


def _file_of(item: pytest.Item) -> str:
    return item.nodeid.split("::", 1)[0]


def _recorded(config: pytest.Config) -> dict[str, float]:
    cache = getattr(config, "cache", None)
    if cache is None:
        return {}
    seconds: dict[str, float] = cache.get(_SECONDS, {})
    return seconds


def _heaviest_files_first(items: list[pytest.Item], seconds: dict[str, float]) -> list[pytest.Item]:
    by_file: dict[str, list[pytest.Item]] = {}
    for item in items:
        by_file.setdefault(_file_of(item), []).append(item)
    weight = {name: sum(seconds.get(item.nodeid, _UNTIMED) for item in tests)
              for name, tests in by_file.items()}
    return [item for name in sorted(by_file, key=lambda name: -weight[name]) for item in by_file[name]]


def _remember(config: pytest.Config, seconds: dict[str, float]) -> None:
    cache = getattr(config, "cache", None)
    if cache is not None and seconds:
        cache.set(_SECONDS, {**_recorded(config), **seconds})


def temp_paths(config: pytest.Config) -> pytest.TempPathFactory:
    factory: pytest.TempPathFactory = getattr(config, "_tmp_path_factory")
    return factory


def _send(fd: int, *message: Any) -> None:
    body = pickle.dumps(message)
    view = memoryview(_FRAME.pack(len(body)) + body)
    while view:
        view = view[os.write(fd, view):]


def _read_exactly(fd: int, size: int) -> bytes | None:
    data = b""
    while len(data) < size:
        more = os.read(fd, size - len(data))
        if not more:
            return None
        data += more
    return data


def _portable(warning: warnings.WarningMessage) -> tuple[Any, ...]:
    message: Warning | str = warning.message
    try:
        pickle.dumps(message)
    except Exception:
        message = str(message)
    category = warning.category if not isinstance(message, str) else UserWarning
    return message, category, warning.filename, warning.lineno, None, warning.line


class _Child:
    def __init__(self, config: pytest.Config, results: int) -> None:
        self.config = config
        self.results = results

    def pytest_runtest_logstart(self, nodeid: str, location: tuple[str, int | None, str]) -> None:
        _send(self.results, "logstart", nodeid, location)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        _send(self.results, "logreport", self.config.hook.pytest_report_to_serializable(
            config=self.config, report=report))

    def pytest_runtest_logfinish(self, nodeid: str, location: tuple[str, int | None, str]) -> None:
        _send(self.results, "logfinish", nodeid, location)

    def pytest_warning_recorded(self, warning_message: warnings.WarningMessage, when: str,
                                nodeid: str, location: tuple[str, int, str] | None) -> None:
        _send(self.results, "warning", _portable(warning_message), when, nodeid, location)


def _items_to_run(session: pytest.Session, work: int) -> Iterator[pytest.Item]:
    while (span := _read_exactly(work, _SPAN.size)) is not None:
        start, end = _SPAN.unpack(span)
        yield from session.items[start:end]


def _run_child(session: pytest.Session, number: int, work: int, results: int,
               live_tests: set[str]) -> None:
    config = session.config
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if isinstance(reporter, TerminalReporter):
        reporter._tw = TerminalWriter(open(os.devnull, "w"))
    factory = temp_paths(config)
    own = factory.getbasetemp() / f"fork-{number}"
    own.mkdir()
    factory._basetemp = own
    data = Path(tempfile.mkdtemp(prefix="github-orchestrator-tests-"))
    config_file = data / "config.toml"
    config_file.write_bytes(Path(os.environ["GITHUB_ORCHESTRATOR_CONFIG"]).read_bytes())
    os.environ["GITHUB_ORCHESTRATOR_DATA_DIR"] = str(data)
    os.environ["GITHUB_ORCHESTRATOR_CONFIG"] = str(config_file)
    config.pluginmanager.register(_Child(config, results), "forked-child")
    items = _items_to_run(session, work)
    item = next(items, None)
    while item is not None and not (session.shouldfail or session.shouldstop):
        nextitem = next(items, None)
        config.hook.pytest_runtest_protocol(item=item, nextitem=nextitem)
        item = nextitem
    shutil.rmtree(data, ignore_errors=True)
    _send(results, "done", sorted(live_tests))


def _child(session: pytest.Session, number: int, work: int, results: int,
           live_tests: set[str]) -> None:
    status = 0
    try:
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        _run_child(session, number, work, results, live_tests)
    except BaseException:
        traceback.print_exc()
        status = 3
    finally:
        os._exit(status)


def run_in_forks(session: pytest.Session, forks: int, live_tests: set[str]) -> None:
    if threading.active_count() > 1:
        raise pytest.UsageError("--forks needs a single-threaded process when collection ends")
    recorded = _recorded(session.config)
    session.items[:] = _heaviest_files_first(session.items, recorded)
    spans = list(_spans([recorded.get(item.nodeid, _UNTIMED) for item in session.items], forks))
    temp_paths(session.config).getbasetemp()
    work_read, work_write = os.pipe()
    children: dict[int, tuple[int, int]] = {}
    for number in range(min(forks, len(spans))):
        results_read, results_write = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(work_write)
            os.close(results_read)
            _child(session, number, work_read, results_write, live_tests)
        os.close(results_write)
        children[results_read] = (pid, number)
    os.close(work_read)
    os.write(work_write, b"".join(_SPAN.pack(*span) for span in spans))
    os.close(work_write)
    _gather(session, children, live_tests)


def _deliver(config: pytest.Config, message: tuple[Any, ...]) -> None:
    hook = config.hook
    kind = message[0]
    if kind == "logstart":
        hook.pytest_runtest_logstart(nodeid=message[1], location=message[2])
    elif kind == "logreport":
        hook.pytest_runtest_logreport(
            report=hook.pytest_report_from_serializable(config=config, data=message[1]))
    elif kind == "logfinish":
        hook.pytest_runtest_logfinish(nodeid=message[1], location=message[2])
    elif kind == "warning":
        hook.pytest_warning_recorded.call_historic(kwargs={
            "warning_message": warnings.WarningMessage(*message[1]),
            "when": message[2], "nodeid": message[3], "location": message[4]})


def _crashed(session: pytest.Session, running: tuple[str, Any] | None, status: int) -> None:
    if running is None:
        return
    nodeid, location = running
    hook = session.config.hook
    report = pytest.TestReport(nodeid, location, {}, "failed",
                               f"the forked process running this test ended (wait status {status})",
                               "call")
    hook.pytest_runtest_logreport(report=report)
    hook.pytest_runtest_logfinish(nodeid=nodeid, location=location)


def _gather(session: pytest.Session, children: dict[int, tuple[int, int]],
            live_tests: set[str]) -> None:
    buffers = {fd: b"" for fd in children}
    seconds: dict[str, float] = {}
    finished: set[int] = set()
    running: dict[int, tuple[str, Any] | None] = dict.fromkeys(children)
    ran = 0
    selector = selectors.DefaultSelector()
    for fd in children:
        selector.register(fd, selectors.EVENT_READ)
    try:
        while buffers and not (session.shouldfail or session.shouldstop):
            for key, _ in selector.select():
                fd = int(key.fd)
                data = os.read(fd, 1 << 16)
                if not data:
                    selector.unregister(fd)
                    del buffers[fd]
                    continue
                buffers[fd] += data
                while len(buffers[fd]) >= _FRAME.size:
                    (size,) = _FRAME.unpack_from(buffers[fd])
                    if len(buffers[fd]) < _FRAME.size + size:
                        break
                    message = pickle.loads(buffers[fd][_FRAME.size:_FRAME.size + size])
                    buffers[fd] = buffers[fd][_FRAME.size + size:]
                    if message[0] == "done":
                        finished.add(fd)
                        live_tests.update(message[1])
                        continue
                    if message[0] == "logstart":
                        running[fd] = (message[1], message[2])
                    elif message[0] == "logfinish":
                        running[fd] = None
                        ran += 1
                    elif message[0] == "logreport":
                        nodeid = message[1]["nodeid"]
                        seconds[nodeid] = seconds.get(nodeid, 0.0) + message[1]["duration"]
                    _deliver(session.config, message)
    finally:
        _remember(session.config, seconds)
        stopping = session.shouldfail or session.shouldstop
        crashed = []
        for fd, (pid, number) in children.items():
            if stopping:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            _, status = os.waitpid(pid, 0)
            os.close(fd)
            if fd not in finished and not stopping:
                crashed.append(number)
                _crashed(session, running[fd], status)
                ran += running[fd] is not None
    if crashed:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if isinstance(reporter, TerminalReporter):
            reporter.write_line(
                f"forks {crashed} ended early: {len(session.items) - ran} tests never ran", red=True)
        session.testsfailed += len(crashed)
        raise session.Failed(f"forks {crashed} ended early")
    if session.shouldfail:
        raise session.Failed(session.shouldfail)
    if session.shouldstop:
        raise session.Interrupted(session.shouldstop)
