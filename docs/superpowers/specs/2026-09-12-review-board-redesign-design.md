# Review board redesign

The review board was built one verb at a time: a row per thread, a panel, five
decisions, a reply box. It works, and it is hard to read. Fifty threads on one PR
are a flat list in three bands, the agent's proposal is a diff behind a click, and
the only sign of progress on a running thread is its last tool call.

The prototype (private design page),
file `PR Review Flow Prototype.dc.html`, redraws the board as a queue you work and
a monitor you glance at. It models a thread's life in named states, gives every
proposal a summary, a step list and a confidence, makes every decision but accept
reversible, and adds defer, resolve and an autonomous rework. It also assumes
things the board does not have and forgets things the board does.

This spec is the union. Every point where the two disagreed was put as a question
on 2026-09-12 and answered; the full record is the appendix. It is the second of
two specs. The first, `2026-09-12-review-domain-port-design.md`, ports the board
onto a layered domain with no change in behaviour, and everything here is
written against that domain: a Conversation that owns a Fix, commands that
change their states and return effects, adapters that run them. Read that one
first.

Where the questions left a gap, the choice made here is listed under "Choices made
while writing this" so it can be overturned before the plan is written.

## What the board is for

A queue for what needs you, and a monitor for everything else. "Ready for you" is
worked top to bottom with Prev and Next. The other groups are there to be seen,
not walked, and nothing in them asks for a click until it moves into Ready.

The board stays one page per PR, served by the agent manager from `v`. The
watcher, the manager loop and the filesystem queue between them stay where they
are. What changes is the domain's states and verbs, what the agent reports, and
the whole board adapter.

## What this adds to the domain

The port gives the conversation three states and the fix eight. The redesign
extends the conversation, adds a run kind, and adds facts to both.

| Conversation state    | Meaning                                           |
| --------------------- | ------------------------------------------------- |
| `open`                | the board is working on it or waiting for you     |
| `waiting_on_reviewer` | you replied without deciding                      |
| `deferred`            | parked by you until a wake condition or by hand   |
| `rejected`            | you turned the fix down and told them, or did not |
| `resolved`            | closed from the board with no code change         |
| `removed`             | GitHub deleted the root before the board finished |

`dismissed` goes. The verb behind it becomes Resolve on GitHub, and a
conversation closed for a comment that has no GitHub thread lands in `resolved`
too, with the reply that closed it.

| Fix state    | Meaning                                                            |
| ------------ | ------------------------------------------------------------------ |
| `queued`     | waiting for an agent; carries the kind of run wanted               |
| `running`    | an agent is at work; carries the kind and the head it started from |
| `declined`   | the agent classified the conversation not safe and said why        |
| `failed`     | the attempt budget is spent                                        |
| `proposed`   | a commit to decide on, or one that could not land                  |
| `in_session` | a human is steering an agent in the fix's workspace                |
| `landing`    | accepted; records which landing steps have succeeded               |
| `landed`     | on the PR branch, pushed, and answered                             |

Run kinds gain `rework`, carrying the brief you wrote and the lines you pointed
at, beside `first` and `rebase`. A running fix records the head it started from.

New facts on the conversation: the reviewer's display name and the state of the
review the root belongs to; the start line of the anchored range; GitHub's
resolved flag and who set it; a reopened mark set when a reviewer replies after
you had spoken; a decidable stamp written whenever the fix becomes `proposed`,
`declined` or `failed`; the private note and wake condition of a deferral.

New facts on the fix: the plan the agent declared and which steps are done, the
one-line summary of the proposal, the confidence level and its sentence. The
summary is the fix's, stored apart from the conversation's gist, which is the
comment's one-line summary and stays what the row shows.

## States and groups

The rail groups rows by conversation state and fix state together.

| Group                | Contents                                                                                                                         |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Ready for you        | `open` with a fix `proposed`, `declined` or `failed`, or no fix; `removed`; a reopened `open` whose fix is `queued` or `running` |
| Agent working        | `open`, fix `running` on a `first` run, not reopened                                                                             |
| Queued for agent     | `open`, fix `queued` for a `first` run, not reopened                                                                             |
| Sent back for rework | `open`, fix `queued` or `running` on a `rework` run, or `in_session`                                                             |
| Landing              | `open`, fix `landing`, or `queued` or `running` on a `rebase` run                                                                |
| Waiting on reviewer  | `waiting_on_reviewer`                                                                                                            |
| Deferred             | `deferred`                                                                                                                       |
| Done                 | `open` with fix `landed`; `rejected`; `resolved`                                                                                 |

Empty groups are not drawn. The header counts ready, agent working (working plus
queued), rework, landing, waiting (waiting plus deferred) and done. Landing is
shown only when it is not zero.

Parking a conversation in waiting or deferred leaves its fix exactly as it was,
so the way back is one transition to `open` and the row lands in the group its
fix state puts it in. Nothing has to remember where it came from. Rejected is the
exception since the 2026-09-15 amendment: it drops the workspace, so its way back
re-queues the fix rather than restoring it.

### Reopening

A reviewer's reply is a command on the conversation. It requeues the fix for a
`first` run with attempts reset, whatever the fix was doing, as today. Where the
row sits while that run happens depends on whether you had already spoken on
the conversation: if you had replied, landed or rejected, the conversation is
marked reopened and the row sits at the top of Ready for you with a black
square, the new reply highlighted and the panel showing what you already pushed;
if you had not, the row goes to Agent working like any other. The reopened mark
is cleared by any verb or composer reply on the conversation.

A reply on a conversation GitHub holds resolved, whoever resolved it, refreshes
the transcript and reopens nothing, as today. The reviewer un-resolving it is
what brings it back.

A landed fix has no workspace any more. Reopening asks for a new one cut from
the current PR head, which already carries the landed fix, before the run is
queued. Today nothing on the reopen path does this, and a reviewer replying on a
landed thread sends the pool into a deleted directory until the attempt budget is
spent.

### Ordering

Ready for you: reopened conversations first, then by the decidable stamp, newest
first. A reopened conversation keeps its place at the top until you act on it,
including after the agent finishes.

Every other group: newest comment activity first, as today.

The captioned gap under the last row that wants you goes; the groups carry that
information now. The held list that refused to move rows under the pointer goes
too, along with its pulsing border and its twenty-second ceiling.

## Views

The header carries the PR title and number, the Queue and Board toggle, the group
counts, and the PR's CI state read from the state snapshot. CI is a fact about
the PR, not about a row, so it lives here and not on done rows.

Two views, toggled in the header: Queue and Board. Queue is the default and the
only one with a panel. Both draw the same read model.

**Queue** is the prototype's rail and detail pane: a 300px rail grouped as above,
each row a status square, `file.py:142`, the gist, and a meta line that says what
the row is doing ("Anna Example · 2 of 3 changes", "Your note · agent re-running",
"Pushed a1f9c3e · 2h ago"). Rows with no path show the kind label as today,
"conversation" or "review summary". Done rows are struck through.

**Board** is the prototype's five columns: Agent working, Ready for you, Reviewer
replied, Waiting, Done. Agent working takes the queued and running groups; Ready
for you takes that group less the reopened rows, which are Reviewer replied;
Waiting takes rework, landing, waiting and deferred; Done is Done. Cards carry
the location, the gist, the step dots and the meta line. Clicking a card switches
to Queue with that conversation open.

## Walking the list

`j` and `k` open and walk every row, as today. `n` and `p` walk Ready for you
only, reopened first, and are what the panel's Prev and Next buttons press. A
click opens a row in either view.

After a decision the panel stays on the decided row. It shows the row's new state
and the toast says what happened; `n` moves on when you are ready.

## The panel

Top to bottom, following the prototype:

1. **Kicker and reviewer.** "3 of 12 ready · billing/invoice_writer.py line 142", then
   the reviewer's display name and the state of the review the comment belongs to
   ("requested changes", "commented", "approved"). Both come from GitHub; the
   poller's query gains `author { login name }` on every comment and
   `pullRequestReview { state }` on review comments. No team label.
2. **The thread.** Every comment with author, when, and body, oldest first. On a
   reopened conversation the newest reviewer comment is highlighted.
3. **The composer.** A "Reply to Anna" link under the thread, which the operator
   clicks to open the box and the post button; posting folds it back to the link.
   A line under the box says what posting does to the row. On a row in Ready for you, posting parks
   the conversation in Waiting on reviewer once the reply is on GitHub, with the
   fix untouched. On a landed conversation the reply carries the landed commit
   link under it. Everywhere else it posts and the row does not move. Every reply
   joins the transcript when it posts and is kept off the next poll, as today.
4. **The code under the comment.** The PR's diff around the anchor with
   expandable context, as today, plus the whole commented range highlighted from
   the start line to the end line. No "Open file" link.
5. **The fix.** A label ("Agent proposal · 2 of 3 changes", "Agent working · 1 of
   3 changes", "Queued for agent", "Accepted · pushed"), a state banner, the
   agent's one-line summary, the step list with a filled square per finished
   step and the file it touched, the confidence callout, and a meta line with a
   files popover (count and per-file plus and minus from git) and the test
   verdict. A declined fix shows the agent's reason where the summary would be
   and no steps. A failed fix shows the failure reason. No reasoning popover.
6. **The diff.** The fix's range as a unified diff with file headers. Its title
   follows the state: "Proposed diff · 2 files", "Pushed as a1f9c3e", "Previous
   proposal (being reworked)" during rework, "Click lines to point the agent at
   them" while the rework composer is open. A reopened conversation whose earlier
   fix landed shows two: "What you already pushed · c07b21d" over the landed
   range, and the new fix's diff once there is one. A queued or running fix with
   no commit yet shows a placeholder instead.
7. **The action bar**, sticky at the bottom, by state:
   - Ready with a proposed fix: Accept, Send back for rework; secondary links
     Defer, Reject, Resolve on GitHub, Open a session.
   - Ready with a declined fix: Send back for rework labelled "disagree, try a
     fix anyway"; secondary Reject, Resolve on GitHub, Open a session.
   - Ready with a failed fix: Try again; secondary Reject, Resolve on GitHub,
     Open a session.
   - Removed: Accept where there is a commit worth keeping, and Close, which
     posts nothing and moves the row to Done.
   - Queued, running, in session, reopened: Reply to X; secondary Defer, Reject,
     Resolve on GitHub.
   - Landing: the button that resumes the step that failed ("push it", "retry
     the reply"), as today.
   - Landed: Next ready, Reply to X.
   - Waiting, deferred, rejected, resolved: Next ready, and the way back
     ("Bring back to Ready", "Undefer", "Reconsider", "Un-resolve").

The deleted-comment handling stays exactly as it is: the presence check while a
conversation is open, the `removed` state, the notice on a settled row, and
dialogs that drop their reply box. Which states a deletion can interrupt is a
question the conversation answers, not a second table.

## Verbs and what they do

Every verb is a command. The conversation answers with its new state and the
effects to run; the `decide` service runs them and feeds the results back. What
follows is what each verb means, and what reaches git and GitHub.

### Accept

The dialog shows the commit message the fix will land with, the changed files
with plus and minus counts, a reply box, an "also mark the thread resolved on
GitHub" tick that is off by default, and on a comment of your own with no
replies the "delete GitHub comment" tick. The message is the agent's, from the
tip of the fix's range, and an Edit message link swaps in a box for your own;
the landed commit then carries yours. Left as it was, or emptied, the agent's
lands.

The fix moves to `landing`. Landing cherry-picks the fix's range onto the PR
branch and squashes it into one commit, so one accepted conversation is one
commit on the PR whatever the workspace holds. It pushes, then answers: your
words with the commit link under them, or the robot-prefixed link alone when the
box was empty, or the deletion of your own comment if you ticked that. If the
resolve tick was set it then resolves the conversation on GitHub and the row
lands in Done reading "Resolved · a1f9c3e". Each success is recorded on the fix
before the next effect runs, and accepting again resumes at the first step not
done, as today.

The workspace is dropped once the fix is on the PR branch, as today. A landed
fix is reachable from the PR's history, which is all anything downstream needs.

### Send back for rework

Opens the rework composer in the panel rather than a dialog: a note box, and the
diff's lines become clickable while it is open. A clicked line is a pointed line
and shows as a chip with its text; clicking again unpoints it. The send button is
disabled until there is a note or a pointed line.

Sending queues the fix for a `rework` run carrying the brief: the note and the
pointed lines as file, line and content. The pool picks the rework prompt, which
carries the whole conversation, the brief, and the instruction to start from the
commit already in the workspace. The row sits in Sent back for rework with a
blue square. When the agent reports, the fix is `proposed` again with the note
"Revised after your rework note" and a fresh decidable stamp; it is not pinned
above other ready rows.

When a run exits without reporting, the pool compares the workspace head against
the head the run started from, not against the fix's base, so a rework that died
at once is a failure and not a stale proposal wearing a new stamp.

### Open a session

A separate action, not a choice inside rework. It moves the fix to `in_session`
and does what reject does today: splits the PR's tmux window and starts `claude`
in the fix's workspace with an optional steer that may be empty. The row sits in
Sent back for rework reading "session open". The session reports back through
`cli thread ready` like any run, which moves the fix to `proposed`. The
scheduler never starts a run for a fix in session. Hidden when Claude is
disabled, like rework.

### Reject

Turns the fix down. The dialog takes an optional reply and, on your own comment,
the delete tick; "Reject without reply" is allowed. The conversation moves to
`rejected` in Done, struck through, and its workspace is dropped — which takes
the fix's branch with it, so the proposed diff is unreachable the moment gc runs.
Reconsider moves the conversation back to `open` with the fix re-queued from
scratch, its attempts reset and a fresh workspace cut, because there is no longer
a proposal to restore. Reject on a queued or running fix first stops the run.

*Amended 2026-09-15.* This section originally kept the fix and its workspace
untouched, and had Reconsider restore the proposal. Dropping the workspace is the
deliberate reversal: Reject is the verb that says the agent's answer is not wanted,
and keeping a worktree per rejected conversation for the life of the PR costs disk
for a diff nobody asked to see again. The cost is that Reconsider is no longer
free — it re-runs the agent. Defer is the verb to reach for when you want the
proposal kept, and it keeps its workspace exactly as specified below.

### Defer

Parks the conversation with nothing posted. The dialog offers three wake
conditions and a private note kept on the conversation:

- by hand, with Undefer on the row;
- when this PR's CI is green, checked by the `tick` service against the state
  snapshot each pass, so a conversation deferred while CI is already green wakes
  on the next tick rather than never;
- when another PR, chosen by number, is closed, which the `tick` service asks
  GitHub about once a poll interval for as long as any conversation on the PR
  is waiting on it.

Waking moves the conversation back to `open` with a fresh decidable stamp and a
note saying what woke it. A deferred fix keeps its workspace. Defer on a queued
or running fix first stops the run.

### Resolve on GitHub

On a review conversation: posts your reply first if you typed one, then resolves
the conversation on GitHub through the raising GraphQL helper, and moves the
conversation to `resolved` in Done. The fix and its workspace are kept, so
Un-resolve, which unresolves on GitHub and moves the conversation back to
`open`, lands the row where its fix puts it with the diff still there. The
dialog offers the reply box and, on your own comment, the delete tick.

On a conversation comment or a review summary there is nothing to resolve. The
verb posts your reply on the PR quoting the comment if you typed one, as decline
does today, and moves the conversation to `resolved`. Un-resolve is not offered
for these. On a removed comment the verb reads Close, posts nothing, and moves
the conversation to `resolved` reading "comment deleted".

The poller writes GitHub's resolved flag, and who set it, onto the conversation
every cycle as a refresh that moves no state. A conversation the reviewer
resolves on GitHub reads "resolved by Anna" in Done and offers nothing until
they un-resolve it. A conversation the reviewer un-resolves after the board
resolved it returns to `open`. For the un-resolve to be visible at all, the
poller's snapshot has to carry the resolved flag beside each comment's id and
hash, since a resolved conversation's comments already match the snapshot.
Today the poller drops resolved conversations before diffing them, and a
conversation resolved before the board first saw it has no record; from here
the diff refreshes them like any other and the `poll` service creates a record
for one it has never seen without queueing a fix for it.

### Try again

On a failed fix only. Today's retry: back to `queued` for a `first` run with a
fresh attempt budget.

### Reply

The composer, described above. Posting is an effect; when the GitHub adapter
reports the reply posted, the conversation applies it, and that is the one
command that parks an `open` conversation in Waiting on reviewer. Bring back to
Ready undoes it.

### What is gone

Revert is not built. Dismiss and retry as verbs are gone, folded into Resolve and
Try again. There is no reasoning popover, no test counts, no per-commit CI, no "include Bob's replies" toggles, and no reviewer team
label.

## What the agent reports

The report contract grows in three places and stays the same everywhere else.
Every report is a command through the `report` service, applied under the
conversation's lock, so the agent's process and the manager's never overwrite
each other.

**A plan before the work.** Both the first-run prompt and the rework prompt ask
the agent to write its steps before touching code:

```
cli thread plan --repo R --pr N --thread-id X --step "Raise instead of continue" --file billing/invoice_writer.py --step "Test: export raises on missing tax rate" --file tests/test_invoice_writer.py
```

and to mark each one as it finishes:

```
cli thread step --repo R --pr N --thread-id X --done 1
```

The plan lives on the fix. A rework declares a new plan. A declined fix has none.

**Summary and confidence on ready.**

```
cli thread ready ... --summary "Raise MissingTaxRate in _collect() instead of skipping, add a unit test." --confidence medium --confidence-note "Callers in cli/billing.py may rely on the silent skip. Not verified."
```

`--tests passed|failed|unverified`, `--tests-note` and `--note` stay as they are.
Files and their line counts come from `git diff --stat` over the fix's range, not
from the agent.

The skill's subagent prompt gains the same two instructions and the `RESULT:`
line grows to carry the summary and confidence, so the orchestrator can relay
them. The one-commit rule stays: steps are how the agent thinks, commits are how
the fix lands. The prompts read the contract from the one place the port put it.

**Rework prompt.** Carries the whole conversation in order, the brief, the
pointed lines as `path:line  content`, and says to start from the commit in the
workspace and to write the new commit's message as if it were the only commit,
describing the fix as it now stands. Landing squashes, and takes that message.

## What the board writes to GitHub

Only these, and nothing without one of them:

- your words, as a reply on the conversation, or on the PR quoting the comment
  where there is no thread;
- the commit link on landing, under your words or robot-prefixed on its own;
- the commit link under a reply posted from the composer on a landed
  conversation;
- resolve and unresolve, when you tick or ask;
- deletion of your own comment, when you tick.

Every reply the board posts joins the conversation as it posts and is kept off
the next poll by id, as today.

## The look

The board adopts the prototype's design system as drawn: a licensed typeface from the OTF
files in the design project, served by the board's own server from a configured
local directory; black type; colour only as status squares and fills; no radii,
no shadows; unified diffs with added lines on green and removed lines on yellow;
one grey ground behind the Board view and white behind Queue. The status squares
are the design's: yellow filled for ready, black outline for working, dashed
outline for queued, blue for rework and sessions, grey for waiting, deferred and
rejected, black filled for reopened, green for landed and resolved,
struck-through text for everything in Done. The design has no square for
declined, failed or landing rows; declined and failed wear the ready yellow,
landing the working outline.

Plus an equivalent dark mode: the same structure with the grounds inverted, the
squares and fills kept, chosen so a diff and a square read the same way in both.
It follows the system setting as the board does today.

Toasts are added: a black bar at the top right for every outcome ("Pushed
a1f9c3e and replied to Anna.", "Deferred. Nothing posted to GitHub.") and when an
agent finishes and a row moves into Ready. The failure banner stays for
transport failures and a server that has gone away; toasts never carry a
failure.

The diff palette is written today in three places that must agree: as `delta`
arguments, as inline styles from the ANSI converter, and as page CSS. The board
adapter defines it once and derives the other two from it, in both modes. The
diff row structure, the expand rows and the anchor logic stay. The rule in
CLAUDE.md that a narrow list hides the path goes; the 300px rail shows a path on
every row.

## What stays exactly as it is

The skip classification and its reasons. The poller's snapshot and hash diffing,
the five-second cutoff, and the reply suppression by id. One approval, one push,
one CI run. The rebasing flow on a conflicting approve. The presence check and
everything under "comment deleted". The delete-own-comment tick, offered wherever
a closing verb offers a reply. Kind labels for rows with no path, and the
outdated-thread fallback to the original line. `claude_enabled = false`, under
which Accept, Reject, Defer, Resolve, Try again and Reply stay live and rework
and sessions are hidden. Node-id keys, percent-encoded slugs, whole-file writes,
and every rule in CLAUDE.md about them.

## Verified against the live API

Checked on 2026-09-12 with `gh api graphql` introspection:

- `PullRequestReviewComment` has `pullRequestReview`, whose `state` is the review's
  state, and `author`, whose `User.name` is the display name.
- `Mutation` has `resolveReviewThread` and `unresolveReviewThread`, alongside the
  `addPullRequestReviewThreadReply` the board already uses.

## Choices made while writing this

These were not asked. Each is a default to keep the spec whole, not a decision
already taken.

01. **Landing on the Board view** goes in the Waiting column, since those rows wait
    on the machine rather than on you, and the design has five columns.
02. **The squashed commit's message** is the message of the last commit in the
    fix's range, and the rework prompt is told to write that message as if it
    were the only one. A message given on Accept replaces it, and a one-commit
    range is then recommitted with it rather than left as the cherry-pick made
    it.
03. **Resolve takes an optional reply** and the delete tick, because it inherits
    dismiss, which took both. The design's resolve modal had neither.
04. **Un-resolve on a landed conversation** flips GitHub and leaves the row in
    Done. Elsewhere it returns the conversation to `open`.
05. **`n` and `p`** are the ready-only walk keys. Any pair not already taken would
    do.
06. **A reworked fix is not pinned** above other ready rows when it returns; only
    a reopened conversation is. It gets a fresh decidable stamp and sorts by that.
07. **Header counts** add a Landing count when it is not zero, so the header and
    the rail agree.
08. **A deferred conversation woken by an event** returns to `open`, not to the
    top of Ready; it is not a reviewer reply.
09. **A session reports** with `cli thread ready` as today, and may declare a plan
    and steps if it wants to, but is not required to.
10. **The typeface files are not committed.** They are licensed, and the repo is
    public. `config.toml` gets a `board_font_dir` pointing at a local copy; when
    it is unset or empty the board falls back to a system stack and the layout
    does not change.
11. **Squares the design did not draw.** Declined and failed fixes wear the ready
    yellow because they sit in Ready for you; landing rows wear the working
    outline because a machine is busy on them.
12. **Reject and Defer on a running fix** stop the run first. The design offers
    both on working rows ("reject to skip the agent") without saying what
    happens to the agent.
13. **A rejected conversation counts as one you had spoken on** for the reopened
    pin, even when you rejected it without a reply. The answer to A5 named
    replied and landed; rejecting is a decision the reviewer can see the effect
    of.
14. **Defer's wake conditions are checked by the manager**, not raised by the
    watcher. The watcher's CI event fires only on a change, and the watcher
    knows nothing about conversations; the manager loop already reads the state
    snapshot and can ask GitHub about one PR number.

## Build order

The port in `2026-09-12-review-domain-port-design.md` comes first and is a
prerequisite for every step here. Then, in this order, each a plan of its own
with domain and application tests written first:

1. **States and groups.** The new conversation states, `in_session` and the
   `rework` run kind as first-class, the decidable stamp and the reopened mark,
   the eight groups and their ordering, the rail and header in today's look.
   Dismiss becomes Resolve on the existing dialog, retry becomes Try again.
2. **The look.** Design system tokens, the typeface, dark mode, toasts, the panel
   layout with today's data, the one palette the diff colours derive from.
3. **Agent contract.** `thread plan`, `thread step`, `--summary`, `--confidence`;
   the fix section of the panel. Display name and review state from the poller.
4. **Accept.** File stats, squash, resolve tick, the Landing group's resume
   buttons.
5. **Rework and sessions.** The rework run kind carrying its brief, the run
   start head, the pointed-lines composer, Open a session as its own action.
6. **Waiting, reject, defer, resolve.** The parked states and their ways back,
   the wake checks in `tick`, the resolved flag in the snapshot and on the
   conversation, records for conversations first seen resolved.
7. **Board view.** Five columns over the same read model, card click into Queue.
8. **`n` and `p`**, the range highlight, the two diffs on a reopened landed
   conversation, and the remaining panel details.

The suite must stay under replay: anything that spawns git needs `make record`.

## Appendix: the decision record

Answers as recorded on 2026-09-12. R questions are the roots; the rest followed
from them. Where an answer differed from the recommendation the choice stands.

| Id  | Question                                                  | Answer                                                                                                                                  | Note                                                                                        |
| --- | --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| R1  | What is the board for once this lands?                    | A queue for Ready, a monitor for the rest.                                                                                              |                                                                                             |
| R2  | Does every comment get an agent run?                      | Keep classification and skip.                                                                                                           |                                                                                             |
| R3  | Rework: autonomous run, or a session you steer?           | Autonomous by default, session as a separate action.                                                                                    |                                                                                             |
| R4  | How long does a proposal live?                            | Keep until PR close, except after landing.                                                                                              |                                                                                             |
| R5  | What may the board write to GitHub unprompted?            | What I type, the commit link, and resolve or unresolve when I tick it.                                                                  |                                                                                             |
| R6  | How much does the agent report back?                      | Summary, planned steps reported as they finish, confidence, reasoning.                                                                  | Refined by E2: confidence, no reasoning paragraph.                                          |
| R7  | The prototype's look, or only its structure?              | Adopt the design system as drawn, light only.                                                                                           | "Do it exactly like the prototype in terms of the design, but add an equivalent dark mode." |
| R8  | Does the no-Claude mode stay a requirement?               | Stays a requirement for the git and network verbs.                                                                                      |                                                                                             |
| A1  | Where does a skipped thread go?                           | Ready for you, reason in place of the proposal.                                                                                         |                                                                                             |
| A2  | Where does a failed thread go?                            | Ready for you, with the reason and Try again.                                                                                           |                                                                                             |
| A3  | Rebasing, committed not pushed, reply failed: how shown?  | One extra group, Landing.                                                                                                               |                                                                                             |
| A4  | Keep the deleted-comment handling?                        | Keep it as it is.                                                                                                                       |                                                                                             |
| A5  | Where does a reopened thread sit while the agent re-runs? | Ready only when you had already replied or landed; otherwise agent.                                                                     |                                                                                             |
| A6  | Does a reviewer reply always re-run the agent?            | Always.                                                                                                                                 |                                                                                             |
| A7  | How is Ready ordered?                                     | Reopened first, then agent finished time.                                                                                               |                                                                                             |
| A8  | Groups and header counts                                  | The design's groups and counts.                                                                                                         |                                                                                             |
| B1  | Empty reply on accept                                     | Keep posting the commit link.                                                                                                           |                                                                                             |
| B2  | Editable commit message                                   | Do not show it.                                                                                                                         | Reversed by #140: shown, with an Edit message link that the landed commit honours.          |
| B3  | More than one commit in the range                         | Squash to one commit when landing.                                                                                                      |                                                                                             |
| B4  | The "also mark resolved" tick                             | Yes, default off.                                                                                                                       |                                                                                             |
| B5  | Changed files with line counts in the dialog              | Show them.                                                                                                                              |                                                                                             |
| B6  | The delete-own-comment tick                               | Wherever a closing verb offers a reply.                                                                                                 |                                                                                             |
| C2  | Pointing at diff lines                                    | Build it with the first autonomous rework.                                                                                              |                                                                                             |
| C3  | "Include Bob's replies" toggles                           | Whole thread always.                                                                                                                    |                                                                                             |
| C4  | Rework with an empty note                                 | Refuse for an autonomous run, allow for a session.                                                                                      |                                                                                             |
| C5  | Where does rework start from?                             | From the previous commit.                                                                                                               |                                                                                             |
| D1  | Reject drops the proposal; what does Reconsider do?       | Reject drops the workspace; Reconsider re-queues the agent. Amended 2026-09-15; was "R4 keeps the proposal, so Reconsider restores it". |                                                                                             |
| D2  | Reject without a reply                                    | Allowed.                                                                                                                                |                                                                                             |
| D3  | Defer, and what wakes it                                  | Manual undefer; this PR's CI passes; another PR closes.                                                                                 |                                                                                             |
| D4  | Resolve on GitHub as a verb                               | Resolve and un-resolve.                                                                                                                 |                                                                                             |
| D5  | Resolve on a comment with no thread                       | Post a reply and close.                                                                                                                 |                                                                                             |
| D6  | Revert a landed commit                                    | Do not build it.                                                                                                                        |                                                                                             |
| D7  | After a revert, what goes on GitHub?                      | Not needed.                                                                                                                             |                                                                                             |
| D8  | A composer reply on a Ready thread                        | Park it in waiting, as designed.                                                                                                        |                                                                                             |
| D9  | A reply on a done thread                                  | Append the commit link.                                                                                                                 |                                                                                             |
| D10 | Dismiss and retry                                         | Dismiss becomes Resolve, retry becomes Try again on failed rows.                                                                        |                                                                                             |
| E1  | What is a "change" in "2 of 3 changes"?                   | Agent-declared steps reported as they finish.                                                                                           |                                                                                             |
| E2  | Confidence and reasoning, in detail                       | A confidence level and a sentence.                                                                                                      |                                                                                             |
| E3  | Test counts                                               | Keep the verdict only.                                                                                                                  |                                                                                             |
| E4  | Reviewer name, team and review state                      | Fetch the display name; fetch the review state.                                                                                         |                                                                                             |
| E5  | The code under the comment                                | The diff, plus the range highlight.                                                                                                     |                                                                                             |
| E6  | "Open file"                                               | No link.                                                                                                                                |                                                                                             |
| E7  | CI on the landed commit                                   | No option picked.                                                                                                                       | "CI status would be a global state which should show in the top title bar."                 |
| F1  | The kanban board view                                     | Build it now.                                                                                                                           |                                                                                             |
| F2  | Walking the list                                          | j and k over every row, plus keys for next and previous ready.                                                                          |                                                                                             |
| F3  | Where the panel goes after a decision                     | Stay on the decided row.                                                                                                                |                                                                                             |
| F4  | The reply composer                                        | A link under the transcript that opens the box on click, chosen off the prototype over always visible.                                  |                                                                                             |
| F5  | Toasts                                                    | Add them.                                                                                                                               |                                                                                             |
| F6  | Dark theme                                                | Keep dark theme.                                                                                                                        |                                                                                             |
| F7  | Holding the list still under the pointer                  | Drop it.                                                                                                                                |                                                                                             |
| F8  | Rows without a file and line                              | Show the kind label where there is no path.                                                                                             |                                                                                             |
| G1  | Which pieces come first?                                  | State model and groups.                                                                                                                 |                                                                                             |
| G2  | Anything in the design to drop outright?                  |                                                                                                                                         | "Nothing that I haven't specified above."                                                   |
| G3  | Anything the board does today the design forgot?          |                                                                                                                                         | "Again, nothing that hasn't been specified above."                                          |

E7's note is taken up in the header: the PR's CI state shows in the title bar,
not on done rows.
