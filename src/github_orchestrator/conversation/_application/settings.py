from dataclasses import dataclass


@dataclass(frozen=True)
class ThreadsConfig:
    gh_account: str
    agents_enabled: bool
    max_thread_runs: int
    agent_timeout: int
    poll_interval: int
    tracker: str | None = None
    tracker_project: str | None = None
