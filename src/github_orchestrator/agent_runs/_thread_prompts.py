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


def _ask(commands: ReportCommands, fix: ThreadFix) -> str:
    return commands.ask(fix.pr, fix.key, question='"<one line: what the author must decide>"',
                        context='"<markdown: what you tried and what broke>"',
                        option='"<one concrete way forward>"')


ASK_WHEN = (
    "Stop and ask the author instead of reporting when the brief cannot be met as "
    "stated, or when the way forward goes beyond what the comment and the brief asked "
    "for: a production change for a comment on a test, a change to another module, a "
    "change to a public signature."
)

ASK_HOW = (
    "`--question` is the one thing the author must "
    "decide. `--context` says why you stopped: what you tried and what broke. Give "
    "`--option` once for each way forward, and only when you have narrowed it to "
    "concrete ones. Leave your work in the worktree as it is, committed or not, and "
    "stop once you have asked: the author answers in a session on this same "
    "conversation."
)

DECIDED_IN_THE_NOTE = "Anything else, decide yourself and say what you decided in `--confidence-note`."

def _asking(commands: ReportCommands, fix: ThreadFix,
            decided: str = DECIDED_IN_THE_NOTE) -> list[str]:
    return ["## If you cannot do what was asked", "", f"{ASK_WHEN} {decided} {ASK_HOW}", "",
            f"    {_ask(commands, fix)}", ""]


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

OUT_OF_SCOPE_UNTRACKED = (" For out-of-scope work not in this PR's diff yet, say the work "
                          "belongs outside this pull request.")

OUT_OF_SCOPE_TRACKED = (" For out-of-scope, name the ticket that already covers the work "
                        "and link it.")

SPLIT_WHEN = (
    "- Out-of-scope code already in this PR's diff (\"not part of this ticket\", \"not in "
    "the acceptance criteria\", \"move this to another PR\", \"put it under another "
    "ticket\") is taken out of this pull request, never only answered in words. Judge "
    "what it deserves: working code someone will want gets a pull request of its own, "
    "split out as \"Step 3 for a split\" says; a few lines nobody needs elsewhere are "
    "**safe**, and one commit removes them."
)

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


def _project(fix: ThreadFix) -> str:
    match fix.tracker:
        case None:
            return '"<project>"'
        case "github":
            return str(fix.pr.repo)
    return f'"<{fix.tracker_project}, or {JIRA_PROJECT_CHOICE}>"'


def _ticket(commands: ReportCommands, fix: ThreadFix) -> str:
    return commands.ticket(fix.pr, fix.key, project=_project(fix),
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
        "If the comment is **out-of-scope** and the work is not in this PR's diff yet, "
        "change no code. Search the tracker "
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


def _new_prs_ticket(fix: ThreadFix) -> str:
    if fix.ticket_key:
        return f"{fix.ticket_key}, {fix.ticket_url}"
    if fix.branch_ticket:
        return f"{fix.branch_ticket}, the ticket of the original PR"
    return ("the ticket of the original PR; take its key and link from that PR's title "
            "and body, and leave the ticket out when it names none")


def opening_prompt(commands: ReportCommands, fix: ThreadFix) -> str:
    branch = fix.split_branch
    opened_cmd = commands.opened(fix.pr, fix.key, url='"<the new PR\'s link>"')
    return f"""You are opening one pull request for the author of {fix.pr}, who accepted it \
on the review board. A review comment on {fix.pr} asked for some of its code to move to a \
pull request of its own, and that code is committed on the branch {branch} in this \
worktree. Push the branch, open the pull request with the `{fix.pr_skill}` skill, report \
its link by running exactly one of the report commands below, and stop. Nobody is \
watching this run: decide for yourself and say what you decided in the PR body.

## The new PR
- Branch: {branch}
- Base: {fix.split_base} ({fix.split_base_reason})
- Original PR: {fix.pr_url}
- Review thread the work came from: {fix.thread_url}
- Ticket: {_new_prs_ticket(fix)}

The branch holds exactly what the author accepted, so it goes up as it stands. {fix.pr} \
and its review thread stay as they are: once you have reported, the board posts the reply \
that names the new PR.

## Why the code moved

The review thread, every comment oldest first. It is the reason the new PR exists, so the \
PR body says in its own words what the reviewer asked for and why:
```
{_render_thread(fix)}
```

## Open it

1. Look for a pull request already open from the branch, so it is never opened twice: \
`gh pr list --head {branch} --state open --json url`. If one is listed, report its link \
and stop.
2. Push the branch: `git push -u origin {branch}`.
3. Invoke the `{fix.pr_skill}` skill to open a pull request from {branch} into \
{fix.split_base}. Give it the branch, the base, the original PR's link, the review \
thread's link, why the work moved as the thread above tells it, and the ticket above.

The pull request is open when GitHub has given it a link. Report that link:

    {opened_cmd}

If it cannot be opened, report why and stop:

    {_fail(commands, fix)}
"""


def _landed_fix(fix: ThreadFix) -> str:
    if fix.landed_sha is None:
        return ("No fix for this thread is on the PR branch yet: once you report, the board "
                "picks it onto the worktree as it stands and pushes it.")
    return (f"The fix the author accepted for this thread is already on the PR branch here as "
            f"{fix.landed_sha}, and is one of the commits origin lacks. Carry it onto origin's "
            f"branch, and report the sha it ends up as with `--landed-sha`; leave "
            f"`--landed-sha` out only if you dropped it, and the board picks it again.")


def reconcile_prompt(commands: ReportCommands, fix: ThreadFix) -> str:
    branch = fix.pr_branch
    reconciled_cmd = commands.reconciled(
        fix.pr, fix.key, note='"<what you found and did>"',
        landed_sha="<the sha the accepted fix ended up as>")
    return f"""You are reconciling the PR worktree of {fix.pr} with origin, for its author, \
who accepted a fix on the review board. The accept cannot land: origin's branch {branch} was \
rewritten from somewhere other than this worktree, and this worktree holds commits origin has \
no equivalent of. Nobody is watching this run. Find out what happened, make this worktree \
origin's branch plus whatever of its own commits still belongs on the PR, report what you \
did, and stop. Once you report, the board carries the accept on and lands it.

## How they diverged
{fix.conflict}

{_landed_fix(fix)}

## Find out why
- The pull request: {fix.pr_url}, and the review thread the accept is for: {fix.thread_url}.
- When origin's branch was force-pushed, by whom, and from which commit to which: \
`gh api graphql -f query='query {{ repository(owner: "{fix.pr.repo.owner}", name: \
"{fix.pr.repo.name}") {{ pullRequest(number: {fix.pr.number}) {{ timelineItems(last: 20, \
itemTypes: [HEAD_REF_FORCE_PUSHED_EVENT]) {{ nodes {{ ... on HeadRefForcePushedEvent {{ \
createdAt actor {{ login }} beforeCommit {{ oid }} afterCommit {{ oid }} }} }} }} }} }} }}'`
- Every thread the board holds for this PR, and what each is doing: `{commands.listing(fix.pr)}`
- Who rewrote it and why: an agent run often did, from a worktree of its own. Claude Code \
keeps each session as a `.jsonl` transcript under `$CLAUDE_CONFIG_DIR/projects/` (or \
`~/.claude/projects/` when that is unset), one folder per working directory. Search them \
for the sha origin's branch now points at, newest first, and read what that session was \
asked and what it did around its push.
- `git log --oneline` and `git range-diff` between origin's branch and this worktree's \
head show which local commits origin rewrote and which it never had.

## Reconcile
Make this worktree's branch origin's {branch} plus each local commit that still belongs on the \
PR, as a fast-forward of origin. You may overwrite or drop local commits, but only once you \
know why each one goes: a commit origin carries in another form is already there, and one \
the rewrite meant to remove stays removed. Do not push: the board pushes when it lands. \
Leave the worktree clean.

Then report what you found and did: who rewrote origin and why, and each local commit you \
kept, carried over or dropped, with the reason:

    {reconciled_cmd}

If you cannot reconcile it safely, put the worktree back as you found it, report why and stop:

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


def _pr_base(fix: ThreadFix) -> str:
    return fix.pr_base or "main"


def _split_ticket_choice(fix: ThreadFix) -> list[str]:
    if fix.tracker is None:
        return ["5. Pass `--same-ticket`: no tracker is set up for this repository, so the new "
                "PR goes under this PR's own ticket, or under none when this PR names none."]
    return [
        "5. Choose the new PR's ticket. First search the tracker for a ticket, other than "
        f"this PR's own, that already covers the moved code: {_search(fix)}.",
        "   - Found one you judge to be the same work: the new PR goes under it. Pass its "
        "key as `--ticket-key` and its link as `--ticket-url`; nothing is filed.",
        "   - Found none, and the work is still part of this PR's ticket and only belongs "
        "in a pull request of its own: pass `--same-ticket`.",
        "   - Found none, and the comment says the work is not part of this PR's ticket: "
        "draft one with `--project`, `--title` and `--body`: a title that names the work, "
        "and a body that says what was asked, why it belongs outside this pull request, and "
        "which comment raised it. It is filed only once the author accepts it, so never "
        "file it yourself.",
    ]


def _split_new(commands: ReportCommands, fix: ThreadFix) -> str:
    return commands.split(fix.pr, fix.key, sha="<the removal's full 40-character sha>",
                          branch="<branch>", base='"<the base>"',
                          base_reason='"<one line: why that base>"',
                          project=_project(fix), title='"<the ticket\'s title>"',
                          body='"<the ticket\'s description>"',
                          ticket_key="<the existing ticket's key>",
                          ticket_url='"<the existing ticket\'s link>"',
                          reply='"<the reply to post on the comment>"')


def _split_out(commands: ReportCommands, fix: ThreadFix, heading: str) -> list[str]:
    base = _pr_base(fix)
    branch = f"`{fix.pr_branch}`" if fix.pr_branch else "this PR's branch"
    return [
        f"## {heading}",
        "",
        "The comment asks for code that is already in this PR's diff "
        f"(`git diff origin/{base}...HEAD` shows it) to leave this pull request. Take it "
        "out here, and carry it to a branch of its own for a new pull request. Nothing is "
        "pushed or opened until the author accepts. If what stays in this PR still needs "
        "the code, it cannot leave: ask instead, as \"If you cannot do what was asked\" says.",
        "",
        "1. Take it out: remove exactly that code in this worktree, run the project's linter "
        "and the tests for the files you touched, and commit once. That commit is the "
        "removal; `git rev-parse HEAD` prints its full sha.",
        "2. Choose the new PR's base, and say why in one line:",
        f"   - `{base}` when the code stands alone and works without anything else this "
        "PR adds;",
        f"   - {branch} when it uses something this PR adds, so the new PR stacks on "
        "this one.",
        "3. Build the branch, named `split/<a few words naming the work>`, from the base "
        "you chose:",
        f"   - onto `{base}`: `git switch -c <branch> origin/{base}`;",
        "   - stacked: `git switch -c <branch> <removal>`.",
        "   Bring the code back with `git diff <removal> <removal>^ | git apply --3way`, "
        "finishing by hand where it does not apply cleanly. Make anything else the "
        "comment asks of the moved code (a rename, say) here, on this branch, not in the "
        "removal. Run the linter and the tests for the files on this branch, and commit "
        "with messages describing the code, matching the repo's convention from recent "
        "`git log`. No co-authors.",
        "4. Come back with `git switch -`: the tip of this worktree is the removal again.",
        *_split_ticket_choice(fix),
        "6. Report:",
        "",
        f"    {_split_new(commands, fix)}",
        "",
        "`--sha` is the removal, `--branch` the new branch, `--base` the base you chose and "
        "`--base-reason` your one line. `--reply` is posted on the comment as the PR author "
        "once the new PR is open; the board adds the new PR's link, and the ticket's, below "
        "it, so leave links out. Pass exactly one ticket choice: `--ticket-key` and "
        "`--ticket-url`, `--same-ticket`, or `--project`, `--title` and `--body`.",
        "",
    ]


UNATTENDED = ("as part of an autonomous feedback pass. Do the work and report the outcome "
              "yourself by running exactly one of the report commands below. Nobody is "
              "watching this run, so a question asked in your last message goes unread: "
              "when you need the author, ask through the report command for it.")

WATCHED = ("in a terminal session the author is watching and may type into. Do the work, "
           "and answer the author here when they write to you. The board takes the outcome "
           "only from a report, so whatever the author says in this session, finish by "
           "running exactly one of the report commands below yourself.")


def thread_prompt(commands: ReportCommands, fix: ThreadFix, workers: int, *,
                  watched: bool = False) -> str:
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
    asking = "".join(f"{line}\n" for line in _asking(commands, fix))
    split_out = "".join(f"{line}\n" for line in _split_out(
        commands, fix, "Step 3 for a split — take the code out and carry it to a branch of "
                       "its own"))

    path, line_text = _anchor(fix)
    parallelism_note = test_parallelism_note(workers)

    return f"""You are addressing one PR review thread on {pr} \
{WATCHED if watched else UNATTENDED}

Work ONLY in `{worktree}` — an isolated git worktree created for this one \
thread. Every file you read or change, every command you run, and every \
commit you make happen there, never anywhere else.

## The thread
- Opened by: {fix.author}
- Path: {path}  (`general` means non-anchored: locate the relevant code from \
the body, e.g. by grepping and reading `git diff origin/{_pr_base(fix)}...HEAD`)
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
{SPLIT_WHEN}

If the comment needs an answer and no code — {replied_as} — change no code, write the reply and report
it, then stop:

    {reply_cmd}

{_reply_advice(fix)}

{out_of_scope}If the comment is **risky**, **needs-human** or an **acknowledgement**, change
no code and report, then stop:

    {skip_cmd}

## Step 2 — if safe or a split, write down the steps before you touch any code

{ONE_COMMIT} Say what you mean to do, one `--step` at a time, in the order you \
mean to do them:

    {plan_cmd}

{PAIRING_ADVICE}

Mark each step the moment you finish it, so the board can watch the work go by:

    {step_cmd}

## Step 3 — if safe, make the change

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

{split_out}{asking}## Real failure vs infrastructure failure — opposite handling

- Tests RAN and FAILED (your change is wrong) and you cannot trivially fix it:
  revert your changes and report, committing nothing (for a split, delete the
  new branch too):

      {fail_cmd}

- Tests COULD NOT RUN — Docker not up, DB unreachable, or a port, database or
  lock held by another thread's run happening concurrently; nothing to do
  with your change — do NOT revert. Commit and report with
  `--tests unverified --tests-note "<infra reason>"`. Never destroy correct
  work because you could not verify it.

## Hard rules

- Never push — not this branch, not any branch.
- Never commit to the PR branch. Commit only in this worktree: on its own
  branch and, for a split, on the new branch.
- Exactly one commit on this worktree's branch when safe or a split: the fix,
  or for a split the removal. A split's new branch holds as many commits as its
  work needs. Zero commits when you reply, skip or fail; as many as you have
  made when you ask.
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


def carry_on_prompt(commands: ReportCommands, fix: ThreadFix) -> str:
    return "\n".join([
        "While you waited for the author to answer your question, a new reply arrived "
        "on the thread:",
        "",
        *(f"{comment.author_name or comment.author}: {comment.body}"
          for comment in fix.replies),
        "",
        "If it settles your question, carry on from where you stopped and report as "
        "before:",
        _ready(commands, fix, FULL_SHA, "<one line: what changed>"),
        "",
        "If it does not, ask again, saying what the reply changed:",
        _ask(commands, fix),
    ])


def answered_prompt(commands: ReportCommands, fix: ThreadFix) -> str:
    return "\n".join([
        "The author answered your question:",
        "",
        fix.note,
        "",
        "Carry on from where you stopped and report as before:",
        _ready(commands, fix, FULL_SHA, "<one line: what changed>"),
        "",
        "If the answer does not settle it, ask again, saying what the answer changed:",
        _ask(commands, fix),
    ])


def watched_answer_prompt(commands: ReportCommands, fix: ThreadFix, answer: str) -> str:
    return "\n".join([
        "The author answered your question, and is now watching this session and may "
        "type to you here. Nobody was watching when you asked; that no longer holds, so "
        "answer the author here when they write to you. Their answer:",
        "",
        answer,
        "",
        "Carry on from where you stopped. The board takes the outcome only from a "
        "report, so whatever the author says in this session, finish by running a report "
        "command yourself, as before:",
        _ready(commands, fix, FULL_SHA, "<one line: what changed>"),
        "",
        "If you need the author to decide something again, ask through the board:",
        _ask(commands, fix),
    ])


PART_NAMES = {"ticket": "the ticket", "changes": "the changes to this PR",
              "new-pr": "the new PR", "reply": "the reply"}


def _split_ticket(fix: ThreadFix) -> list[str]:
    if fix.ticket_title is None and fix.ticket_key:
        return [f"- Ticket: the existing ticket {fix.ticket_key}, {fix.ticket_url}; the new "
                "PR goes under it and nothing is filed."]
    if fix.ticket_title is None:
        return ["- Ticket: none of its own; the new PR goes under this PR's own ticket."]
    return [f"- Ticket: a new one in {fix.ticket_project}, titled {fix.ticket_title}:",
            "```", fix.ticket_body or "", "```"]


def _split_parts(fix: ThreadFix) -> list[str]:
    return [
        *_split_ticket(fix),
        f"- Changes to this PR: commit {fix.split_sha}, the tip of this worktree, which "
        f"takes the code out of {fix.pr}.",
        f"- New PR: the branch {fix.split_branch}, onto {fix.split_base} "
        f"({fix.split_base_reason}).",
        "- Reply on the comment, posted once the new PR is open:",
        "```", fix.reply or "", "```",
    ]


def _rework_of(fix: ThreadFix) -> str:
    sha = fix.split_sha
    branch = fix.split_branch
    match fix.reworks_part:
        case "ticket":
            return ("Change the ticket's project, title or body. If the new PR belongs "
                    "under an existing ticket after all, report its `--ticket-key` and "
                    "`--ticket-url` instead; if under this PR's own ticket, `--same-ticket`.")
        case "changes":
            return (f"The changes to this PR are commit {sha}, the tip of this worktree. "
                    "Amend it here, run the project's linter and the tests for the files "
                    "it touches, and report the new tip.")
        case "new-pr":
            return (f"The new PR's code is the branch {branch}. Switch to it with "
                    f"`git switch {branch}`, make the change, run the project's linter and "
                    "the tests for the files it touches, and commit. Then come back with "
                    f"`git switch -`: the tip of this worktree is {sha} again, and that "
                    "commit stays as it is. A new base goes in `--base`, with its reason "
                    "in `--base-reason`.")
    return "Rewrite the reply, written as the PR author."


def _split_report(commands: ReportCommands, fix: ThreadFix) -> str:
    sha = FULL_SHA if fix.reworks_part == "changes" else str(fix.split_sha)
    return commands.split(fix.pr, fix.key, sha=sha, branch=str(fix.split_branch),
                          base='"<the base>"', base_reason='"<why that base>"',
                          project='"<project>"', title='"<title>"', body='"<body>"',
                          ticket_key="<key>", ticket_url='"<link>"', reply='"<the reply>"')


def _split_rework_prompt(commands: ReportCommands, fix: ThreadFix, steer: str) -> str:
    part = PART_NAMES[fix.reworks_part or ""]
    fixed = ", ".join(PART_NAMES[one] for one in fix.parts_run)
    lines = [
        f"Rework one part of a split proposal on {fix.pr}, in this worktree.",
        "",
        "The review thread, every comment oldest first:",
        "```",
        _render_thread(fix),
        "```",
        "",
        f"The last attempt split code out of {fix.pr} into a pull request of its own. "
        "The split, part by part:",
        "",
        *_split_parts(fix),
        "",
        f"You are reworking {part}, and only {part}. Why it was sent back, in the words "
        f"of the author of {fix.pr}:",
        "",
        steer,
        "",
    ]
    if fixed:
        lines += [f"Fixed, because it has run: {fixed}. Fixed parts stay exactly as they "
                  "are.", ""]
    lines += [
        f"## Rework {part}",
        "",
        _rework_of(fix),
        "",
        "## Report",
        "",
        f"Once {part} is reworked, report the split again. The board takes only {part} "
        "from this report and keeps every other part as listed above, so pass the others "
        "as they stand:",
        "",
        f"    {_split_report(commands, fix)}",
        "",
        "Pass `--ticket-key` and `--ticket-url` where the new PR goes under an existing "
        "ticket, `--same-ticket` where it goes under this PR's own ticket, and "
        "`--project`, `--title` and `--body` where it has a new ticket of its own.",
        "",
        *_asking(commands, fix, "Anything else, decide yourself."),
        f"If {part} cannot be reworked as asked, report why and stop; the split stays as "
        "it was:",
        "",
        f"    {_fail(commands, fix)}",
    ]
    return "\n".join(lines)


def rework_prompt(commands: ReportCommands, fix: ThreadFix, steer: str | None,
                  workers: int) -> str:
    if fix.reworks_part is not None:
        return _split_rework_prompt(commands, fix, steer or fix.note)
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
    if fix.split_branch is not None:
        lines += [
            f"The last attempt split code out of {pr} into a pull request of its own, part "
            "by part:",
            "",
            *_split_parts(fix),
            "",
            f"Commit {fix.split_sha} is the removal, the tip of this worktree, and the branch "
            f"{fix.split_branch} holds the new PR's code. To keep the split, rework whichever "
            f"the author asks: the removal here, the new PR's code after `git switch "
            f"{fix.split_branch}` (come back with `git switch -`), and report the split "
            "again. If the code should stay in this PR after all, take the removal off with "
            f"`git reset --hard {fix.split_sha}^`, delete {fix.split_branch} with "
            f"`git branch -D {fix.split_branch}`, and report another way.",
            "",
        ]
    elif fix.ticket_title is not None:
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
        "",
        *_asking(commands, fix),
    ]
    if fix.tracker is not None:
        lines += ["", *_out_of_scope(commands, fix)]
    lines += ["", *_split_out(commands, fix, "If the code belongs in another pull request, "
                                             "split it out")]
    return "\n".join(lines)
