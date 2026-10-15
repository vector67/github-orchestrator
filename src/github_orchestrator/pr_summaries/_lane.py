import contextlib
import fcntl
import json
import logging
import os
import shutil
import signal
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from github_orchestrator.domain import Pr, Repo, UtcClock
from github_orchestrator.pr_summaries._disk import working_folder
from github_orchestrator.pr_summaries.interface import Progress, PrSummaries, Summary

log = logging.getLogger(__name__)

WORKING_FILES = "Working files: "
WITNESSES = ("requested", "claimed", "implementation", "tests", "why", "alignment")


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


def _in_flight(pr: Pr, since: datetime) -> bytes:
    return json.dumps({"owner": pr.repo.owner, "repo": pr.repo.name, "number": pr.number,
                       "since": since.isoformat()}).encode()


def _named(content: bytes) -> tuple[Pr, datetime] | None:
    try:
        fields = json.loads(content)
        return (Pr(Repo(fields["owner"], fields["repo"]), fields["number"]),
                datetime.fromisoformat(fields["since"]))
    except (ValueError, KeyError, TypeError):
        return None


class LocalSummaryLane:
    def __init__(self, summaries_dir: Path, summaries: PrSummaries, clock: UtcClock, *,
                 plugin: Sequence[str], config_path: Path, clones: Mapping[Repo, Path],
                 head_of: Callable[[Pr], str | None], url_of: Callable[[Pr], str],
                 gh_token: Callable[[], str],
                 agents_enabled: bool, timeout: float,
                 run_in: Callable[[Callable[[], None]], None]) -> None:
        self._dir = summaries_dir
        self._summaries = summaries
        self._clock = clock
        self._plugin = tuple(plugin)
        self._config_path = config_path
        self._clones = clones
        self._head_of = head_of
        self._url_of = url_of
        self._gh_token = gh_token
        self._agents_enabled = agents_enabled
        self._timeout = timeout
        self._run_in = run_in

    def poll(self) -> None:
        if not self._agents_enabled:
            return
        due = [pr for pr in self._summaries.due(set()) if pr.repo in self._clones]
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
        started = self._clock()
        os.ftruncate(slot, 0)
        os.pwrite(slot, _in_flight(pr, started), 0)
        self._run_in(lambda: self._run(pr, slot, started, use_github_api=use_github_api))
        return None

    def progress(self, pr: Pr) -> Progress | None:
        held = self._held()
        if held is None or held[0] != pr:
            return None
        return Progress(since=held[1], done=_done(working_folder(self._dir, pr)))

    def behind(self, pr: Pr, head: str | None) -> int | None:
        read = (self._summaries.load(pr) or Summary()).head_sha
        clone = self._clones.get(pr.repo)
        if read is None or head is None or clone is None:
            return None
        counted = subprocess.run(["git", "rev-list", "--count", f"{read}..{head}"],
                                 cwd=clone, capture_output=True, text=True, check=False)
        return int(counted.stdout) if counted.returncode == 0 else None

    def _held(self) -> tuple[Pr, datetime] | None:
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

    def _run(self, pr: Pr, slot: int, started: datetime, *, use_github_api: bool) -> None:
        try:
            self._summarise(pr, slot, started, use_github_api=use_github_api)
        except Exception:
            log.exception("Summary of %s failed", pr)
        finally:
            os.close(slot)

    def _summarise(self, pr: Pr, slot: int, started: datetime, *,
                   use_github_api: bool) -> None:
        wanted = (self._summaries.load(pr) or Summary()).wanted
        head = self._head_of(pr)
        folder = working_folder(self._dir, pr)
        shutil.rmtree(folder, ignore_errors=True)
        command = [*self._plugin, self._url_of(pr), "--config", str(self._config_path),
                   "--work-dir", str(folder), *(["--use-github-api"] if use_github_api else [])]
        exit_status, stdout, stderr = self._plugin_run(command, self._clones[pr.repo], slot)
        previous = self._summaries.load(pr) or Summary()
        report = (replace(previous, head_sha=head, markdown=_markdown(stdout),
                          mismatches=_mismatches(folder))
                  if exit_status == 0 else previous)
        self._summaries.save(pr, replace(report, answered=wanted, started=started,
                                         finished=self._clock(),
                                         exit_status=exit_status, stderr=stderr))

    def _plugin_run(self, command: list[str], cwd: Path,
                    slot: int) -> tuple[int | None, str, str]:
        try:
            env = {**os.environ, "GH_TOKEN": self._gh_token()}
        except Exception as failure:
            return None, "", f"github-orchestrator could not read a GitHub token for the plugin: {failure}\n"
        try:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True,
                                       start_new_session=True, pass_fds=(slot,))
        except OSError as failure:
            return None, "", f"github-orchestrator could not start the plugin: {failure}\n"
        try:
            stdout, stderr = process.communicate(timeout=self._timeout)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
            stderr += (f"github-orchestrator stopped the run after "
                       f"{self._timeout / 60:g} minutes.\n")
        return process.returncode, stdout, stderr
