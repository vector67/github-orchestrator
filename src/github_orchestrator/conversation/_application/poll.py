import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from github_orchestrator.conversation._application.ports import Ports
from github_orchestrator.conversation._application.runner import perform, run
from github_orchestrator.conversation._domain.apply import create
from github_orchestrator.conversation._domain.conversation import (
    ROLE_AUTHOR,
    Anchor,
    Comment,
    Conversation,
)
from github_orchestrator.conversation._domain.events import Refresh, Reopen, VerdictDue
from github_orchestrator.conversation._domain.machine import Accepted, Deferred, Refused
from github_orchestrator.conversation._domain.steps import First
from github_orchestrator.conversation._domain.thread import FetchedThread
from github_orchestrator.conversation._domain.verdict import verdict_due
from github_orchestrator.domain import Pr

log = logging.getLogger(__name__)

OPEN_WORKERS = 4


def _open_or_skip(pr: Pr, thread: FetchedThread, created_at: str,
                  ports: Ports, cutoff: str | None) -> Conversation | None:
    try:
        return open_one(thread, created_at, ports, cutoff=cutoff)
    except Exception:
        log.exception("materialise %s: thread %s failed; skipping it",
                      pr, thread.key)
        return None


def _posted_before_it_was_listed(conversation: Conversation,
                                 thread: FetchedThread) -> bool:
    """A thread the board opened itself and GitHub did not list straight
    after the post.

    The post names the comment it created but not the thread, so the draft
    kept a null node id. The root comment is the board's own post, and its
    id is what both sides still share.
    """
    comments = thread.comments
    root = conversation.comment_id
    return (conversation.github_node_id is None and root is not None
            and root in conversation.panel_reply_ids
            and conversation.comment_type == thread.kind
            and bool(comments) and comments[0].id == root)


def _record_key(thread: FetchedThread, ports: Ports) -> str:
    node_id = thread.key
    named = ports.records.load(node_id)
    if named is not None and named.github_node_id == node_id:
        return node_id
    conversations = ports.records.list()
    for conversation in conversations:
        if conversation.github_node_id == node_id:
            return conversation.key
    for conversation in conversations:
        if _posted_before_it_was_listed(conversation, thread):
            return conversation.key
    return node_id


def _holds(conversation: Conversation, thread: FetchedThread) -> bool:
    return (thread.key in (conversation.key, conversation.github_node_id)
            or _posted_before_it_was_listed(conversation, thread))


def without_records(threads: list[FetchedThread], ports: Ports) -> list[FetchedThread]:
    conversations = ports.records.list()
    return [thread for thread in threads
            if not any(_holds(conversation, thread) for conversation in conversations)]


def _identified(conversation: Conversation,
                thread: FetchedThread) -> Conversation:
    if conversation.github_node_id is not None:
        return conversation
    return replace(conversation, github_node_id=thread.key)


class RoleUnknown(Exception):
    pass


def known_role(ports: Ports) -> str:
    role = ports.pull_requests.role()
    if role is None:
        raise RoleUnknown("whether this PR is yours is not known until its first poll "
                          "is saved, so no thread is opened on it yet")
    return role


def _create(key: str, thread: FetchedThread, created_at: str,
            ports: Ports) -> Accepted | Refused | Deferred:
    role = known_role(ports)
    comments = thread.comments
    root = comments[0] if comments else Comment()
    return perform(ports, create(
        key=key,
        github_node_id=thread.key,
        comment_id=root.id,
        comment_type=thread.kind,
        author=root.author,
        path=thread.path,
        line=thread.line,
        body=root.body,
        comments=comments,
        comment_created_at=root.created_at,
        created_at=created_at,
        anchor=thread.anchor or Anchor(),
        role=role,
        resolved=bool(thread.is_resolved),
    ))


def open_one(thread: FetchedThread, created_at: str, ports: Ports, *,
             cutoff: str | None = None) -> Conversation:
    key = _record_key(thread, ports)
    with ports.records.update(key) as update:
        conversation = update.conversation
        if conversation is None:
            outcome = _create(key, thread, created_at, ports)
        else:
            conversation = _identified(conversation, thread)
            outcome = run(ports, conversation,
                          Reopen(viewer=ports.config.gh_account,
                                 comments=thread.comments,
                                 anchor=thread.anchor,
                                 resolved=thread.is_resolved,
                                 as_of=cutoff))
            if ports.pull_requests.role() == ROLE_AUTHOR:
                queued = run(ports, outcome.conversation, First())
                if isinstance(queued, Accepted):
                    outcome = queued
        if outcome.conversation != conversation:
            update.conversation = outcome.conversation
    return outcome.conversation


def _refresh_one(thread: FetchedThread, ports: Ports,
                 cutoff: str | None) -> bool:
    with ports.records.update(_record_key(thread, ports)) as update:
        conversation = update.conversation
        if conversation is None:
            return False
        outcome = run(ports, _identified(conversation, thread),
                      Refresh(comments=thread.comments,
                              anchor=thread.anchor,
                              resolved=thread.is_resolved,
                              as_of=cutoff))
        update.conversation = outcome.conversation
        return True


def refresh(pr: Pr, stale: list[FetchedThread], ports: Ports, *,
            cutoff: str | None = None) -> list[str]:
    refreshed = []
    for thread in stale:
        try:
            changed = _refresh_one(thread, ports, cutoff)
        except Exception:
            log.exception("refresh %s: thread %s failed; skipping it",
                          pr, thread.key)
            continue
        if changed:
            refreshed.append(thread.key)
    return refreshed


def ask_due_verdicts(ports: Ports) -> None:
    now = ports.clock.now()
    for listed in ports.records.list():
        if listed.is_unreadable or not verdict_due(listed, now):
            continue
        with ports.records.update(listed.key) as update:
            conversation = update.conversation
            if conversation is None or not verdict_due(conversation, now):
                continue
            outcome = run(ports, conversation, VerdictDue())
            if outcome.conversation != conversation:
                update.conversation = outcome.conversation


def materialise(pr: Pr, threads: list[FetchedThread], ports: Ports,
                *, cutoff: str | None = None) -> list[Conversation]:
    stamps = ports.clock.stamps(len(threads))

    def open_at(thread: FetchedThread, created_at: str) -> Conversation | None:
        return _open_or_skip(pr, thread, created_at, ports, cutoff)

    if len(threads) < 2:
        opened = list(map(open_at, threads, stamps))
    else:
        with ThreadPoolExecutor(max_workers=OPEN_WORKERS) as pool:
            opened = list(pool.map(open_at, threads, stamps))
    return [conversation for conversation in opened if conversation is not None]
