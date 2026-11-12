from dataclasses import dataclass
from typing import Protocol

from github_orchestrator.domain import Pr


@dataclass(frozen=True)
class HeldFolder:
    pr: Pr
    thread: str
    folder: str


@dataclass(frozen=True)
class StuckBranch:
    pr: Pr
    thread: str
    branch: str
    new_branch: str
    clone: str
    error: str


class NameMigration(Protocol):
    def migrated(self) -> bool: ...

    def held(self) -> list[HeldFolder]: ...

    def stuck(self) -> list[StuckBranch]: ...

    def close_sessions(self) -> None: ...

    def migrate(self) -> list[HeldFolder]: ...
