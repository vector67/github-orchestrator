# Board API contract revisions

Decided on 2026-09-22, in a third session that reviewed
`2026-09-22-board-api-contract.openapi.yaml` line by line and then took the
findings one at a time. `2026-09-22-board-api-decisions.md` is why the contract
looked the way it did before this. This file is why it looks the way it does
now, and where the two disagree, this wins.

Three of these reverse decisions that were written down. They are listed
together at the end so nobody has to discover them.

## The document

**The dated file is a record, not a contract.** It is frozen as the argument
made on 2026-09-22 and never regenerated. FastAPI's output becomes the live
contract at its own path. The prose that explains why the shape is what it is
moves into pydantic `Field` descriptions and route docstrings, where someone
changing the code will read it.

**A ledger accounts for every discrepancy, once.** When the generated contract
first exists, one document lists every difference between it and this record,
each with a verdict: *mechanical* for the generator's idiom, *record wins* for
a change the code needs, *code wins* for a place this record was wrong, with
the reason. Expect a large mechanical section: pydantic writes
`anyOf: [{type: string}, {type: "null"}]` where this file writes
`type: [string, "null"]`, adds `422` and `HTTPValidationError` to every route
with a body, injects `title` on every property, and does not reproduce a
`discriminator` mapping that folds four kinds onto one schema. Reconciliation
is a single event, not a standing check, because the code drifts from a frozen
record by design.

## Caching and concurrency

**Three etags, three scopes.** `/api/pull-request`'s covers its own fields.
`/api/conversations`'s means some thread moved, so a poll can come back `304`.
Each `Conversation` carries its own `etag` field, and `If-Match` on an
operation is checked against that.

**The thread's etag is a field, not only a header.** A client that drew forty
cards from one collection read holds no per-thread tag, and the collection's
tag moves whenever any thread moves, so using it as a precondition fails on a
busy pull request for reasons that have nothing to do with the thread being
acted on. AIP-154 puts the etag in the resource for exactly this case, and the
contract already follows AIP-136 for custom methods.

## Who works out what

**The browser folds, with two exceptions.** Labels, wording, relative times and
which buttons a state calls for are the front end's. The back end still ships
no list of the operations a thread will accept.

**The back end computes the thread's state.** One state machine over the
thread, whose answer is stored on the conversation and sent to the front end.
Walking a whole operation history to work out which heading a card belongs
under is a dozen states of compound conditions, and getting one row wrong puts
a card in the wrong section. This reverses the deletion of `situation`.

**The back end orders.** If the board is ever paged, ordering has to be the
server's, and a rule that has to move later should not be built in the browser
first. Within-group ordering goes with it.

**`state` is the machine's answer.** GitHub's `open` / `removed` becomes
`github_removed`, a boolean beside `github_resolved` on the same object.

**Two clocks.** A thread is ordered by whichever is later: the moment its state
last changed, or its newest comment. One clock alone loses the case where
someone replies again to a thread already in its final state, and per-state
sort rules are what produced a sort key with three different segment counts
that was only safe because the buckets kept them apart.

## Errors

**A stable enumerated code beside every sentence.** Everywhere the domain
refuses or judges, it ships a code the front end branches on and a sentence it
displays. The sentence may be agent-written and situation-specific; the code is
a closed vocabulary written into the contract. `ErrorDetail.code`,
`OperationSummary.reason`, and `classification` all gain one. This reverses
"no structured error codes".

## Stopping and rejecting

**One verb means stop.** The operator's intent is to stop the thing, and
whether the drain has picked it up yet is the domain's problem. `:cancel`
disappears into `:stop`.

**`stop` and `reject` are different work.** `stop` halts what is in flight,
posts nothing, and leaves the thread's standing untouched. `reject` turns down
a finished proposal, drops its worktree, and posts the reply. Stopping a rework
because the brief had a typo must not post to GitHub.

**Two tests.** `stop` is allowed when an operation is pending or running, and
errors otherwise. `reject` is allowed when nothing is in flight and a proposal
exists, and errors otherwise. A rework running over an older proposal can be
stopped but not rejected. A thread where the agent declined, with nothing
running and no proposal, refuses both, with different codes.

**`stop` refuses rather than guesses.** If the front end drew a card showing a
run in progress and the proposal landed in between, the refusal carries a code
that lets the front end say the proposal is there and reject is the verb.

## One state machine

**One machine over the thread's state, recorded as a table.** Allowed
transitions, and a code on every disallowed edge so the refusal can say why.
The machine is a written artifact that the domain enforces and the front end
draws buttons from. It is not a field on the wire, so "the back end refuses; it
does not enumerate" still holds.

**Its states are the headings, rewritten.** The group tables in
`2026-09-12-review-board-redesign-design.md` and
`2026-09-21-reviewer-board-design.md` are keyed on vocabulary this contract
removed. Each row is rewritten in terms of what survives, and a row that will
not rewrite is a named missing fact rather than a judgement call. That rewrite
is the acceptance test for the contract's completeness.

## Work in flight

**The plan and progress live on the fix operation.** A running agent has no
proposal yet, so a plan on `Proposal` cannot draw a card that says how many
steps are done. The summary stays on `Proposal`, because the agent writes it at
the end and it describes the artifact rather than the run.

**A card carries the step count and the two stamps.** `OperationSummary` gains
`requested_at`, `settled_at`, and how many plan steps are done out of how many.
All of them are written rarely, so the collection's `304` survives.

**`last_action` and `progress` stay off the summary.** They change every second.
On an embedded summary they would move the conversation's etag on every agent
heartbeat, which moves the collection's etag, which means the board's poll
never returns `304` while any agent is running.

**One live read serves the fast poll.** A pull-request-level collection of the
operations currently pending or running, with plan, progress and last action.
One request per tick whatever the number of agents, and one etag answering
whether anything in flight has changed. It returns the same operation resources
the per-thread reads return, selected differently.

**A session runs until it reports.** `start-session` is `running` while the
pane is open. The operator tells Claude in the session to update the board, and
that settles the operation, carrying a proposal. This gives the kind a terminal
state, makes it stoppable like anything else in flight, and removes the only
operation that could never fail or finish. A proposal stops being "what one
agent run left behind" and becomes what any completed work leaves behind.

## The reviewer board

**It is in.** Drafts, creating a thread GitHub does not have, and submitting a
review are designed into this contract rather than deferred. The contract was
already half reviewer-aware, and half is the worst place to stop.

**A draft is a conversation, marked by kind.** `ThreadKind` gains `draft`, so
the difference is declared in the type rather than implied by which fields are
null. One collection, one order, one card component. A draft's kind changes
when it is posted, because kind decides whether a reply can be threaded under
the thread and a posted draft can be replied to.

**A conversation's key is the board's own, always.** GitHub's node id becomes a
field, null until the thread exists there. Nothing ever re-keys, which is what
every etag, every open panel and every in-flight request already assumes. The
contract already described `key` as the name the records adapter gives the
file; drafts are the case that proves that is not GitHub's name for the thread.
This reverses "the key is always a GitHub node id".

**Every draft verb is an operation.** Creating, editing, enrolling in the
outgoing review, discarding and posting on its own. One write mechanism, one
refusal shape, one history.

**Edits collapse.** Consecutive edits to the same draft update one operation
rather than appending. Without this a draft fiddled with for ten minutes puts
forty summaries on the board's cheapest read. A blanket cap was rejected
because the machine reads the history, and dropping the oldest entries
eventually drops the operation that established the current state.

**Work that is not about one thread lives on a pull-request-level operations
collection.** Creating a draft has no conversation to hang off, and sending a
review is about the whole review. Both are created by custom methods on that
collection, the same way per-thread verbs are created on theirs.

**Sending a review writes one operation plus a child on each draft.** The
pull-request operation holds the verdict, the summary body and whether GitHub
took it. Each enrolled draft gets a posted operation in its own history, so
"a thread's state comes from a thread's history" stays true and the machine
stays testable one thread at a time.

**Anchors are validated at enrol.** GitHub rejects a review comment on a line
that is not in the diff, and the review POST is one call, so one bad anchor
fails all of them after the verdict is chosen. Enrolling is already an
operation with a refusal path, and checking there means send can only fail for
reasons that are about the review as a whole.

## Housekeeping

**One file entity, `hunks` nullable.** The diffstat and the diff carried the
same three fields in two schemas. They become one, with `hunks` null when they
were not asked for and `[]` when there are none to show, which `is_binary` now
explains.

**`attempts_allowed` beside `attempts`.** A card cannot draw "2 of 3" from a
constant only the server knows.

**`/api/files` gets a ceiling.** A maximum line count with its own refusal
code, a requirement that `to_line` is at or after `from_line`, and a code for a
file that cannot be returned as text. Every other expensive read was moved
behind its own endpoint on cost grounds; this one was not given the same
treatment.

**`is_binary` on the file entity.** Without it a binary file and an unchanged
file are both an empty `hunks` array.

**`html_url` and `head_sha` on the pull request.** `Comment.html_url` exists so
the front end does not have to learn GitHub's URL format, and the same argument
applies to the pull request itself. The head matters because a `rebase`
operation carries `onto` and nothing says what it is rebasing from.

**`Comment.html_url` is nullable.** A draft's comment does not exist on GitHub,
so it has no URL there.

**The operation state `deferred` becomes `requeued`.** It meant "the board put
it back for the next pass", which is unrelated to what a `defer` operation does
to a thread, and the thread now has states of its own with the other meaning.

## What this reverses

- `2026-09-22-board-api-decisions.md:140`, "No structured error codes: nothing
  consumes them and inventing a vocabulary means guessing at failures nobody
  has seen." Codes are now required everywhere the front end branches.
- `2026-09-22-board-api-decisions.md:16-30`, which deleted `situation`,
  `awaiting_you` and `permitted_decisions` because the front end could compute
  them. The state and the ordering come back to the server. The buttons do not.
- `2026-09-07-comment-threads-design.md:29`, "the key is always a GitHub node
  id." It is now the board's id, with the node id as a field.

Neither 09-22 document referenced `2026-09-21-reviewer-board-design.md`
anywhere, so drafts were absent from the contract without any record of whether
they had been considered. That is now decided rather than omitted.

## Out of scope

**How the session's CLI reaches the board.** Through the domain or straight to
the record, it does not go over HTTP, so this contract says nothing about it.

**Validating an anchor as it is typed.** Better feedback than validating at
enrol, and it needs a rule for a draft whose anchor was valid when written and
whose diff has since moved. Worth revisiting once drafts are in use.
