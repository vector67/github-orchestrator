import json
import logging
from datetime import UTC

from github_orchestrator.board_api.interface import REVIEWED, Shelves
from github_orchestrator.domain import Pr, Sha, UtcClock
from github_orchestrator.working_copies import WorkingCopies

log = logging.getLogger(__name__)


class ShelvedReviews:
    def __init__(self, working_copies: WorkingCopies, shelves: Shelves) -> None:
        self._working_copies = working_copies
        self._shelves = shelves

    def keep(self, pr: Pr, sha: str, base_branch: str | None) -> None:
        shelf = self._shelves.of(pr)
        head = Sha.parse(sha)
        if head is None or sha in shelf.list(REVIEWED):
            return
        history = self._working_copies.checkout(pr).revisions.pr_commits(base_branch, head)
        if history is None:
            log.warning("Could not list the commits %s's review of %s saw", pr, sha)
            return
        saw = {"sha": sha, "fork": str(history.fork), "commits": [
            {"sha": str(commit.sha), "parents": [str(parent) for parent in commit.parents],
             "subject": commit.subject, "author": commit.author,
             "authored_at": commit.authored_at.astimezone(UTC).strftime(UtcClock.STAMP)}
            for commit in history.commits]}
        shelf.save(REVIEWED, sha, json.dumps(saw, ensure_ascii=False, separators=(",", ":")).encode())
