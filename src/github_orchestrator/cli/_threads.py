from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

from github_orchestrator.cli._help_format import OptionHelp
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
    HumanDirection,
    Verdict,
)
from github_orchestrator.domain import Location, Pr, Repo, Sha, Side


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
                   direction: HumanDirection = HumanDirection("")) -> None:
    key = args.thread_id
    with conversation_managers.of(_pr_of(args)).editing(key, direction=direction) as conversation:
        outcome = reported(conversation)
    if isinstance(outcome, Denied):
        _die(f"{_pr_of(args)} thread {key} was not marked {target}: {outcome.reason}")


def _directed_or_die(args: argparse.Namespace,
                     conversation_managers: ConversationManagerFactory,
                     asked: Callable[[EditableConversation], object], target: str) -> None:
    _report_or_die(args, conversation_managers, asked, target,
                   HumanDirection(args.human_direction))


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


def _given(*values: str | None) -> bool | None:
    present = [value is not None for value in values]
    if all(present):
        return True
    return None if any(present) else False


def _split_ticket(args: argparse.Namespace) -> dict[str, str]:
    drafted = _given(args.project, args.title, args.body)
    existing = _given(args.ticket_key, args.ticket_url)
    if None in (drafted, existing) or [args.same_ticket, drafted, existing].count(True) != 1:
        _die("pass exactly one of --same-ticket; --ticket-key and --ticket-url for an existing "
             "ticket; or --project, --title and --body for a new ticket")
    if existing:
        return {"ticket_key": args.ticket_key, "ticket_url": args.ticket_url}
    if drafted:
        return {"ticket_project": args.project, "ticket_title": args.title,
                "ticket_body": args.body}
    return {}


def thread_split(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                 gist_model: str | None) -> None:
    ticket = _split_ticket(args)
    _report_or_die(args, conversation_managers, lambda conversation: conversation.split(
        args.sha, branch=args.branch, base=args.base, base_reason=args.base_reason,
        reply=args.reply, **ticket), "split")


def thread_filed(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                 gist_model: str | None) -> None:
    _report_or_die(args, conversation_managers, lambda conversation: conversation.not_a_fix(
        Classification.OUT_OF_SCOPE, "", filed_key=args.key, filed_url=args.url), "filed")


def thread_opened(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                  gist_model: str | None) -> None:
    _report_or_die(args, conversation_managers,
                   lambda conversation: conversation.opened(args.url), "opened")


def thread_reconciled(args: argparse.Namespace, *,
                      conversation_managers: ConversationManagerFactory,
                      gist_model: str | None) -> None:
    landed = None if args.landed_sha is None else Sha.parse(args.landed_sha)
    if args.landed_sha is not None and landed is None:
        _die(f"--landed-sha {args.landed_sha!r} is no commit sha")
    _report_or_die(args, conversation_managers,
                   lambda conversation: conversation.reconciled(args.note, landed),
                   "reconciled")


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


def thread_ask(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
               gist_model: str | None) -> None:
    _report_or_die(args, conversation_managers, lambda conversation: conversation.ask(
        args.question, args.context, args.option or ()), "asking")


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


SPLIT_PARTS = ("ticket", "changes", "new-pr", "reply")

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
        ticket_title=args.ticket_title, ticket_body=args.ticket_body, part=args.part),
        "approved")


def thread_edit_part(args: argparse.Namespace, *,
                     conversation_managers: ConversationManagerFactory,
                     gist_model: str | None) -> None:
    _directed_or_die(args, conversation_managers, lambda conversation: conversation.edit_part(
        args.part, reply=args.reply, ticket_project=args.ticket_project,
        ticket_title=args.ticket_title, ticket_body=args.ticket_body), "edited")


def thread_rework(args: argparse.Namespace, *, conversation_managers: ConversationManagerFactory,
                  gist_model: str | None) -> None:
    pointed = _pointed(args)
    _directed_or_die(args, conversation_managers, lambda conversation: conversation.rework(
        note=args.note, pointed=pointed, include=args.include or (), part=args.part),
        "reworked")


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
        Verdict(args.verdict), args.body, HumanDirection(args.human_direction))
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
    "split": thread_split,
    "filed": thread_filed,
    "opened": thread_opened,
    "reconciled": thread_reconciled,
    "ready": thread_ready,
    "ask": thread_ask,
    "base": thread_base,
    "fail": thread_fail,
    "check": thread_check,
    "place": thread_place,
    "unpark": thread_unpark,
    "approve": thread_approve,
    "rework": thread_rework,
    "edit-part": thread_edit_part,
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


THREAD_LINE = "Report on and act on a pull request's comment threads: the agents' side of the board."

_THREAD_MORE = (
    "Each verb changes one thread, or for send-review one PR's review, and says why when "
    "it refuses. The agents run the reporting "
    "verbs from their briefs; a HUMAN ONLY verb runs only when a person asked for it. Run "
    "thread <verb> --help for a verb's options.")


def _verb(thread_sub: argparse._SubParsersAction[argparse.ArgumentParser], verb: str, line: str, more: str) -> argparse.ArgumentParser:
    return thread_sub.add_parser(verb, help=line, description=f"{line} {more}",
                                 formatter_class=OptionHelp)


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", type=parse_repo, required=True,
                        help="The PR's repo, as owner/name")
    parser.add_argument("--pr", type=int, required=True, help="PR number")


def _thread_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--thread-id", required=True,
                        help="The thread's key, as the brief names it or thread list prints it")


HUMAN_ONLY = ("HUMAN ONLY: {what} An agent runs this only when a human told it to, "
              "and quotes them in --human-direction.")


def _human_only(thread_sub: argparse._SubParsersAction[argparse.ArgumentParser], verb: str, what: str, more: str, *,
                thread: bool = True) -> argparse.ArgumentParser:
    parser = _verb(thread_sub, verb, HUMAN_ONLY.format(what=what), more)
    _common(parser)
    if thread:
        _thread_id(parser)
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
                        choices=[side.value for side in Side],
                        help="The side of the diff the line is on: after for the PR's "
                             "head, before for its base")


def _add_human_only_parsers(thread_sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    place_parser = _human_only(
        thread_sub, "place", "move a thread to the outcome the operator chose, as the "
                             "board's move does; deferred parks it and done confirms it.",
        "Use it to file a thread where the board would, without opening the board.")
    place_parser.add_argument("--to", required=True, choices=[state.value for state in PLACEABLE],
                              help="The outcome to move the thread to")
    place_parser.add_argument("--until", default="manual",
                              help="With --to deferred: what wakes it, one of "
                                   "manual, reply, ci, push or pr:<number>")
    place_parser.add_argument("--note", default="",
                              help="With --to deferred: why it waits")

    _human_only(thread_sub, "unpark", "wake a deferred thread now.",
                "Use it to wake the thread before what it was parked until happens.")

    approve_parser = _human_only(thread_sub, "approve",
                                 "accept the agent's proposal: push its fix, post its reply "
                                 "or file its ticket.",
                                 "For a split, --part accepts one part at a time.")
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
    approve_parser.add_argument("--part", default=None, choices=SPLIT_PARTS,
                                help="The part of a split to accept; every part not yet "
                                     "accepted where none is given")

    edit_part_parser = _human_only(thread_sub, "edit-part",
                                   "save new words for a split's ticket or reply without "
                                   "accepting it.",
                                   "Use it to fix the wording now and accept the part later.")
    edit_part_parser.add_argument("--part", required=True, choices=("ticket", "reply"),
                                  help="The part of the split to edit")
    edit_part_parser.add_argument("--reply", default="", help="The reply, for --part reply")
    edit_part_parser.add_argument("--ticket-project", default=None,
                                  help="The ticket's project, for --part ticket")
    edit_part_parser.add_argument("--ticket-title", default="", help="The ticket's title")
    edit_part_parser.add_argument("--ticket-body", default="", help="The ticket's description")

    rework_parser = _human_only(thread_sub, "rework",
                                "send the agent's proposal back with a note on what to change.",
                                "The agent runs again on the thread with the note, the lines "
                                "pointed at and the files included.")
    rework_parser.add_argument("--note", default="", help="What to change")
    rework_parser.add_argument("--part", default=None, choices=SPLIT_PARTS,
                               help="The part of a split to send back; the whole proposal "
                                    "where none is given, until a part has run")
    _brief_fields(rework_parser)

    session_parser = _human_only(thread_sub, "session",
                                 "open an interactive agent session on the thread.",
                                 "For a thread that needs a conversation rather than a run: "
                                 "the session starts with --steer and is briefed on the lines "
                                 "and files given.")
    session_parser.add_argument("--steer", default="", help="What to start the session with")
    _brief_fields(session_parser)

    _human_only(thread_sub, "fix", "ask the agent to write a fix for the thread.",
                "Queues a fix run on the thread.")
    _human_only(thread_sub, "retry", "run the agent again on a thread whose attempts failed.",
                "Use it once whatever made the attempts fail is out of the way.")
    _human_only(thread_sub, "stop", "stop the agent's run on the thread.",
                "Use it when the run is going the wrong way or is no longer wanted.")

    resolve_parser = _human_only(thread_sub, "resolve",
                                 "close the thread as done, with a reply if one is given.",
                                 "Use it when the comment is dealt with and nothing of the "
                                 "agent's needs to land.")
    resolve_parser.add_argument("--reply", default="", help="The reply to post")
    resolve_parser.add_argument("--delete-comment", action="store_true",
                                help="Delete the comment instead of answering it")
    resolve_parser.add_argument("--resolve", action="store_true",
                                help="Mark the thread resolved on GitHub")
    resolve_parser.add_argument("--no-thumbs-up", action="store_true",
                                help="Leave the comment without a thumbs-up")

    reject_parser = _human_only(thread_sub, "reject",
                                "turn the agent's proposal down and close the thread.",
                                "Nothing the agent proposed lands; the reply, if one is "
                                "given, is posted on the comment.")
    reject_parser.add_argument("--reply", default="", help="The reply to post")
    reject_parser.add_argument("--delete-comment", action="store_true",
                               help="Delete the comment instead of answering it")

    answer_parser = _human_only(thread_sub, "answer",
                                "post the human's own reply on the thread now.",
                                "Posts the words as given, with no proposal from the agent.")
    answer_parser.add_argument("--body", required=True, help="The reply, in full")

    edit_parser = _human_only(thread_sub, "edit", "rewrite a draft or move it to another line.",
                              "The draft stays off GitHub.")
    _anchor_fields(edit_parser)
    edit_parser.add_argument("--body-file", required=True, help="File holding the comment")

    _human_only(thread_sub, "enrol", "put a draft in the review that goes out next.",
                "thread send-review posts every enrolled draft together.")
    _human_only(thread_sub, "withdraw", "take a draft back out of the review.",
                "The draft stays on the board for later.")
    _human_only(thread_sub, "discard", "throw a draft away.",
                "Nothing of it reaches GitHub.")
    _human_only(thread_sub, "post-now", "post a draft on GitHub on its own, now.",
                "Use it for a finding that should not wait for the review.")

    review_parser = _human_only(thread_sub, "send-review",
                                "send the review with every enrolled draft in it. Prints "
                                "its id.",
                                "Takes no --thread-id: the review covers the whole PR.",
                                thread=False)
    review_parser.add_argument("--verdict", required=True,
                               choices=[verdict.value for verdict in Verdict],
                               help="What the review says of the PR")
    review_parser.add_argument("--body", default=None, help="The review's summary")


def _comment_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--thread-id", required=True,
                        help="The key to save the thread under")
    parser.add_argument("--comment-id", type=int, required=True,
                        help="The GitHub id of the comment the thread is about")
    parser.add_argument("--author", required=True, help="The comment author's GitHub login")
    parser.add_argument("--path", default=None,
                        help="Anchored file path (omit for a non-anchored comment)")
    parser.add_argument("--line", type=int, default=None,
                        help="The line of --path the comment hangs on")
    parser.add_argument("--comment-type", default="review",
                        help="What kind of comment it is, such as review, issue or "
                             "review-summary")
    parser.add_argument("--body-file", required=True,
                        help="File holding the comment body")


def add_thread_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    thread_parser = sub.add_parser(
        "thread", description=f"{THREAD_LINE} {_THREAD_MORE}",
        epilog="Example: github-orchestrator thread list --repo acme/widgets --pr 88",
    )
    thread_sub = thread_parser.add_subparsers(dest="thread_command", metavar="<verb>")

    open_parser = _verb(
        thread_sub, "open",
        "Create worktree + branch off PR head, record status=pending, print the worktree path.",
        "The watcher opens a thread for each new comment itself; this opens one by hand, "
        "for a comment it has not picked up.")
    _common(open_parser)
    _comment_fields(open_parser)

    plan_parser = _verb(
        thread_sub, "plan",
        "Write down the steps the fix will take, before making it.",
        "Run it once the brief is understood and before the first edit; the board shows the "
        "steps, and thread step marks each one finished.")
    _common(plan_parser)
    _thread_id(plan_parser)
    plan_parser.add_argument("--step", action="append", required=True,
                             help="One step, in the order you will do them")
    plan_parser.add_argument("--file", action="append", default=None,
                             help="The file that step touches; one per --step "
                                  "or none at all")

    step_parser = _verb(
        thread_sub, "step", "Mark a step of the plan finished, as you finish it.",
        "Name each step by its number in the plan thread plan wrote down.")
    _common(step_parser)
    _thread_id(step_parser)
    step_parser.add_argument("--done", action="append", type=int, required=True,
                             help="The number of a step, counting from 1")

    skip_parser = _verb(
        thread_sub, "skip",
        "The comment needs neither code nor an answer from the agent: working -> skipped.",
        "The thread ends skipped, with the classification and the reason on the board.")
    _common(skip_parser)
    _thread_id(skip_parser)
    skip_parser.add_argument("--classification", required=True, choices=SKIPPED_AS,
                             help="What kind of comment it is")
    skip_parser.add_argument("--reason", required=True,
                             help="One line: why the comment needs nothing")

    reply_parser = _verb(
        thread_sub, "reply",
        "The comment needs an answer and no code: propose the reply for the author "
        "to accept.",
        "Nothing is posted until the author accepts the reply on the board.")
    _common(reply_parser)
    _thread_id(reply_parser)
    reply_parser.add_argument("--classification", required=True, choices=REPLIED_AS,
                              help="What kind of comment it is")
    reply_parser.add_argument("--body", required=True,
                              help="The reply to post on the comment, in full")

    ticket_parser = _verb(
        thread_sub, "ticket",
        "The comment asks for work outside this pull request and the tracker has no "
        "ticket for it: propose a ticket, and the reply that says so, for the author "
        "to accept.",
        "Nothing is filed or posted until the author accepts; once the ticket is filed, "
        "thread filed reports its key and link.")
    _common(ticket_parser)
    _thread_id(ticket_parser)
    ticket_parser.add_argument("--project", required=True,
                               help="The Jira project key, or owner/name for GitHub issues")
    ticket_parser.add_argument("--title", required=True, help="The ticket's title")
    ticket_parser.add_argument("--body", required=True, help="The ticket's description")
    ticket_parser.add_argument("--reply", required=True,
                               help="The reply to post on the comment once the ticket is filed")

    split_parser = _verb(
        thread_sub, "split",
        "The comment's code is already in this pull request but belongs in another: "
        "propose the commit that takes it out, the branch that carries it to a new PR, "
        "and the reply that says where it went, for the author to accept.",
        "Pass exactly one of --same-ticket; --ticket-key with --ticket-url for an existing "
        "ticket; or --project, --title and --body for a new one. Nothing leaves the worktree "
        "until the author accepts; once the new PR is open, thread opened reports its link.")
    _common(split_parser)
    _thread_id(split_parser)
    split_parser.add_argument("--sha", required=True,
                              help="The commit that takes the code out of this PR")
    split_parser.add_argument("--branch", required=True,
                              help="The branch, in this worktree, that carries the code to "
                                   "the new PR")
    split_parser.add_argument("--base", required=True,
                              help="The branch the new PR merges into: main when the code "
                                   "stands alone, this PR's branch when it depends on it")
    split_parser.add_argument("--base-reason", required=True,
                              help="One line: why the new PR goes onto that base")
    split_parser.add_argument("--same-ticket", action="store_true",
                              help="The new PR goes under this PR's ticket")
    split_parser.add_argument("--project", default=None,
                              help="The new ticket's project: the Jira project key, or "
                                   "owner/name for GitHub issues")
    split_parser.add_argument("--title", default=None, help="The new ticket's title")
    split_parser.add_argument("--body", default=None, help="The new ticket's description")
    split_parser.add_argument("--ticket-key", default=None,
                              help="The key of an existing ticket the new PR goes under; "
                                   "nothing is filed")
    split_parser.add_argument("--ticket-url", default=None,
                              help="The link to that existing ticket")
    split_parser.add_argument("--reply", required=True,
                              help="The reply to post on the comment once the new PR is open")

    filed_parser = _verb(
        thread_sub, "filed",
        "The ticket the author accepted is filed: the board posts the reply with its "
        "link.",
        "Run it after filing the ticket an accepted thread ticket proposed.")
    _common(filed_parser)
    _thread_id(filed_parser)
    filed_parser.add_argument("--key", required=True,
                              help="The key the tracker gave the ticket, such as PROJ-12 or #12")
    filed_parser.add_argument("--url", required=True, help="The ticket's link")

    opened_parser = _verb(
        thread_sub, "opened",
        "The new PR the author accepted is open: the board posts the reply with its link.",
        "Run it after opening the new PR an accepted thread split proposed.")
    _common(opened_parser)
    _thread_id(opened_parser)
    opened_parser.add_argument("--url", required=True, help="The new PR's link")

    reconciled_parser = _verb(
        thread_sub, "reconciled",
        "The PR worktree holds origin's branch plus what still belongs on the PR: "
        "the board carries the accept on.",
        "Run it at the end of a reconcile run, when an accepted fix could not land because "
        "origin's branch was rewritten from somewhere else. Do not push: the board pushes "
        "when it lands.")
    _common(reconciled_parser)
    _thread_id(reconciled_parser)
    reconciled_parser.add_argument("--note", required=True,
                                   help="Who rewrote origin and why, and each local commit "
                                        "kept, carried over or dropped")
    reconciled_parser.add_argument("--landed-sha",
                                   help="The sha the accepted fix ended up as, when it was "
                                        "already on the PR branch and you carried it over")

    ready_parser = _verb(
        thread_sub, "ready", "The subagent committed in its worktree: status=ready.",
        "The board shows the commit for the author to accept, rework or reject. Prints the "
        "thread's saved record, as thread show does.")
    _common(ready_parser)
    _thread_id(ready_parser)
    ready_parser.add_argument("--sha", required=True,
                              help="The commit the subagent made")
    ready_parser.add_argument("--tests", required=True, choices=TEST_OUTCOMES,
                              help="Whether the tests passed, failed or could not be run")
    ready_parser.add_argument("--tests-note", default=None,
                              help="One line about the test run, such as what failed or why "
                                   "it could not run")
    ready_parser.add_argument("--note", default=None,
                              help="One line: what the subagent changed")
    ready_parser.add_argument("--summary", default=None,
                              help="One line: what the fix does")
    ready_parser.add_argument("--confidence", default=None,
                              help="How sure the agent is of the fix")
    ready_parser.add_argument("--confidence-note", default=None,
                              help="One sentence behind that level")

    ask_parser = _verb(
        thread_sub, "ask", "The brief cannot be met as stated, or the way forward goes beyond "
                           "what was asked: stop and put a question to the author.",
        "The board shows the question and its options to the author.")
    _common(ask_parser)
    _thread_id(ask_parser)
    ask_parser.add_argument("--question", required=True,
                            help="One line: what the author must decide")
    ask_parser.add_argument("--context", required=True,
                            help="Markdown: what you tried and what broke")
    ask_parser.add_argument("--option", action="append", default=None,
                            help="One concrete way forward; repeat for each, or leave "
                                 "out when you have not narrowed it down")

    base_parser = _verb(
        thread_sub, "base", "Move the commit the thread's fix is built on, after rebasing "
                            "the fix onto a newer tip of the PR branch.",
        "Run it when thread ready or thread split refuses a commit because the thread's base "
        "is not one of its ancestors, then report again.")
    _common(base_parser)
    _thread_id(base_parser)
    base_parser.add_argument("--sha", required=True,
                             help="The PR branch's tip the fix now sits on")

    fail_parser = _verb(
        thread_sub, "fail", "The attempt failed: status=failed, worktree kept for rework.",
        "Use it when the fix cannot be made; the board shows the reason.")
    _common(fail_parser)
    _thread_id(fail_parser)
    fail_parser.add_argument("--reason", required=True,
                             help="One line: why the attempt failed")

    check_parser = _verb(
        thread_sub, "check", "Set by hand whether the commit the PR author named addresses "
                             "your comment, over the commit check's verdict.",
        "Use it when the commit check got it wrong.")
    _common(check_parser)
    _thread_id(check_parser)
    check_parser.add_argument("--verdict", required=True,
                              choices=[verdict.value for verdict in CommitVerdict],
                              help="Whether the commit addresses the comment")
    check_parser.add_argument("--reason", default="set by hand",
                              help="One line: why the commit does or does not address it")

    _add_human_only_parsers(thread_sub)

    draft_parser = _verb(
        thread_sub, "draft",
        "A review finding on one line of the diff: a draft on the "
        "board, nothing on GitHub. Prints its key.",
        "The author enrols, edits, posts or discards it from the board.")
    _common(draft_parser)
    _anchor_fields(draft_parser)
    draft_parser.add_argument("--body-file", required=True,
                              help="File holding the comment")

    list_parser = _verb(
        thread_sub, "list",
        "Print a PR's threads, one a line: key, state, where it hangs, what it is about.",
        "Use it to find a thread's key, or to see what every thread on the PR is doing.")
    _common(list_parser)

    show_parser = _verb(
        thread_sub, "show", "Print one thread's saved record as JSON: state, sha, tests, notes.",
        "Use it to read back what was reported on a thread.")
    _common(show_parser)
    _thread_id(show_parser)

    return thread_parser
