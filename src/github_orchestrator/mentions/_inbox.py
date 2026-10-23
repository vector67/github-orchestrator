import logging
from collections.abc import Collection
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from github_orchestrator.conversation import (
    Conversation,
    ConversationManager,
    ConversationManagerFactory,
    ConversationState,
)
from github_orchestrator.domain import Mention, Pr, Repo, UtcClock
from github_orchestrator.github import CommentKind, PullRequests, Threads
from github_orchestrator.mentions._listing import listed, started_before, write_listing
from github_orchestrator.mentions.interface import StartLine

log = logging.getLogger(__name__)

SEARCH_EVERY = timedelta(minutes=30)
KIND_PR_BODY = "pr-body"


class _Unread(Exception):
    def __init__(self, pr: Pr) -> None:
        super().__init__(str(pr))
        self.pr = pr


class GitHubMentionsInbox:
    def __init__(self, repos: Collection[Repo], pull_requests: PullRequests, threads: Threads,
                 conversation_managers: ConversationManagerFactory, start_line: StartLine,
                 clock: UtcClock, path: Path) -> None:
        self._repos = repos
        self._pull_requests = pull_requests
        self._threads = threads
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
            mentions = [entry for pr in self._pull_requests.mentioned_since(self._repos, start)
                        for entry in self._outstanding(
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

    def _outstanding(self, pr: Pr, start: datetime) -> list[dict[str, Any]]:
        state = self._pull_requests.pr_state(pr)
        manager = self._conversation_managers.of(pr)
        found = manager.poll(state).mentions
        if found is None:
            raise _Unread(pr)
        dated = [replace(mention, at=_latest(mention.at or state.created_at, mention.edited_at))
                 for mention in found]
        outstanding = []
        for mention in dated:
            card = _card(manager, mention)
            if mention.at is not None and _moment(mention.at) >= start and not _closed(card,
                                                                                         mention):
                outstanding.append(listed(pr, mention, url=self._url(pr, mention),
                                          card=card is not None))
        return outstanding

    def _url(self, pr: Pr, mention: Mention) -> str:
        if mention.comment_id is None or mention.kind == KIND_PR_BODY:
            return self._pull_requests.url(pr)
        return self._threads.comment_url(pr, CommentKind(mention.kind), mention.comment_id)


def _card(manager: ConversationManager, mention: Mention) -> Conversation | None:
    return None if mention.thread is None else manager.get(mention.thread)


def _closed(card: Conversation | None, mention: Mention) -> bool:
    return (card is not None and card.standing is ConversationState.DONE
            and card.state_changed_at is not None and mention.at is not None
            and _moment(card.state_changed_at) >= _moment(mention.at))


def _latest(*moments: str | None) -> str | None:
    known = [moment for moment in moments if moment is not None]
    return max(known, key=_moment) if known else None


def _moment(iso: str) -> datetime:
    return datetime.fromisoformat(iso)
