from pathlib import Path
from typing import Protocol


class BoardExtension(Protocol):
    def prepare(self) -> Path | str: ...
