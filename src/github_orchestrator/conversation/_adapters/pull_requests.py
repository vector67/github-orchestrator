from github_orchestrator.change_detection import ChangeDetection, Facts
from github_orchestrator.conversation._domain.conversation import (
    ROLE_AUTHOR,
    ROLE_REVIEWER,
)
from github_orchestrator.domain import Pr
from github_orchestrator.github import PullRequests as GitHubPullRequests


class PullRequests:
    def __init__(self, change_detection: ChangeDetection, pr: Pr,
                 github: GitHubPullRequests) -> None:
        self._change_detection = change_detection
        self._pr = pr
        self._github = github
        self._role: str | None = None

    def ci_green(self) -> bool | None:
        facts = self._change_detection.facts(self._pr)
        if facts is None or facts.ci_status is None:
            return None
        return facts.ci_passed

    def head_sha(self) -> str | None:
        facts = self._facts()
        return (facts.head_sha if facts else None) or None

    def base_branch(self) -> str | None:
        facts = self._facts()
        return (facts.base_branch if facts else None) or None

    def branch(self) -> str | None:
        facts = self._facts()
        return (facts.branch if facts else None) or None

    def ticket(self) -> str | None:
        facts = self._facts()
        return None if facts is None else facts.ticket

    def title(self) -> str | None:
        facts = self._facts()
        return (facts.title if facts else None) or None

    def role(self) -> str | None:
        if self._role is None:
            facts = self._facts()
            is_author = None if facts is None else facts.is_author
            if is_author is not None:
                self._role = ROLE_AUTHOR if is_author else ROLE_REVIEWER
        return self._role

    def author(self) -> str | None:
        facts = self._facts()
        return (facts.author if facts else None) or None

    def _facts(self) -> Facts | None:
        return self._change_detection.facts(self._pr)

    def is_closed(self, number: int) -> bool | None:
        return self._github.is_closed(Pr(self._pr.repo, number))
