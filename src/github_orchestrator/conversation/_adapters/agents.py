from collections.abc import Callable

from github_orchestrator.agent_runs import (
    FixComment,
    PointedAt,
    Run,
    ThreadFix,
    ThreadWork,
)
from github_orchestrator.conversation._application.ports import (
    GitHub,
    PullRequests,
    RunProgress,
)
from github_orchestrator.conversation._domain.conversation import (
    PROPOSED,
    Brief,
    Comment,
    ConfidenceLevel,
    Conversation,
    OperationKind,
    ProposalKind,
)
from github_orchestrator.conversation._domain.parts import has_run, parts
from github_orchestrator.domain import Pr, Sha


def _worktree_of(worktree: str | None) -> str:
    if worktree is None:
        raise ValueError("this conversation has no workspace to run in")
    return worktree


class ThreadAgents:
    def __init__(self, thread_work: ThreadWork, pr: Pr,
                 manager_run_alive: Callable[[], bool], *, account: str,
                 tracker: str | None, tracker_project: str | None,
                 pull_requests: PullRequests, pr_skill: str,
                 pages: GitHub) -> None:
        self.thread_work = thread_work
        self.pr = pr
        self.account = account
        self.tracker = tracker
        self.tracker_project = tracker_project
        self.pull_requests = pull_requests
        self.pr_skill = pr_skill
        self.pages = pages
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
        split = fix.split
        ticket = (fix.ticket if fix.kind == ProposalKind.TICKET
                  else fix.ticket or split.ticket if split is not None else None)
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
            branch_ticket=self.pull_requests.ticket(),
            pr_branch=self.pull_requests.branch(),
            pr_base=self.pull_requests.base_branch(),
            note=brief.note if brief else "",
            pointed=() if brief is None else tuple(
                PointedAt(file=one.file, line=one.line, text=one.text) for one in brief.pointed),
            replies=() if brief is None else tuple(
                self._said(comment) for comment in conversation.comments[1:]
                if comment.author in brief.include),
            split_branch=None if split is None else split.branch,
            split_base=None if split is None else split.base,
            split_base_reason=None if split is None else split.base_reason,
            split_sha=None if split is None or fix.thread_sha is None else str(fix.thread_sha),
            reworks_part=None if brief is None or brief.part is None else brief.part.value,
            parts_run=() if split is None else tuple(
                part.value for part in parts(split) if has_run(fix.steps, part)),
            pr_skill=self.pr_skill,
            pr_url=self.pages.page(),
            thread_url=self._thread_url(conversation),
            ticket_key=fix.ticket_key,
            ticket_url=fix.ticket_url,
            landed_sha=None if fix.landed_sha is None else str(fix.landed_sha),
        )

    def _thread_url(self, conversation: Conversation) -> str | None:
        if conversation.comment_id is None:
            return None
        return self.pages.comment_page(conversation, conversation.comment_id)

    def start_run(self, conversation: Conversation, worktree: str | None, kind: str,
                  onto: Sha | None) -> str | None:
        asked = self._asked(conversation, _worktree_of(worktree),
                            skipped=bool(conversation.fix.classification),
                            brief=conversation.fix.run.brief)
        if conversation.fix.run.resumes:
            run = self.thread_work.carry_on_thread(asked)
        elif kind == OperationKind.REBASE:
            run = self.thread_work.rebase_fix(asked, None if onto is None else str(onto))
        elif kind == OperationKind.REWORK:
            run = self.thread_work.rework(asked)
        elif kind == OperationKind.FILE:
            run = self.thread_work.file_ticket(asked)
        elif kind == OperationKind.OPEN:
            run = self.thread_work.open_pr(asked)
        elif kind == OperationKind.RECONCILE:
            run = self.thread_work.reconcile(asked)
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
                           last_action=run.last_action, last_words=run.last_words)

    def open_session(self, worktree: str | None,
                     conversation: Conversation, steer: str | None,
                     skipped: bool, brief: Brief | None) -> str | None:
        return self.thread_work.open_session(
            self._asked(conversation, _worktree_of(worktree), skipped, brief), steer)

    def answer_in_session(self, worktree: str | None,
                          conversation: Conversation) -> str | None:
        return self.thread_work.answer_in_session(
            self._asked(conversation, _worktree_of(worktree), False, None))

    def open_shell(self, worktree: str | None) -> str | None:
        return self.thread_work.open_shell(self.pr, _worktree_of(worktree))
