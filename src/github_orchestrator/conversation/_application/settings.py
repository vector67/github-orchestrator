from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from github_orchestrator.domain import Repo

CREATE_PR = "create-pr"


@dataclass(frozen=True)
class ThreadsConfig:
    gh_account: str
    agents_enabled: bool
    max_thread_runs: int
    agent_timeout: int
    poll_interval: int
    tracker: str | None = None
    tracker_project: str | None = None
    untested_repos: frozenset[Repo] = frozenset()
    has_tests: bool = True
    pr_skills: Mapping[Repo, str] = field(default_factory=dict)
    drafts: Mapping[Repo, bool] = field(default_factory=dict)
    pr_skill: str = CREATE_PR
    draft: bool | None = None


def for_repo(config: ThreadsConfig, repo: Repo) -> ThreadsConfig:
    return replace(config, has_tests=repo not in config.untested_repos,
                   pr_skill=config.pr_skills.get(repo, config.pr_skill),
                   draft=config.drafts.get(repo))
