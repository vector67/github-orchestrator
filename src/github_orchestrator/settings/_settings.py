from dataclasses import dataclass
from pathlib import Path

from github_orchestrator.domain import Clone, Repo
from github_orchestrator.settings._config import (
    ConfigError,
    OrchestratorConfig,
    child_environment,
)
from github_orchestrator.settings._logging import log_path
from github_orchestrator.settings.interface import Process


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    config_path: Path
    config: OrchestratorConfig
    problem: ConfigError | None = None

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"

    @property
    def queues_dir(self) -> Path:
        return self.data_dir / "queues"

    @property
    def notifications_dir(self) -> Path:
        return self.data_dir / "notifications"

    @property
    def transcripts_dir(self) -> Path:
        return self.data_dir / "transcripts"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def on_hold_dir(self) -> Path:
        return self.data_dir / "on_hold"

    @property
    def dismissed_dir(self) -> Path:
        return self.data_dir / "dismissed"

    @property
    def mismatched_dir(self) -> Path:
        return self.data_dir / "mismatched"

    @property
    def pr_managers_dir(self) -> Path:
        return self.data_dir / "pr_managers"

    @property
    def worktree_conflicts_dir(self) -> Path:
        return self.data_dir / "worktree_conflicts"

    @property
    def threads_dir(self) -> Path:
        return self.data_dir / "threads"

    @property
    def thread_worktrees_dir(self) -> Path:
        return self.data_dir / "thread-worktrees"

    @property
    def board_dir(self) -> Path:
        return self.data_dir / "board"

    @property
    def archive_dir(self) -> Path:
        return self.data_dir / "archive"

    @property
    def runs_log(self) -> Path:
        return self.data_dir / "runs.jsonl"

    @property
    def watcher_heartbeat(self) -> Path:
        return self.data_dir / "watcher.heartbeat"

    @property
    def watcher_failures(self) -> Path:
        return self.data_dir / "watcher.failures.json"

    @property
    def watcher_lock(self) -> Path:
        return self.data_dir / "watcher.lock"

    @property
    def newest_release(self) -> Path:
        return self.data_dir / "newest_release.json"

    @property
    def tour_due(self) -> Path:
        return self.data_dir / "tour_due"

    @property
    def restart_lock(self) -> Path:
        return self.data_dir / "restart-all.lock"

    @property
    def repos(self) -> dict[Repo, Clone]:
        default = self.config.new_worktree_command
        return {
            entry.repo: Clone(
                Path(entry.local_path).expanduser(),
                default if entry.new_worktree_command is None else entry.new_worktree_command)
            for entry in self.config.repos
        }

    def log_path(self, process: Process) -> Path:
        return log_path(self.logs_dir, process)

    def child_environment(self) -> dict[str, str]:
        return child_environment(self.data_dir, self.config_path)
