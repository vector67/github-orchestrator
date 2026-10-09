import os
import re
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class ScriptEnded(BaseException):
    pass


class ManualClock:
    def __init__(self, start: datetime = NOW) -> None:
        self.wall = start
        self.mono = 1000.0

    def now(self) -> datetime:
        return self.wall

    def monotonic(self) -> float:
        return self.mono

    def advance(self, seconds: float) -> None:
        self.wall += timedelta(seconds=seconds)
        self.mono += seconds


Item = str | None | BaseException | Callable[[], None]


class ScriptedSleep:
    def __init__(self, *script: None | BaseException | Callable[[], None],
                 clock: ManualClock) -> None:
        self._items = deque(script)
        self.clock = clock
        self.slept: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.slept.append(seconds)
        if not self._items:
            raise ScriptEnded
        item = self._items.popleft()
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            item()
        self.clock.advance(seconds)


class ScriptedTerminal:
    def __init__(self, *script: Item, columns: int = 100, lines: int = 40,
                 clock: ManualClock | None = None) -> None:
        self._items: deque[Item] = deque()
        for item in script:
            if isinstance(item, str):
                self._items.extend(item)
            else:
                self._items.append(item)
        self.columns = columns
        self.lines = lines
        self.clock = clock
        self.frames: list[str] = []
        self.timeouts: list[float] = []
        self.sessions_entered = 0
        self.sessions_left = 0
        self.in_session = False

    @contextmanager
    def session(self) -> Iterator[None]:
        self.sessions_entered += 1
        self.in_session = True
        try:
            yield
        finally:
            self.in_session = False
            self.sessions_left += 1

    def read_char(self, timeout: float) -> str | None:
        self.timeouts.append(timeout)
        if not self._items:
            raise ScriptEnded
        item = self._items.popleft()
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            item()
            return None
        if item is None and self.clock is not None:
            self.clock.advance(timeout)
        return item

    def draw(self, frame: str) -> None:
        self.frames.append(frame)

    def size(self) -> os.terminal_size:
        return os.terminal_size((self.columns, self.lines))

    @property
    def unread(self) -> int:
        return len(self._items)

    def text(self, index: int = -1) -> str:
        return _ANSI.sub("", self.frames[index])

    @property
    def screen(self) -> str:
        return self.text(-1)
