import logging
from collections.abc import Collection
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from github_orchestrator.board_api.interface import ListedMention
from github_orchestrator.conversation import (
    Conversation,
    ConversationManager,
    ConversationManagerFactory,
    ConversationState,
)
from github_orchestrator.domain import Mention, Pr, Repo, UtcClock
from github_orchestrator.github import (
    CommentKind,
    PullRequests,
    PullRequestState,
    Threads,
)
from github_orchestrator.mentions._listing import (
    ListingFile,
    building_since,
    listed,
    started_before,
    write_listing,
)
from github_orchestrator.mentions.interface import StartLine, StartUnread

log = logging.getLogger(__name__)

SEARCH_EVERY = timedelta(minutes=30)
CARD_BUILT_WITHIN = timedelta(hours=2)
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
        self._building_before: dict[str, str] = {}
        self._building: dict[str, str] = {}

    def unbuilt(self) -> list[Pr]:
        return list(dict.fromkeys(mention.pr for mention in ListingFile(self._path).listed().mentions
                                  if mention.building))

    def search_if_due(self) -> None:
        began = self._clock()
        if self._searched_at is not None and began - self._searched_at < SEARCH_EVERY:
            return
        try:
            start = self._start_line.mentions_start(began)
        except ValueError as unread:
            raise StartUnread(str(unread)) from unread
        self._searched_at = began
        started = self._started(began, start)
        self._building_before = building_since(self._path)
        self._building = {}
        mentions: list[ListedMention] = []
        held = False
        try:
            found = self._pull_requests.search(self._repos, "mentions", updated_since=start)
            for pr in self._configured(found):
                try:
                    state = self._pull_requests.pr_state(pr)
                except Exception:
                    log.exception("mentions in %s skipped: its state will not read", pr)
                    held = True
                    continue
                outstanding = self._outstanding(pr, state,
                                                max(start, _moment(started[str(pr.repo)])),
                                                began)
                if outstanding is None:
                    log.warning("GitHub says %s mentions you, but it names no gh_account the "
                                "config gives; did your GitHub login change?", pr)
                    held = True
                    continue
                mentions += outstanding
        except _Unread as unread:
            log.warning("mentions not searched: the threads of %s will not read", unread.pr)
            return
        write_listing(self._path, began, started, mentions, self._building)
        if not mentions and not held:
            self._start_line.move_mentions_start(began)

    def _configured(self, found: list[Pr]) -> list[Pr]:
        spelled = {str(repo).casefold(): repo for repo in self._repos}
        configured = []
        for pr in found:
            repo = spelled.get(str(pr.repo).casefold())
            if repo is None:
                log.warning("mention in %s skipped: no configured repo is %s", pr, pr.repo)
            else:
                configured.append(replace(pr, repo=repo))
        return configured

    def _started(self, began: datetime, start: datetime) -> dict[str, str]:
        before = started_before(self._path)
        if before is None:
            return {str(repo): start.isoformat() for repo in self._repos}
        return {str(repo): before.get(str(repo), began.isoformat()) for repo in self._repos}

    def _outstanding(self, pr: Pr, state: PullRequestState, start: datetime,
                     began: datetime) -> list[ListedMention] | None:
        manager = self._conversation_managers.of(pr)
        found = manager.poll(state).mentions
        if found is None:
            raise _Unread(pr)
        if not found:
            return None
        dated = [replace(mention, at=_latest(mention.at or state.created_at, mention.edited_at))
                 for mention in found]
        outstanding = []
        for mention in dated:
            if mention.answered:
                continue
            card = _card(manager, mention)
            if mention.at is not None and _moment(mention.at) >= start and not _closed(card,
                                                                                         mention):
                outstanding.append(listed(pr, mention, url=self._url(pr, mention),
                                          on_board=card is not None,
                                          building=card is None and self._still_building(
                                              pr, mention, began)))
        return outstanding

    def _still_building(self, pr: Pr, mention: Mention, began: datetime) -> bool:
        if not self._open(pr):
            return False
        key = f"{pr}:{mention.thread}:{mention.comment_id}"
        since = self._building_before.get(key, began.isoformat())
        self._building[key] = since
        return began - _moment(since) < CARD_BUILT_WITHIN

    def _open(self, pr: Pr) -> bool:
        try:
            relevance = self._pull_requests.relevance(pr)
        except Exception:
            log.exception("whether %s is open will not read; its mention cards stay building", pr)
            return True
        return relevance is not None and relevance.is_open

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
    moment = datetime.fromisoformat(iso)
    return moment.astimezone() if moment.tzinfo is None else moment
