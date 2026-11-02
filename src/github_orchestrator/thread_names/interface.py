from typing import Protocol


class NameMigration(Protocol):
    def migrated(self) -> bool: ...

    def migrate(self) -> None: ...
