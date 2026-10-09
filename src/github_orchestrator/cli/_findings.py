from dataclasses import dataclass
from enum import Enum


class Level(Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "FAIL"


@dataclass(frozen=True)
class Finding:
    level: Level
    reason: str
    fix: str = ""


def ok(reason: str) -> Finding:
    return Finding(Level.OK, reason)


def warn(reason: str, fix: str) -> Finding:
    return Finding(Level.WARN, reason, fix)


def fail(reason: str, fix: str) -> Finding:
    return Finding(Level.FAIL, reason, fix)
