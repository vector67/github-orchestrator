import json
import logging
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from github_orchestrator.board_api.interface import Dashboard, ManagerStanding
from github_orchestrator.domain import Pr, UtcClock

log = logging.getLogger(__name__)

STATUS_STALE_SECONDS = 10.0

_STAMP = "%Y-%m-%dT%H:%M:%S.%fZ"


class StatusFiles:
    def __init__(self, data_dir: Path, clock: UtcClock) -> None:
        self._dir = data_dir / "status"
        self._clock = clock

    def begin(self, pr: Pr) -> None:
        path = self._path(pr)
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            log.warning("could not clear the status file %s: %s", path, error)

    def write(self, dashboard: Dashboard) -> None:
        now = self._clock()
        status = {
            "written_at": now.strftime(_STAMP),
            "active_run": _active_run(dashboard, now),
            "notice": dashboard.notice,
            "threads_live": sorted(dashboard.threads_live),
            "frozen_on": dashboard.frozen_on,
            "expected_branch": dashboard.expected_branch,
            "seconds_left": dashboard.seconds_left,
            "run_working": dashboard.run_working,
            "release_requested": dashboard.release_requested,
            "flags_changed_at": dashboard.flags_changed_at,
        }
        path = self._path(dashboard.pr)
        try:
            _write_atomically(path, json.dumps(status).encode())
        except OSError as error:
            log.warning("could not write the status file %s: %s", path, error)

    def standing(self, pr: Pr) -> ManagerStanding:
        path = self._path(pr)
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            return ManagerStanding.STARTING
        try:
            written_at = datetime.strptime(json.loads(content)["written_at"], _STAMP).replace(tzinfo=UTC)
        except (ValueError, KeyError, TypeError) as error:
            log.warning("could not read the status file %s: %s", path, error)
            return ManagerStanding.GONE
        if (self._clock() - written_at).total_seconds() < STATUS_STALE_SECONDS:
            return ManagerStanding.ANSWERING
        return ManagerStanding.GONE

    def _path(self, pr: Pr) -> Path:
        return self._dir / pr.repo.owner / pr.repo.name / f"{pr.number}.json"


def _active_run(dashboard: Dashboard, now: datetime) -> dict[str, str] | None:
    if dashboard.working_on is None:
        return None
    return {
        "event": dashboard.working_on,
        "started_at": _ago(now, dashboard.elapsed_seconds),
        "last_output_at": _ago(now, dashboard.silent_seconds),
    }


def _ago(now: datetime, seconds: float | None) -> str:
    return (now - timedelta(seconds=seconds or 0.0)).strftime(_STAMP)


def _write_atomically(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, suffix=".tmp",
                                     delete=False) as tmp:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
    try:
        Path(tmp.name).replace(path)
    except BaseException:
        Path(tmp.name).unlink(missing_ok=True)
        raise
