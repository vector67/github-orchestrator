from typing import Protocol


class Cli(Protocol):
    def main(self, argv: list[str]) -> int: ...
