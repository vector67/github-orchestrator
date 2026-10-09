import itertools
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from github_orchestrator.thread_records import PrRecords, ThreadRecords
from github_orchestrator.wiring import ThreadRecordsWiring, wire
from tests.builders import a_pr

REPO = "owner/name"
PR = 5
THE_PR = a_pr(PR, REPO)
KEY = "PRRT_kwDO"
VERSION = 2
THREAD = "json"


def ticking_clock() -> Callable[[], datetime]:
    start = datetime(2026, 3, 1, tzinfo=timezone.utc)
    ticks = itertools.count()
    return lambda: start + timedelta(seconds=next(ticks))


def disk_thread_records(threads_dir: Path) -> ThreadRecords:
    records: ThreadRecords = wire(ThreadRecordsWiring(threads_dir)).get(ThreadRecords)
    return records


def thread(key: str = KEY, **fields: object) -> dict[str, Any]:
    return {"thread_key": key, **fields}


def keep(records: PrRecords, document: dict[str, Any]) -> None:
    records.save(THREAD, document["thread_key"],
                 json.dumps({"version": VERSION} | document).encode())
