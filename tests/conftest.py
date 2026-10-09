import asyncio
import atexit
import functools
import gc
import hashlib
import itertools
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types
from collections.abc import Callable, Iterator, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import dishka
import pytest
import uvicorn.server
from _pytest.unraisableexception import gc_collect_iterations_key

_SESSION_DATA_DIR = Path(tempfile.mkdtemp(prefix="github-orchestrator-tests-"))
os.environ["GITHUB_ORCHESTRATOR_DATA_DIR"] = str(_SESSION_DATA_DIR)

_SESSION_CONFIG = _SESSION_DATA_DIR / "config.toml"
_SESSION_CONFIG.write_text(
    'gh_account = "octocat"\n'
    '[[repos]]\n'
    'repo = "octocat/hello-world"\n'
    'local_path = "/tmp/github-orchestrator-tests/hello-world"\n'
)
os.environ["GITHUB_ORCHESTRATOR_CONFIG"] = str(_SESSION_CONFIG)

from github_orchestrator.agent_runs import History, PrWork, Summaries, ThreadWork
from github_orchestrator.agent_runs.fake import FakeAgentRuns
from github_orchestrator.desktop.fake import FakeDesktop
from github_orchestrator.domain import LocalClock, Monotonic, Sleep, UtcClock
from github_orchestrator.github import Access, PullRequests, Reviews, Threads
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.notifications import (
    Polling,
    PrStatus,
    Runs,
    ThreadNews,
    Worktrees,
)
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.pr_processes.fake import FakePrProcesses
from github_orchestrator.settings.fake import Settings, fake_settings
from github_orchestrator.wiring import (
    ClocksWiring,
    Part,
    SettingsWiring,
    Wiring,
    change_detection_wiring,
    conversation_wiring,
    logs_wiring,
    pr_event_queue_wiring,
    switches_wiring,
    thread_records_wiring,
    utcnow,
    wire,
    working_copies_wiring,
)
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.forked_run import run_in_forks, temp_paths
from tests.subprocess_recording import RECORDING, Recorder, covers_whole_suite

os.environ["GIT_CONFIG_COUNT"] = "1"
os.environ["GIT_CONFIG_KEY_0"] = "maintenance.auto"
os.environ["GIT_CONFIG_VALUE_0"] = "false"
os.environ["GIT_AUTHOR_DATE"] = os.environ["GIT_COMMITTER_DATE"] = "2026-01-01T00:00:00Z"

UVICORN_POLL_SECONDS = 0.01


async def _uvicorn_poll(delay: float, result: Any = None) -> Any:
    return await asyncio.sleep(min(delay, UVICORN_POLL_SECONDS), result)


setattr(uvicorn.server, "asyncio", types.SimpleNamespace(**{**vars(asyncio), "sleep": _uvicorn_poll}))

_REAL_RUN = subprocess.run
_REAL_POPEN = subprocess.Popen
_TEMPLATES: dict[tuple[Callable[..., Any], tuple[Any, ...]], tuple[Path, Any]] = {}
_SHARED: dict[tuple[Callable[..., Any], tuple[Any, ...]], Any] = {}
_RECORDER = pytest.StashKey[Recorder]()
_COLLECTED = pytest.StashKey[set[str]]()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--record", action="store_true",
        help="run every subprocess for real and save its output and file "
             f"changes to {RECORDING.name}; needs a serial run",
    )
    parser.addoption(
        "--no-replay", action="store_true",
        help="run every subprocess for real and leave the recording alone",
    )
    parser.addoption(
        "--forks", type=int, default=0,
        help="collect once, then run the tests in this many forked processes",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.stash[gc_collect_iterations_key] = 1
    config.addinivalue_line(
        "markers",
        "no_replay: run this test's subprocesses for real even when a recording exists",
    )
    if config.getoption("--record"):
        mode = "record"
        if getattr(config.option, "numprocesses", None):
            raise pytest.UsageError("--record needs a serial run: drop -n")
    elif config.getoption("--no-replay"):
        mode = "live"
    else:
        mode = "replay"
    config.stash[_RECORDER] = Recorder(mode, _REAL_RUN)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    config.stash[_COLLECTED] = {item.nodeid for item in items}


@pytest.hookimpl(trylast=True)
def pytest_collection_finish(session: pytest.Session) -> None:
    gc.collect()
    gc.freeze()


def _forks(config: pytest.Config) -> int:
    forks: int = config.getoption("--forks")
    if config.getoption("--record") or config.option.collectonly:
        return 0
    return forks


@pytest.hookimpl(tryfirst=True)
def pytest_runtestloop(session: pytest.Session) -> bool | None:
    forks = _forks(session.config)
    if forks < 2 or len(session.items) < 2:
        return None
    if session.testsfailed and not session.config.option.continue_on_collection_errors:
        raise session.Interrupted(f"{session.testsfailed} errors during collection")
    run_in_forks(session, forks, session.config.stash[_RECORDER].live_tests)
    return True


def _remove_in_the_background(worker_temp: Path) -> None:
    doomed = worker_temp.parent.parent / f"doomed-{worker_temp.parent.name}-{worker_temp.name}"
    try:
        worker_temp.rename(doomed)
    except OSError:
        return
    _REAL_POPEN(["rm", "-rf", str(doomed)], start_new_session=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


_PASSED_SESSIONS: list[pytest.Session] = []


@atexit.register
def _exit_without_tearing_down_the_interpreter() -> None:
    if _PASSED_SESSIONS:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if exitstatus == 0:
        _PASSED_SESSIONS.append(session)
        if hasattr(session.config, "workerinput"):
            _remove_in_the_background(Path(session.config.option.basetemp))
        elif _forks(session.config) > 1:
            factory = temp_paths(session.config)
            if factory._basetemp is not None and factory._given_basetemp is None:
                _remove_in_the_background(factory._basetemp)
                factory._basetemp = None
    recorder = session.config.stash[_RECORDER]
    if recorder.mode == "record":
        collected = session.config.stash.get(_COLLECTED, set())
        recorder.save(collected, full_run=covers_whole_suite(
            session.config.args, session.config.invocation_params.dir,
            selected=len(session.items), collected=len(collected),
        ))
    shutil.rmtree(_SESSION_DATA_DIR, ignore_errors=True)


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter,
                            config: pytest.Config) -> None:
    recorder = config.stash[_RECORDER]
    if recorder.mode == "record":
        terminalreporter.write_line(f"recorded subprocess output to {RECORDING}")
    elif recorder.live_tests:
        terminalreporter.write_line(
            f"{len(recorder.live_tests)} tests ran subprocesses live because "
            f"{RECORDING.name} has no entry for them; `make record` captures them"
        )


def _repoint(dest: Path, old: str, new: str) -> None:
    for path in dest.rglob("*"):
        if path.is_file() and path.name in ("config", "gitdir", ".git"):
            text = path.read_text()
            if old in text:
                path.write_text(text.replace(old, new))


def _template_name(build: Callable[..., Any], args: tuple[Any, ...]) -> str:
    name = f"{build.__module__}.{build.__qualname__}"
    if args:
        name += ":" + hashlib.sha1(repr(args).encode()).hexdigest()[:8]
    return name


_TMP_PATHS = itertools.count()


@pytest.fixture
def tmp_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.getbasetemp() / f"test-{next(_TMP_PATHS)}"
    path.mkdir()
    return path


@pytest.fixture
def git_template(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory,
                 tmp_path: Path) -> Callable[..., Any]:
    recorder = request.config.stash[_RECORDER]

    def _copy(build: Callable[..., Any], *args: Any) -> Any:
        key = (build, args)
        if key not in _TEMPLATES:
            root = tmp_path_factory.mktemp(build.__name__)
            with recorder.template_scope(_template_name(build, args), root):
                _TEMPLATES[key] = (root, build(root, *args))
        root, extra = _TEMPLATES[key]
        shutil.copytree(root, tmp_path, symlinks=True, dirs_exist_ok=True)
        _repoint(tmp_path, str(root), str(tmp_path))
        return extra

    return _copy


@pytest.fixture
def shared_template(request: pytest.FixtureRequest,
                    tmp_path_factory: pytest.TempPathFactory) -> Callable[..., Any]:
    recorder = request.config.stash[_RECORDER]

    def _share(build: Callable[..., Any], *args: Any) -> Any:
        key = (build, args)
        if key not in _SHARED:
            name = _template_name(build, args)
            root = tmp_path_factory.mktemp(name.replace(":", "-"), numbered=False)
            with recorder.template_scope(name, root):
                _SHARED[key] = build(root, *args)
        return _SHARED[key]

    return _share


def build_container(settings: Settings, *fakes: Part,
                    clocks: ClocksWiring | None = None) -> dishka.Container:
    return wire(
        clocks or clocks_of(),
        SettingsWiring(settings),
        logs_wiring(settings),
        switches_wiring(settings),
        pr_event_queue_wiring(settings),
        fake_notifications(FakeNotifications()),
        working_copies_wiring(settings),
        thread_records_wiring(settings),
        change_detection_wiring(settings),
        conversation_wiring(settings),
        *fakes,
    )


def ticking_clock(start: datetime | None = None) -> Callable[[], datetime]:
    first = start or utcnow()
    ticks = itertools.count()

    def ticking() -> datetime:
        return first + timedelta(microseconds=next(ticks))

    return ticking


def clocks_of(utc: Callable[[], datetime] | None = None, *,
              local: Callable[[], datetime] | None = None,
              monotonic: Callable[[], float] = time.monotonic,
              sleep: Callable[[float], None] = time.sleep) -> ClocksWiring:
    now = utc or ticking_clock()
    return ClocksWiring(UtcClock(now), LocalClock(local or now), Monotonic(monotonic),
                        Sleep(sleep))


@functools.cache
def _fake_provider_class(roles: tuple[type, ...]) -> type[dishka.Provider]:
    sources: dict[str, object] = {
        f"role_{index}": dishka.from_context(provides=role, scope=dishka.Scope.APP)
        for index, role in enumerate(roles)}
    return type("FakeProvider", (dishka.Provider,), {"scope": dishka.Scope.APP, **sources})


class Fake(Wiring):
    def __init__(self, instance: object, *roles: type) -> None:
        self._instance = instance
        self._roles = roles

    def provider(self) -> type[dishka.Provider]:
        return _fake_provider_class(self._roles)

    def context(self) -> Mapping[object, object]:
        return {role: self._instance for role in self._roles}


def fake_provider(interface: type, instance: object) -> Fake:
    return Fake(instance, interface)


def fake_notifications(instance: FakeNotifications) -> Fake:
    return Fake(instance, ThreadNews, Runs, Worktrees, PrStatus, Polling)


def fake_agent_runs_roles(instance: FakeAgentRuns) -> Fake:
    return Fake(instance, History, PrWork, Summaries, ThreadWork)


def fake_github(instance: FakeGitHub) -> Fake:
    return Fake(instance, PullRequests, Threads, Reviews, Access)


@pytest.fixture(autouse=True)
def _no_checkout_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("github_orchestrator.settings._load.CHECKOUT_CONFIG", tmp_path / "no-checkout-config.toml")


@pytest.fixture(autouse=True)
def _no_uv_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UV_TOOL_DIR", str(tmp_path / "no-uv-tools"))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return fake_settings(tmp_path)


@pytest.fixture
def desktop() -> FakeDesktop:
    return FakeDesktop()


@pytest.fixture
def notifications() -> FakeNotifications:
    return FakeNotifications()


@pytest.fixture
def working_copies() -> FakeWorkingCopies:
    return FakeWorkingCopies()


@pytest.fixture
def pr_processes(settings: Settings) -> FakePrProcesses:
    return FakePrProcesses()


def fake_agent_runs() -> FakeAgentRuns:
    return FakeAgentRuns(FakePrProcesses())


@pytest.fixture
def agent_runs(desktop: FakeDesktop, pr_processes: FakePrProcesses) -> FakeAgentRuns:
    return FakeAgentRuns(pr_processes)


NEVER_SPAWNED = ("gh", "claude", "osascript", "open", "tmux")


def _spawns_a_guarded_binary(cmd: object) -> str | None:
    if isinstance(cmd, (list, tuple)) and cmd:
        head = str(cmd[0])
    elif isinstance(cmd, str) and cmd.split():
        head = cmd.split()[0]
    else:
        return None
    name = head.rsplit("/", 1)[-1]
    return name if name in NEVER_SPAWNED else None


def _this_repository() -> tuple[Path, ...]:
    checkout = Path(__file__).resolve().parents[1]
    common = _REAL_RUN(["git", "-C", str(checkout), "rev-parse", "--path-format=absolute",
                        "--git-common-dir"], capture_output=True, text=True).stdout.strip()
    return (checkout, Path(common).resolve().parent) if common else (checkout,)


_THIS_REPOSITORY = _this_repository()
_NEEDS_NO_REPOSITORY = ("init", "clone", "version")


def _git_directories(cmd: object, cwd: object) -> list[Path]:
    if not isinstance(cmd, (list, tuple)) or not cmd or Path(str(cmd[0])).name != "git":
        return []
    here = Path(str(cwd)) if cwd is not None else Path.cwd()
    named: list[Path] = []
    words = iter(str(word) for word in cmd[1:])
    for word in words:
        if word == "-C":
            here = here / next(words, "")
        elif word == "-c":
            next(words, "")
        elif word.startswith(("--git-dir=", "--work-tree=")):
            named.append(here / word.split("=", 1)[1])
        elif word == "--version":
            return []
        elif not word.startswith("-"):
            return [] if word in _NEEDS_NO_REPOSITORY else [here, *named]
    return [here, *named]


def _reaches_this_repository(cmd: object, cwd: object) -> Path | None:
    for directory in _git_directories(cmd, cwd):
        resolved = directory.resolve()
        if any(resolved.is_relative_to(root) for root in _THIS_REPOSITORY):
            return resolved
    return None


def _guarded(real: Callable[..., Any]) -> Callable[..., Any]:
    def wrapper(cmd: Any, *args: Any, **kwargs: Any) -> Any:
        reached = _reaches_this_repository(cmd, kwargs.get("cwd"))
        if reached is not None:
            pytest.fail(
                f"test ran git in {reached}, inside the orchestrator's own repository: "
                f"{cmd!r}. An empty or missing path runs git in the directory pytest "
                f"stands in; hand the code a repository under tmp_path.",
                pytrace=False,
            )
        name = _spawns_a_guarded_binary(cmd)
        if name is not None:
            pytest.fail(
                f"test spawned a real {name} subprocess: {cmd!r}. Hand the "
                f"code a FakeGitHub from github_orchestrator.github or a "
                f"FakeDesktop from github_orchestrator.desktop or a FakePrProcesses "
                f"from github_orchestrator.pr_processes or a FakeAgentRuns from "
                f"github_orchestrator.agent_runs in place of the real one, so the "
                f"test never reaches the network or the desktop.",
                pytrace=False,
            )
        return real(cmd, *args, **kwargs)

    return wrapper


def _recorded_name(item: pytest.Item) -> str:
    group = item.get_closest_marker("xdist_group")
    return item.nodeid.removesuffix(f"@{group.args[0]}") if group else item.nodeid


@pytest.fixture(autouse=True)
def _recorded_subprocesses(request: pytest.FixtureRequest, tmp_path: Path,
                           monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    recorder = request.config.stash[_RECORDER]
    if request.node.get_closest_marker("no_replay") is None:
        recorder.begin_test(_recorded_name(request.node), tmp_path)
    monkeypatch.setattr(subprocess, "run", _guarded(recorder.run))
    monkeypatch.setattr(subprocess, "Popen", _guarded(_REAL_POPEN))
    yield
    recorder.end_test()
