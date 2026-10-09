import dataclasses
import logging
import os
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import anyio
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Header,
    Query,
    Request,
    Response,
    WebSocket,
)
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from github_orchestrator import conversation as domain
from github_orchestrator.board_api import _etag as etag
from github_orchestrator.board_api import _routes as routes
from github_orchestrator.board_api._contract import (
    AgentOutput,
    ApproveRequest,
    BriefRequest,
    ClientError,
    CloseRequest,
    Comment,
    CommentList,
    Conversation,
    ConversationList,
    Dashboard,
    DeferRequest,
    Diff,
    DiffSource,
    DismissRequest,
    DraftBody,
    ErrorCode,
    Errors,
    FileLines,
    GitRequest,
    GitRun,
    Health,
    ManagerChanges,
    Operation,
    OperationList,
    Outcome,
    OutputLine,
    Person,
    PersonList,
    PlaceRequest,
    Proposal,
    ProposalList,
    PullRequest,
    ReplyRequest,
    ResolveRequest,
    SendReviewRequest,
    Sha,
    StartSessionRequest,
    TerminalRequest,
    TerminalSession,
    TerminalSessionList,
    ThreadKey,
    error_code,
    side_of,
    verdict_of,
)
from github_orchestrator.board_api._errors import (
    BAD_RANGE,
    DIFF_FAILED,
    FETCH_FAILED,
    NO_SUCH_DIFF,
    NO_SUCH_FILE,
    NOT_FOUND,
    NOT_TEXT,
    OUTSTANDING,
    PR_DIFF_FAILED,
    PRECONDITION_FAILED,
    TOO_LONG,
    UNREADABLE_RECORD,
    Refusal,
    RefusingApp,
    add_refusal_handlers,
)
from github_orchestrator.board_api._guarded import guard, page_at, target
from github_orchestrator.board_api._projection import (
    MAX_FILE_LINES,
    collection_of,
    comments_of,
    conversation_of,
    dashboard_of,
    diff_of,
    lines_of,
    newest_operation,
    one_operation,
    operations_of,
    people_of,
    proposal_of,
    proposals_of,
    reviews_of,
    viewer_of,
    work_in_flight,
)
from github_orchestrator.board_api._streams import described, streamed
from github_orchestrator.board_api._terminal import carried
from github_orchestrator.board_api.interface import ManagerPanel
from github_orchestrator.conversation import (
    ConversationManager,
    Denied,
    EditableConversation,
)
from github_orchestrator.domain import Location, Pr, UtcClock
from github_orchestrator.domain import Sha as CommitSha
from github_orchestrator.terminal_sessions import TerminalSessions
from github_orchestrator.working_copies import PrCheckout

log = logging.getLogger(__name__)

MAX_OUTPUT_LINES = 2000

PREFIX = "/api"

AS_OF_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

SERVER_ERROR_DETAIL = ("the board failed unexpectedly; the traceback is in "
                       "the PR manager's log")

DESCRIPTION = """
One pull request's comment threads, and what the agent wrote for them, on
loopback with no authentication.

This document is generated from the routes and the models and is the only
contract. The board web app's wire types are generated from it.
"""


@dataclasses.dataclass(frozen=True)
class Board:
    conversations: ConversationManager
    git: PrCheckout
    pr: Pr
    port: int
    manager: ManagerPanel
    app_root: Path
    hub_url: str
    heartbeat_seconds: float
    check_seconds: float
    terminals: TerminalSessions
    terminal_threads: anyio.CapacityLimiter
    first_names_only: bool
    clock: UtcClock
    fonts: routes.Fonts = routes.NO_FONTS
    check_presence: bool = True


async def board_of(request: Request) -> Board:
    board: Board = request.app.state.board
    return board


Serving = Annotated[Board, Depends(board_of)]

reads = APIRouter(prefix=PREFIX)

ONE_THREAD: dict[int | str, dict[str, Any]] = {
    404: NOT_FOUND, 500: UNREADABLE_RECORD}


def _thread(board: Board, key: str) -> domain.Conversation:
    """The record behind a key, with its pending decisions drawn as pending work, or the
    `404` that says there is none.

    A file that will not parse comes back from the review threads as a
    conversation in an unreadable state, and the app answers that `500`: the
    thread is there, and the board saying nothing about it would leave the
    operator with no way to find out that it cannot be read.
    """
    conversation = board.conversations.get(key)
    if conversation is None:
        raise Refusal(404, ErrorCode.NOT_FOUND,
                      f"this board has no thread called {key}")
    if conversation.is_unreadable:
        raise Refusal(500, ErrorCode.UNREADABLE_RECORD,
                      f"thread {key} will not read; the PR manager's log says why")
    return conversation


def _lines(board: Board, sha: str, path: str, first: int,
           last: int | None) -> FileLines:
    commit = CommitSha.parse(sha)
    if commit is None or not board.git.has_commit(commit):
        raise Refusal(404, ErrorCode.NO_SUCH_COMMIT,
                      board.git.no_worktree() or f"this repository has no commit {sha}")
    content = board.git.blob(commit, path)
    if content is None:
        raise Refusal(404, ErrorCode.NO_SUCH_PATH,
                      f"{sha} holds nothing at {path}")
    try:
        text = content.decode()
    except UnicodeDecodeError as exc:
        raise Refusal(415, ErrorCode.NOT_TEXT,
                      f"{path} at {sha} is not text, so it cannot be "
                      f"returned as lines") from exc
    return lines_of(sha, path, text, first, last)


def _proposal(board: Board, key: str, proposal_id: str) -> Proposal:
    proposal = proposal_of(board.git, _thread(board, key))
    if proposal is None or proposal.id != proposal_id:
        raise Refusal(404, ErrorCode.NOT_FOUND,
                      f"thread {key} holds no proposal {proposal_id}")
    return proposal


@reads.get("/pull-request", response_model=PullRequest, tags=["pull request"],
           operation_id="readPullRequest",
           summary="The pull request this board serves.",
           responses=etag.TAGGED)
def read_pull_request(request: Request, board: Serving) -> Response:
    """One board serves one pull request, so this is a singleton rather than
    a member of a collection. It carries an `ETag`; a poll that sends it back
    as `If-None-Match` is answered `304`.
    """
    facts = board.conversations.facts()
    return etag.answered(request, PullRequest(
        repo=str(board.pr.repo),
        number=board.pr.number,
        title=facts.title,
        html_url=facts.url,
        base_branch=facts.base_branch,
        branch=facts.branch,
        head_sha=facts.head_sha,
    ))


@reads.get("/pull-request/diff", response_model=Diff, tags=["pull request"],
           operation_id="readPullRequestDiff",
           summary="The pull request's diff, from the merge base to its head, as hunks.",
           responses={**etag.TAGGED, 500: PR_DIFF_FAILED})
def read_pull_request_diff(request: Request, board: Serving,
                           source: DiffSource = DiffSource.ORIGIN) -> Response:
    """What GitHub's "Files changed" shows: `git diff <merge base> <head>`,
    the merge base of `origin/<base_branch>` and the head. The head is
    `origin/<branch>` as last fetched, or with `source=local` the commit the
    worktree has checked out, pushed or not. The same `Diff` shape the
    `/diffs` answers.
    """
    facts = board.conversations.facts()
    head = board.git.origin_head() if source is DiffSource.ORIGIN else board.git.local_head()
    if head is None:
        raise Refusal(500, ErrorCode.GIT_FAILED,
                      board.git.no_worktree()
                      or f"git could not find the pull request's {source} head")
    diff = board.git.pr_diff(facts.base_branch, head)
    if diff is None:
        raise Refusal(500, ErrorCode.GIT_FAILED,
                      board.git.no_worktree()
                      or f"git could not diff {head} against its merge base with "
                         f"{facts.base_branch or 'the default branch'}")
    return etag.answered(request, diff_of(
        str(diff.base), str(diff.head), diff.files,
        lambda path: board.git.blob(diff.head, path)))


@reads.get("/viewer", tags=["people"], operation_id="readViewer",
           summary="Whoever is driving this board.")
def read_viewer(board: Serving) -> Person:
    """Its own path rather than `/people/me`, which would shadow a GitHub
    login of "me". No `ETag`: it is one login the board was configured with,
    and a poll has nothing to save.
    """
    return viewer_of(board.conversations.all(), board.conversations.facts().account,
                     board.first_names_only)


@reads.get("/health", tags=["board"], operation_id="readHealth",
           summary="Whether this board is serving, and from which process.")
async def read_health(board: Serving) -> Health:
    """Nothing is read to answer it, so it says the process is up and
    routing, not that the records behind it are sound. The pid is what finds
    this board's lines among every agent manager's in the shared log.
    """
    return Health(status="ok", pid=os.getpid(), serves="board", hub_url=board.hub_url,
                  font_problem=board.fonts.problem, state=None, version=None, watcher=None,
                  newest_release=None)


@reads.get("/people", response_model=PersonList, tags=["people"],
           operation_id="listPeople",
           summary="Everyone who has interacted with the pull request.",
           responses=etag.TAGGED)
def list_people(request: Request, board: Serving) -> Response:
    """A projection over the records rather than a store of its own, so the
    board knows only the logins and display names GitHub has handed it. A
    login it has no display name for comes back with `name` null.
    """
    return etag.answered(request,
                         PersonList(people_of(board.conversations.all(),
                                              board.first_names_only)))


@reads.get("/people/{login}", tags=["people"], operation_id="readPerson",
           summary="One participant.", responses={404: NOT_FOUND})
def read_person(login: str, board: Serving) -> Person:
    """Whoever the records name. Someone who has said nothing on this pull
    request is not here, including the viewer, who is on `/viewer`.
    """
    for person in people_of(board.conversations.all(), board.first_names_only):
        if person.login == login:
            return person
    raise Refusal(404, ErrorCode.NOT_FOUND,
                  f"nobody called {login} has spoken on this pull request")


@reads.get("/conversations", response_model=ConversationList,
           tags=["conversations"], operation_id="listConversations",
           summary="Every comment thread on the pull request, and every "
                   "draft.",
           responses=etag.TAGGED)
def list_conversations(request: Request, board: Serving) -> Response:
    """One record read per thread, no subprocesses. A thread's comment
    bodies, its proposals and their diffs are their own reads.

    **Ordered**, newest first, by whichever is later: the moment the thread's
    state last changed, or its newest comment. The board groups by `state`
    and keeps the order it was given inside each group. Grouping and group
    order are the front end's; this order is not.

    A record that will not parse is named in `unreadable` and does not stop
    the read. One bad file on disk must not take the whole board with it, and
    the board must not pretend the thread is not there.
    """
    listed_at = board.clock().strftime(AS_OF_FORMAT)
    return etag.answered(request, collection_of(board.conversations.all(),
                                                board.conversations.facts().account,
                                                listed_at))


@reads.get("/conversations/{key}", response_model=Conversation,
           tags=["conversations"], operation_id="readConversation",
           summary="One comment thread.",
           responses={**etag.TAGGED, **ONE_THREAD})
def read_conversation(key: ThreadKey, request: Request,
                      board: Serving) -> Response:
    """The same schema the collection returns. The collection was made cheap
    by moving what costs subprocesses out to `/proposals` and what changes
    every second out to `/operations`, not by holding fields back, so there
    is nothing left for a narrower list shape to withhold.
    """
    return etag.answered(request, conversation_of(_thread(board, key),
                                                  board.conversations.facts().account))


def _comments(board: Board, conversation: domain.Conversation) -> list[Comment]:
    return comments_of(conversation,
                       lambda comment_id: board.conversations.comment_url(conversation, comment_id))


@reads.get("/conversations/{key}/comments", response_model=CommentList,
           tags=["comments"], operation_id="listComments",
           summary="The thread's comments, oldest first.",
           responses={**etag.TAGGED, **ONE_THREAD})
def list_comments(key: ThreadKey, request: Request,
                  board: Serving) -> Response:
    """The bodies. The ids, authors, timestamps and review states are
    already on the conversation as summaries; this is the read that carries
    what people actually wrote. A draft has exactly one comment, the body you
    are composing, with no GitHub id and no URL.
    """
    conversation = _thread(board, key)
    if board.check_presence:
        board.conversations.recheck(conversation)
    return etag.answered(request, CommentList(_comments(board, conversation)))


@reads.get("/conversations/{key}/comments/{comment_id}",
           response_model=Comment, tags=["comments"],
           operation_id="readComment", summary="One comment.",
           responses={**etag.TAGGED, **ONE_THREAD})
def read_comment(key: ThreadKey, comment_id: int, request: Request,
                 board: Serving) -> Response:
    """Addressed by GitHub's id. A draft's comment has none and is read
    through the collection.
    """
    conversation = _thread(board, key)
    for comment in _comments(board, conversation):
        if comment.id == comment_id:
            return etag.answered(request, comment)
    raise Refusal(404, ErrorCode.NOT_FOUND,
                  f"thread {key} holds no comment {comment_id}")


@reads.get("/conversations/{key}/operations", response_model=OperationList,
           tags=["operations"], operation_id="listOperations",
           summary="Everything asked of this thread, and everything the "
                   "board started on it.",
           responses={**etag.TAGGED, **ONE_THREAD})
def list_operations(key: ThreadKey, request: Request,
                    board: Serving) -> Response:
    """Oldest first. A couple of dozen at most over a thread's life, so the
    whole history comes back; there is no paging.

    The same list is on the conversation as summaries. This read adds each
    operation's own fields: the brief a rework carried, the plan it is
    working through, how far a landing got, what an agent classified a
    comment as.
    """
    return etag.answered(request,
                         operations_of(board.conversations, _thread(board, key)))


@reads.get("/conversations/{key}/operations/{operation_id}",
           response_model=Operation, tags=["operations"],
           operation_id="readOperation", summary="One operation.",
           responses={**etag.TAGGED, **ONE_THREAD})
def read_operation(key: ThreadKey, operation_id: str, request: Request,
                   board: Serving) -> Response:
    operation = one_operation(board.conversations, _thread(board, key), operation_id)
    if operation is None:
        raise Refusal(404, ErrorCode.NOT_FOUND,
                      f"thread {key} holds no operation {operation_id}")
    return etag.answered(request, operation)


@reads.get("/operations", response_model=OperationList, tags=["review"],
           operation_id="listWorkInFlight",
           summary="Every operation currently pending or running on this "
                   "pull request.",
           responses=etag.TAGGED)
def list_work_in_flight(request: Request, board: Serving) -> Response:
    """The fast poll. The board reads this about once a second while the
    conversation list stays on a slower one, because these are the fields
    that change as an agent works: the plan's progress, what it last did,
    how far ahead of its base it is.

    The same operation resources the per-thread reads return, selected
    differently, the way `/people` and `/people/{login}` relate.
    """
    return etag.answered(request, work_in_flight(board.conversations,
                                                 board.conversations.all()))


@reads.get("/operations/{operation_id}", response_model=Operation,
           tags=["review"], operation_id="readReviewOperation",
           summary="One piece of work about the whole review.",
           responses={**etag.TAGGED, 404: NOT_FOUND})
def read_review_operation(operation_id: str, request: Request,
                          board: Serving) -> Response:
    """Where `:send-review` says to read what became of the review. The
    per-thread operations live under their thread; this holds the ones that
    belong to no thread."""
    for review in reviews_of(board.conversations):
        if review.id == operation_id:
            return etag.answered(request, review)
    raise Refusal(404, ErrorCode.NOT_FOUND,
                  f"this pull request holds no operation {operation_id}")


@reads.get("/conversations/{key}/proposals", response_model=ProposalList,
           tags=["proposals"], operation_id="listProposals",
           summary="What has been left on this thread, oldest first.",
           responses={**etag.TAGGED, **ONE_THREAD})
def list_proposals(key: ThreadKey, request: Request,
                   board: Serving) -> Response:
    """Empty on a draft, and on a reviewer's threads where no agent runs.

    This is the read that shells out to git, for the commit message and the
    worktree. It sits below the fold on a card, so it is fetched on its own
    rather than embedded. Its diff is `/diffs/{base}..{head}` of its `commits`.
    """
    return etag.answered(request,
                         proposals_of(board.git, _thread(board, key)))


@reads.get("/conversations/{key}/proposals/{proposal_id}",
           response_model=Proposal, tags=["proposals"],
           operation_id="readProposal", summary="One proposal.",
           responses={**etag.TAGGED, **ONE_THREAD})
def read_proposal(key: ThreadKey, proposal_id: str, request: Request,
                  board: Serving) -> Response:
    return etag.answered(request, _proposal(board, key, proposal_id))


def _commit(board: Board, sha: str) -> CommitSha:
    commit = CommitSha.parse(sha)
    if commit is None or not board.git.has_commit(commit):
        raise Refusal(404, ErrorCode.NO_SUCH_COMMIT,
                      board.git.no_worktree() or f"this repository has no commit {sha}")
    return commit


@reads.get("/diffs/{base}..{head}", response_model=Diff, tags=["revisions"],
           operation_id="readDiff",
           summary="The changes from one commit to another, as hunks.",
           description="Addressed by its commits, so a diff never changes and "
                       "a reader may keep it for good. A proposal names its "
                       "`commits`; a moved base is new commits, so a new diff. "
                       "Lines carry their text and their old and new numbers; "
                       "nothing is highlighted and nothing is HTML.",
           responses={**etag.TAGGED, 404: NO_SUCH_DIFF, 500: DIFF_FAILED})
def read_diff(base: Sha, head: Sha, request: Request, board: Serving) -> Response:
    since, until = _commit(board, base), _commit(board, head)
    files = board.git.diff_files(since, until)
    if files is None:
        raise Refusal(500, ErrorCode.GIT_FAILED,
                      board.git.no_worktree() or f"git could not diff {base}..{head}")
    return etag.answered(request, diff_of(
        base, head, files, lambda path: board.git.blob(until, path)))


@reads.get("/files", response_model=FileLines, tags=["revisions"],
           operation_id="readFileLines",
           summary="Lines of one file at one commit.",
           responses={**etag.TAGGED, 400: BAD_RANGE,
                      404: NO_SUCH_FILE, 415: NOT_TEXT})
def read_file_lines(request: Request, board: Serving, sha: Sha, path: str,
                    from_line: Annotated[int | None, Query(ge=1)] = None,
                    to_line: Annotated[int | None, Query(ge=1)] = None,
                    ) -> Response:
    """What the panel needs to show a comment beside the code it was written
    on, what expanding a hunk needs, and what the draft composer redraws as
    its anchor changes. A query rather than a path, because a repository
    path has slashes in it.

    Bounded. At most 2000 lines come back in one read; a wider range is
    refused with `range-too-wide` rather than truncated, so a caller never
    mistakes a clipped answer for the whole file.
    """
    first = from_line or 1
    if to_line is not None:
        if to_line < first:
            raise Refusal(400, ErrorCode.RANGE_INVERTED,
                          f"line {to_line} comes before line {first}")
        if to_line - first + 1 > MAX_FILE_LINES:
            raise Refusal(
                400, ErrorCode.RANGE_TOO_WIDE,
                f"lines {first} to {to_line} is more than the "
                f"{MAX_FILE_LINES} this read returns at once")
    return etag.answered(request,
                         _lines(board, sha, path, first, to_line))


@reads.get("/openapi.json", include_in_schema=False)
def read_contract(request: Request) -> Response:
    """This API, described by the routes and models that serve it.

    This is the contract a client reads. `tests/board_api/test_contract_copy.py`
    keeps the front end's copy of it and its TypeScript types in step.
    """
    document: dict[str, Any] = request.app.openapi()
    return JSONResponse(document)


writes = APIRouter(prefix=PREFIX, tags=["operations"])

HANDED_TO_THE_MANAGER: dict[int | str, dict[str, Any]] = {202: {
    "description": "Handed to the PR manager, which carries it out on its next "
                   "tick exactly as the dashboard's key would, refusals and "
                   "notices included. Poll the dashboard to see it land.",
    "headers": {"Location": {
        "description": "The dashboard to poll.",
        "schema": {"type": "string", "format": "uri-reference"}}}},
    409: {"description": "The PR manager's last status already rules it out: the "
                         "worktree holds another branch, agents are disabled, or "
                         "an agent is already running. The detail says which.",
          "model": Errors}}


def _handed_over(refused: str | None) -> Response:
    if refused is not None:
        raise Refusal(409, ErrorCode.MANAGER_REFUSED, refused)
    return Response(status_code=202, headers={"Location": f"{PREFIX}/dashboard"})


@writes.post("/manager:hold", status_code=202, tags=["manager"],
             operation_id="holdManager", responses=HANDED_TO_THE_MANAGER,
             summary="Put the pull request on hold: take no events but a closing one.")
def hold_manager(board: Serving) -> Response:
    """The dashboard's `p` on a pull request not on hold. On one on hold it
    leaves it on hold.
    """
    return _handed_over(board.manager.set_on_hold(True))


@writes.post("/manager:resume", status_code=202, tags=["manager"],
             operation_id="resumeManager", responses=HANDED_TO_THE_MANAGER,
             summary="Resume a pull request on hold.")
def resume_manager(board: Serving) -> Response:
    """The dashboard's `p` on a pull request on hold. On one not on hold it
    does nothing.
    """
    return _handed_over(board.manager.set_on_hold(False))


@writes.post("/manager:carry-on", status_code=202, tags=["manager"],
             operation_id="carryOn", responses=HANDED_TO_THE_MANAGER,
             summary="Start the agent again on this pull request, carrying on "
                     "from where its last session left off.")
def carry_on(board: Serving) -> Response:
    """The dashboard's `r`. Refused when agents are disabled or a run is
    already going.
    """
    return _handed_over(board.manager.carry_on())


@writes.post("/manager:start-review", status_code=202, tags=["manager"],
             operation_id="startReview", responses=HANDED_TO_THE_MANAGER,
             summary="Start a review agent on this pull request, as a review "
                     "request does.")
def start_review(board: Serving) -> Response:
    """The fallback for when the review agent a review request starts went
    wrong. A re-review when you have reviewed before. Refused when agents
    are disabled or a run is already going.
    """
    return _handed_over(board.manager.start_review())


@writes.post("/manager:dismiss", status_code=202, tags=["manager"],
             operation_id="dismissManager", responses=HANDED_TO_THE_MANAGER,
             summary="Dismiss this pull request until its next event, or for "
                     "good.")
def dismiss_manager(board: Serving, asked: DismissRequest) -> Response:
    """The dashboard's `x u` and `x f`. The manager records the dismissal,
    stops its run and exits, so this board stops answering soon after.
    """
    return _handed_over(board.manager.dismiss(asked.forever))


@writes.post("/manager:close", status_code=202, tags=["manager"],
             operation_id="closePullRequest", responses=HANDED_TO_THE_MANAGER,
             summary="Close this pull request on GitHub.")
def close_pull_request(board: Serving) -> Response:
    """The dashboard's `c y`. The manager closes the pull request on GitHub,
    or puts GitHub's refusal in the status's notice; the watcher's next poll
    sees it closed and tears it down.
    """
    return _handed_over(board.manager.close())


MAX_GIT_LINES = 2000


@writes.post("/pull-request:fetch", status_code=204, tags=["pull request"],
             operation_id="fetchPullRequest", responses={500: FETCH_FAILED},
             summary="Fetch the pull request's branch and its base from origin.")
def fetch_pull_request(board: Serving) -> Response:
    """The diff tab asks for this when it opens, then reads the origin diff
    again, so it shows what was pushed since the last fetch.
    """
    failed = board.git.fetch(board.conversations.facts().base_branch)
    if failed is not None:
        raise Refusal(500, ErrorCode.GIT_FAILED, failed)
    return Response(status_code=204)


@writes.post("/manager/git", response_model=GitRun, tags=["manager"],
             operation_id="runGit",
             summary="Run one of the git palette's captured commands in the "
                     "worktree and answer what it printed.")
def run_git(board: Serving, asked: GitRequest) -> GitRun:
    """The dashboard's `g` then the command's keys and Enter, for the commands
    that need no terminal. It runs now, in this request, as the terminal's
    palette runs it: bounded in time, never prompting. A push that fails is
    answered here with its exit code, not refused.
    """
    exit_code, lines, seconds = board.manager.run_git(asked.keys.value)
    return GitRun(exit_code=exit_code, lines=lines[:MAX_GIT_LINES], seconds=seconds,
                  truncated=len(lines) > MAX_GIT_LINES)


def _sessions(board: Board) -> TerminalSessionList:
    return TerminalSessionList(sessions=[
        TerminalSession(id=session.id, argv=list(session.argv), worktree=session.worktree)
        for session in board.terminals.listed()])


TERMINAL_REFUSED = {"description": "The PR manager did not open it: the worktree "
                                   "holds another branch, or the command could not "
                                   "start. The detail says which.",
                    "model": Errors}


@reads.get("/terminal/sessions", response_model=TerminalSessionList, tags=["terminal"],
           operation_id="listTerminalSessions",
           summary="The terminal sessions running for this pull request.")
def list_terminal_sessions(board: Serving) -> TerminalSessionList:
    """Each is a pty in a worktree. Connect to one with a websocket at
    `/api/terminal/sessions/{id}`, and add `?after=N` to resume after the
    first N bytes it printed. It ends when its command does or its pull
    request closes, and one nobody connects to ends after 30 seconds.
    """
    return _sessions(board)


@writes.post("/terminal/sessions", response_model=TerminalSessionList, tags=["terminal"],
             operation_id="openTerminal", responses={409: TERMINAL_REFUSED},
             summary="Open a command that needs a terminal, as the git palette "
                     "opens it.")
def open_terminal(board: Serving, asked: TerminalRequest) -> TerminalSessionList:
    """The git palette's keys, or the Terminal tab's launchers. The PR
    manager opens it as a new session here. Answered with the sessions after
    it opened, so a new one is the one not listed before.
    """
    refused = board.manager.open_terminal(asked.keys)
    if refused is not None:
        raise Refusal(409, ErrorCode.TERMINAL_REFUSED, refused)
    return _sessions(board)


IfMatch = Annotated[str, Header(
    alias="If-Match",
    description="The `etag` field of the conversation being acted on, as the "
                "last read gave it. A field rather than the collection's "
                "header, because a client holding forty cards from one list "
                "read has no per-thread header, and the list's own tag moves "
                "whenever any of the forty moves. Required: without it a "
                "write would be answered by whatever the thread has become.")]

WRITE_REFUSALS: dict[ErrorCode, int] = {
    ErrorCode.EMPTY_BODY: 400,
    ErrorCode.EMPTY_BRIEF: 400,
    ErrorCode.GIT_FAILED: 500,
}

QUEUED: dict[str, Any] = {
    "description": "The operation was queued. The board holds it on disk, so "
                   "it survives the tab closing and the machine sleeping.",
    "headers": {"Location": {
        "description": "Where to read the operation.",
        "schema": {"type": "string", "format": "uri-reference"}}}}

ACCEPTED: dict[int | str, dict[str, Any]] = {
    202: QUEUED, **ONE_THREAD, 409: OUTSTANDING,
    412: PRECONDITION_FAILED}

ACCEPTED_WITH_A_REPLY: dict[int | str, dict[str, Any]] = {
    **ACCEPTED, 413: TOO_LONG}


def _denied(denied: Denied) -> Refusal:
    code = error_code(denied.code)
    return Refusal(WRITE_REFUSALS.get(code, 409), code, denied.reason)


def _within_githubs_limit(board: Board, reply: str | None) -> None:
    why = None if reply is None else board.conversations.too_long(reply)
    if why is not None:
        raise Refusal(413, ErrorCode.BODY_TOO_LONG, f"that reply is too long; {why}")


def _minted() -> str:
    return f"op_{secrets.token_hex(6)}"


def _accepted(answer: Operation | Outcome, operation_id: str, key: str) -> Response:
    return JSONResponse(
        status_code=202, content=answer.model_dump(mode="json"),
        headers={"Location": f"{PREFIX}/conversations/{key}/operations/"
                             f"{operation_id}"})


def _queued(board: Board, conversation: domain.Conversation, if_match: str,
            ask: Callable[[EditableConversation], domain.Conversation | Denied]) -> Response:
    """The precondition, then the verb asked of the thread.

    A verb goes into the pending decisions the drain reads and is answered `202`, which
    is how every decision the board takes already reaches the review threads.
    """
    key = conversation.key
    if if_match != conversation_of(conversation, board.conversations.facts().account).etag:
        raise Refusal(412, ErrorCode.PRECONDITION_FAILED,
                      f"thread {key} has moved since {if_match} was read")
    with board.conversations.editing(key) as editable:
        projected = ask(editable)
    if isinstance(projected, Denied):
        raise _denied(projected)
    waiting = _thread(board, key)
    account = board.conversations.facts().account
    operation = newest_operation(board.conversations, waiting)
    return _accepted(Outcome(
        operation=operation,
        conversation=conversation_of(projected, account).model_copy(
            update={"etag": conversation_of(waiting, account).etag})), operation.id, key)


@writes.post("/client-errors", status_code=204, tags=["board"],
             operation_id="reportClientError",
             summary="Write an error the page hit into the agent manager's log.")
def report_client_error(asked: ClientError) -> Response:
    """The page runs in a browser nobody is watching, so what goes wrong
    there is otherwise seen by no one who reads the logs afterwards.
    """
    stack = f"\n{asked.stack}" if asked.stack else ""
    log.warning("board page error in %s: %s%s", asked.where, asked.message, stack)
    return Response(status_code=204)


@writes.post("/conversations/{key}/seen", status_code=204, tags=["board"],
             operation_id="markSeen", responses=ONE_THREAD,
             summary="Say the operator opened this conversation on the board.")
def mark_seen(key: ThreadKey, board: Serving) -> Response:
    """A ready fix the operator has already opened is no news, so its banner
    is dropped. The stamp is kept out of the etag: a click is not a change a
    verb in flight should be refused over.
    """
    with board.conversations.editing(_thread(board, key).key) as editable:
        editable.mark_seen()
    return Response(status_code=204)


@writes.post("/conversations/{key}/operations:stop", status_code=202,
             response_model=Outcome, operation_id="stopWork",
             summary="Stop whatever is happening on this thread.",
             responses={**ACCEPTED, 409: {
                 "description": "Nothing is in flight, or a proposal is "
                                "waiting and `:reject` is the verb.",
                 "model": Errors}})
def stop_work(key: ThreadKey, board: Serving, if_match: IfMatch) -> Response:
    """One verb for the whole of "make it not happen", whether the board has
    picked the work up yet or not. The operator should not have to know
    which side of the drain it landed on, so the domain decides: a queued
    operation is withdrawn, a running one is halted. Nothing is posted to
    GitHub either way.

    Allowed only while something is in flight. On a thread where a run has
    finished and left a proposal this is refused with `proposal-exists`,
    which is the front end's cue to offer `:reject` instead; on a thread
    with nothing running and nothing to turn down, `nothing-in-flight`.
    """
    return _queued(board, _thread(board, key), if_match, lambda editable: editable.stop())


@writes.post("/conversations/{key}/operations:approve", status_code=202,
             response_model=Outcome, operation_id="approveThread",
             summary="Land the newest proposal on the PR branch and answer "
                     "the comment.",
             responses=ACCEPTED_WITH_A_REPLY)
def approve_thread(key: ThreadKey, board: Serving, if_match: IfMatch,
                   asked: ApproveRequest) -> Response:
    """The commit that lands carries the agent's message and authorship,
    unless the request gives a message of its own, which the commit then
    carries instead.

    Refused when the thread has no proposal, when the newest proposal has
    committed nothing, or when a landing is already under way. An approve
    over a proposal a rebase caught up whose tests did not pass is refused
    `confirm-again`: nothing failed, and the same request repeated lands it.
    """
    _within_githubs_limit(board, asked.reply)
    ticket = asked.ticket
    return _queued(
        board, _thread(board, key), if_match,
        lambda editable: editable.approve(
            reply=asked.reply or "", delete_comment=asked.delete_comment,
            resolve=asked.resolve, message=asked.message or "",
            ticket_project=None if ticket is None else ticket.project,
            ticket_title="" if ticket is None else ticket.title,
            ticket_body="" if ticket is None else ticket.body))


@writes.post("/conversations/{key}/operations:rework", status_code=202,
             response_model=Outcome, operation_id="reworkThread",
             summary="Send the newest proposal back to the agent with a "
                     "brief.",
             responses={**ACCEPTED, 400: {
                 "description": "A brief with neither a note nor a pointed "
                                "line: an autonomous rework has nothing to "
                                "work from.",
                 "model": Errors}})
def rework_thread(key: ThreadKey, board: Serving, if_match: IfMatch,
                  brief: BriefRequest) -> Response:
    """Autonomous. The agent runs on its own with the brief and leaves a
    new proposal. To drive it by hand instead, use `:start-session`.
    """
    pointed = tuple((line.file, line.line, line.text) for line in brief.pointed)
    include = tuple(brief.include)
    return _queued(
        board, _thread(board, key), if_match,
        lambda editable: editable.rework(note=brief.note, pointed=pointed,
                                           include=include))


@writes.post("/conversations/{key}/operations:start-session", status_code=202,
             response_model=Outcome, operation_id="startSession",
             summary="Open an agent session on this thread for the operator "
                     "to steer.",
             responses=ACCEPTED)
def start_session(key: ThreadKey, board: Serving, if_match: IfMatch,
                  asked: StartSessionRequest) -> Response:
    """Interactive, unlike `:rework`. The board opens an agent session on
    the thread's worktree as a terminal session, and the operator drives it.

    The operation is `running` from the moment the session opens. Nothing
    watches the session; instead the operator tells the agent in it to
    update the board, and that settles the operation, carrying a proposal
    built from whatever the session committed. A session that is abandoned
    stays `running` until it is stopped, the same as a run that hangs.
    """
    return _queued(
        board, _thread(board, key), if_match,
        lambda editable: editable.start_session(
            steer=asked.steer or "",
            pointed=[(line.file, line.line, line.text) for line in asked.pointed],
            include=asked.include))


@writes.post("/conversations/{key}/operations:retry", status_code=202,
             response_model=Outcome, operation_id="retryThread",
             summary="Run the agent again with a fresh attempt budget.",
             responses=ACCEPTED)
def retry_thread(key: ThreadKey, board: Serving, if_match: IfMatch) -> Response:
    """No brief, so a thread with a proposal waiting is refused
    `proposal-exists` rather than throwing that proposal away in silence.
    """
    return _queued(board, _thread(board, key), if_match, lambda editable: editable.retry())


@writes.post("/conversations/{key}/operations:fix", status_code=202,
             response_model=Outcome, operation_id="fixThread",
             summary="Put an agent on a thread that has no fix yet.",
             responses=ACCEPTED)
def fix_thread(key: ThreadKey, board: Serving, if_match: IfMatch) -> Response:
    """For a comment you posted yourself, which no agent picked up; a thread
    with a fix already is refused rather than started over.
    """
    return _queued(board, _thread(board, key), if_match, lambda editable: editable.fix())


@writes.post("/conversations/{key}/operations:resolve", status_code=202,
             response_model=Outcome, operation_id="resolveThread",
             summary="Close the thread on the board, and on GitHub where it "
                     "can.",
             responses=ACCEPTED_WITH_A_REPLY)
def resolve_thread(key: ThreadKey, board: Serving, if_match: IfMatch,
                   asked: ResolveRequest) -> Response:
    """With nothing written, a reviewer's thread gets a thumbs-up on its
    newest reply instead of a comment, unless `thumbs_up` is false. Refused on a thread that is already
    closed.
    """
    _within_githubs_limit(board, asked.reply)
    return _queued(
        board, _thread(board, key), if_match,
        lambda editable: editable.resolve(reply=asked.reply or "",
                                            delete_comment=asked.delete_comment,
                                            resolve=asked.resolve,
                                            thumbs_up=asked.thumbs_up))


@writes.post("/conversations/{key}/operations:reject", status_code=202,
             response_model=Outcome, operation_id="rejectProposal",
             summary="Turn down a finished proposal and drop its worktree.",
             responses={**ACCEPTED_WITH_A_REPLY, 409: {
                 "description": "Something is in flight, or there is no "
                                "proposal to turn down.",
                 "model": Errors}})
def reject_proposal(key: ThreadKey, board: Serving, if_match: IfMatch,
                    asked: CloseRequest) -> Response:
    """A decision about work that has already been done, not a way to stop
    work in progress. That is `:stop`, which posts nothing.

    Allowed only when nothing is in flight and a proposal exists: a queued
    or running operation gives `work-in-flight`, and a thread with no
    proposal gives `no-proposal`. A rework running over an older proposal
    cannot be rejected until it settles; it can be stopped.
    """
    _within_githubs_limit(board, asked.reply)
    return _queued(
        board, _thread(board, key), if_match,
        lambda editable: editable.reject(reply=asked.reply or "",
                                           delete_comment=asked.delete_comment))


@writes.post("/conversations/{key}/operations:defer", status_code=202,
             response_model=Outcome, operation_id="deferThread",
             summary="Park the thread until a condition is met.",
             responses={**ACCEPTED, 400: {
                 "description": "A wake condition the board cannot parse.",
                 "model": Errors}})
def defer_thread(key: ThreadKey, board: Serving, if_match: IfMatch,
                 asked: DeferRequest) -> Response:
    """Nothing is posted to GitHub, and a run still going is stopped, so
    that the thread has one place to come back to when it is unparked.

    `push` is the head as the drain reads it rather than as this request
    saw it, because the point of the condition is the next push after the
    park.
    """
    return _queued(
        board, _thread(board, key), if_match,
        lambda editable: editable.place(domain.ConversationState.DEFERRED, until=asked.until,
                                          note=asked.note or ""))


@writes.post("/conversations/{key}/operations:unpark", status_code=202,
             response_model=Outcome, operation_id="unparkThread",
             summary="Bring a parked thread back.", responses=ACCEPTED)
def unpark_thread(key: ThreadKey, board: Serving,
                  if_match: IfMatch) -> Response:
    """From rejected or landed this also re-runs the agent, because both
    dropped the worktree. From resolved on a reviewer's thread it unresolves
    it on GitHub, which is public. Refused on a thread that is not waiting,
    deferred or done.
    """
    return _queued(board, _thread(board, key), if_match, lambda editable: editable.unpark())


@writes.post("/conversations/{key}/operations:confirm", status_code=202,
             response_model=Outcome, operation_id="confirmThread",
             summary="Move an Assumed done thread to Done on the board alone.",
             responses={**ACCEPTED, 409: {
                 "description": "No agent placed the thread in Assumed done.",
                 "model": Errors}})
def confirm_thread(key: ThreadKey, board: Serving, if_match: IfMatch) -> Response:
    """Only the operator moves a thread to Done. Nothing is resolved, posted or
    reacted to on GitHub; the thread reads `done` with `record_state`
    `confirmed`, and a new comment brings it back.
    """
    return _queued(board, _thread(board, key), if_match,
                   lambda editable: editable.place(domain.ConversationState.DONE))


@writes.post("/conversations/{key}/operations:place", status_code=202,
             response_model=Outcome, operation_id="placeThread",
             summary="Move a thread an agent placed to the outcome the operator "
                     "chose.",
             responses={**ACCEPTED, 400: {
                 "description": "A state no outcome on this pull request lands a "
                                "thread in.",
                 "model": Errors}, 409: {
                 "description": "The thread is not Assumed done or Not my "
                                "conversation.",
                 "model": Errors}})
def place_thread(key: ThreadKey, board: Serving, if_match: IfMatch,
                 asked: PlaceRequest) -> Response:
    """Not confirm on an Assumed done thread and Move on a Not my conversation
    one. Nothing reaches GitHub; `queued`, on your own pull request, starts a
    fresh agent run.
    """
    return _queued(board, _thread(board, key), if_match,
                   lambda editable: editable.place(asked.to))


@writes.post("/conversations/{key}/operations:reply", status_code=202,
             response_model=Outcome, operation_id="replyToThread",
             summary="Post a reply to the thread.",
             responses={**ACCEPTED_WITH_A_REPLY, 400: {
                 "description": "Nothing in the reply, or GitHub no longer "
                                "has the comment to reply to.",
                 "model": Errors}})
def reply_to_thread(key: ThreadKey, board: Serving, if_match: IfMatch,
                    asked: ReplyRequest) -> Response:
    """What it does to the thread is the domain's to decide — a reply on a
    thread that was awaiting you parks it on the other party.

    It goes through the same pending decisions as every other verb, carrying the id
    this answer gives it, so the reply the drain posts is recorded as the
    operation named here.
    """
    _within_githubs_limit(board, asked.body)
    return _queued(board, _thread(board, key), if_match,
                   lambda editable: editable.reply(asked.body))


def _anchored(asked: DraftBody) -> Location:
    side = side_of(asked.side)
    start_side = None if asked.start_line is None else side_of(asked.start_side or asked.side)
    return Location(path=asked.path, line=asked.line, start_line=asked.start_line,
                    start_side=start_side, side=side)


ANCHOR_CHECKED: dict[int | str, dict[str, Any]] = {
    **ACCEPTED, 409: {
        "description": "Not a draft, already enrolled, or its anchor is not "
                       "in the diff.",
        "model": Errors},
    500: DIFF_FAILED}

EDIT_CHECKED: dict[int | str, dict[str, Any]] = {
    **ACCEPTED_WITH_A_REPLY, 409: {
        "description": "Not a draft, an enrolled draft's new anchor is not "
                       "in the diff, or it is in a review on its way to GitHub.",
        "model": Errors},
    500: DIFF_FAILED}


@writes.post("/operations:create-draft", status_code=202,
             response_model=Operation, tags=["review"],
             operation_id="createDraft",
             summary="Start a comment on a line, before it exists on GitHub.",
             responses={202: QUEUED, 413: TOO_LONG})
def create_draft(board: Serving, asked: DraftBody) -> Response:
    """Creates a conversation with kind `draft`, state `draft`, a key the
    board mints, and `github_node_id` null. Its one comment is the body
    given here, with no GitHub id, no URL and no GitHub timestamps.

    On the pull request's operations collection rather than a thread's,
    because there is no thread yet. Nothing waits on the drain, so the
    operation is `applied` in the answer.

    The anchor is not validated here. A draft may hang anywhere while it is
    being written; the check happens at `:enrol` or `:post-now`.
    """
    _within_githubs_limit(board, asked.body)
    drafted = board.conversations.open_draft(asked.body, _anchored(asked), _minted())
    if isinstance(drafted, Denied):
        raise _denied(drafted)
    made = newest_operation(board.conversations, drafted)
    return _accepted(made, made.id, drafted.key)


@writes.post("/conversations/{key}/operations:edit-draft", status_code=202,
             response_model=Outcome, operation_id="editDraft",
             summary="Change a draft's body and where it is anchored.",
             responses=EDIT_CHECKED)
def edit_draft(key: ThreadKey, board: Serving, if_match: IfMatch,
               asked: DraftBody) -> Response:
    """On a draft, enrolled or not; an enrolled one stays in the review. The
    body and the anchor are replaced together.

    **An enrolled draft's new anchor is validated here**, as `:enrol`
    validates it, when the anchor changed. One that is not in the diff is
    refused with `anchor-not-in-diff` and the draft keeps its old body and
    anchor. An edit to the body alone is not checked. While a review is on
    its way to GitHub its drafts are refused with `review-in-flight`.

    Consecutive edits collapse into one operation carrying the newest
    edit's id, so a draft composed over ten minutes leaves one entry in the
    history rather than forty.
    """
    _within_githubs_limit(board, asked.body)
    anchor = _anchored(asked)
    return _queued(board, _thread(board, key), if_match,
                   lambda editable: editable.edit(asked.body, anchor))


@writes.post("/conversations/{key}/operations:enrol", status_code=202,
             response_model=Outcome, operation_id="enrolDraft",
             summary="Add a draft to the review you are about to send.",
             responses=ANCHOR_CHECKED)
def enrol_draft(key: ThreadKey, board: Serving,
                if_match: IfMatch) -> Response:
    """Moves the thread from `draft` to `enrolled`.

    **The anchor is validated here**, against the diff from the pull
    request's merge base to its head. A draft whose anchor is not in it is
    refused with `anchor-not-in-diff` and stays a draft. A range is in it
    when its first line on `start_side` and its line on `side` are lines of
    one hunk, the first no later than the line.
    """
    conversation = _thread(board, key)
    return _queued(board, conversation, if_match, lambda editable: editable.enrol())


@writes.post("/conversations/{key}/operations:withdraw-from-review",
             status_code=202, response_model=Outcome,
             operation_id="withdrawDraft",
             summary="Take an enrolled draft back out of the outgoing review.",
             responses=ACCEPTED)
def withdraw_draft(key: ThreadKey, board: Serving,
                   if_match: IfMatch) -> Response:
    """Moves the thread from `enrolled` back to `draft`."""
    return _queued(board, _thread(board, key), if_match, lambda editable: editable.withdraw())


@writes.post("/conversations/{key}/operations:discard", status_code=202,
             response_model=Outcome, operation_id="discardDraft",
             summary="Throw a draft away.", responses=ACCEPTED)
def discard_draft(key: ThreadKey, board: Serving,
                  if_match: IfMatch) -> Response:
    """Moves the thread to `done` rather than deleting it, so a wrong
    discard is one `:unpark` back. Nothing reaches GitHub.
    """
    return _queued(board, _thread(board, key), if_match, lambda editable: editable.discard())


@writes.post("/conversations/{key}/operations:post-now", status_code=202,
             response_model=Outcome, operation_id="postDraftNow",
             summary="Post one draft on its own, without waiting for the "
                     "review.",
             responses=ANCHOR_CHECKED)
def post_draft_now(key: ThreadKey, board: Serving,
                   if_match: IfMatch) -> Response:
    """For the comment that should not wait. Posts a standalone review
    comment against the pull request's head. Once GitHub has it the
    thread's `github_node_id` is filled in and its `kind` changes from
    `draft` to `review`; its `key` does not change.

    The anchor is validated the same way `:enrol` validates it.
    """
    conversation = _thread(board, key)
    return _queued(board, conversation, if_match, lambda editable: editable.post_now())


@writes.post("/operations:send-review", status_code=202,
             response_model=Operation, tags=["review"],
             operation_id="sendReview",
             summary="Post one GitHub review carrying every enrolled draft.",
             responses={202: QUEUED, 409: {
                 "description": "A review is already going out.",
                 "model": Errors}, 413: TOO_LONG})
def send_review(board: Serving, asked: SendReviewRequest) -> Response:
    """One call to GitHub with a verdict, a summary body, and every
    `enrolled` draft as a comment, so the author gets one notification with
    the comments that justify the decision.

    The drain sends it, and it takes whatever is enrolled when it does.
    When GitHub takes it, each draft it carried gains a `posted` operation
    of its own, its `github_node_id`, and kind `review`, under the key it
    always had. When GitHub refuses it, every draft stays `enrolled` and
    this operation settles `refused` with `github-rejected` and GitHub's
    words, so the operator fixes and sends again.

    `body` is required for `REQUEST_CHANGES` and `COMMENT` and refused
    `empty-body` here, before anything reaches GitHub. Nothing enrolled is
    not refused: an approval, or a summary on its own, is a review GitHub
    takes.
    """
    _within_githubs_limit(board, asked.body)
    review = board.conversations.send_review(verdict_of(asked.verdict), asked.body)
    if isinstance(review, Denied):
        raise _denied(review)
    sent = next(one for one in reviews_of(board.conversations) if one.id == review.id)
    return JSONResponse(
        status_code=202, content=sent.model_dump(mode="json"),
        headers={"Location": f"{PREFIX}/operations/{review.id}"})


def _dashboard(board: Board) -> Dashboard:
    return dashboard_of(board.manager.dashboard())


def _changes(board: Board) -> ManagerChanges:
    return ManagerChanges(markdown=board.manager.changes())


def _output(board: Board, lines: int) -> AgentOutput:
    return AgentOutput(lines=[OutputLine(text=text, run_boundary=boundary)
                               for text, boundary in board.manager.agent_output(lines)])


OutputLines = Annotated[int, Query(ge=1, le=MAX_OUTPUT_LINES)]


@reads.get("/dashboard", response_model=Dashboard, tags=["manager"],
           operation_id="readDashboard",
           summary="Everything the PR manager's dashboard shows, as data.",
           responses=etag.TAGGED)
def read_dashboard(request: Request, board: Serving) -> Response:
    """Built on each read from what is on disk, with the PR manager's status
    file laid over it: the same dashboard the hub's wall shows for this pull
    request. The manager rewrites its status once a tick; a poll that sends
    the `ETag` back is answered `304` while the manager is idle and nothing
    moves.
    """
    return etag.answered(request, _dashboard(board))


@reads.get("/manager/changes", response_model=ManagerChanges, tags=["manager"],
           operation_id="readManagerChanges",
           summary="The agent's notes on what it changed in this pull request.",
           responses=etag.TAGGED)
def read_manager_changes(request: Request, board: Serving) -> Response:
    """Read from the worktree on each request, so it is as fresh as the file."""
    return etag.answered(request, _changes(board))


@reads.get("/manager/agent-output", response_model=AgentOutput, tags=["manager"],
           operation_id="readAgentOutput",
           summary="The tail of what the agent has said on this pull request.",
           responses=etag.TAGGED)
def read_agent_output(request: Request, board: Serving, lines: OutputLines = 200) -> Response:
    """The last `lines` lines across this pull request's runs, with a marker
    where one run ends and the next begins.
    """
    return etag.answered(request, _output(board, lines))


@reads.get("/dashboard/stream", tags=["manager"], operation_id="streamDashboard",
           response_class=StreamingResponse, responses=described("dashboard", Dashboard),
           summary="The dashboard, sent again each time it changes.")
def stream_dashboard(request: Request, board: Serving) -> Response:
    return streamed(request, "dashboard", lambda: _dashboard(board), board.heartbeat_seconds, board.check_seconds)


@reads.get("/manager/changes/stream", tags=["manager"],
           operation_id="streamManagerChanges", response_class=StreamingResponse,
           responses=described("changes", ManagerChanges),
           summary="The agent's notes, sent again each time they change.")
def stream_manager_changes(request: Request, board: Serving) -> Response:
    return streamed(request, "changes", lambda: _changes(board), board.heartbeat_seconds, board.check_seconds)


@reads.get("/manager/agent-output/stream", tags=["manager"],
           operation_id="streamAgentOutput", response_class=StreamingResponse,
           responses=described("agent-output", AgentOutput),
           summary="The tail of the agent's output, sent again each time it grows.")
def stream_agent_output(request: Request, board: Serving, lines: OutputLines = 200) -> Response:
    return streamed(request, "agent-output", lambda: _output(board, lines),
                    board.heartbeat_seconds, board.check_seconds)


@reads.websocket("/terminal/sessions/{session}")
async def connect_terminal(websocket: WebSocket, session: str,
                           after: Annotated[int, Query(ge=0)] = 0) -> None:
    board: Board = websocket.app.state.board
    await carried(websocket, board.terminals, session, after, board.terminal_threads)


@reads.api_route("/{unknown:path}", methods=["GET", "POST"],
                 include_in_schema=False)
def read_nothing(unknown: str) -> Response:
    raise Refusal(404, ErrorCode.NOT_FOUND,
                  f"this board serves nothing at {PREFIX}/{unknown}")


page = APIRouter()


@page.get("/{whatever:path}", include_in_schema=False)
async def serve_the_page(request: Request, board: Serving) -> Response:
    return await run_in_threadpool(
        page_at, board.fonts, board.app_root, target(request),
        request.headers.get("Accept-Encoding"),
        failed=b"<p>board error \xe2\x80\x94 see the PR manager's log</p>")


def board_app(board: Board) -> FastAPI:
    app = RefusingApp(
        title="Review board",
        version="5.0.0",
        summary="One pull request's comment threads, and what the agent "
                "wrote for them.",
        description=DESCRIPTION,
        openapi_url=None, docs_url=None, redoc_url=None,
        routes=[*writes.routes, *reads.routes, *page.routes],
    )
    app.state.board = board
    add_refusal_handlers(app)
    guard(app, board.port, name="board", failed=SERVER_ERROR_DETAIL)
    return app
