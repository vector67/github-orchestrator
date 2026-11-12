import logging
from collections.abc import Collection, Mapping
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from github_orchestrator.board_api.interface import (
    ListedMention,
    MentionDeferral,
    PrEnded,
    PrMilestone,
)
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
from github_orchestrator.mentions._deferrals import over, seen
from github_orchestrator.mentions._listing import (
    ListingFile,
    building_since,
    change_deferrals,
    deferrals,
    dismissal,
    dismissed,
    listed,
    started_before,
    write_listing,
)
from github_orchestrator.mentions.interface import PrNow, StartLine, StartUnread

log = logging.getLogger(__name__)

SEARCH_EVERY = timedelta(minutes=30)
CARD_BUILT_WITHIN = timedelta(hours=2)
KIND_PR_BODY = "pr-body"
OPEN = "OPEN"
UNKNOWN = "UNKNOWN"
ENDINGS = {"MERGED": PrEnded.MERGED, "CLOSED": PrEnded.CLOSED}


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
        self._dismissed: frozenset[str] = frozenset()

    def unbuilt(self) -> list[Pr]:
        return list(dict.fromkeys(mention.pr for mention in self._listing().listed().mentions
                                  if mention.building))

    def opened(self) -> list[Pr]:
        return [opened.pr for opened in self._listing().listed().opened]

    def settle_deferrals(self, prs: Mapping[Pr, PrNow]) -> None:
        if not deferrals(self._path):
            return
        listed = {dismissal(mention.pr, mention.comment_id): mention
                  for mention in self._listing().listed().mentions}
        now = self._clock()

        def settle(held: dict[str, MentionDeferral]) -> None:
            for key, deferral in list(held.items()):
                mention = listed.get(key)
                if mention is None:
                    continue
                if over(deferral, now=now, prs=prs, thread_spoken=self._spoken(mention),
                        pr_spoken=self._pr_spoken(deferral)):
                    del held[key]
                else:
                    held[key] = seen(deferral, prs)

        change_deferrals(self._path, settle)

    def _listing(self) -> ListingFile:
        return ListingFile(self._path, self._clock)

    def _spoken(self, mention: ListedMention) -> list[str]:
        card = (None if mention.thread is None
                else self._conversation_managers.of(mention.pr).get(mention.thread))
        return [] if card is None else _said_at(card)

    def _pr_spoken(self, deferral: MentionDeferral) -> list[str]:
        awaited = deferral.until_pr
        if awaited is None or awaited.state is not PrMilestone.ANY_ACTIVITY:
            return []
        return [moment for card in self._conversation_managers.of(awaited.pr).all()
                for moment in _said_at(card)]

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
        self._dismissed = dismissed(self._path)
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
                mentions += self._outstanding(pr, state,
                                              max(start, _moment(started[str(pr.repo)])), began)
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
                     began: datetime) -> list[ListedMention]:
        manager = self._conversation_managers.of(pr)
        found = manager.poll(state).mentions
        if found is None:
            raise _Unread(pr)
        dated = [replace(mention, at=_latest(mention.at or state.created_at, mention.edited_at))
                 for mention in found]
        outstanding = []
        github_state: str | None = None
        for mention in dated:
            if mention.answered or dismissal(pr, mention.comment_id) in self._dismissed:
                continue
            card = _card(manager, mention)
            if mention.at is not None and _moment(mention.at) >= start and not _closed(card,
                                                                                         mention):
                github_state = github_state or self._state(pr)
                outstanding.append(listed(pr, mention, url=self._url(pr, mention),
                                          on_board=card is not None,
                                          building=card is None and self._still_building(
                                              pr, mention, began, github_state),
                                          ended=ENDINGS.get(github_state)))
        return outstanding

    def _still_building(self, pr: Pr, mention: Mention, began: datetime,
                        github_state: str) -> bool:
        if github_state != OPEN:
            return False
        key = f"{pr}:{mention.thread}:{mention.comment_id}"
        since = self._building_before.get(key, began.isoformat())
        self._building[key] = since
        return began - _moment(since) < CARD_BUILT_WITHIN

    def _state(self, pr: Pr) -> str:
        try:
            relevance = self._pull_requests.relevance(pr)
        except Exception:
            log.exception("whether %s is open will not read; its mention cards stay building", pr)
            return OPEN
        return UNKNOWN if relevance is None or relevance.state is None else relevance.state

    def _url(self, pr: Pr, mention: Mention) -> str:
        if mention.comment_id is None or mention.kind == KIND_PR_BODY:
            return self._pull_requests.url(pr)
        return self._threads.comment_url(pr, CommentKind(mention.kind), mention.comment_id)


def _said_at(card: Conversation) -> list[str]:
    return [comment.created_at for comment in card.comments if comment.created_at is not None]


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
