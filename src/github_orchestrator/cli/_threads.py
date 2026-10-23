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
    CommitVerdict,
    Conversation,
    ConversationManagerFactory,
    ConversationState,
    Denied,
    EditableConversation,
    Verdict,
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
                   reported: Callable[[EditableConversation], object], target: str,
                   direction: str = "") -> None:
    key = args.thread_id
    with conversation_managers.of(_pr_of(args)).editing(key, direction=direction) as conversation:
        outcome = reported(conversation)
    if isinstance(outcome, Denied):
        _die(f"{_pr_of(args)} thread {key} was not marked {target}: {outcome.reason}")


def _directed_or_die(args: argparse.Namespace,
                     conversation_managers: ConversationManagerFactory,
                     asked: Callable[[EditableConversation], object], target: str) -> None:
    _report_or_die(args, conversation_managers, asked, target, args.human_direction)


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


def thread_check(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                 gist_model: str | None) -> None:
    _report_or_die(args, conversation_managers, lambda conversation: conversation.set_commit_verdict(
        CommitVerdict(args.verdict), args.reason), args.verdict)


PLACEABLE = (ConversationState.READY, ConversationState.WAITING, ConversationState.NOT_MINE,
             ConversationState.QUEUED, ConversationState.DEFERRED, ConversationState.DONE)


def thread_place(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                 gist_model: str | None) -> None:
    _directed_or_die(args, conversation_managers, lambda conversation: conversation.place(
        ConversationState(args.to), until=args.until, note=args.note), args.to)


def _pointed(args: argparse.Namespace) -> tuple[tuple[str, int | None, str], ...]:
    pointed = []
    for point in args.point or []:
        file, _, rest = point.partition(":")
        line, _, text = rest.partition(":")
        if not file or not (line == "" or line.isdigit()):
            _die(f"--point {point!r} is not FILE:LINE:TEXT")
        pointed.append((file, int(line) if line else None, text))
    return tuple(pointed)


def thread_unpark(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                  gist_model: str | None) -> None:
    _directed_or_die(args, conversation_managers,
                   lambda conversation: conversation.unpark(), "unparked")


def thread_approve(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                   gist_model: str | None) -> None:
    _directed_or_die(args, conversation_managers, lambda conversation: conversation.approve(
        reply=args.reply, delete_comment=args.delete_comment, resolve=args.resolve,
        message=args.message, ticket_project=args.ticket_project,
        ticket_title=args.ticket_title, ticket_body=args.ticket_body), "approved")


def thread_rework(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                  gist_model: str | None) -> None:
    pointed = _pointed(args)
    _directed_or_die(args, conversation_managers, lambda conversation: conversation.rework(
        note=args.note, pointed=pointed, include=args.include or ()), "reworked")


def thread_session(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                   gist_model: str | None) -> None:
    pointed = _pointed(args)
    _directed_or_die(args, conversation_managers, lambda conversation: conversation.start_session(
        steer=args.steer, pointed=pointed, include=args.include or ()), "given a session")


def thread_fix(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
               gist_model: str | None) -> None:
    _directed_or_die(args, conversation_managers,
                   lambda conversation: conversation.fix(), "queued for a fix")


def thread_retry(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                 gist_model: str | None) -> None:
    _directed_or_die(args, conversation_managers,
                   lambda conversation: conversation.retry(), "retried")


def thread_stop(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                gist_model: str | None) -> None:
    _directed_or_die(args, conversation_managers,
                   lambda conversation: conversation.stop(), "stopped")


def thread_resolve(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                   gist_model: str | None) -> None:
    _directed_or_die(args, conversation_managers, lambda conversation: conversation.resolve(
        reply=args.reply, delete_comment=args.delete_comment, resolve=args.resolve,
        thumbs_up=args.resolve and not args.no_thumbs_up), "resolved")


def thread_reject(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                  gist_model: str | None) -> None:
    _directed_or_die(args, conversation_managers, lambda conversation: conversation.reject(
        reply=args.reply, delete_comment=args.delete_comment), "rejected")


def thread_answer(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                  gist_model: str | None) -> None:
    _directed_or_die(args, conversation_managers,
                   lambda conversation: conversation.reply(args.body), "answered")


def _location(args: argparse.Namespace) -> Location:
    return Location(path=args.path, line=args.line, start_line=args.start_line,
                    start_side=(None if args.start_line is None
                                else Side(args.start_side or args.side)),
                    side=Side(args.side))


def _said(body_file: str) -> str:
    body = _body_of(body_file)
    if not body.strip():
        _die(f"--body-file {body_file!r} holds nothing to say")
    return body


def thread_edit(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                gist_model: str | None) -> None:
    body, anchor = _said(args.body_file), _location(args)
    _directed_or_die(args, conversation_managers,
                   lambda conversation: conversation.edit(body, anchor), "edited")


def thread_enrol(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                 gist_model: str | None) -> None:
    _directed_or_die(args, conversation_managers,
                   lambda conversation: conversation.enrol(), "enrolled")


def thread_withdraw(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                    gist_model: str | None) -> None:
    _directed_or_die(args, conversation_managers,
                   lambda conversation: conversation.withdraw(), "withdrawn")


def thread_discard(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                   gist_model: str | None) -> None:
    _directed_or_die(args, conversation_managers,
                   lambda conversation: conversation.discard(), "discarded")


def thread_post_now(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                    gist_model: str | None) -> None:
    _directed_or_die(args, conversation_managers,
                   lambda conversation: conversation.post_now(), "posted")


def thread_send_review(args: argparse.Namespace, *,
                       conversation_managers: ConversationManagerFactory,
                       gist_model: str | None) -> None:
    review = conversation_managers.of(_pr_of(args)).send_review(
        Verdict(args.verdict), args.body, args.human_direction)
    if isinstance(review, Denied):
        _die(f"{_pr_of(args)} sent no review: {review.reason}")
    print(review.id)


def thread_draft(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                gist_model: str | None) -> None:
    drafted = conversation_managers.of(_pr_of(args)).open_draft(
        _said(args.body_file), _location(args))
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
    "check": thread_check,
    "place": thread_place,
    "unpark": thread_unpark,
    "approve": thread_approve,
    "rework": thread_rework,
    "session": thread_session,
    "fix": thread_fix,
    "retry": thread_retry,
    "stop": thread_stop,
    "resolve": thread_resolve,
    "reject": thread_reject,
    "answer": thread_answer,
    "edit": thread_edit,
    "enrol": thread_enrol,
    "withdraw": thread_withdraw,
    "discard": thread_discard,
    "post-now": thread_post_now,
    "send-review": thread_send_review,
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


WAKES = ("manual", "reply", "ci", "push")


def _wake(text: str) -> str:
    if text in WAKES or (text.startswith("pr:") and text[3:].isdigit()):
        return text
    raise argparse.ArgumentTypeError(f"{text!r} is none of {', '.join(WAKES)} or pr:<number>")


HUMAN_ONLY = ("HUMAN ONLY: {what} An agent runs this only when a human told it to, "
              "and quotes them in --human-direction.")


def _human_only(thread_sub: argparse._SubParsersAction[argparse.ArgumentParser], verb: str,
                what: str, *, thread: bool = True) -> argparse.ArgumentParser:
    parser = thread_sub.add_parser(verb, help=HUMAN_ONLY.format(what=what),
                                   description=HUMAN_ONLY.format(what=what))
    _common(parser)
    if thread:
        parser.add_argument("--thread-id", required=True)
    parser.add_argument("--human-direction", required=True,
                        help="The human's instruction, quoted, with who gave it; "
                             "kept in the thread's history")
    return parser


def _brief_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--point", action="append", default=None,
                        help="A line to point the agent at, as FILE:LINE:TEXT "
                             "(LINE may be empty); repeat for more")
    parser.add_argument("--include", action="append", default=None,
                        help="A file to hand the agent; repeat for more")


def _anchor_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--path", required=True,
                        help="The file, relative to the repo root")
    parser.add_argument("--line", type=int, required=True,
                        help="The line on the pull request's head")
    parser.add_argument("--start-line", type=int, default=None,
                        help="The first line, where it spans several")
    parser.add_argument("--start-side", default=None,
                        choices=[side.value for side in Side],
                        help="The side the first line is on; --side where not given")
    parser.add_argument("--side", default=Side.AFTER.value,
                        choices=[side.value for side in Side])


def _add_human_only_parsers(thread_sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    place_parser = _human_only(
        thread_sub, "place", "move a thread to the outcome the operator chose, as the "
                             "board's move does; deferred parks it and done confirms it.")
    place_parser.add_argument("--to", required=True, choices=[state.value for state in PLACEABLE])
    place_parser.add_argument("--until", type=_wake, default="manual",
                              help="With --to deferred: what wakes it, one of "
                                   "manual, reply, ci, push or pr:<number>")
    place_parser.add_argument("--note", default="",
                              help="With --to deferred: why it waits")

    _human_only(thread_sub, "unpark", "wake a deferred thread now.")

    approve_parser = _human_only(thread_sub, "approve",
                                 "accept the agent's proposal: push its fix, post its reply "
                                 "or file its ticket.")
    approve_parser.add_argument("--reply", default="", help="The reply to post with it")
    approve_parser.add_argument("--delete-comment", action="store_true",
                                help="Delete the comment instead of answering it")
    approve_parser.add_argument("--resolve", action="store_true",
                                help="Mark the thread resolved on GitHub")
    approve_parser.add_argument("--message", default="",
                                help="The commit message, in place of the agent's")
    approve_parser.add_argument("--ticket-project", default=None,
                                help="The ticket's project, in place of the agent's")
    approve_parser.add_argument("--ticket-title", default="", help="The ticket's title")
    approve_parser.add_argument("--ticket-body", default="", help="The ticket's description")

    rework_parser = _human_only(thread_sub, "rework",
                                "send the agent's proposal back with a note on what to change.")
    rework_parser.add_argument("--note", default="", help="What to change")
    _brief_fields(rework_parser)

    session_parser = _human_only(thread_sub, "session",
                                 "open an interactive agent session on the thread.")
    session_parser.add_argument("--steer", default="", help="What to start the session with")
    _brief_fields(session_parser)

    _human_only(thread_sub, "fix", "ask the agent to write a fix for the thread.")
    _human_only(thread_sub, "retry", "run the agent again on a thread whose attempts failed.")
    _human_only(thread_sub, "stop", "stop the agent's run on the thread.")

    resolve_parser = _human_only(thread_sub, "resolve",
                                 "close the thread as done, with a reply if one is given.")
    resolve_parser.add_argument("--reply", default="", help="The reply to post")
    resolve_parser.add_argument("--delete-comment", action="store_true",
                                help="Delete the comment instead of answering it")
    resolve_parser.add_argument("--resolve", action="store_true",
                                help="Mark the thread resolved on GitHub")
    resolve_parser.add_argument("--no-thumbs-up", action="store_true",
                                help="Leave the comment without a thumbs-up")

    reject_parser = _human_only(thread_sub, "reject",
                                "turn the agent's proposal down and close the thread.")
    reject_parser.add_argument("--reply", default="", help="The reply to post")
    reject_parser.add_argument("--delete-comment", action="store_true",
                               help="Delete the comment instead of answering it")

    answer_parser = _human_only(thread_sub, "answer",
                                "post the human's own reply on the thread now.")
    answer_parser.add_argument("--body", required=True, help="The reply, in full")

    edit_parser = _human_only(thread_sub, "edit", "rewrite a draft or move it to another line.")
    _anchor_fields(edit_parser)
    edit_parser.add_argument("--body-file", required=True, help="File holding the comment")

    _human_only(thread_sub, "enrol", "put a draft in the review that goes out next.")
    _human_only(thread_sub, "withdraw", "take a draft back out of the review.")
    _human_only(thread_sub, "discard", "throw a draft away.")
    _human_only(thread_sub, "post-now", "post a draft on GitHub on its own, now.")

    review_parser = _human_only(thread_sub, "send-review",
                                "send the review with every enrolled draft in it. Prints "
                                "its id.", thread=False)
    review_parser.add_argument("--verdict", required=True,
                               choices=[verdict.value for verdict in Verdict])
    review_parser.add_argument("--body", default=None, help="The review's summary")


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

    check_parser = thread_sub.add_parser(
        "check", help="Set by hand whether the commit the PR author named addresses "
                      "your comment, over the commit check's verdict.")
    _common(check_parser)
    check_parser.add_argument("--thread-id", required=True)
    check_parser.add_argument("--verdict", required=True,
                              choices=[verdict.value for verdict in CommitVerdict])
    check_parser.add_argument("--reason", default="set by hand",
                              help="One line: why the commit does or does not address it")

    _add_human_only_parsers(thread_sub)

    draft_parser = thread_sub.add_parser(
        "draft",
        help="A review finding on one line of the diff: a draft on the "
             "board, nothing on GitHub. Prints its key.",
    )
    _common(draft_parser)
    _anchor_fields(draft_parser)
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

