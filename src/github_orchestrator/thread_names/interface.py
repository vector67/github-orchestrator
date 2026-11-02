from dataclasses import dataclass
from typing import Protocol

from github_orchestrator.domain import Pr


@dataclass(frozen=True)
class HeldFolder:
    pr: Pr
    thread: str
    folder: str


class NameMigration(Protocol):
    def migrated(self) -> bool: ...

    def held(self) -> list[HeldFolder]: ...

    def close_sessions(self) -> None: ...

    def migrate(self) -> list[HeldFolder]: ...
