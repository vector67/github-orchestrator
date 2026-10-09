import logging

from github_orchestrator.domain import Pr, Repo
from github_orchestrator.github._gh_cli import Gh
from github_orchestrator.github._pull_requests import STATE_FIELDS, pulls, state_of
from github_orchestrator.github._threads import CONNECTIONS, CURSORS, first_page_threads
from github_orchestrator.github.interface import PullRequestState, Thread

log = logging.getLogger(__name__)

CHUNK = 10


def fetch_ahead(gh: Gh, account: str, prs: list[Pr]
                ) -> tuple[dict[Pr, PullRequestState], dict[Pr, list[Thread]]]:
    states: dict[Pr, PullRequestState] = {}
    threads: dict[Pr, list[Thread]] = {}
    by_repo: dict[Repo, list[Pr]] = {}
    for pr in dict.fromkeys(prs):
        by_repo.setdefault(pr.repo, []).append(pr)
    for repo_prs in by_repo.values():
        for start in range(0, len(repo_prs), CHUNK):
            chunk = repo_prs[start:start + CHUNK]
            found, errors = pulls(gh, chunk, STATE_FIELDS + CONNECTIONS, CURSORS)
            if errors:
                log.warning("fetching %d PRs of %s ahead carried errors: %s",
                            len(chunk), chunk[0].repo, errors)
            for pr in chunk:
                pull = found.get(f"pr{pr.number}")
                if not isinstance(pull, dict):
                    continue
                states[pr] = state_of(gh, account, pr, pull)
                listed = first_page_threads(gh, pr, pull)
                if listed is not None:
                    threads[pr] = listed
    return states, threads
