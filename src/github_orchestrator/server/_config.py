from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServerConfig:
    port: int
    workers: int
    lock: Path
    pid: Path
