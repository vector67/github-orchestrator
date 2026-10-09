from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class Badge(Enum):
    READY = "ready"
    FAILED = "failed"
    NEEDS_YOU = "needs-you"
    INFO = "info"
    COMMENTS = "comments"


@dataclass(frozen=True)
class Announcement:
    badge: Badge
    title: str
    body: str
    key: str
    link: str | None


class Desktop(Protocol):
    def announce(self, badge: Badge, title: str, body: str, key: str,
                 link: str | None) -> str | None: ...

    def open_url(self, url: str) -> str | None: ...

    def notifications(self, path: str) -> tuple[str, str] | None: ...
