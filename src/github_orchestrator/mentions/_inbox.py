import logging
from collections.abc import Collection
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from github_orchestrator.conversation import (
    ConversationManager,
    ConversationManagerFactory,
    ConversationState,
)
from github_orchestrator.domain import Mention, Pr, Repo, UtcClock
from github_orchestrator.github import PullRequests
from github_orchestrator.mentions._listing import listed, started_before, write_listing
from github_orchestrator.mentions.interface import StartLine

log = logging.getLogger(__name__)

SEARCH_EVERY = timedelta(minutes=30)


class _Unread(Exception):
    def __init__(self, pr: Pr) -> None:
        super().__init__(str(pr))
        self.pr = pr


class GitHubMentionsInbox:
    def __init__(self, repos: Collection[Repo], pull_requests: PullRequests,
                 conversation_managers: ConversationManagerFactory, start_line: StartLine,
                 clock: UtcClock, path: Path) -> None:
        self._repos = repos
        self._pull_requests = pull_requests
        self._conversation_managers = conversation_managers
        self._start_line = start_line
        self._clock = clock
        self._path = path
        self._searched_at: datetime | None = None

    def search_if_due(self) -> None:
        began = self._clock()
        if self._searched_at is not None and began - self._searched_at < SEARCH_EVERY:
            return
        self._searched_at = began
        start = self._start_line.mentions_start(began)
        started = self._started(began, start)
        try:
            mentions = [listed(pr, mention)
                        for pr in self._pull_requests.mentioned_since(self._repos, start)
                        for mention in self._outstanding(
                            pr, max(start, _moment(started[str(pr.repo)])))]
        except _Unread as unread:
            log.warning("mentions not searched: the threads of %s will not read", unread.pr)
            return
        write_listing(self._path, began, started, mentions)
        if not mentions:
            self._start_line.move_mentions_start(began)

    def _started(self, began: datetime, start: datetime) -> dict[str, str]:
        before = started_before(self._path)
        if before is None:
            return {str(repo): start.isoformat() for repo in self._repos}
        return {str(repo): before.get(str(repo), began.isoformat()) for repo in self._repos}

    def _outstanding(self, pr: Pr, start: datetime) -> list[Mention]:
        state = self._pull_requests.pr_state(pr)
        manager = self._conversation_managers.of(pr)
        found = manager.poll(state).mentions
        if found is None:
            raise _Unread(pr)
        dated = [replace(mention, at=_latest(mention.at or state.created_at, mention.edited_at))
                 for mention in found]
        return [mention for mention in dated
                if mention.at is not None and _moment(mention.at) >= start
                and not _closed(manager, mention)]


def _closed(manager: ConversationManager, mention: Mention) -> bool:
    card = None if mention.thread is None else manager.get(mention.thread)
    return (card is not None and card.standing is ConversationState.DONE
            and card.state_changed_at is not None and mention.at is not None
            and _moment(card.state_changed_at) >= _moment(mention.at))


def _latest(*moments: str | None) -> str | None:
    known = [moment for moment in moments if moment is not None]
    return max(known, key=_moment) if known else None


def _moment(iso: str) -> datetime:
    return datetime.fromisoformat(iso)
