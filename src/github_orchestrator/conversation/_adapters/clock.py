from collections.abc import Callable
from datetime import datetime, timedelta

CREATED_AT_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
STARTED_AT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class SystemClock:
    def __init__(self, utcnow: Callable[[], datetime],
                 monotonic: Callable[[], float]) -> None:
        self._utcnow = utcnow
        self._monotonic = monotonic

    def now(self) -> str:
        return self._utcnow().strftime(STARTED_AT_FORMAT)

    def stamps(self, count: int) -> list[str]:
        stamped = []
        last = None
        for _ in range(count):
            now = self._utcnow()
            if last is not None and now <= last:
                now = last + timedelta(microseconds=1)
            last = now
            stamped.append(now.strftime(CREATED_AT_FORMAT))
        return stamped

    def monotonic(self) -> float:
        return self._monotonic()
