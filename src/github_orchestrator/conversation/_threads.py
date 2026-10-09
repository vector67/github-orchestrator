import builtins
import logging
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime

from github_orchestrator.agent_runs import History, Summaries, ThreadWork
from github_orchestrator.change_detection import ChangeDetection
from github_orchestrator.conversation._adapters.agents import ThreadAgents
from github_orchestrator.conversation._adapters.clock import SystemClock
from github_orchestrator.conversation._adapters.conversations import Conversations
from github_orchestrator.conversation._adapters.gists import Gists
from github_orchestrator.conversation._adapters.github_threads import GitHubThreads
from github_orchestrator.conversation._adapters.poller import (
    ThreadPoll,
    comment_cutoff,
    poll_threads,
)
from github_orchestrator.conversation._adapters.pull_requests import PullRequests
from github_orchestrator.conversation._application.asking import (
    Denied,
    ask,
    pending_of,
    send_review,
)
from github_orchestrator.conversation._application.decide import decide
from github_orchestrator.conversation._application.drafts import open_draft
from github_orchestrator.conversation._application.poll import (
    RoleUnknown,
    ask_due_verdicts,
    known_role,
    materialise,
    open_one,
    refresh,
    without_records,
)
from github_orchestrator.conversation._application.ports import (
    Held,
    Intent,
    PendingDecision,
    Ports,
    WorkspaceRefused,
    thread_workspace,
)
from github_orchestrator.conversation._application.presence import Presence
from github_orchestrator.conversation._application.report import (
    answered,
    not_a_key,
)
from github_orchestrator.conversation._application.settings import ThreadsConfig
from github_orchestrator.conversation._application.tick import Runs
from github_orchestrator.conversation._domain.apply import (
    apply,
)
from github_orchestrator.conversation._domain.commands import (
    Approve,
    Command,
    Confirm,
    DeclarePlan,
    Defer,
    Discard,
    EditDraft,
    Enrol,
    Fail,
    MoveBase,
    Place,
    PostNow,
    Reject,
    Reply,
    ReportFiled,
    ReportReady,
    Resolve,
    Retry,
    Rework,
    StartSession,
    StepDone,
    Stop,
    Unpark,
    WithdrawFromReview,
    WriteFix,
    report_without_code,
)
from github_orchestrator.conversation._domain.conversation import (
    ASSUMED_DONE,
    CONFIRMED,
    DEFERRED,
    DRAFT,
    OPEN,
    RESOLVED,
    ROLE_AUTHOR,
    UNREADABLE,
    WAITING_ON_REVIEWER,
    WAKE_MANUAL,
    Classification,
    Comment,
    Conversation,
    ConversationState,
    OperationState,
    PointedLine,
    Ticket,
    UnreadableRecord,
)
from github_orchestrator.conversation._domain.diff import KIND_REVIEW_SUMMARY
from github_orchestrator.conversation._domain.events import WorkspaceCut
from github_orchestrator.conversation._domain.mentions import (
    mentioning_threads,
    mentions,
    unanswered_threads,
)
from github_orchestrator.conversation._domain.news import (
    fix_queued,
    fix_started,
    handled_since_ready,
    opens_thread,
    reopens,
    replied_since,
)
from github_orchestrator.conversation._domain.review import Review, Verdict
from github_orchestrator.conversation._domain.standing import ErrorCode
from github_orchestrator.conversation._domain.thread import FetchedThread
from github_orchestrator.conversation._layout import is_thread_key
from github_orchestrator.conversation.interface import (
    Absorbed,
    Activity,
    ConversationManager,
    Counts,
    EditableConversation,
    Polled,
    PrFacts,
    ThreadActivity,
)
from github_orchestrator.domain import (
    Location,
    Monotonic,
    Pr,
    Sha,
    ThreadRow,
    UtcClock,
    author_kind_of,
    threads_listed,
)
from github_orchestrator.github import PullRequests as GitHubPullRequests
from github_orchestrator.github import PullRequestState, Reviews, Threads
from github_orchestrator.notifications import FixProgress, ThreadNews
from github_orchestrator.thread_records import ThreadRecords
from github_orchestrator.working_copies import WorkingCopies

log = logging.getLogger(__name__)

_ANSWERED = frozenset({OPEN, RESOLVED, ASSUMED_DONE, CONFIRMED})
_YOURS = _ANSWERED | {WAITING_ON_REVIEWER, DEFERRED}

@dataclass(frozen=True)
class _Arrival:
    key: str
    comment_id: int | None
    author: str
    body: str
    created_at: str
    opens_thread: bool
    reopens: bool
    review_comment: bool


def _announcing(pr: Pr, arrivals: Sequence[_Arrival]) -> Callable[[ThreadNews], None]:
    def announce(news: ThreadNews) -> None:
        for arrived in arrivals:
            news.comment_arrived(
                pr, arrived.key, comment_id=arrived.comment_id, author=arrived.author,
                body=arrived.body, created_at=arrived.created_at,
                opens_thread=arrived.opens_thread, reopens=arrived.reopens,
                review_comment=arrived.review_comment)

    return announce


@dataclass(frozen=True)
class _Modules:
    github_prs: GitHubPullRequests
    threads: Threads
    reviews: Reviews
    working_copies: WorkingCopies
    thread_work: ThreadWork
    summaries: Summaries
    history: History
    thread_records: ThreadRecords
    change_detection: ChangeDetection
    config: ThreadsConfig
    clock: SystemClock
    utcnow: Callable[[], datetime]
    presence: Presence


def _marked(conversation: Conversation, mentioning: frozenset[str]) -> Conversation:
    if mentioning.isdisjoint({conversation.key, conversation.github_node_id}):
        return conversation
    return replace(conversation, mention=True)


def _drawn(pending: PendingDecision | None) -> tuple[Intent | None, str | None]:
    if pending is None:
        return None, None
    return pending.intent, pending.reply


def _conversations(modules: _Modules, pr: Pr) -> Conversations:
    return Conversations(modules.thread_records.of(pr), modules.utcnow)


class _Pr:
    def __init__(self, modules: _Modules, pr: Pr) -> None:
        self.modules = modules
        self.pr = pr
        self._pull_requests = PullRequests(modules.change_detection, pr, modules.github_prs)
        config = modules.config
        self._agents = ThreadAgents(modules.thread_work, pr,
                                    lambda: modules.history.live(pr),
                                    account=config.gh_account, tracker=config.tracker,
                                    tracker_project=config.tracker_project,
                                    branch_ticket=self._pull_requests.ticket)
        self.runs = Runs()
        self.ports = self.built()

    def built(self) -> Ports:
        modules = self.modules
        config = modules.config
        return Ports(
            records=_conversations(modules, self.pr),
            github=GitHubThreads(modules.github_prs, modules.threads, modules.reviews,
                                 self.pr),
            git=modules.working_copies.checkout(self.pr),
            agents=self._agents,
            summaries=Gists(modules.summaries, config.agents_enabled, config.gh_account,
                            self._pull_requests.author),
            clock=modules.clock,
            config=config,
            pull_requests=self._pull_requests,
        )

    def recorded(self, key: str) -> Conversation | None:
        records = self.ports.records
        conversation = records.load(key)
        if conversation is None:
            return None
        return pending_of(conversation, *_drawn(records.pending_on(key)))

    def conversation(self, key: str) -> Conversation | None:
        try:
            found = self.recorded(key)
        except UnreadableRecord as exc:
            log.warning("%s: thread %s will not read: %s", self.pr, key, exc)
            return Conversation(key=key, state=UNREADABLE)
        return None if found is None else _marked(found, self.mentioning())

    def mentioning(self) -> frozenset[str]:
        facts = self.modules.change_detection.facts(self.pr)
        if facts is None or facts.is_author is not False:
            return frozenset()
        return unanswered_threads(facts.mentions)

    def decide(self) -> None:
        decide(self.pr, self.built())


def _ticket(project: str | None, title: str, body: str) -> Ticket | None:
    return None if project is None else Ticket(project=project, title=title, body=body)


class _Editable:
    def __init__(self, pr: _Pr, key: str, held: Held | None) -> None:
        self._pr = pr
        self._key = key
        self._held = held
        self._open = True

    def close(self) -> None:
        self._open = False

    def _still_open(self) -> None:
        if not self._open:
            raise RuntimeError(f"the edit of {self._key} has closed")

    def _loaded(self, held: Held) -> Conversation | None:
        pr, key = self._pr.pr, self._key
        try:
            if held.unreadable is not None:
                raise UnreadableRecord(held.unreadable)
            if held.conversation is None:
                return None
            return pending_of(held.conversation,
                              *_drawn(self._pr.ports.records.pending_on(key)))
        except UnreadableRecord as exc:
            log.warning("%s: thread %s will not read: %s", pr, key, exc)
            return Conversation(key=key, state=UNREADABLE)

    def _ask(self, command: Command) -> Conversation | Denied:
        self._still_open()
        pr, key, held = self._pr.pr, self._key, self._held
        conversation = None if held is None else self._loaded(held)
        if held is None or conversation is None:
            return Denied(ErrorCode.NOT_FOUND, f"{pr} has no thread called {key}")
        if conversation.is_unreadable:
            return Denied(ErrorCode.INTERNAL_REFUSAL, f"thread {key} will not read")
        try:
            return ask(self._pr.ports, conversation, command, held)
        except UnreadableRecord as exc:
            return Denied(ErrorCode.INTERNAL_REFUSAL, str(exc))

    def _answer(self, command: Command) -> Conversation | Denied:
        self._still_open()
        if self._held is None:
            return not_a_key(self._key)
        return answered(self._pr.pr, self._key, command, self._pr.ports, self._held)

    def approve(self, *, reply: str = "", delete_comment: bool = False,
                resolve: bool = False, message: str = "", ticket_project: str | None = None,
                ticket_title: str = "", ticket_body: str = "") -> Conversation | Denied:
        return self._ask(Approve(reply=reply, delete_comment=delete_comment,
                                 resolve=resolve, message=message,
                                 ticket=_ticket(ticket_project, ticket_title, ticket_body)))

    def rework(self, *, note: str = "",
               pointed: Sequence[tuple[str, int | None, str]] = (),
               include: Sequence[str] = ()) -> Conversation | Denied:
        lines = tuple(PointedLine(file=file, line=line, text=text)
                      for file, line, text in pointed)
        return self._ask(Rework(note=note, pointed=lines,
                                              include=tuple(include)))

    def start_session(self, *, steer: str = "",
                      pointed: Sequence[tuple[str, int | None, str]] = (),
                      include: Sequence[str] = ()) -> Conversation | Denied:
        lines = tuple(PointedLine(file=file, line=line, text=text)
                      for file, line, text in pointed)
        return self._ask(StartSession(steer=steer, pointed=lines, include=tuple(include)))

    def retry(self) -> Conversation | Denied:
        return self._ask(Retry())

    def fix(self) -> Conversation | Denied:
        return self._ask(WriteFix())

    def stop(self) -> Conversation | Denied:
        return self._ask(Stop())

    def resolve(self, *, reply: str = "", delete_comment: bool = False,
                resolve: bool = False,
                thumbs_up: bool = True) -> Conversation | Denied:
        return self._ask(Resolve(reply=reply, delete_comment=delete_comment,
                                 resolve=resolve, thumbs_up=thumbs_up))

    def reject(self, *, reply: str = "",
               delete_comment: bool = False) -> Conversation | Denied:
        return self._ask(Reject(reply=reply, delete_comment=delete_comment))

    def place(self, to: ConversationState, *, until: str = WAKE_MANUAL,
              note: str = "") -> Conversation | Denied:
        if to is ConversationState.DONE:
            return self._ask(Confirm())
        if to is ConversationState.DEFERRED:
            return self._ask(Defer(wake_on=until, note=note))
        return self._ask(Place(to))

    def unpark(self) -> Conversation | Denied:
        return self._ask(Unpark())

    def reply(self, text: str) -> Conversation | Denied:
        return self._ask(Reply(text))

    def mark_seen(self) -> None:
        self._still_open()
        held = self._held
        if held is not None and held.conversation is not None:
            held.conversation = replace(held.conversation,
                                        seen_at=self._pr.ports.clock.now())

    def edit(self, body: str, anchor: Location) -> Conversation | Denied:
        return self._ask(EditDraft(body=body, anchor=anchor))

    def enrol(self) -> Conversation | Denied:
        return self._ask(Enrol())

    def withdraw(self) -> Conversation | Denied:
        return self._ask(WithdrawFromReview())

    def discard(self) -> Conversation | Denied:
        return self._ask(Discard())

    def post_now(self) -> Conversation | Denied:
        return self._ask(PostNow())

    def plan(self, steps: Sequence[tuple[str, str | None]]) -> Conversation | Denied:
        return self._answer(DeclarePlan(steps=tuple(steps)))

    def step_done(self, indexes: Sequence[int]) -> Conversation | Denied:
        return self._answer(StepDone(indexes=tuple(indexes)))

    def ready(self, sha: str, *, tests: str | None = None,
              tests_note: str | None = None, note: str | None = None,
              summary: str | None = None, confidence: str | None = None,
              confidence_note: str | None = None) -> Conversation | Denied:
        return self._answer(ReportReady(
            sha=sha, on_base=self._on_base(sha), tests=tests, tests_note=tests_note,
            agent_note=note, summary=summary, confidence=confidence,
            confidence_note=confidence_note))

    def _on_base(self, sha: str) -> bool:
        conversation = None if self._held is None else self._held.conversation
        commit = Sha.parse(sha)
        if conversation is None or commit is None or conversation.fix.base_sha is None:
            return True
        return thread_workspace(self._pr.ports, conversation).descends(
            conversation.fix.base_sha, commit)

    def move_base(self, sha: str) -> Conversation | Denied:
        return self._answer(MoveBase(sha=sha))

    def not_a_fix(self, classification: Classification, text: str, *,
                  ticket_project: str | None = None, ticket_title: str = "",
                  ticket_body: str = "", filed_key: str | None = None,
                  filed_url: str = "") -> Conversation | Denied:
        if filed_key is not None:
            return self._answer(ReportFiled(key=filed_key, url=filed_url))
        return self._answer(report_without_code(
            classification, text, _ticket(ticket_project, ticket_title, ticket_body)))

    def fail(self, reason: str) -> Conversation | Denied:
        return self._answer(Fail(reason=reason))


class _ConversationManager:
    def __init__(self, modules: _Modules, pr: Pr) -> None:
        self._pr = _Pr(modules, pr)

    @contextmanager
    def editing(self, key: str) -> Iterator[EditableConversation]:
        if not is_thread_key(key):
            unheld = _Editable(self._pr, key, None)
            try:
                yield unheld
            finally:
                unheld.close()
            return
        with self._pr.ports.records.held(key) as held:
            editable = _Editable(self._pr, key, held)
            try:
                yield editable
            finally:
                editable.close()

    def get(self, key: str) -> Conversation | None:
        return self._pr.conversation(key)

    def all(self) -> builtins.list[Conversation]:
        records = self._pr.ports.records
        pending = records.pending()
        mentioning = self._pr.mentioning()
        return [_marked(pending_of(conversation, *_drawn(pending.get(conversation.key))),
                        mentioning)
                for conversation in records.list()]

    def open_draft(self, body: str, anchor: Location,
                   operation: str | None = None) -> Conversation | Denied:
        try:
            role = known_role(self._pr.ports)
        except RoleUnknown as unknown:
            return Denied(ErrorCode.INTERNAL_REFUSAL, str(unknown))
        return open_draft(self._pr.ports, body, anchor, role, operation)

    def open_thread(self, key: str, *, kind: str, path: str | None, line: int | None,
                    comment_id: int, author: str, body: str) -> str | None | Denied:
        if not is_thread_key(key):
            return not_a_key(key)
        ports = self._pr.ports
        try:
            known_role(ports)
        except RoleUnknown as unknown:
            return Denied(ErrorCode.INTERNAL_REFUSAL, str(unknown))
        opened_at = ports.clock.stamps(1)[0]
        thread = FetchedThread(
            key=key, kind=kind, path=path, line=line,
            comments=(Comment(id=comment_id, author=author, body=body,
                              created_at=opened_at, updated_at=opened_at),))
        try:
            opened = open_one(thread, opened_at, ports)
        except WorkspaceRefused as refused:
            return Denied(ErrorCode.GIT_FAILED, str(refused))
        with ports.records.update(opened.key) as update:
            conversation = update.conversation or opened
            cut = thread_workspace(ports, conversation).ensure()
            if cut.workspace is None:
                return Denied(ErrorCode.GIT_FAILED, cut.failure)
            outcome = apply(conversation, WorkspaceCut(base_sha=cut.workspace.base_sha))
            if outcome.conversation != conversation:
                update.conversation = outcome.conversation
            return cut.workspace.path

    def send_review(self, verdict: Verdict, body: str | None) -> Review | Denied:
        return send_review(self._pr.ports, verdict, body)

    def reviews(self) -> Sequence[Review]:
        return self._pr.ports.records.reviews()

    def facts(self) -> PrFacts:
        ports = self._pr.ports
        return PrFacts(title=ports.pull_requests.title(), url=ports.github.page(),
                       base_branch=ports.pull_requests.base_branch(),
                       branch=ports.pull_requests.branch(),
                       head_sha=ports.pull_requests.head_sha(),
                       is_author=_is_author(ports.pull_requests.role()),
                       account=ports.config.gh_account)

    def activity(self, conversation: Conversation) -> Activity:
        ports = self._pr.ports
        return Activity(last_action=ports.records.read_action(conversation.key),
                        progress=thread_workspace(ports, conversation).progress())

    def comment_url(self, conversation: Conversation, comment_id: int) -> str:
        return self._pr.ports.github.comment_page(conversation, comment_id)

    def too_long(self, text: str) -> str | None:
        return self._pr.ports.github.too_long(text)

    def poll(self, state: PullRequestState) -> Polled:
        modules, pr = self._pr.modules, self._pr.pr
        polled_at = comment_cutoff(modules.utcnow())
        records = _conversations(modules, pr)
        cursor = records.cursor()
        found = poll_threads(modules.threads, pr, bot_login=modules.config.gh_account,
                             old_snapshot=cursor, cutoff_iso=polled_at,
                             posted_reply_ids=records.posted_reply_ids(),
                             posted_comment_keys=records.posted_comment_keys())
        moved = found.snapshot or {}
        account = modules.config.gh_account
        found_mentions = None if found.fetched is None else mentions(
            found.fetched, account=account, pr_body=state.body, pr_author=state.author)
        mentioned = ([] if found_mentions is None or found.fetched is None
                     else mentioning_threads(found.fetched, found_mentions, account=account,
                                             pr_body=state.body, pr_author=state.author))
        mine = [comment.created_at for active in found.active
                for comment in active.new_comments
                if comment.author == account and comment.created_at]
        return Polled(
            polled_at=polled_at,
            my_last_comment_at=max(mine) if mine else None,
            comments_by_others=sum(
                1 for active in found.active for comment in active.new_comments
                if comment.author and comment.author != account
                and not _is_review_verdict(active.thread)),
            unresolved_count=found.unresolved_count,
            mentions=found_mentions,
            activity=_activity(found, polled_at,
                               self._unrecorded(found, mentioned, first=cursor is None),
                               first=cursor is None),
            _announce=_announcing(pr, () if cursor is None
                                  else self._arrivals(found, polled_at)),
            _keep=lambda: records.save_cursor(moved),
        )

    def _unrecorded(self, found: ThreadPoll, mentioned: Sequence[FetchedThread], *,
                    first: bool) -> list[FetchedThread]:
        ports = self._pr.ports
        if not first and _drains(ports):
            return []
        opening = found.open_review_threads
        return without_records(
            opening + [thread for thread in mentioned if thread not in opening], ports)

    def _arrivals(self, found: ThreadPoll, polled_at: str) -> tuple[_Arrival, ...]:
        account = self._pr.modules.config.gh_account
        arrivals: list[_Arrival] = []
        for active in found.active:
            thread = active.thread
            record = self.get(thread.key)
            root = thread.comments[0].id if thread.comments else None
            for comment in active.new_comments:
                if comment.author == account:
                    continue
                arrivals.append(_Arrival(
                    key=thread.key, comment_id=comment.id,
                    author=comment.author, body=comment.body,
                    created_at=comment.created_at or polled_at,
                    opens_thread=opens_thread(record, is_root=comment.id == root),
                    reopens=reopens(record,
                                    first=not any(a.key == thread.key for a in arrivals)),
                    review_comment=thread.kind == KIND_REVIEW_SUMMARY))
        return tuple(arrivals)

    def absorb(self, activity: ThreadActivity) -> Absorbed:
        pr, ports = self._pr.pr, self._pr.ports
        if _drains(ports):
            log.info("%s: agents disabled — draining %s without records", pr, activity.kind)
            return Absorbed(threads=len(activity.threads), created=(), refreshed=(),
                            drained=True)
        cutoff = activity.cutoff
        created = materialise(pr, list(activity.threads), ports, cutoff=cutoff)
        refreshed = refresh(pr, list(activity.stale), ports, cutoff=cutoff)
        return Absorbed(threads=len(activity.threads), created=tuple(created),
                        refreshed=tuple(refreshed), drained=False)

    def tick(self, news: ThreadNews, *, on_hold: bool) -> None:
        pr, ports = self._pr.pr, self._pr.ports
        if not on_hold:
            try:
                if ports.records.pending() or _review_waiting(ports):
                    self._pr.decide()
            except Exception:
                log.exception("loop %s: the board's pending decisions could not be read", pr)
        try:
            ask_due_verdicts(ports)
        except Exception:
            log.exception("loop %s: the threads waiting on a verdict could not be asked", pr)
        for settled in self._pr.runs.pump_and_schedule(pr, ports, schedule=not on_hold):
            _announce_settled(news, pr, settled)

    def counts(self) -> Counts:
        runs, ports = self._pr.runs, self._pr.ports
        held = ports.records.list()
        account = self._pr.modules.config.gh_account
        listed_at = ports.clock.now()
        readable, unreadable = threads_listed(self.all())
        yours = [conversation for conversation in held
                 if conversation.author == account and conversation.state in _YOURS]
        return Counts(queued=runs.queued_count(ports), live=runs.live_count(ports),
                      proposed=runs.proposed_count(ports),
                      drafts=sum(1 for conversation in held if conversation.state == DRAFT),
                      answered=tuple(conversation.key for conversation in yours
                                     if conversation.state in _ANSWERED),
                      rows=tuple(ThreadRow(
                          key=conversation.key, standing=conversation.standing.value,
                          state=conversation.state,
                          author_kind=author_kind_of(conversation.author, account),
                          updated_at=conversation.updated_at)
                          for conversation in readable),
                      unreadable=tuple(unreadable), listed_at=listed_at)

    def recheck(self, conversation: Conversation) -> None:
        self._pr.modules.presence.check_later(self._pr.pr, conversation.key, self._pr.ports)


def _announce_settled(news: ThreadNews, pr: Pr, conversation: Conversation) -> None:
    fix = conversation.fix
    if fix.is_proposed:
        news.fix_ready(pr, conversation.key, gist=conversation.gist,
                       comments=[(comment.author, comment.body)
                                 for comment in conversation.comments],
                       fix_summary=fix.summary)
    elif fix.is_declined:
        news.needs_your_call(pr, author=conversation.author,
                             classification=fix.classification, reason=fix.reason)
    elif fix.has_failed:
        news.fix_failed(pr, gist=conversation.gist, author=conversation.author,
                        reason=fix.reason)


def _is_author(role: str | None) -> bool | None:
    return None if role is None else role == ROLE_AUTHOR


def _drains(ports: Ports) -> bool:
    return ports.pull_requests.role() == ROLE_AUTHOR and not ports.config.agents_enabled


def _review_waiting(ports: Ports) -> bool:
    return any(review.state == OperationState.PENDING for review in ports.records.reviews())


def _is_review_verdict(thread: FetchedThread) -> bool:
    return (thread.kind == KIND_REVIEW_SUMMARY and thread.state is not None
            and thread.state.is_verdict)


def _activity(found: ThreadPoll, cutoff: str, unrecorded: Sequence[FetchedThread], *,
              first: bool) -> ThreadActivity | None:
    heard = [] if first else [active.thread for active in found.active]
    threads = heard + [thread for thread in unrecorded if thread not in heard]
    if not threads and not found.stale:
        return None
    return ThreadActivity(threads=tuple(threads), stale=tuple(found.stale), cutoff=cutoff)


class GitHubConversationManagerFactory:
    def __init__(self, pull_requests: GitHubPullRequests, threads: Threads,
                 reviews: Reviews, working_copies: WorkingCopies,
                 thread_work: ThreadWork, summaries: Summaries, history: History,
                 thread_records: ThreadRecords,
                 change_detection: ChangeDetection, config: ThreadsConfig,
                 clock: UtcClock, monotonic: Monotonic) -> None:
        self._modules = _Modules(pull_requests, threads, reviews, working_copies,
                                 thread_work, summaries, history, thread_records,
                                 change_detection, config, SystemClock(clock, monotonic),
                                 clock, Presence())

    def of(self, pr: Pr) -> ConversationManager:
        return _ConversationManager(self._modules, pr)

    def _recorded(self, pr: Pr, key: str) -> Conversation | None:
        return _Pr(self._modules, pr).recorded(key)

    def fix_still_news(self, pr: Pr, key: str) -> bool:
        try:
            return not handled_since_ready(self._recorded(pr, key))
        except UnreadableRecord:
            return True

    def comment_still_news(self, pr: Pr, key: str, since: str) -> bool:
        try:
            record = self._recorded(pr, key)
        except UnreadableRecord:
            return True
        return not replied_since(record, self._modules.config.gh_account, since)

    def fix_progress(self, pr: Pr, key: str) -> FixProgress:
        try:
            record = self._recorded(pr, key)
        except UnreadableRecord:
            return FixProgress.NONE
        if fix_queued(record):
            return FixProgress.QUEUED
        if fix_started(record):
            return FixProgress.STARTED
        return FixProgress.NONE
