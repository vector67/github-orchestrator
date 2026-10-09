from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

from github_orchestrator.cli._report_commands import (
    REPLIED_AS,
    SKIPPED_AS,
    TEST_OUTCOMES,
)
from github_orchestrator.conversation import (
    Classification,
    Conversation,
    ConversationManagerFactory,
    Denied,
    EditableConversation,
)
from github_orchestrator.domain import Location, Pr, Repo, Side


def _die(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    sys.exit(1)


def _pr_of(args: argparse.Namespace) -> Pr:
    return Pr(args.repo, args.pr)


def _body_of(body_file: str) -> str:
    path = Path(body_file)
    if not path.is_file():
        _die(f"--body-file {body_file!r} is not a file")
    try:
        return path.read_text()
    except OSError as exc:
        _die(f"--body-file {body_file!r} could not be read: {exc}")


def thread_open(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                gist_model: str | None) -> None:
    body = _body_of(args.body_file)
    if gist_model:
        print(f"waiting for {gist_model} to write the comment's one-line gist…",
              file=sys.stderr)
    manager = conversation_managers.of(_pr_of(args))
    worktree = manager.open_thread(args.thread_id, kind=args.comment_type,
                                   path=args.path, line=args.line,
                                   comment_id=args.comment_id, author=args.author,
                                   body=body)
    if isinstance(worktree, Denied):
        _die(worktree.reason)
    print(worktree)


def _report_or_die(args: argparse.Namespace, conversation_managers: ConversationManagerFactory,
                   reported: Callable[[EditableConversation], object], target: str) -> None:
    key = args.thread_id
    with conversation_managers.of(_pr_of(args)).editing(key) as conversation:
        outcome = reported(conversation)
    if isinstance(outcome, Denied):
        _die(f"{_pr_of(args)} thread {key} was not marked {target}: {outcome.reason}")


def thread_skip(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                gist_model: str | None) -> None:
    _report_or_die(args, conversation_managers, lambda conversation: conversation.not_a_fix(
        Classification(args.classification), args.reason), "skipped")


def thread_reply(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                 gist_model: str | None) -> None:
    _report_or_die(args, conversation_managers, lambda conversation: conversation.not_a_fix(
        Classification(args.classification), args.body), "replied")


def thread_ticket(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                  gist_model: str | None) -> None:
    _report_or_die(args, conversation_managers, lambda conversation: conversation.not_a_fix(
        Classification.OUT_OF_SCOPE, args.reply, ticket_project=args.project,
        ticket_title=args.title, ticket_body=args.body), "ticketed")


def thread_filed(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                 gist_model: str | None) -> None:
    _report_or_die(args, conversation_managers, lambda conversation: conversation.not_a_fix(
        Classification.OUT_OF_SCOPE, "", filed_key=args.key, filed_url=args.url), "filed")


def _paired_steps(args: argparse.Namespace) -> tuple[tuple[str, str | None], ...]:
    files = args.file or []
    if files and len(files) != len(args.step):
        _die(f"--file was given {len(files)} times for {len(args.step)} "
             f"--step; pass one --file per step, in the same order, or none "
             f"at all")
    named = [file or None for file in files]
    return tuple(zip(args.step, named or [None] * len(args.step)))


def thread_plan(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                gist_model: str | None) -> None:
    steps = _paired_steps(args)
    _report_or_die(args, conversation_managers,
                   lambda conversation: conversation.plan(steps), "planned")


def thread_step(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                gist_model: str | None) -> None:
    _report_or_die(args, conversation_managers,
                   lambda conversation: conversation.step_done(args.done), "done")


def thread_ready(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                gist_model: str | None) -> None:
    _report_or_die(args, conversation_managers, lambda conversation: conversation.ready(
        args.sha, tests=args.tests, tests_note=args.tests_note, note=args.note,
        summary=args.summary, confidence=args.confidence,
        confidence_note=args.confidence_note), "ready")
    thread_show(args, conversation_managers=conversation_managers, gist_model=gist_model)


def thread_base(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                gist_model: str | None) -> None:
    _report_or_die(args, conversation_managers,
                   lambda conversation: conversation.move_base(args.sha), "rebased")


def thread_fail(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                gist_model: str | None) -> None:
    _report_or_die(args, conversation_managers,
                   lambda conversation: conversation.fail(args.reason), "failed")


def thread_draft(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                gist_model: str | None) -> None:
    body = _body_of(args.body_file)
    if not body.strip():
        _die(f"--body-file {args.body_file!r} holds nothing to say")
    drafted = conversation_managers.of(_pr_of(args)).open_draft(
        body, Location(path=args.path, line=args.line, start_line=args.start_line,
                       start_side=(None if args.start_line is None
                                   else Side(args.start_side or args.side)),
                       side=Side(args.side)))
    if isinstance(drafted, Denied):
        _die(drafted.reason)
    print(drafted.key)


def _listed(conversation: Conversation) -> str:
    if conversation.is_unreadable:
        return f"{conversation.key}  unreadable"
    where = f"{conversation.path}:{conversation.line}" if conversation.path else ""
    return "  ".join(part for part in (conversation.key, conversation.standing.value,
                                       where, conversation.gist) if part)


def thread_list(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                gist_model: str | None) -> None:
    for conversation in conversation_managers.of(_pr_of(args)).all():
        print(_listed(conversation))


def _shown(conversation: Conversation) -> dict[str, object]:
    fix = conversation.fix
    return {
        "key": conversation.key, "state": conversation.standing.value,
        "path": conversation.path, "line": conversation.line, "gist": conversation.gist,
        "sha": fix.thread_sha.hex if fix.thread_sha else None, "tests": fix.tests, "tests_note": fix.tests_note,
        "note": fix.agent_note, "summary": fix.summary,
        "confidence": fix.confidence.value if fix.confidence else None,
        "confidence_note": fix.confidence_note,
    }


def thread_show(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                gist_model: str | None) -> None:
    conversation = conversation_managers.of(_pr_of(args)).get(args.thread_id)
    if conversation is None:
        _die(f"{_pr_of(args)} has no thread {args.thread_id}")
    if conversation.is_unreadable:
        _die(f"{_pr_of(args)} thread {args.thread_id} is unreadable")
    print(json.dumps(_shown(conversation), indent=2))


THREAD_COMMANDS = {
    "open": thread_open,
    "plan": thread_plan,
    "step": thread_step,
    "skip": thread_skip,
    "reply": thread_reply,
    "ticket": thread_ticket,
    "filed": thread_filed,
    "ready": thread_ready,
    "base": thread_base,
    "fail": thread_fail,
    "draft": thread_draft,
    "list": thread_list,
    "show": thread_show,
}


def parse_repo(text: str) -> Repo:
    try:
        return Repo.parse(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", type=parse_repo, required=True,
                        help="The PR's repo, as owner/name")
    parser.add_argument("--pr", type=int, required=True, help="PR number")


def _comment_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--comment-id", type=int, required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--path", default=None,
                        help="Anchored file path (omit for a non-anchored comment)")
    parser.add_argument("--line", type=int, default=None)
    parser.add_argument("--comment-type", default="review")
    parser.add_argument("--body-file", required=True,
                        help="File holding the comment body")


def add_thread_parsers(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    thread_parser = sub.add_parser(
        "thread",
        description="Manage comment-fix threads (review-board Phase 1).",
    )
    thread_sub = thread_parser.add_subparsers(dest="thread_command")

    open_parser = thread_sub.add_parser(
        "open",
        help="Create worktree + branch off PR head, record status=pending, print the worktree path.",
    )
    _common(open_parser)
    _comment_fields(open_parser)

    plan_parser = thread_sub.add_parser(
        "plan",
        help="Write down the steps the fix will take, before making it.",
    )
    _common(plan_parser)
    plan_parser.add_argument("--thread-id", required=True)
    plan_parser.add_argument("--step", action="append", required=True,
                             help="One step, in the order you will do them")
    plan_parser.add_argument("--file", action="append", default=None,
                             help="The file that step touches; one per --step "
                                  "or none at all")

    step_parser = thread_sub.add_parser(
        "step", help="Mark a step of the plan finished, as you finish it."
    )
    _common(step_parser)
    step_parser.add_argument("--thread-id", required=True)
    step_parser.add_argument("--done", action="append", type=int, required=True,
                             help="The number of a step, counting from 1")

    skip_parser = thread_sub.add_parser(
        "skip",
        help="The comment needs neither code nor an answer from the agent: working -> skipped.",
    )
    _common(skip_parser)
    skip_parser.add_argument("--thread-id", required=True)
    skip_parser.add_argument(
        "--classification", required=True, choices=SKIPPED_AS,
    )
    skip_parser.add_argument("--reason", required=True)

    reply_parser = thread_sub.add_parser(
        "reply",
        help="The comment needs an answer and no code: propose the reply for the author "
             "to accept.",
    )
    _common(reply_parser)
    reply_parser.add_argument("--thread-id", required=True)
    reply_parser.add_argument(
        "--classification", required=True, choices=REPLIED_AS,
    )
    reply_parser.add_argument("--body", required=True,
                              help="The reply to post on the comment, in full")

    ticket_parser = thread_sub.add_parser(
        "ticket",
        help="The comment asks for work outside this pull request and the tracker has no "
             "ticket for it: propose a ticket, and the reply that says so, for the author "
             "to accept.",
    )
    _common(ticket_parser)
    ticket_parser.add_argument("--thread-id", required=True)
    ticket_parser.add_argument("--project", required=True,
                               help="The Jira project key, or owner/name for GitHub issues")
    ticket_parser.add_argument("--title", required=True, help="The ticket's title")
    ticket_parser.add_argument("--body", required=True, help="The ticket's description")
    ticket_parser.add_argument("--reply", required=True,
                               help="The reply to post on the comment once the ticket is filed")

    filed_parser = thread_sub.add_parser(
        "filed",
        help="The ticket the author accepted is filed: the board posts the reply with its "
             "link.",
    )
    _common(filed_parser)
    filed_parser.add_argument("--thread-id", required=True)
    filed_parser.add_argument("--key", required=True,
                              help="The key the tracker gave the ticket, such as PROJ-12 or #12")
    filed_parser.add_argument("--url", required=True, help="The ticket's link")

    ready_parser = thread_sub.add_parser(
        "ready", help="The subagent committed in its worktree: status=ready."
    )
    _common(ready_parser)
    ready_parser.add_argument("--thread-id", required=True)
    ready_parser.add_argument("--sha", required=True,
                              help="The commit the subagent made")
    ready_parser.add_argument("--tests", required=True, choices=TEST_OUTCOMES)
    ready_parser.add_argument("--tests-note", default=None)
    ready_parser.add_argument("--note", default=None,
                              help="One line: what the subagent changed")
    ready_parser.add_argument("--summary", default=None,
                              help="One line: what the fix does")
    ready_parser.add_argument("--confidence", default=None,
                              help="How sure the agent is of the fix")
    ready_parser.add_argument("--confidence-note", default=None,
                              help="One sentence behind that level")

    base_parser = thread_sub.add_parser(
        "base", help="Move the commit the thread's fix is built on, after rebasing "
                     "the fix onto a newer tip of the PR branch.")
    _common(base_parser)
    base_parser.add_argument("--thread-id", required=True)
    base_parser.add_argument("--sha", required=True,
                             help="The PR branch's tip the fix now sits on")

    fail_parser = thread_sub.add_parser(
        "fail", help="The attempt failed: status=failed, worktree kept for rework."
    )
    _common(fail_parser)
    fail_parser.add_argument("--thread-id", required=True)
    fail_parser.add_argument("--reason", required=True)

    draft_parser = thread_sub.add_parser(
        "draft",
        help="A review finding on one line of the diff: a draft on the "
             "board, nothing on GitHub. Prints its key.",
    )
    _common(draft_parser)
    draft_parser.add_argument("--path", required=True,
                              help="The file, relative to the repo root")
    draft_parser.add_argument("--line", type=int, required=True,
                              help="The line on the pull request's head")
    draft_parser.add_argument("--start-line", type=int, default=None,
                              help="The first line, where it spans several")
    draft_parser.add_argument("--start-side", default=None,
                              choices=[side.value for side in Side],
                              help="The side the first line is on; --side where not given")
    draft_parser.add_argument("--side", default=Side.AFTER.value,
                              choices=[side.value for side in Side])
    draft_parser.add_argument("--body-file", required=True,
                              help="File holding the comment")

    list_parser = thread_sub.add_parser(
        "list", help="Print a PR's threads, one a line: key, state, where it hangs, what it is about.")
    _common(list_parser)

    show_parser = thread_sub.add_parser(
        "show", help="Print one thread's saved record as JSON: state, sha, tests, notes.")
    _common(show_parser)
    show_parser.add_argument("--thread-id", required=True)

    return thread_parser

