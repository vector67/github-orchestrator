from collections.abc import Callable

from github_orchestrator.agent_runs import (
    FixComment,
    PointedAt,
    Run,
    ThreadFix,
    ThreadWork,
)
from github_orchestrator.conversation._application.ports import RunProgress
from github_orchestrator.conversation._domain.conversation import (
    PROPOSED,
    Brief,
    Comment,
    ConfidenceLevel,
    Conversation,
    OperationKind,
    ProposalKind,
)
from github_orchestrator.domain import Pr, Sha


def _worktree_of(worktree: str | None) -> str:
    if worktree is None:
        raise ValueError("this conversation has no workspace to run in")
    return worktree


class ThreadAgents:
    def __init__(self, thread_work: ThreadWork, pr: Pr,
                 manager_run_alive: Callable[[], bool], *, account: str,
                 tracker: str | None, tracker_project: str | None,
                 branch_ticket: Callable[[], str | None]) -> None:
        self.thread_work = thread_work
        self.pr = pr
        self.account = account
        self.tracker = tracker
        self.tracker_project = tracker_project
        self.branch_ticket = branch_ticket
        self.manager_run_alive = manager_run_alive
        self.runs: dict[str, Run] = {}

    def run_alive(self) -> bool:
        return self.manager_run_alive()

    def live_keys(self) -> frozenset[str]:
        return frozenset(self.runs)

    def _said(self, comment: Comment) -> FixComment:
        return FixComment(author=comment.author, body=comment.body,
                          created_at=comment.created_at, author_name=comment.author_name,
                          by_pr_author=bool(comment.author) and comment.author == self.account)

    def _asked(self, conversation: Conversation, worktree: str, skipped: bool,
               brief: Brief | None) -> ThreadFix:
        fix = conversation.fix
        ticket = fix.ticket if fix.kind == ProposalKind.TICKET else None
        return ThreadFix(
            pr=self.pr, key=conversation.key, worktree=worktree,
            author=conversation.author, path=conversation.path, line=conversation.line,
            body=conversation.body,
            comments=tuple(self._said(comment) for comment in conversation.comments),
            confidence_levels=tuple(level.value for level in ConfidenceLevel),
            before_reply=conversation.before_reply,
            withdraws_proposal=conversation.before_reply == PROPOSED,
            conflict=fix.run.conflict,
            classification=fix.classification,
            skipped_because=fix.reason if skipped and fix.reason else None,
            reply=None if fix.kind == ProposalKind.COMMIT else fix.reply,
            ticket_project=None if ticket is None else ticket.project,
            ticket_title=None if ticket is None else ticket.title,
            ticket_body=None if ticket is None else ticket.body,
            tracker=self.tracker, tracker_project=self.tracker_project,
            branch_ticket=self.branch_ticket(),
            note=brief.note if brief else "",
            pointed=() if brief is None else tuple(
                PointedAt(file=one.file, line=one.line, text=one.text) for one in brief.pointed),
            replies=() if brief is None else tuple(
                self._said(comment) for comment in conversation.comments[1:]
                if comment.author in brief.include),
        )

    def start_run(self, conversation: Conversation, worktree: str | None, kind: str,
                  onto: Sha | None) -> str | None:
        asked = self._asked(conversation, _worktree_of(worktree),
                            skipped=bool(conversation.fix.classification),
                            brief=conversation.fix.run.brief)
        if kind == OperationKind.REBASE:
            run = self.thread_work.rebase_fix(asked, None if onto is None else str(onto))
        elif kind == OperationKind.REWORK:
            run = self.thread_work.rework(asked)
        elif kind == OperationKind.FILE:
            run = self.thread_work.file_ticket(asked)
        else:
            run = self.thread_work.fix(asked)
        if isinstance(run, str):
            return run
        self.runs[conversation.key] = run
        return None

    def stop_run(self, key: str) -> None:
        run = self.runs.get(key)
        if run is None:
            return
        run.terminate()
        self.runs.pop(key, None)

    def pump(self, key: str) -> RunProgress:
        run = self.runs[key]
        alive = run.pump()
        if not alive:
            del self.runs[key]
        return RunProgress(alive=alive, elapsed=run.elapsed(),
                           last_action=run.last_action)

    def open_session(self, worktree: str | None,
                     conversation: Conversation, steer: str | None,
                     skipped: bool, brief: Brief | None) -> str | None:
        return self.thread_work.open_session(
            self._asked(conversation, _worktree_of(worktree), skipped, brief), steer)
