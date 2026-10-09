from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from github_orchestrator.domain import Clone, Repo


@dataclass(frozen=True)
class WatcherConfig:
    repos: Mapping[Repo, Clone]
    gh_account: str
    config_location: str
    agents_enabled: bool
    poll_interval: int
    heartbeat: Path
    lock: Path
    failures: Path
    log_file: Path
    hub_port: int
    home: Path
    archive_dir: Path
    newest_release: Path
    tour_due: Path
    check_for_updates: bool
    github_token: str | None
