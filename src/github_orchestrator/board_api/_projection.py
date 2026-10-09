from collections.abc import Callable, Sequence
from typing import TypedDict

from github_orchestrator import conversation as domain
from github_orchestrator.board_api import _contract as contract
from github_orchestrator.board_api._contract import Person
from github_orchestrator.board_api._etag import etag_of
from github_orchestrator.board_api.interface import Dashboard
from github_orchestrator.conversation import (
    Conversation,
    ConversationManager,
    OperationKind,
)
from github_orchestrator.domain import Location, Sha, author_kind_of, threads_listed
from github_orchestrator.working_copies import FileDiff, PrCheckout

MAX_FILE_LINES = 2000

def _named(conversations: Sequence[Conversation], first_names_only: bool) -> dict[str, str]:
    names: dict[str, str] = {}
    for conversation in conversations:
        for login, name in ((conversation.author, conversation.reviewer_name),
                            *((c.author, c.author_name)
                              for c in conversation.comments)):
            if login and name and login not in names:
                names[login] = name.split()[0] if first_names_only else name
    return names


def people_of(conversations: Sequence[Conversation], first_names_only: bool) -> list[Person]:
    names = _named(conversations, first_names_only)
    logins = {conversation.author for conversation in conversations}
    logins |= {comment.author for conversation in conversations
               for comment in conversation.comments}
    return [Person(login=login, name=names.get(login))
            for login in sorted(logins - {""})]


def viewer_of(conversations: Sequence[Conversation], account: str,
              first_names_only: bool) -> Person:
    return Person(login=account, name=_named(conversations, first_names_only).get(account))


def _kind_of(conversation: Conversation) -> contract.ThreadKind:
    """A record with no `comment_type` is a review comment.

    The poller defaults an incoming thread's kind to `review`, and the
    records the board makes for itself leave the field empty rather than
    choosing a different kind. `ThreadKind` has no member for the empty
    string and should not grow one for a value that means "the usual".
    """
    return contract.ThreadKind(conversation.comment_type or contract.ThreadKind.REVIEW)


def _drafted_at(anchor: Location | None) -> contract.Anchor | None:
    if anchor is None:
        return None
    return contract.Anchor(
        path=anchor.path, line=anchor.line, start_line=anchor.start_line,
        start_side=contract.diff_side(anchor.start_side), side=contract.diff_side(anchor.side), original_line=None, original_start_line=None,
        original_commit=None, is_outdated=False)


def _anchor_of(conversation: Conversation) -> contract.Anchor:
    return contract.Anchor(
        path=conversation.path or None,
        line=conversation.line,
        start_line=conversation.start_line,
        start_side=contract.diff_side(conversation.start_side),
        side=contract.diff_side(conversation.side),
        original_line=conversation.original_line,
        original_start_line=conversation.original_start_line,
        original_commit=conversation.original_commit,
        is_outdated=conversation.is_outdated,
    )


def _review_state(state: domain.ReviewState | None) -> contract.ReviewState | None:
    return contract.review_state(state)


def comments_of(conversation: Conversation,
                url_of: Callable[[int], str]) -> list[contract.Comment]:
    posted = conversation.posted_by_board
    root = conversation.comment_id
    return [contract.Comment(
        id=comment.id,
        author=comment.author,
        created_at=comment.created_at,
        review_state=_review_state(comment.review_state),
        body=comment.body,
        updated_at=comment.updated_at,
        html_url=None if comment.id is None else url_of(comment.id),
        posted_by_board=comment.id in posted,
        deleted=comment.id is not None and comment.id == root and conversation.comment_deleted,
        deleted_by_board=(comment.id is not None and comment.id == root
                          and conversation.deleted_by_board),
    ) for comment in conversation.comments]


def _summaries(conversation: Conversation) -> list[contract.OperationSummary]:
    summaries: list[contract.OperationSummary] = []
    for view in conversation.views:
        operation = view.operation
        run = operation.is_run
        summaries.append(contract.OperationSummary(
            id=operation.id,
            kind=operation.kind,
            state=operation.state,
            reason=operation.reason,
            reason_code=operation.reason_code,
            requested_at=operation.requested_at,
            settled_at=operation.settled_at,
            steps_done=view.steps_done,
            steps_total=view.steps_total,
            attempts=operation.attempts if run else None,
            attempts_allowed=operation.attempts_allowed if run else None,
            lands=None if view.landing.kind is None else contract.ProposalKind(view.landing.kind),
            ticket_key=view.landing.ticket_key,
        ))
    return summaries


def conversation_of(conversation: Conversation, account: str) -> contract.Conversation:
    """One record as the contract's conversation, with its own etag.

    The etag is the hash of everything else on the resource, which is why it
    is filled in on a second pass: a client holding forty cards has no
    per-thread header to send as `If-Match`, and the collection's tag moves
    whenever any of the forty moves.
    """
    drawn = contract.Conversation(
        key=conversation.key,
        github_node_id=conversation.github_node_id,
        kind=_kind_of(conversation),
        state=conversation.standing,
        state_changed_at=conversation.state_changed_at,
        reopened=conversation.reopened,
        etag="",
        github_removed=conversation.is_removed,
        github_resolved=conversation.github_resolved,
        github_resolved_at=conversation.github_resolved_at,
        created_at=conversation.created_at,
        anchor=_anchor_of(conversation),
        gist=conversation.gist or None,
        comments=[contract.CommentSummary(
            id=comment.id, author=comment.author, created_at=comment.created_at,
            review_state=_review_state(comment.review_state))
            for comment in conversation.comments],
        operations=_summaries(conversation),
        mention=conversation.mention,
        updated_at=conversation.updated_at,
        author_kind=author_kind_of(conversation.author, account),
        unread=conversation.unread,
        record_state=contract.RecordState(conversation.state),
    )
    return drawn.model_copy(update={"etag": etag_of(
        drawn.model_dump_json(exclude={"updated_at"}).encode())})


class _Envelope(TypedDict):
    id: str
    conversation: str
    state: domain.OperationState
    reason: str | None
    reason_code: domain.ReasonCode | None
    requested_at: str | None
    settled_at: str | None


def _operation_of(threads: ConversationManager, conversation: Conversation,
                  operation_id: str) -> contract.Operation:
    view = next(one for one in conversation.views if one.operation.id == operation_id)
    operation = view.operation
    envelope = _Envelope(
        id=operation.id,
        conversation=conversation.key,
        state=operation.state,
        reason=operation.reason,
        reason_code=operation.reason_code,
        requested_at=operation.requested_at,
        settled_at=operation.settled_at,
    )
    match operation.kind:
        case OperationKind.APPROVE as approve:
            landing = view.landing
            return contract.ApproveOperation(
                **envelope, kind=approve, reply=view.text or None,
                delete_comment=operation.delete_comment, proposal=view.proposal,
                steps=contract.LandingSteps(filed=landing.filed, picked=landing.picked,
                                            pushed=landing.pushed, answered=landing.answered),
                landed_base=_hex(landing.landed_base), landed_sha=_hex(landing.landed_sha),
                posted_comment=view.posted_comment, reply_note=landing.reply_note,
                ticket_key=landing.ticket_key, ticket_url=landing.ticket_url)
        case OperationKind.FILE as filing:
            return contract.FileOperation(**envelope, kind=filing)
        case OperationKind.STOP as stop:
            return contract.StopOperation(**envelope, kind=stop, stopped=operation.stopped)
        case OperationKind.RESOLVE | OperationKind.REJECT as closing:
            return contract.CloseOperation(
                **envelope, kind=closing, reply=view.text or None,
                delete_comment=operation.delete_comment,
                posted_comment=view.posted_comment)
        case OperationKind.DEFER as defer:
            return contract.DeferOperation(
                **envelope, kind=defer, until=operation.wakes_on,
                note=view.text or None)
        case OperationKind.UNPARK as unpark:
            return contract.UnparkOperation(**envelope, kind=unpark)
        case OperationKind.CONFIRM | OperationKind.PLACE as placing:
            return contract.PlaceOperation(**envelope, kind=placing)
        case OperationKind.REPLY as reply:
            return contract.ReplyOperation(
                **envelope, kind=reply, body=view.text,
                posted_comment=view.posted_comment)
        case OperationKind.POSTED as posted:
            return contract.PostedOperation(
                **envelope, kind=posted, review=operation.review,
                posted_comment=view.posted_comment,
                github_node_id=operation.github_node_id)
        case (OperationKind.CREATE_DRAFT | OperationKind.EDIT_DRAFT | OperationKind.ENROL
              | OperationKind.WITHDRAW_FROM_REVIEW | OperationKind.DISCARD
              | OperationKind.POST_NOW as drafted):
            return contract.DraftOperation(
                **envelope, kind=drafted, body=view.text or None,
                anchor=_drafted_at(operation.anchor),
                posted_comment=view.posted_comment)
        case OperationKind.SEND_REVIEW:
            raise ValueError(f"{conversation.key} holds a review's operation, which "
                             f"belongs to no thread")
    activity = threads.activity(conversation) if view.current else None
    last_action = activity.last_action if activity else None
    progress = activity.progress if activity else None
    plan = [contract.PlanStep(text=step.text, file=step.file, done=step.done)
            for step in view.plan]
    brief = view.brief
    match operation.kind:
        case OperationKind.START_SESSION as session:
            return contract.SessionOperation(
                **envelope, kind=session, steer=view.text or None,
                last_action=last_action, progress=progress, plan=plan,
                proposal=view.proposal)
        case (OperationKind.FIRST | OperationKind.REBASE | OperationKind.REWORK
              | OperationKind.RETRY as run):
            return contract.FixOperation(
                **envelope, kind=run,
                attempts=operation.attempts, attempts_allowed=operation.attempts_allowed,
                last_action=last_action, progress=progress, plan=plan,
                onto=_hex(view.onto), conflict=view.conflict,
                brief=None if brief is None else contract.Brief(
                    note=brief.note,
                    pointed=[contract.PointedLine(file=line.file, line=line.line,
                                                  text=line.text)
                             for line in brief.pointed],
                    include=list(brief.include)),
                proposal=view.proposal, classification=view.classification,
            )


def operations_of(threads: ConversationManager,
                  conversation: Conversation) -> contract.OperationList:
    return contract.OperationList([_operation_of(threads, conversation, operation.id)
                                   for operation in conversation.operations])


def newest_operation(threads: ConversationManager,
                     conversation: Conversation) -> contract.Operation:
    return _operation_of(threads, conversation, conversation.operations[-1].id)


def one_operation(threads: ConversationManager, conversation: Conversation,
                  operation_id: str) -> contract.Operation | None:
    if not any(operation.id == operation_id for operation in conversation.operations):
        return None
    return _operation_of(threads, conversation, operation_id)


def reviews_of(threads: ConversationManager, *, in_flight: bool = False) -> list[contract.ReviewOperation]:
    return [contract.ReviewOperation(
        id=review.id,
        conversation=None,
        kind=OperationKind.SEND_REVIEW,
        state=review.state,
        reason=review.reason,
        reason_code=review.reason_code,
        requested_at=review.requested_at,
        settled_at=review.settled_at,
        verdict=contract.review_verdict(review.verdict),
        body=review.body,
        drafts=list(review.drafts),
        posted_review=review.posted_review,
    ) for review in threads.reviews() if review.in_flight or not in_flight]


def work_in_flight(threads: ConversationManager,
                   conversations: Sequence[Conversation]) -> contract.OperationList:
    """Every operation the board has pending or running, across the threads,
    and a review on its way out after them.

    One read per tick whatever the number of agents, and one etag answering
    whether anything in flight has changed.
    """
    running: list[contract.Operation] = []
    for conversation in conversations:
        if conversation.is_unreadable:
            continue
        running.extend(_operation_of(threads, conversation, operation.id)
                       for operation in conversation.operations if operation.in_flight)
    running.extend(reviews_of(threads, in_flight=True))
    return contract.OperationList(running)


def _hex(sha: Sha | None) -> str | None:
    return None if sha is None else str(sha)


def proposal_of(git: PrCheckout,
                conversation: Conversation) -> contract.Proposal | None:
    proposal = conversation.proposal
    if proposal is None:
        return None
    commits = proposal.commits
    return contract.Proposal(
        id=proposal.id,
        conversation=conversation.key,
        kind=contract.ProposalKind(proposal.kind),
        reply=proposal.reply,
        ticket=None if proposal.ticket is None else contract.Ticket(
            project=proposal.ticket.project, title=proposal.ticket.title,
            body=proposal.ticket.body),
        operation=proposal.operation,
        created_at=proposal.created_at,
        updated_at=conversation.updated_at,
        commits=None if commits is None
        else contract.Commits(base=str(commits[0]), head=str(commits[1])),
        directory=git.workspace(conversation.key, proposal.base_sha).path,
        summary=proposal.summary,
        agent_note=proposal.agent_note,
        confidence=proposal.confidence,
        confidence_note=proposal.confidence_note,
        tests=proposal.tests,
        tests_note=proposal.tests_note,
        commit_message=(None if proposal.thread_sha is None
                        else git.commit_message(proposal.thread_sha)),
    )


def proposals_of(git: PrCheckout,
                 conversation: Conversation) -> contract.ProposalList:
    proposal = proposal_of(git, conversation)
    return contract.ProposalList([] if proposal is None else [proposal])


def _changed(file: FileDiff, blob: bytes | None) -> contract.FileChange:
    return contract.FileChange(
        path=file.path, old_path=file.old_path,
        status=contract.DiffFileStatus(file.status), added=file.added,
        removed=file.removed, is_binary=file.is_binary,
        line_count=None if blob is None else len(blob.removesuffix(b"\n").split(b"\n")),
        hunks=[contract.DiffHunk(
            old_start=hunk.old_start, old_lines=hunk.old_lines,
            new_start=hunk.new_start, new_lines=hunk.new_lines,
            section=hunk.section,
            lines=[contract.DiffLine(kind=contract.DiffLineKind(line.kind),
                                     old_line=line.old_line,
                                     new_line=line.new_line, text=line.text)
                   for line in hunk.lines])
            for hunk in file.hunks])


def diff_of(base: str, head: str, files: Sequence[FileDiff],
            blob_of: Callable[[str], bytes | None]) -> contract.Diff:
    return contract.Diff(
        base=base, head=head,
        files=[_changed(file, blob_of(file.path) if file.hunks else None)
               for file in files])


def lines_of(sha: str, path: str, text: str, first: int,
             last: int | None) -> contract.FileLines:
    """The file's lines, numbered, within the range asked for.

    A read that named no end gets at most `MAX_FILE_LINES` and is told the
    file goes on. A read that named one has already been refused if it was
    wider than that, which is why an explicit range is never truncated.
    """
    numbered = text.split("\n")
    if numbered and numbered[-1] == "":
        numbered.pop()
    end = last if last is not None else min(len(numbered),
                                            first + MAX_FILE_LINES - 1)
    return contract.FileLines(
        sha=sha, path=path, from_line=first, to_line=end,
        truncated=last is None and len(numbered) > end,
        lines=[contract.FileLine(number=number, text=numbered[number - 1])
               for number in range(first, min(end, len(numbered)) + 1)])


def _ordered_at(thread: contract.Conversation) -> str:
    """The later of the thread's two clocks.

    `state_changed_at` is null on every record written before the machine
    started stamping it, so the comment clock has to be able to answer
    alone. Both stamps are `%Y-%m-%dT%H:%M:%SZ`, which sorts as text, and an
    empty string is older than any of them rather than newer.
    """
    newest = thread.comments[-1].created_at if thread.comments else None
    return max(thread.state_changed_at or "", newest or "")


def collection_of(conversations: Sequence[Conversation], account: str,
                  listed_at: str) -> contract.ConversationList:
    readable, unreadable = threads_listed(conversations)
    drawn = [conversation_of(conversation, account) for conversation in readable]
    drawn.sort(key=lambda thread: (_ordered_at(thread), thread.key),
               reverse=True)
    return contract.ConversationList(conversations=drawn, unreadable=unreadable,
                                     listed_at=listed_at)


def dashboard_of(dashboard: Dashboard) -> contract.Dashboard:
    working = dashboard.working_on is not None
    frozen_on, expected, left = (dashboard.frozen_on, dashboard.expected_branch,
                                 dashboard.seconds_left)
    return contract.Dashboard(
        pr=contract.DashboardPr(
            repo=str(dashboard.pr.repo), number=dashboard.pr.number, title=dashboard.title,
            url=dashboard.url, branch=dashboard.branch, ticket=dashboard.ticket,
            author=dashboard.author),
        polled=dashboard.polled,
        status=contract.DashboardStatus(
            detailed_reviewer=dashboard.detailed_reviewer,
            you_are_the_detailed_reviewer=dashboard.is_detailed_reviewer,
            mergeable=dashboard.mergeable, needs_rebase=dashboard.needs_rebase,
            last_event_at=dashboard.last_event_at, review_ready_at=dashboard.review_ready_at,
            since_you_last_acted=None if dashboard.since_commits is None
            else contract.SinceYouActed(
                commits=dashboard.since_commits, force_pushed=dashboard.since_force_push,
                reviews=dashboard.since_reviews, comments=dashboard.since_comments,
                threads_resolved=dashboard.since_resolved),
            failed_checks=list(dashboard.failed_checks), checks_done=dashboard.checks_done,
            checks_total=dashboard.checks_total, changed_files=dashboard.changed_files,
            approved_by=list(dashboard.approved_by)),
        system=contract.DashboardSystem(
            agent=contract.AgentActivity(
                name=dashboard.agent_name,
                enabled=dashboard.agents_enabled,
                state=contract.AgentState.WORKING if working else contract.AgentState.IDLE,
                event=dashboard.working_on, elapsed_seconds=dashboard.elapsed_seconds,
                silent_seconds=dashboard.silent_seconds),
            last_run=None if dashboard.last_run_event is None
            or dashboard.last_run_ended_at is None
            else contract.LastRun(event=dashboard.last_run_event,
                                  exit_code=dashboard.last_run_exit_code,
                                  ended_at=dashboard.last_run_ended_at),
            queued_events=dashboard.queued_events,
            on_hold=dashboard.on_hold,
            unpushed_commits=dashboard.unpushed_commits,
            threads=contract.ThreadCounts(
                queued=dashboard.threads_queued, live=len(dashboard.threads_live),
                proposed=dashboard.threads_proposed, drafts=dashboard.threads_drafts)),
        frozen=None if frozen_on is None or expected is None or left is None
        else contract.FrozenWorktree(
            worktree=dashboard.worktree, here=frozen_on, expected=expected,
            seconds_left=left, run_working=dashboard.run_working,
            release_requested=dashboard.release_requested),
        undismiss_command=dashboard.undismiss_command,
        notice=dashboard.notice,
        facts=_facts_of(dashboard) if dashboard.polled else None,
        manager=contract.ManagerFlags(
            frozen_on=dashboard.frozen_on, on_hold=dashboard.on_hold,
            working_on=dashboard.working_on, hidden=dashboard.hidden,
            threads_live=len(dashboard.threads_live), changed_at=dashboard.flags_changed_at),
        threads=[contract.ThreadRow(
            key=row.key, state=domain.ConversationState(row.standing),
            record_state=contract.RecordState(row.state), author_kind=row.author_kind,
            updated_at=row.updated_at) for row in dashboard.thread_rows],
        unreadable=list(dashboard.unreadable_threads),
        listed_at=dashboard.threads_listed_at,
    )


def _facts_of(dashboard: Dashboard) -> contract.PrFacts:
    return contract.PrFacts(
        polled_at=dashboard.polled_at, ended=dashboard.ended, is_author=dashboard.is_author,
        changes_requested_by=list(dashboard.changes_requested_by),
        pending_reviewers=list(dashboard.pending_reviewers), ci_status=dashboard.ci,
        merge_state=None if dashboard.merge_state is None
        else contract.MergeState(dashboard.merge_state),
        draft=dashboard.draft, review_decision=dashboard.review_decision,
        my_review=dashboard.my_review, my_review_at=dashboard.my_review_at,
        viewer_requested=dashboard.viewer_requested, mentioned=dashboard.mentioned,
        mentions=[contract.MentionFact(author=mention.author, at=mention.at,
                                       answered=mention.answered)
                  for mention in dashboard.mentions],
        unresolved_threads=dashboard.unresolved_threads)
