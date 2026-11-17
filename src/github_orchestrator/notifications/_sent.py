import json
import logging
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from github_orchestrator.atomic_write import locked, write_atomically
from github_orchestrator.domain import LocalClock

log = logging.getLogger(__name__)

SENT = "sent.json"
KEPT = timedelta(days=3)


class SentFile:
    def __init__(self, root: Path, clock: LocalClock) -> None:
        self._path = root / SENT
        self._clock = clock
        self._lock = threading.Lock()

    def once(self, key: str, send: Callable[[], None]) -> None:
        with self._lock, locked(self._path.with_suffix(".lock")):
            now = self._clock()
            sent = {old: at for old, at in self._read().items() if _within(at, now)}
            if key in sent:
                return
            send()
            try:
                write_atomically(self._path, json.dumps({**sent, key: now.isoformat()}).encode())
            except OSError:
                log.exception("could not record %r as sent in %s", key, self._path)

    def _read(self) -> dict[str, object]:
        try:
            sent = json.loads(self._path.read_text())
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            log.warning("could not read %s; starting it afresh", self._path)
            return {}
        if not isinstance(sent, dict):
            log.warning("%s holds no record of what was sent; starting it afresh", self._path)
            return {}
        return sent


def _within(at: object, now: datetime) -> bool:
    try:
        return isinstance(at, str) and now - datetime.fromisoformat(at) < KEPT
    except (ValueError, TypeError):
        return False
