# What we decided about the board's API

Decided on 2026-09-22, across two sessions. The second reopened most of the
first. `2026-09-22-board-api-contract.openapi.yaml` was the contract until
2026-10-01, when it was retired for the one the board serves at
`/api/openapi.json`; this file is why it looks the way it does. It supersedes
`2026-09-22-board-api-contract-design.md`, and where the two disagree, this
wins.

## What the back end is for

**The API carries stored facts and ISO timestamps. Nothing else.** No labels,
no colours, no assembled sentences, no relative times, no sort keys, no
classifications. This reverses the design doc, which held up `RowView`'s
composed `meta` and `notes` strings as the virtue that made it narrow.

**Anything the back end computes from fields already on the wire is the front
end's to compute instead.** The first pass kept three derived fields —
`situation`, `awaiting_you` and `permitted_decisions` — on the grounds that
each was a rule rather than a label, shared with `apply`, and that a front end
reimplementing them would reopen a bug class. All three are gone. The
information they fold over is already on the wire, so shipping the fold as well
puts one truth in two places, and a front end that reads the inputs in one
screen and the verdict in another can disagree with itself.

The bug-class argument did not survive contact with the code either:
`standing.py`'s table already offers `resolve` and `defer` on a reviewer's
parked cards that `apply` refuses, found by the shared-table test and left as a
strict `xfail`. It was a promise the code did not keep.

Partly reversed by `2026-09-22-board-api-contract-revisions.md`: the thread's
state and the collection's order come back to the server as `state` and the
order of the list, because the fold is a state machine rather than a label and
ordering has to be the server's if the board is ever paged. Which buttons a
state calls for stays the front end's.

The PR dashboard broke the first rule until 2026-10-01: `your_move`,
`action.label`, `action.detail`, `pr.whose`, `since_you_last_acted` and
`dismiss` were sentences the manager assembled. Since the architecture
review's candidate 3 they are facts: `move` names which branch of the verb
holds, `action` carries `wants` and `blocker`, the status carries the checks,
reviewers and counts the detail was worded from, `pr.author` and
`undismiss_command` replace their sentences, and the front end's
`dashboardOf` words all of it. `move` and `group` stay a fold the server
makes, for the reason the thread's `state` does: the hub orders the wall by
group and tracks moves between polls, and a verb worked out apart from its
group could disagree with it. `notice` stays a sentence, because it carries
what GitHub said when it refused.

**The back end refuses; it does not enumerate.** There is no list of what a
thread will accept. The front end draws the buttons its own view of a state
calls for, and a request the domain will not take is answered 409 with the
domain's own sentence. The front end holds views-per-state, which implies a
state machine on the back end; where the implication is wrong, an error says
so.

**When the front end needs something the API does not have, look for the
missing entity.** Usually the information has no natural home yet and the
answer is a new endpoint, sometimes a new field on one that exists. The answer
is never a field shaped like what one screen wants to draw.

## The shape on the wire

**No envelope.** A comment is `Comment`, not `CommentDocument`. No `data`
member, no `type`, no `attributes` nesting. The cost is a normalisation step in
the front end, because WarpDrive's Polaris schemas expect the JSON:API shape.

**Four DTO tiers, named so nobody has to rediscover them.** A **read** DTO is
everything about one entity, from `GET /entity/{id}`. A **list** DTO is an
element of `GET /entities`. A **summary** DTO is what an entity looks like
embedded in another one. An **identity** DTO is a bare id, whose type the
consumer knows from where it sits.

**Exactly one summary per entity, carrying the union of what its parents need
and no more.** One summary per referencing parent would make the summary a
property of the consumer rather than of the entity, and that is how fields
shaped for a screen get back in.

**Two tiers turned out to have no users here.** `Conversation` has no separate
list DTO: the collection was made cheap by moving what costs subprocesses out
to `/proposals`, not by holding fields back, so nothing is left to withhold.
And once comments are embedded as summaries and every other cross-reference
moved onto an operation, no bare id is left to wrap. The tiers stay in the
vocabulary; they are just not all spent.

**Collections are bare arrays.** Nothing in this API is unbounded: conversations
are the threads on one pull request, comments are one thread's, people are one
PR's participants, operations are a couple of dozen over a thread's life. The
one read that can get large is a proposal's diff, and that is a single
resource, which pagination would not have helped.

## Work is an operation

**From the smallest to the largest.** Rejecting a thread and running an agent
on it for an hour are the same kind of thing: asked for, takes time, can be
refused, worth recording. Anything outstanding is visible on the thread it is
outstanding on.

**A thread keeps a history of them, not one.** An operation that carries its
own outcome is worth keeping; the first pass had at most one per thread, which
would have destroyed the previous outcome on every new decision.

**One at a time, and a second is 409.** Never a silent replacement. Today the
board is worse than loose about this: `write_intent` overwrites any existing
intent unconditionally and answers 201, while a second reply gets a 409. The
two halves of the same queue disagree. The API is right and the back end gets
fixed.

**Operations are thick.** They track the work, not just the ask, which is what
`running` is for. The alternative — the operation is the ask, and what the
agent then does is the fix's business — collapses the moment `Fix` becomes an
operation, because then the work has nowhere else to live.

**Created by a custom method on the collection.**
`POST /api/conversations/{key}/operations:reject`, in the manner of AIP-136.
The collection is the resource, so creating one is a POST to it; the verb stays
in the path so each ask documents its own body and its own refusals. Folding
all nine into one endpoint would have collapsed every refusal into a single
undifferentiated list, which matters more now that the permitted-decisions
table is gone and the reference documentation is the only place a front-end
author can learn what will be refused.

**`kind`, not `decision`.** Two of the three agent runs are the board's own: a
thread gets a run when it appears, and another when the pull request's head
moves under a proposal. Neither was decided by anyone, so the discriminator
cannot be named after a decision. `first` and `rebase` have no custom method;
you cannot POST them.

**`Fix` is a subclass of `Operation`.** `FixState` turned out to be several
operations' lifecycles flattened onto one record: `queued`/`running` and
`declined`/`failed` belong to an agent run, `in_session` to a session,
`landing`/`landed` to an approve — and `Fix.steps` is plainly the approve's
progress. Each now sits on the operation it belongs to.

**Spelled as named variants under `oneOf` with a discriminator, never
`allOf`.** Measured, not chosen: pydantic flattens model inheritance, emitting
one flat schema per variant plus `oneOf` and a `discriminator`, and no
`allOf` anywhere. Generating TypeScript from both spellings, the flat variants
give a discriminated union that narrows on `kind` and rejects unguarded access
to a variant field; the hand-written `allOf` version gives an
intersection-of-intersections whose hover text is unreadable. Since step 4
replaces this file with FastAPI's output, the only spellings worth choosing are
ones pydantic can produce.

**A proposal is the artifact, not the operation.** The operation is the work;
what an agent leaves behind — commits, a plan, a summary, a diffstat — is a
proposal. One per completed run, kept as a history, so a rework does not
overwrite what the run before it proposed. Fetched on its own rather than
embedded, because it sits below the fold on a card: the comment and its context
must be instant, the proposal can arrive late without moving anything.

**Errors are `reason` plus a field where the variant needs one.**
`decision_error` is the base `reason` on a refused operation.
`push_error` and `reply_error` are an approve that failed, and `steps` already
says where. `classification` stays its own field on a fix operation because it
is a domain value the front end may branch on, not prose. `reply_note` stays
its own field on an approve because it belongs to an operation that *applied* —
folding it into `reason` would make a success carry something that reads like a
failure everywhere else. No structured error codes: nothing consumes them and
inventing a vocabulary means guessing at failures nobody has seen.

Reversed by `2026-09-22-board-api-contract-revisions.md`: a code is required
everywhere the front end branches, because branching on a sentence an agent
wrote is not something a client can be held to.

## What the conversation keeps

`key`, `kind`, `state`, `github_resolved`, `github_resolved_at`, `created_at`,
`anchor`, `gist`, and its comments and operations as summaries.

**`state` is only what GitHub owns** — `open` and `removed`. `deferred`,
`rejected`, `resolved` and `waiting_on_reviewer` were operation outcomes stored
a second time on the thread, which is how a failed reject leaves `state: open`
beside `closing_into: rejected`. The board's verdict is read off the newest
applied operation.

**The whole operation list is embedded, not a chosen one.** Embedding "the
newest" or "the newest applied" would put the server back to folding, and
either choice hides something: a pending `unpark` masks the `defer` that
established the parked state, and the newest applied hides what is in flight.
A couple of dozen summaries is not worth a selection rule.

**Comments are embedded as summaries too** — `{id, author, created_at, review_state}`. Without them the board cannot sort itself, because ordering
folds over comment timestamps and `last_activity_at` is gone. `review_state` is
there because a thread opened with `CHANGES_REQUESTED` reads differently and
nothing else on the wire says so. No body excerpt: an excerpt has a length, and
a length is a presentation decision.

**`gist` stays, and loses its cap.** `GIST_MAX_CHARS = 60` truncated an
agent-written line server-side, which is the same presentation decision by
another route. The agent is told to write well under sixty characters; the front
end cuts it off if it has to.

**`html_url` stays.** It is derivable from the comment id and the thread kind,
so the rule condemns it — but what it encodes is GitHub's URL scheme, not this
domain's reasoning, and the rule is about not duplicating ours.

## What leaves

**Every fold.** `situation`, `awaiting_you`, `permitted_decisions`,
`reopened`, `decidable_at`, `last_activity_at`, `has_fix`, and
`Comment.can_delete`, which is `permitted_decisions` in miniature.

**Every duplicate.** `author` (the root comment's, copied), `role` (a
pull-request fact stamped on every thread — `pull_requests.py` derives it once
from `is_author`), and `closing_into`, which was the drain's note to itself
about which branch of `_settled` to take when a callback landed.

**Everything that belongs to an operation.** `wake_on` and `defer_note` are
field-for-field the body of a defer. `closing_comment` and `approved_comment`
are reply ids produced by a close and an approve. `pending_reply` is the words a
queued operation is waiting to post.

**Server-side rendering of anything.** The `delta`-rendered diff fragments, the
comment-in-context fragment and the expand-rows fragment all go. Diffs become
files, hunks and lines; the browser highlights them.

**`/context` and `/expand` were both asking "give me lines N–M of file F at
commit S".** That is a file at a revision, and it is one endpoint, `/api/files`.

**The accept and rework endpoints go.** Everything in them is copy or already
elsewhere. The one apparent exception, `AcceptView.commit_message`, is
fabricated: the landing runs `git commit -C <tip>`, so the commit carries the
agent's own message and the dialog was showing one git never writes.

**Colours and fonts are front-end concerns.** The palette this board served as
generated CSS goes, and so does enumerating the font files on disk. The app
shell still serves the font files, because a browser cannot read
`board_font_dir`, but which families to ask for is the front end's business.

**`/api/settings` goes with them.** All that was left was `agents_enabled`, and
nothing needs it.

**The colour tests go and do not come back.** About 700 lines across
`test_palette.py`, `test_board_palette.py`, `test_board_contrast.py`,
`test_git_diff_contrast.py`, `test_git_diff_highlighting.py` and
`test_syntax_theme.py`. The WCAG AA guarantee the contrast tests encoded is
dropped rather than rebuilt in the front end.

## What the back end has to be fixed to match

Found while checking the contract against the code. The API is right in each
case; the code is not.

**`reject` with a reply or a delete has never worked.** `_reply_outcome` and
`_delete_outcome` in `runner.py` match the verb against `Approve()`, `Resolve()`
and `Reply()` only; `Reject` is a separate dataclass and is not imported there,
so both fall through to `raise NotImplementedError`. Reproduced against the
repo's own fakes: a bare `Reject()` settles, `Reject(reply=...)` and
`Reject(delete_comment=True)` raise. `decide.py` catches per item and does not
clear the intent, so it retries every tick forever, and nothing sets
`decision_error`, so the card shows nothing at all. No test covers `Reject`
below `apply()`.

**A second decision silently replaces the first.** `write_intent` overwrites
unconditionally and answers 201. The optimistic-concurrency tokens do not catch
it: the front end never sends `seen_intent`, and `seen` is
`state|fix.state|fix.run.kind`, which does not change when an intent is queued
because queuing writes no record.

**An unreadable record does not 500.** `ConversationRecords.list` substitutes an
`UNREADABLE` stand-in rather than raising. The contract keeps the 500, because
`unreadable` is not in the thread vocabulary any more and nothing should have to
draw a row for it.

**The drain is not a separate process and not minutes late.** The board's HTTP
server is a daemon thread inside the agent-manager process, and the drain runs
once per dashboard tick, default one second. What is slow is the effects: `gh`
at 120s, git at 60s, a new worktree at 300s, an agent run capped at 3600s. The
first version of this document said "minutes later" and was wrong.

## Consequences we have accepted

**The design doc's build order no longer holds.** It has routes porting one at a
time with behaviour unchanged, and the contract generated before it is narrowed.
Neither survives.

**The front end's bill.** A normalisation layer, a markdown renderer and
sanitiser, a syntax highlighter, and the label, square, column, group, kicker,
note and ordering tables it now owns — plus the folds that used to arrive
precomputed: the thread's standing from its operations, its last activity from
its comments, whether it was reopened, and which buttons a state calls for.

**`standing_of` and `keyed_standing` collapse into one function**, and it stops
being shared over the wire. It still governs what `apply` accepts.

**Every card needs its operations to render**, so the operations list is
load-bearing for the board's cheapest read.

## Not settled

- **Markdown sanitisation moving to the browser.** It follows from no
  server-side rendering, but it is a security boundary, not a layering one.
- **What an operation id looks like.** The contract says an opaque string;
  nothing generates one yet.
- **Retention.** A couple of dozen operations per thread needs no pruning, but
  nothing enforces the couple of dozen.
- **`start-session` reaching a terminal state.** It is `applied` when the pane
  opens, because nothing watches an interactive session afterwards — `live_keys`
  lists only `build_claude_run` runs.
- **Whether `:cancel` is the right shape.** It replaces the `DELETE` on the old
  singleton and nothing has exercised it.
- **A reviewer's parked cards are offered decisions `apply` refuses** —
  `resolve` and `defer` on a card waiting on the author, `resolve` on a deferred
  one. Now a front-end bug rather than an API one, but the domain still has to
  refuse them.
- **Re-planning the build order.** Deliberately not started until the contract
  is right.
