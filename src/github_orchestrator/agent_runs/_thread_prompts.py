from github_orchestrator.agent_runs._report_commands import ReportCommands
from github_orchestrator.agent_runs._rules import test_parallelism_note
from github_orchestrator.agent_runs.interface import (
    FixComment,
    PointedAt,
    ThreadFix,
)

FULL_SHA = "<full 40-character sha, as `git rev-parse HEAD` prints it>"
REBASED_SHA = ("<full 40-character sha of the rebased tip, as "
               "`git rev-parse HEAD` prints it>")

PLANNED_STEPS = (("<the first thing you will do>", "<the file it touches>"),
                 ("<the next thing>", "<the file it touches>"))

FINISHED_STEP = "<the number of the step you have just finished>"

ONE_COMMIT = "Steps are how you think; one commit is how the fix lands."

PAIRING_ADVICE = (
    "Pass one `--file` per `--step`, in the same order, or leave `--file` off "
    "altogether. Where only some of the steps have a file you can name yet, "
    "pass `--file \"\"` for the ones that do not. Declaring a plan again "
    "replaces the whole of the one before it."
)

CONFIDENCE_ADVICE = (
    "`--summary` is one line saying what the fix does. `--confidence` is how "
    "sure you are that the fix is what the reviewer wanted and that it breaks "
    "no caller, and `--confidence-note` is the one sentence behind that level: "
    "what you checked, or what you could not. Say `low` where you guessed at "
    "the ask, and say so. Pass all three every time you report: the brackets "
    "mean only that the CLI will not stop you."
)


def _plan(commands: ReportCommands, fix: ThreadFix) -> str:
    return commands.plan(fix.pr, fix.key, PLANNED_STEPS)


def _step(commands: ReportCommands, fix: ThreadFix) -> str:
    return commands.step(fix.pr, fix.key, done=FINISHED_STEP)


def _ready(commands: ReportCommands, fix: ThreadFix, sha: str, note: str) -> str:
    return commands.ready(
        fix.pr, fix.key, sha=sha, tests_note='"..."', note=f'"{note}"',
        summary='"<one line: what the fix does>"',
        confidence="|".join(fix.confidence_levels),
        confidence_note='"<one sentence: why that level, in your own words>"')


def _fail(commands: ReportCommands, fix: ThreadFix) -> str:
    return commands.fail(fix.pr, fix.key, reason='"<why>"')


def _who(comment: FixComment) -> str:
    if comment.by_pr_author:
        return f"{comment.author}, the PR author"
    return comment.author or "ghost"


def _render_thread(fix: ThreadFix) -> str:
    if not fix.comments:
        return fix.body
    return "\n\n".join(
        f"--- {_who(comment)} "
        f"({comment.created_at or 'unknown time'})\n{comment.body}"
        for comment in fix.comments
    )


WITHDRAWN_WITHOUT_A_COMMIT = (
    "A fix was proposed and was waiting on the author's approval; it is the "
    "tip of this worktree. Skipping or replying now withdraws it: the author "
    "will no longer see the proposed fix and can no longer approve it. Do "
    "either only if the newest reply means that fix should not land."
)

REPLY_ADVICE = (
    "`--body` is the whole reply, written as the PR author and posted as it "
    "stands once the author accepts it; the author can edit it first. For "
    "already-done, say where the branch already does it. For a question, "
    "answer it. For unclear, ask the reviewer the one clarifying question "
    "that would settle what to change."
)

OUT_OF_SCOPE_UNTRACKED = " For out-of-scope, say the work belongs outside this pull request."

OUT_OF_SCOPE_TRACKED = (" For out-of-scope, name the ticket that already covers the work "
                        "and link it.")

TICKET_ADVICE = (
    "`--title` and `--body` are the ticket as it will be filed: a title that "
    "names the work, and a body that says what was asked, why it belongs "
    "outside this pull request, and which comment raised it. `--reply` is "
    "posted on the comment once the author accepts; the ticket is filed first "
    "and its link is added below the reply, so leave the link out. The author "
    "can edit all four first. Never file the ticket yourself: nothing is "
    "created until the author accepts."
)

JIRA_PROJECT_CHOICE = "the key of the project the work plainly belongs to"


def _reply(commands: ReportCommands, fix: ThreadFix) -> str:
    return commands.reply(fix.pr, fix.key, body='"<the reply, in full>"')


def _reply_advice(fix: ThreadFix) -> str:
    return REPLY_ADVICE + (OUT_OF_SCOPE_UNTRACKED if fix.tracker is None
                           else OUT_OF_SCOPE_TRACKED)


def _ticket(commands: ReportCommands, fix: ThreadFix) -> str:
    project = (str(fix.pr.repo) if fix.tracker == "github"
               else f'"<{fix.tracker_project}, or {JIRA_PROJECT_CHOICE}>"')
    return commands.ticket(fix.pr, fix.key, project=project,
                           title='"<the ticket\'s title>"', body='"<the ticket\'s description>"',
                           reply='"<the reply to post on the comment>"')


def _search(fix: ThreadFix) -> str:
    if fix.tracker == "github":
        return (f'`gh issue list --repo {fix.pr.repo} --state all --search '
                '"<words that name the work>"`')
    return ("a JQL search through the Atlassian MCP in the project you would file "
            f'it in, such as `project = {fix.tracker_project} AND text ~ '
            '"<words that name the work>"`')


def _tracker_facts(fix: ThreadFix) -> list[str]:
    if fix.tracker is None:
        return []
    lines = ["## The tracker"]
    if fix.tracker == "github":
        lines.append(f"- Tickets are GitHub issues on {fix.pr.repo}")
    else:
        lines += ["- Tickets are Jira issues, reached through the Atlassian MCP",
                  f"- Default project: {fix.tracker_project}"]
    lines.append(f"- Repository: {fix.pr.repo}")
    if fix.branch_ticket:
        lines.append(f"- This branch's ticket, the work this pull request is for: {fix.branch_ticket}")
    return [*lines, ""]


def _out_of_scope(commands: ReportCommands, fix: ThreadFix) -> list[str]:
    if fix.tracker is None:
        return []
    return [
        "If the comment is **out-of-scope**, change no code. Search the tracker "
        f"for a ticket that already covers the work: {_search(fix)}. If one you "
        "judge to be the same work exists, reply as above, classified "
        "out-of-scope, naming and linking it. If none does, propose a ticket and "
        "the reply that goes with it, then stop:",
        "",
        f"    {_ticket(commands, fix)}",
        "",
        TICKET_ADVICE,
        "",
    ]


def _filing_facts(fix: ThreadFix) -> tuple[str, str, str, str]:
    repo = fix.pr.repo
    if fix.tracker == "github":
        return (f"GitHub issues on {repo}",
                "Create a GitHub issue with the title and body exactly as given: write the "
                "body to a file outside this worktree and run "
                f'`gh issue create --repo {repo} --title "<the title>" --body-file '
                "<that file>`. gh prints the issue's link; the number at its end is the "
                "issue's number.",
                f'`gh issue list --repo {repo} --state all --search "<the title>"`',
                '"#<the issue\'s number>"')
    project = fix.ticket_project
    return (f"Jira, project {project}",
            f"Create a Jira issue through the Atlassian MCP in project {project}, with the "
            "title as its summary and the body as its description, exactly as given, and "
            "the project's standard issue type: Task, where the project has one. Jira "
            f"answers with the issue's key, such as {project}-123; its link is the site's "
            "`/browse/<key>` address.",
            f'a JQL search through the Atlassian MCP: `project = {project} AND summary ~ '
            '"<the title>"`',
            f"<the issue's key, such as {project}-123>")


def filing_prompt(commands: ReportCommands, fix: ThreadFix) -> str:
    tracker, how, search, key = _filing_facts(fix)
    filed_cmd = commands.filed(fix.pr, fix.key, ticket=key, url='"<the ticket\'s link>"')
    return f"""You are filing one ticket for the author of {fix.pr}, who accepted it on \
the review board. File it, report what the tracker gave back by running exactly one of \
the report commands below, and stop — do not ask questions; nobody is watching this run.

Change no files, make no commits and push nothing. Post nothing on {fix.pr}: once you \
have reported the ticket, the board posts the reply that links it.

## The ticket
- Tracker: {tracker}
- Title: {fix.ticket_title}
- Body:
```
{fix.ticket_body}
```

## File it

{how}

File it once. If the tracker refuses it, you may try once more after reading why. If you \
cannot tell whether a try created it, look for it first with {search}, so the ticket is \
never filed twice.

Then report the key and the link the tracker gave it:

    {filed_cmd}

If it cannot be filed, report why and stop:

    {_fail(commands, fix)}
"""


def _before_reply(fix: ThreadFix) -> str:
    if not fix.before_reply:
        return ""
    consequence = f" {WITHDRAWN_WITHOUT_A_COMMIT}" if fix.withdraws_proposal else ""
    return ("\nBefore the newest reply, the thread had ended up: "
            f"{fix.before_reply}. Read the reply in that light."
            f"{consequence}\n")


def _anchor(fix: ThreadFix) -> tuple[str, str]:
    line = fix.line
    return (fix.path or "general",
            str(line) if line is not None else "(none)")


def thread_prompt(commands: ReportCommands, fix: ThreadFix, workers: int) -> str:
    pr = fix.pr
    worktree = fix.worktree
    skip_cmd = commands.skip(pr, fix.key, reason='"<why>"')
    reply_cmd = _reply(commands, fix)
    replied_as = ("**already-done**, **question**,\n**unclear** or **out-of-scope**"
                  if fix.tracker is None else
                  "**already-done**, **question**\nor **unclear**")
    tracker = "".join(f"{line}\n" for line in _tracker_facts(fix))
    out_of_scope = "".join(f"{line}\n" for line in _out_of_scope(commands, fix))
    plan_cmd = _plan(commands, fix)
    step_cmd = _step(commands, fix)
    ready_cmd = _ready(commands, fix, FULL_SHA, "<one line: what changed>")
    fail_cmd = _fail(commands, fix)

    path, line_text = _anchor(fix)
    parallelism_note = test_parallelism_note(workers)

    return f"""You are addressing one PR review thread on {pr} as part of an \
autonomous feedback pass. Do the work and report the outcome yourself by running \
exactly one of the report commands below — do not ask questions; nobody is \
watching this run.

Work ONLY in `{worktree}` — an isolated git worktree created for this one \
thread. Every file you read or change, every command you run, and the one \
commit you may make happen there, never anywhere else.

## The thread
- Opened by: {fix.author}
- Path: {path}  (`general` means non-anchored: locate the relevant code from \
the body, e.g. by grepping and reading `git diff main...HEAD`)
- Line: {line_text}
- Every comment, oldest first:
```
{_render_thread(fix)}
```
{_before_reply(fix)}
The last comment is the most recent thing the reviewer said. Earlier comments \
are the context it was said in — read the whole thread before deciding what is \
being asked.

{tracker}## Step 1 — classify the comment before doing any work

- **safe** — address it. Examples: typos, missing types, a rename, extracting a
  small helper, adding a test for a stated case, simplifying an expression,
  fixing an obvious bug the reviewer points at.
- **acknowledgement** — thanks, praise, a 👍, "LGTM" or any other pure ack: the
  reviewer asks for nothing and nothing is left to do.
- **question** — the reviewer asks the author something, says "consider for
  future" or raises a general concern, and no code change is asked for.
- **unclear** — the comment has multiple plausible
  interpretations, or depends on information you don't have. Answer it with a
  clarifying question to the reviewer.
- **risky** — requires an architectural change, touches an unrelated module,
  asks to remove a feature, add a new dependency, or change behavior without a
  clear spec.
- **out-of-scope** — the change belongs outside this pull request.
- **already-done** — the branch already does what the comment asks.
- **needs-human** — it needs a decision only the author can make.

Classification rules:
- `path: general` comments are usually a question, an acknowledgement or
  architectural — be especially conservative with them. Only classify a general
  comment as safe if it is clearly a small, locatable change.
- Classify against the whole thread above, not its last comment alone: the
  actionable ask often lives in an earlier comment and the last one only
  qualifies it.
- "I'll do X" from the PR author is NOT a reason to hold back: "I" is ambiguous
  between the human and you acting as the human's hands. If the work is simple,
  locatable and in scope, do it.
- Be conservative on risk, not on action: when in doubt about WHAT to change,
  ask a clarifying question rather than guess; do not hold back a clear, simple
  change just because the author said "I'll".

If the comment needs an answer and no code — {replied_as} — change no code, write the reply and report
it, then stop:

    {reply_cmd}

{_reply_advice(fix)}

{out_of_scope}If the comment is **risky**, **needs-human** or an **acknowledgement**, change
no code and report, then stop:

    {skip_cmd}

## Step 2 — if safe, write down the steps before you touch any code

{ONE_COMMIT} Say what you mean to do, one `--step` at a time, in the order you \
mean to do them:

    {plan_cmd}

{PAIRING_ADVICE}

Mark each step the moment you finish it, so the board can watch the work go by:

    {step_cmd}

## Step 3 — make the change

1. Locate the relevant code in the worktree. If the path is a real file, read
   it and grep for the symbol or phrase the reviewer mentions.
2. Make the MINIMAL change that addresses the comment. Do not refactor
   surrounding code or improve things the reviewer did not mention.
3. Run the project's linter/formatter and the tests for the changed files
   (check `Makefile`/`justfile`/`package.json`/`.github/workflows/` for the
   commands).
{parallelism_note}
4. Commit in this worktree with a message describing the change (not the
   review comment), matching the repo's convention from recent `git log`. No
   co-authors.
5. Report:

    {ready_cmd}

{CONFIDENCE_ADVICE}

## Real failure vs infrastructure failure — opposite handling

- Tests RAN and FAILED (your change is wrong) and you cannot trivially fix it:
  revert your changes and report, committing nothing:

      {fail_cmd}

- Tests COULD NOT RUN — Docker not up, DB unreachable, or a port, database or
  lock held by another thread's run happening concurrently; nothing to do
  with your change — do NOT revert. Commit and report with
  `--tests unverified --tests-note "<infra reason>"`. Never destroy correct
  work because you could not verify it.

## Hard rules

- Never push — not this branch, not any branch.
- Never commit to the PR branch. The only commit is the one in this worktree.
- Exactly one commit when safe; zero commits when you reply, skip or fail.
"""


def fix_rebase_prompt(commands: ReportCommands, fix: ThreadFix, onto: str | None,
                  workers: int) -> str:
    pr = fix.pr
    worktree = fix.worktree
    ready_cmd = _ready(commands, fix, REBASED_SHA,
                       "<one line: how the conflict was resolved>")
    reply_cmd = _reply(commands, fix)
    fail_cmd = _fail(commands, fix)

    path, line_text = _anchor(fix)
    parallelism_note = test_parallelism_note(workers)

    return f"""You are rebasing an already-reviewed fix for one PR review comment on \
{pr} so it can land on the PR branch. Do the work and report the outcome \
yourself by running exactly one of the report commands below — do not ask \
questions; nobody is watching this run.

Work ONLY in `{worktree}` — the isolated git worktree holding the fix. The fix is \
the commit(s) already on this branch. Since it was written the PR branch has moved \
to {onto}, and cherry-picking the fix onto it conflicted:

```
{fix.conflict or ""}
```

## The thread the fix addresses
- Opened by: {fix.author}
- Path: {path}
- Line: {line_text}
- Every comment, oldest first:
```
{_render_thread(fix)}
```

## Steps

1. Run `git rebase {onto}`. Resolve each conflict so the fix still does what the
   comment asks against the PR's current code. Keep the fix's own commit(s) and
   touch nothing else: do not change the PR's commits, do not fold in unrelated
   changes.
2. Run the project's linter/formatter and the tests for the changed files
   (check `Makefile`/`justfile`/`package.json`/`.github/workflows/` for the
   commands).
{parallelism_note}
3. Report:

    {ready_cmd}

{CONFIDENCE_ADVICE}

If the PR already does what the comment asked, run `git rebase --abort` and
propose a reply instead, classified already-done:

    {reply_cmd}

{_reply_advice(fix)}

If the fix no longer applies because the code it changed is gone, run
`git rebase --abort` and report:

    {fail_cmd}

Tests that COULD NOT RUN — Docker not up, DB unreachable, or a port, database or
lock held by another thread's run — are not a failure of the fix: report with
`--tests unverified --tests-note "<infra reason>"`.

## Hard rules

- Never push — not this branch, not any branch.
- Never commit to the PR branch.
- When you report ready, this branch must be {onto} plus the fix's commits and
  nothing else.
"""


def _pointed_lines(pointed: tuple[PointedAt, ...]) -> list[str]:
    if not pointed:
        return []
    return [
        "The lines the author pointed at, which is where to look first:",
        "",
        *(f"  {one.file}:{one.line}  {one.text.strip()}"
          if one.line is not None else f"  {one.file}  {one.text.strip()}"
          for one in pointed),
        "",
    ]


def _included_replies(wanted: tuple[FixComment, ...]) -> list[str]:
    if not wanted:
        return []
    return [
        "Replies on the thread the author asked you to read as part of the ask:",
        "",
        *(f"{comment.author_name or comment.author}: {comment.body}"
          for comment in wanted),
        "",
    ]


def rework_prompt(commands: ReportCommands, fix: ThreadFix, steer: str | None,
                  workers: int) -> str:
    pr = fix.pr
    anchor = ""
    if fix.path:
        anchor = f" on {fix.path}"
        if fix.line is not None:
            anchor += f":{fix.line}"
    lines = [
        f"Rework the fix for a review comment on {pr} in this worktree.",
        "",
        f"The comment, by {fix.author or 'unknown'}{anchor}:",
        "",
        fix.body,
        "",
    ]
    if fix.skipped_because:
        lines += [
            f"It was classified {fix.classification or 'not safe'} and "
            f"skipped: {fix.skipped_because}",
            "",
        ]
    if fix.ticket_title is not None:
        lines += [
            "The last attempt proposed this ticket instead of a change:",
            "",
            f"Project: {fix.ticket_project}",
            f"Title: {fix.ticket_title}",
            "",
            fix.ticket_body or "",
            "",
            "with this reply on the comment:",
            "",
            fix.reply or "",
            "",
        ]
    elif fix.reply:
        lines += [
            "The last attempt proposed this reply instead of a change:",
            "",
            fix.reply,
            "",
        ]
    lines += _tracker_facts(fix)
    steer = steer or fix.note
    if steer:
        lines += [
            "Why the last attempt was sent back, in the words of the author of "
            f"{pr}. This is what the rework is for — do this:",
            "",
            steer,
            "",
        ]
    lines += _pointed_lines(fix.pointed)
    lines += _included_replies(fix.replies)
    lines += [
        "Any prior attempt is already committed in this worktree — start from "
        "what is here rather than redoing it.",
        "",
        f"{ONE_COMMIT} Write down the steps this attempt will take before you "
        f"touch any code:",
        _plan(commands, fix),
        f"{PAIRING_ADVICE} Mark each step the moment you finish it:",
        _step(commands, fix),
        "",
        test_parallelism_note(workers).strip(),
        "",
        "When you have committed a new attempt, run:",
        _ready(commands, fix, FULL_SHA, "<one line: what changed>"),
        "That command is re-runnable: if you amend the commit afterwards, run "
        "it again with the new sha and the board follows.",
        "",
        CONFIDENCE_ADVICE,
        "",
        "If the comment needs an answer and no code, change no code and report "
        "the reply instead:",
        _reply(commands, fix),
        _reply_advice(fix),
    ]
    if fix.tracker is not None:
        lines += ["", *_out_of_scope(commands, fix)]
    return "\n".join(lines)
