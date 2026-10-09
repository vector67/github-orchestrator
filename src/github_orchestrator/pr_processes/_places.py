from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Places:
    manager_records_dir: Path
    manager_logs_dir: Path
    environment: Mapping[str, str]
