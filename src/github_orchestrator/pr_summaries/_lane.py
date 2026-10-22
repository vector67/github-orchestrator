import contextlib
import fcntl
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from github_orchestrator.domain import Pr, Repo, UtcClock
from github_orchestrator.pr_summaries._disk import working_folder
from github_orchestrator.pr_summaries.interface import Progress, PrSummaries, Summary

log = logging.getLogger(__name__)

WORKING_FILES = "Working files: "
WITNESSES = ("primer", "requested", "claimed", "implementation", "tests", "why", "alignment", "critic", "verdict")
LOST = "github-orchestrator lost the run: it ended without an exit status.\n"
RECORDING_THE_EXIT = """
import json, subprocess, sys
try:
    status = subprocess.run(sys.argv[2:]).returncode
except OSError as failure:
    sys.stderr.write(f"github-orchestrator could not start the plugin: {failure}\\n")
    status = None
with open(sys.argv[1], "w") as recorded:
    recorded.write(json.dumps(status))
"""


@dataclass(frozen=True)
class _Run:
    pr: Pr
    since: datetime
    head: str | None
    wanted: datetime | None


def _markdown(stdout: str) -> str:
    lines = stdout.splitlines(keepends=True)
    if lines and lines[-1].startswith(WORKING_FILES):
        lines.pop()
    return "".join(lines)


def _mismatches(folder: Path) -> int | None:
    try:
        judged = json.loads((folder / "alignment" / "output.json").read_text())
    except (OSError, ValueError):
        return None
    mismatches = judged.get("mismatches") if isinstance(judged, dict) else None
    return len(mismatches) if isinstance(mismatches, list) else None


def _done(folder: Path) -> dict[str, bool]:
    return {witness: (folder / witness / "output.json").exists()
            for witness in WITNESSES if (folder / witness).is_dir()}


def _outputs(pr_folder: Path) -> Path:
    return pr_folder.with_suffix(".run")


def _kept_primer(pr_folder: Path) -> Path:
    return pr_folder.with_suffix(".primer.json")


def _keep_primer(pr_folder: Path) -> None:
    written = pr_folder / "primer" / "output.json"
    try:
        primer = json.loads(written.read_text())
    except (OSError, ValueError):
        return
    if isinstance(primer, dict) and "concepts" in primer:
        shutil.copy(written, _kept_primer(pr_folder))


def _read(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError:
        return ""


def _exit_status(outputs: Path) -> tuple[bool, int | None]:
    try:
        status = json.loads((outputs / "exit_status").read_text())
    except (OSError, ValueError):
        return False, None
    return True, status if isinstance(status, int) else None


def _in_flight(run: _Run) -> bytes:
    return json.dumps({"owner": run.pr.repo.owner, "repo": run.pr.repo.name,
                       "number": run.pr.number, "since": run.since.isoformat(),
                       "head": run.head,
                       "wanted": None if run.wanted is None else run.wanted.isoformat()}).encode()


def _named(content: bytes) -> _Run | None:
    try:
        fields = json.loads(content)
        wanted = fields.get("wanted")
        return _Run(Pr(Repo(fields["owner"], fields["repo"]), fields["number"]),
                    datetime.fromisoformat(fields["since"]), fields.get("head"),
                    None if wanted is None else datetime.fromisoformat(wanted))
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


class LocalSummaryLane:
    def __init__(self, summaries_dir: Path, summaries: PrSummaries, clock: UtcClock, *,
                 plugin: Sequence[str], config_path: Path, clones: Mapping[Repo, Path],
                 head_of: Callable[[Pr], str | None], holds: Callable[[Pr], bool],
                 url_of: Callable[[Pr], str],
                 gh_account: str, mcp_config: str, agents_enabled: bool, timeout: float,
                 run_in: Callable[[Callable[[], None]], None], clamp: Sequence[str]) -> None:
        self._dir = summaries_dir
        self._summaries = summaries
        self._clock = clock
        self._plugin = tuple(plugin)
        self._config_path = config_path
        self._clones = clones
        self._head_of = head_of
        self._holds = holds
        self._url_of = url_of
        self._gh_account = gh_account
        self._mcp_config = mcp_config
        self._agents_enabled = agents_enabled
        self._timeout = timeout
        self._run_in = run_in
        self._clamp = tuple(clamp)

    def poll(self) -> None:
        if not self._agents_enabled:
            return
        self._store_an_orphaned_run()
        due = [pr for pr in self._summaries.due(set()) if pr.repo in self._clones and self._holds(pr)]
        if due:
            self.start(due[0], use_github_api=False)

    def start(self, pr: Pr, *, use_github_api: bool) -> str | None:
        if not self._agents_enabled:
            return "agents are disabled (agents_enabled=false)"
        if pr.repo not in self._clones:
            return f"{pr.repo} is not a watched repository"
        slot = self._slot()
        if slot is None:
            return "another summary is running"
        try:
            self._store(slot)
            run = _Run(pr, self._clock(), self._head_of(pr),
                       (self._summaries.load(pr) or Summary()).wanted)
            folder = working_folder(self._dir, pr)
            _keep_primer(folder)
            shutil.rmtree(folder, ignore_errors=True)
            shutil.rmtree(_outputs(folder), ignore_errors=True)
            os.ftruncate(slot, 0)
            os.pwrite(slot, _in_flight(run), 0)
            self._run_in(lambda: self._run(pr, slot, use_github_api=use_github_api))
        except BaseException:
            os.close(slot)
            raise
        return None

    def progress(self, pr: Pr) -> Progress | None:
        held = self._held()
        if held is None:
            self._store_an_orphaned_run()
            return None
        if held.pr != pr:
            return None
        return Progress(since=held.since, done=_done(working_folder(self._dir, pr)), agents=len(WITNESSES))

    def behind(self, pr: Pr, head: str | None) -> int | None:
        read = (self._summaries.load(pr) or Summary()).head_sha
        clone = self._clones.get(pr.repo)
        if read is None or head is None or clone is None:
            return None
        counted = subprocess.run(["git", "rev-list", "--count", f"{read}..{head}"],
                                 cwd=clone, capture_output=True, text=True, check=False)
        return int(counted.stdout) if counted.returncode == 0 else None

    def _held(self) -> _Run | None:
        try:
            descriptor = os.open(self._lock, os.O_RDONLY)
        except FileNotFoundError:
            return None
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return _named(os.read(descriptor, 4096))
        finally:
            os.close(descriptor)
        return None

    @property
    def _lock(self) -> Path:
        return self._dir / "lane.lock"

    def _slot(self) -> int | None:
        self._dir.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self._lock, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            return None
        return descriptor

    def _store_an_orphaned_run(self) -> None:
        slot = self._slot()
        if slot is None:
            return
        try:
            self._store(slot)
        finally:
            os.close(slot)

    def _run(self, pr: Pr, slot: int, *, use_github_api: bool) -> None:
        try:
            self._plugin_run(pr, slot, use_github_api=use_github_api)
            self._store(slot)
        except Exception:
            log.exception("Summary of %s failed", pr)
        finally:
            os.close(slot)

    def _store(self, slot: int) -> None:
        run = _named(os.pread(slot, 4096, 0))
        if run is None:
            return
        folder = working_folder(self._dir, run.pr)
        outputs = _outputs(folder)
        ended, exit_status = _exit_status(outputs)
        stderr = _read(outputs / "stderr") + ("" if ended else LOST)
        previous = self._summaries.load(run.pr) or Summary()
        report = (replace(previous, head_sha=run.head,
                          markdown=_markdown(_read(outputs / "stdout")),
                          mismatches=_mismatches(folder))
                  if ended and exit_status == 0 else previous)
        self._summaries.save(run.pr, replace(
            report, answered=run.wanted if ended else previous.answered, started=run.since,
            finished=self._clock(), exit_status=exit_status, stderr=stderr))
        os.ftruncate(slot, 0)

    def _plugin_run(self, pr: Pr, slot: int, *, use_github_api: bool) -> None:
        folder = working_folder(self._dir, pr)
        outputs = _outputs(folder)
        outputs.mkdir(parents=True)
        kept = _kept_primer(folder)
        command = [*self._plugin, self._url_of(pr), "--config", str(self._config_path),
                   "--work-dir", str(folder), "--gh-account", self._gh_account,
                   *(["--mcp-config", self._mcp_config] if self._mcp_config else []),
                   *(["--use-github-api"] if use_github_api else []),
                   *(["--earlier-primer", str(kept)] if kept.exists() else [])]
        with open(outputs / "stdout", "w") as stdout, open(outputs / "stderr", "w") as stderr:
            process = subprocess.Popen(
                [*self._clamp, sys.executable, "-c", RECORDING_THE_EXIT, str(outputs / "exit_status"), *command],
                cwd=self._clones[pr.repo], stdout=stdout, stderr=stderr,
                start_new_session=True, pass_fds=(slot,))
        stopped = threading.Event()

        def stop() -> None:
            stopped.set()
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)

        deadline = threading.Timer(self._timeout, stop)
        deadline.start()
        try:
            process.wait()
        finally:
            deadline.cancel()
            deadline.join()
        if stopped.is_set():
            with open(outputs / "stderr", "a") as stderr:
                stderr.write(f"github-orchestrator stopped the run after "
                             f"{self._timeout / 60:g} minutes.\n")
            (outputs / "exit_status").write_text(json.dumps(process.returncode))
