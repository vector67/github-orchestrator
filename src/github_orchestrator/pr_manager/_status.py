import json
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from github_orchestrator.board_api.interface import Dashboard, ManagerStanding
from github_orchestrator.domain import Pr, UtcClock
from github_orchestrator.pr_manager._files import write_whole
from github_orchestrator.pr_manager._refusals import NOTHING_KNOWN, Conditions

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
            write_whole(path, json.dumps(status).encode())
        except OSError as error:
            log.warning("could not write the status file %s: %s", path, error)

    def laid_over(self, dashboard: Dashboard) -> Dashboard:
        path = self._path(dashboard.pr)
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            return replace(dashboard, standing=ManagerStanding.STARTING)
        except OSError as error:
            log.warning("could not read the status file %s: %s", path, error)
            return replace(dashboard, standing=ManagerStanding.GONE)
        now = self._clock()
        try:
            status = json.loads(content)
            if _seconds_since(now, status["written_at"]) >= STATUS_STALE_SECONDS:
                return replace(dashboard, standing=ManagerStanding.GONE)
            return _over(dashboard, status, now)
        except (ValueError, KeyError, TypeError) as error:
            log.warning("could not read the status file %s: %s", path, error)
            return replace(dashboard, standing=ManagerStanding.GONE)

    def conditions(self, pr: Pr) -> Conditions:
        path = self._path(pr)
        try:
            status = json.loads(path.read_bytes())
            return Conditions(frozen=status["frozen_on"] is not None,
                              running=status["active_run"] is not None)
        except FileNotFoundError:
            return NOTHING_KNOWN
        except (OSError, ValueError, KeyError, TypeError) as error:
            log.warning("could not read the status file %s: %s", path, error)
            return NOTHING_KNOWN

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


def _seconds_since(now: datetime, stamp: str) -> float:
    return (now - datetime.strptime(stamp, _STAMP).replace(tzinfo=UTC)).total_seconds()


def _over(dashboard: Dashboard, status: dict[str, Any], now: datetime) -> Dashboard:
    run = status["active_run"]
    return replace(
        dashboard,
        standing=ManagerStanding.ANSWERING,
        working_on=None if run is None else run["event"],
        elapsed_seconds=None if run is None else _seconds_since(now, run["started_at"]),
        silent_seconds=None if run is None else _seconds_since(now, run["last_output_at"]),
        notice=status["notice"],
        threads_live=frozenset(status["threads_live"]),
        frozen_on=status["frozen_on"],
        expected_branch=status["expected_branch"],
        seconds_left=status["seconds_left"],
        run_working=status["run_working"],
        release_requested=status["release_requested"],
        flags_changed_at=status["flags_changed_at"],
    )
