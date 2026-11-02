from github_orchestrator.thread_names.interface import HeldFolder


class FakeNameMigration:
    def __init__(self, *held: list[HeldFolder]) -> None:
        self.rounds = list(held)
        self.tries = 0
        self.closed = 0
        self._migrated = False

    def migrated(self) -> bool:
        return self._migrated

    def held(self) -> list[HeldFolder]:
        return [] if self._migrated or not self.rounds else self.rounds[0]

    def close_sessions(self) -> None:
        self.closed += 1
        self.rounds = []

    def migrate(self) -> list[HeldFolder]:
        self.tries += 1
        held = self.rounds.pop(0) if self.rounds else []
        self._migrated = not held
        return held
