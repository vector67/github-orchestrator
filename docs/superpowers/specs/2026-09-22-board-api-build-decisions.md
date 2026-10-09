# Board API build decisions

A running record of what was decided while building the board API, so the
reasoning sits somewhere a later reader will look rather than only in a commit
message. `2026-09-22-board-api-contract-revisions.md` governs the contract's
shape and still wins where the two disagree; this file records what the build
decided once the phases of `2026-09-22-board-api-contract-plan.md` started
turning that shape into code.

## Phase 0

**The trigger set gains the board's own transitions.** The first pass of the
transition table took the triggers to be every `OperationKind` plus a comment
arriving. Every one of those moves a thread into a working state and only
`stop` moves it out, so `queued` to `working`, `working` to `ready`, `rework`
to `ready`, `in-session` to `ready` and `landing` to `done` were transitions
the machine has to make and no row could name. Phase 1 generates its tests from
the table, so the five would have gone untested.

Four triggers join `comment`, none of them an `OperationKind`: `pick-up` for
the drain taking a `pending` operation to `running`, `settle-applied` and
`settle-refused` for it ending, and `requeue` for the board putting it back.
`ConversationState`'s description now says the machine has three sorts of
trigger — work asked for, an operation's own state moving, and a comment
arriving — and that only the first can be refused. The destinations come off
the operation the thread's state is named for, which is why `landing` needs a
qualifier: settling `applied` it is `done` if an approve was landing and
`ready` if a rebase was catching a proposal up, and settling `refused` it is
`ready` either way.

Making them `OperationKind` members was rejected. A kind is a sort of work
somebody can ask for; the front end draws buttons and cards off that enum, and
four members nobody can ask for would have to be filtered out of every one of
those lists. A single `settle` trigger qualified by the outcome was rejected
too: applied and refused part company at `landing`, and a qualifier that
appears on every settle row is a column pretending to be a parenthesis.

Working the destinations out exposed a hole the four triggers do not close.
Every operation is accepted with `202` and settles later, but the table moved
the thread when the request was accepted — `ready` plus `reply` was `waiting`
before GitHub had the reply — so the six states that are not working states
had operations in flight that no row followed. That is the hole the decision
below on verbs that touch GitHub closes.

**`reopened` leaves the enum and becomes a boolean.** `apply.py:295-303`
re-queues the fix whenever a comment arrives on the author's board, so a thread
is reopened and `queued` in the same tick. As one member of `ConversationState`
among twelve, the value was overwritten before it could ever be drawn, and the
author board's Ready for you heading has a clause — "a reopened `open` whose
fix is `queued` or `running`" — that could not be rewritten against the
contract at all.

`reopened` is now a boolean on `Conversation` and `ConversationState` has
eleven members. It is set when a comment arrives on a thread whose history
holds an applied `reply`, `approve`, `resolve` or `reject`, and cleared by the
next applied one of those four, which is the next time you speak. It is
independent of `state` and survives every transition until it is cleared. The
two facts are orthogonal — one is about the conversation, the other about the
work — and a thread can be both. In the table this retires the
`(you had already spoken)` and `(you had not)` qualifiers: the flag is set by
the rule rather than by an edge, and `comment` is a self-loop on every state
that accepts it but `waiting`, which the decision below on discharging a wait
takes to `ready`.

Keeping it in the enum and living with the loss was rejected: it costs the
redesign a heading it asked for, on the commonest card there is. A precedence
rule inside the enum — `reopened` outranks `queued` while both hold — was
rejected because it hides the other direction just as badly: a card showing a
reply waiting would say nothing about the agent running on it.

**Unreadable records are named rather than stated.** `group_of` synthesises an
`unreadable` conversation state today and draws a card saying so. The contract
deleted it and gave the per-thread read the `unreadable-record` refusal, but
said nothing about the collection, which declared `200`, `304` and a `500`. One
bad file on disk therefore either failed the whole board's read or vanished
from it.

`/api/conversations` now carries a top-level `unreadable` array of the keys
whose records would not parse, answers `200` with the threads it could read,
and no longer declares the `500`. `ConversationList` becomes an envelope for
the two arrays. What a client draws for an unreadable key is its own business,
and the per-thread read of one is still the `unreadable-record` refusal.

An `unreadable` member of `ConversationState` was rejected. A record that will
not parse has no kind, no comments and no operations, so every downstream table
would carry a row for a thing with nothing in it, and every consumer of a
`Conversation` would need a branch for the case where all of it is missing.
Failing the collection was rejected because one bad file must not take forty
good threads with it, and dropping the key silently was rejected because the
thread exists and the operator has no other way to find out that the board
cannot read it.

**The error vocabulary gains two codes and `Outstanding` names the ones it
carries.** The table needs `parked` fourteen times, for the seven work verbs
asked of a `waiting` or `deferred` thread, and `still-a-draft` fourteen times,
for the thread verbs asked of a draft. `ErrorCode` had only the converses,
`not-parked` and `not-a-draft`, so phase 1's generated test would not have
imported. Both are added, and the enum's description now says that the two
pairs exist because the table refuses in both directions.

`Outstanding`'s description claimed the code told two refusals apart when only
`operation-outstanding` existed. It now names what it can actually carry:
`operation-outstanding` when something is already in flight, and otherwise one
of the eleven verb-specific codes the table refuses with. Checked against the
table, that list is exactly `work-in-flight`, `proposal-exists`, `no-proposal`,
`nothing-in-flight`, `parked`, `not-parked`, `still-a-draft`, `not-a-draft`,
`already-enrolled`, `nothing-enrolled` and `already-closed`, all twelve used.

A second generic code for "the state forbids this verb" was rejected. It would
answer for every refusal that is not `operation-outstanding`, which is most of
the table, and a front end holding it would have to read the sentence to say
anything a person could act on — which is the thing the code vocabulary exists
to stop.

**`attempts` and `attempts_allowed` move onto the operation summary.** The
revisions document decided `attempts_allowed` belongs beside `attempts`, and it
landed on `FixOperation` only. The conversation embeds `OperationSummary`, and
the conversation collection is the only read that draws the redesign's queued
and working cards, which carry "attempt 2 of 3". Both are now nullable integers
on the summary, null on the kinds that do not attempt.

Keeping them off on caching grounds was rejected. The rule the summary is built
under is that fields changing every second stay on `/api/operations`, which is
why `last_action` and `progress` are not here. These two change at most once
per attempt, which is rarer than `steps_done`, so the collection's `304`
survives them.

**A verb that touches GitHub does not move the thread until it applies.** The
table moved the thread the moment an operation was accepted, and every
operation is accepted with `202` and settles later. `ready` plus `reply` was
`waiting` before GitHub had the reply, and `waiting` plus `settle-refused` was
marked cannot-arise, so a post that came back `reply-failed` or `comment-gone`
stranded the thread in `waiting` with no edge to bring it back. The same hole
sat under `resolve`, `reject` and `post-now`.

The run verbs never had it, because the state they move to on acceptance is
the operation being in flight: `first` goes to `queued` and `approve` goes to
`landing`, and the settle triggers carry the thread on from there. The other
four outward-facing verbs now work the same way. `reply`, `resolve`, `reject`
and
`post-now` are self-loops on acceptance, and the thread moves on
`settle-applied`, qualified by the kind that settled: an applied `reply` takes
`ready` to `waiting`, an applied `resolve` or `reject` takes it to `done`, an
applied `post-now` takes `draft` to `waiting`, and an applied `reply` takes
`deferred` to `waiting`, which is the unpark its old row was doing early.
`settle-refused` is a self-loop on all four states rather than cannot-arise,
so a refusal leaves the thread where it was and the card reads the operation's
`reason_code`. Because settles now arrive in `draft`, `ready`, `waiting` and
`deferred`, `pick-up` and `requeue` there become self-loops too: both columns
`—` means the event cannot arise, and in those four states it can.

Rolling the thread back on `settle-refused` with a kind qualifier was
rejected. It keeps the optimistic move, so it needs a rollback edge for every
one of them and a qualifier on every `settle-refused` row to say which way
back, and it still shows the operator a state the server never reached — the
card says `waiting`, then says `ready` again when the post fails, and the
thread was never parked on anybody.

What this costs is that nothing on `state` says a verb is in the air. The
operator clicks Resolve and the thread is still `ready`; the card has to draw
the outstanding operation off `operations[]` to show the click did anything.
That is recorded as a risk rather than answered with a second field.

**A comment discharges a wait.** `waiting` plus `comment` was a self-loop.
`waiting` means parked on the other party because you spoke last, so when they
speak the reason for the park is gone. Leaving the thread parked means every
work verb on it is refused `parked` until the operator unparks a thread that is
plainly their move again, which is a regression against `apply.py`'s `_reopen`,
which sets the thread open from any state when a comment arrives.

`waiting` plus `comment` is now `ready`. The `reopened` boolean is set by its
own rule as well, so the card is both ready and marked. `deferred` plus
`comment` stays a self-loop: a deferral is parked until its `WakeCondition`
rather than until the other party speaks, and moving it would leave `manual`
indistinguishable from `waiting`. `done` plus `comment` stays a self-loop,
which the revisions document's two clocks already argue for.

Leaving the park in place and relying on the `reopened` flag to pull the card
forward was rejected. The flag does put the card under Ready for you on both
boards, but `state` still says `waiting`, so every verb the operator reaches
for from that heading is refused behind a manual `unpark` — one click to undo
a park the comment had already undone, on the commonest card there is.

## Phase 1

**Two codes join the vocabulary: one for Claude switched off, one for the
refusals no client sees.** Giving every `Refused` in the domain an `ErrorCode`
left six sites with no honest code to take. `_rework` and `_start_session`
refuse with "Claude is disabled (claude_enabled=false)" and were given
`precondition-failed`, which in this contract means `If-Match` found the thread
had moved; a front end branching on it retries the request as a lost race, and
no number of retries turns Claude back on. The other five refuse things no
client ever asked for — an off-vocabulary confidence and a plan step index in
an agent's own report, a gist written against wording that had moved on, and
the runner giving up after eight passes — and had been squeezed into
`empty-body` where the body is not empty, `not-found` where the step is not a
resource, `precondition-failed` for a race no client ran, and `git-failed`
where no git command failed.

`claude-disabled` and `internal-refusal` join `ErrorCode` in the domain and in
the contract. `claude-disabled` is client-facing and actionable: the board can
say the agent runner is off and offer to turn it on, which is why it is a
member rather than a reused code. `internal-refusal` is the domain refusing for
a reason outside the client-facing vocabulary, and the contract's description
says exactly that — it reaches no client by any path that exists, a client that
somehow sees one should treat it as an unexpected fault rather than something
to act on, and it is not a general-purpose fallback, because a refusal a client
can reach gets a code of its own. No refusal sentence changes: the sentences
are the domain's own words, and what was wrong is the machine-readable code
beside them.

Leaving `precondition-failed` on a capability that is switched off was
rejected. The code names a conditional request that lost a race, so re-reading
and retrying is the front end's obvious response to it, and that is the one
response the condition can never clear. Splitting `Refused` into a
client-facing type and an internal one was rejected too. It is the honest
shape, and it would make the split a thing the type system checks rather than a
code a site has to pick, but it touches every refusal in `apply.py` and every
caller of one, which is a larger refactor than the problem justifies while one
refusal shape still serves.

## Phase 3

**A fifth code joins the vocabulary, for a request that does not parse.**
FastAPI answers a `RequestValidationError` before any route runs, and phase 3a
gave that answer `empty-body` because nothing else in `ErrorCode` came close.
The stretch shows on a query parameter: `/api/files?from_line=plenty` is a
request whose body is not empty and was never meant to be, and a front end
branching on `empty-body` would go looking for a body to fill in.

`malformed-request` joins `ErrorCode` in the domain and in the record, and the
validation handler takes it. It is the request itself not parsing, or a
parameter outside its declared type, as distinct from a request that parses and
the domain then refuses — which is the whole of the rest of the vocabulary. The
distinction is worth a member because the two call for different things from a
client: a malformed request is a bug in the client, and a refusal is the state
of the thread.

Reusing `not-found` for a bad path parameter was rejected. It is a real code
with a real meaning — the thread or the commit is not there — and a request
that never got as far as a lookup has not established that. Answering `422`
with FastAPI's own `detail` array was rejected in 3a and stays rejected: it is
a second error shape for a client to learn, and the whole point of `Errors` is
that there is one.

## Phase 4a

**A sixth code joins the vocabulary, for a gate that is not a refusal.**
`_rebase_gate` refused with `git-failed` while saying "the rebased fix reports
tests {tests}; approve again to land it anyway". Nothing had failed and no git
command had run: the rebase caught the proposal up, its tests did not pass,
and the domain wants the operator to say so twice. It clears itself, because
handing the thread back resets the run to `first` and the same request
repeated lands it. With `approve` an HTTP verb from this phase on, a front end
branching on `git-failed` would tell the operator that git broke.

`confirm-again` joins `ErrorCode` in the domain and in the record, and
`_handed_back` takes the code as an argument so the gate carries it while the
conflict hand-back beside it keeps `git-failed`, where a cherry-pick really
did fail. The sentence does not change.

Reusing `nothing-committed` or `no-proposal` was rejected: there is a proposal
and it committed something, and both codes tell a client to offer a rework.
Dropping the gate and landing on the first press was rejected because the
second press is the only place the operator is told the tests are red.

**Every verb writes an intent and the answer is `202`; `apply` is asked first
and its answer thrown away.** The board already takes decisions by writing an
intent to the records inbox that the drain picks up, and the contract already
models every operation as accepted now and settled later, so the ten custom
methods reuse that path rather than applying anything themselves. What they
add is the refusal the domain can give *now*: the route calls `apply` on the
loaded record, and a `Refused` becomes the HTTP answer — `409` with the code
the transition table names, or `400` for the two codes about the body rather
than the state. The outcome is otherwise discarded; nothing is saved.

Applying the command in the route and saving the result was rejected. It is a
second write mechanism beside the inbox, it performs GitHub and git effects
inside a request the browser is waiting on, and it would race the drain for
the record's lock. Letting the drain discover every refusal was rejected too:
the operator would see a card that said the click worked and a refusal a tick
later with nowhere to put it.

`:reply` writes to the replies inbox rather than the intents one, because that
is the queue the board has always posted an operator's own words through and
both drain the same way in `decide`.

**`Stop` is a command of its own, and `reject` narrows behind it.** There was
no `Stop`: halting a running agent was a side effect of `reject` and `defer`,
which is why `reject` was offered on a card with a run in flight and dropped
the run and closed the thread in one press. `Stop` now takes a thread in any
of the four in-flight fix states, issues `StopRun` and leaves the fix `failed`
with a reason, so the thread is `ready` again and nothing is posted to GitHub.
`reject` refuses `work-in-flight` while anything is in flight and `no-proposal`
where no run left one, which is what the transition table says and what the
revisions document's two tests ask for.

The old board's `ACTIONS` shed `reject` everywhere apply now refuses it, which
is every standing but `proposed`; the invariant test that every offered
decision is one `apply` takes is what forces the two to agree. Adding a Stop
button to the old board was rejected: it needs a label, a square, a title and
a weight in a read model phase 9 deletes, and the new API is where the verb
lives.

**The `202` carries the operation the command would be.** Nothing on the
record has moved when a verb is accepted, so the operation in the answer is
built from the command rather than read back: `pending`, stamped with the
board's clock, with the body's own fields on it. The five operation variants
the ledger lists against this phase — `StopOperation`, `CloseOperation`,
`DeferOperation`, `UnparkOperation`, `ReplyOperation` — exist for that answer.

Its `Location` resolves only once the drain has moved the fix, because the id
is still the synthesised `{key}.{kind}` the ledger describes. Writing an
operation history to the record was rejected here: it is the change phase 5 is
for, and the etag that a second write ought to move is the same one the
"a second decision silently replaces the first" defect turns on.

**The body of `:rework` is `BriefRequest`, not `Brief`.** The record uses one
schema for both, and the built `Brief` is what a `FixOperation` carries, where
all three fields are always there. As a request body that would make a client
send `pointed` and `include` to say a sentence. A second model with defaults
was cheaper than making the read's fields optional and weakening what a
response promises.

## Phase 4b

**`reject` settles a reply or a delete the way `resolve` does.** The domain
already had the whole path: `_reject` marks the thread `closing_into=REJECTED`
and asks for `PostReply` or `DeleteComment`, and `_closing_reply_posted` and
`ClosingCommentDeleted` settle into `closing_into` when it is set. What broke
it was one layer down. `_reply_outcome` and `_delete_outcome` in `runner.py`
match the verb that asked for the effect against `Approve`, `Resolve` and
`Reply` to decide which outcome command to hand back, `Reject` was not among
them, and both fell through to `NotImplementedError`. The drain logged it and
kept the intent, so a reject with words or a delete retried every tick and the
card said nothing. `Reject` now matches beside `Resolve` in all four places.

Fixing it exposed a second fault behind the first. `ClosingFailed` refuses
without clearing `closing_into`, so a reject whose reply GitHub refused left
the marker on the saved record, and the next `resolve` with a reply settled
into `rejected`. The refusal now clears it. `resolve` never set the marker, so
the fault was unreachable until `reject` could get that far.

A `Reject` of its own in the runner, with its own outcome commands, was
rejected: the two verbs differ only in where they settle, and the domain
already carries that on the record.

**A second verb while the first waits for the drain is refused
`operation-outstanding`.** Every verb is written to an inbox and answered
`202`, and the record does not move until the drain applies it, so the
thread's `etag` was the same before and after the first write and a second
request carrying it passed `If-Match` and overwrote the first intent in
silence. `_queued` now refuses `409 operation-outstanding` when the thread has
an intent or a reply waiting in either inbox. That is the state machine's
"one operation at a time is a precondition" read against the only record of a
pending operation there is until phase 5 stores them.

Answering `412` was rejected. `precondition-failed` tells a client to read
again and retry, and a re-read returns the same tag, because nothing the tag
covers has moved; a client following the code would loop. Folding the pending
intent into the `etag` was rejected for the same reason from the other side —
the conversation's `operations[]` does not draw the pending intent yet, so the
tag would move while the body it hashes did not. That belongs to phase 5,
where the operation is on the record.

A reply and a verb block each other. The old board drained a composer reply
and a decision on the same thread in the same tick, which is how
`test_a_reply_that_parks_a_ready_row_visibly_refuses_the_same_drains_resolve`
came to exist; the new API takes one at a time. `stop` is refused like the
rest while something waits, rather than withdrawing the waiting intent: the
drain takes an intent within a second, and withdrawing one is an operation
phase 5 can name. The check and the write do not share a lock, because the
drain holds the record's lock through GitHub calls that can take minutes and
a request must not wait on them, so two requests landing in the same instant
can still both pass; the drain then refuses whichever no longer fits.

**An unreadable record already answers `500` everywhere it is addressed; the
contract now says so.** `ConversationRecords.list` substituting an `UNREADABLE`
stand-in was the defect as first written, against the old board. Phase 0 moved
the collection onto the `unreadable` array, and phase 3's `_thread` loads
through `records.load`, which raises `UnreadableRecord`, which the app answers
`500 unreadable-record`. Probed with a corrupt file and with a record whose
fix state does not decode, every per-thread read and every verb answers that,
and `/operations`, `/people` and `/viewer` pass over the stand-in. What was
wrong was the generated document: `readConversation` declared the `500` and
the diff read declared one for git, and the other sixteen routes under
`/conversations/{key}` gave one they did not declare. `ONE_THREAD` declares `404` and `500` together and every such route
spreads it. The diff read already declared a `500` for git failing, and one
status carries one description, so `GIT_FAILED` became `DIFF_FAILED` and says
both.

The test that a verb on a corrupt record answers `500` and queues nothing was
born green; it pins what phase 3 built. The test that every per-thread route
declares the `500` went red on sixteen routes.

**`status_token` and the `seen` echo go from the old board as well as the new
one.** The new API never had them. The old board computed
`state|fix.state|fix.run.kind` in `standing.status_token`, put it on the panel
read model, drew it into `data-status`, sent it back as `seen` with every
decision, and refused the decision `409` when it differed. The removal takes
all of it: the function, the `PanelView` and `PanelState` fields, the route's
comparison and its `409`, the unused `seen_intent` beside it, the Ember
service's `seen` argument and `PanelActions`' `statusToken`, and the fixtures
that carried them. No Python test exercised the refusal.

The old board is left with no staleness check of its own. Keeping the token
until phase 9 was rejected: it is categorical, so it never caught the case the
etag exists for, and the plan puts its removal in this phase. `PanelState` and
`panel_state` have no caller outside their tests; they are left for phase 9
with the rest of the read model.

## Phase 5

**Operations are a history on the record, and their ids are stored.** An
operation's id was synthesised as `{key}.{kind}` from the record's one `Fix`,
so it changed when the fix's kind did, and a client holding the id of a
`first` run held nothing once the thread was sent back for rework.
`Conversation` now carries `operations`, oldest first, and
`domain/operations.py` writes it from `apply`. The run, session or landing the
fix is on is synced from the fix after every command; every other verb is
recorded when it is taken and settled by the outcome command that answers its
effect. A record written before the history existed adopts its fix as an
operation deterministically, so the id a read hands out for it is the id the
history gives it once something moves it, and nothing is written until
something does.

Ids come from two places. What the domain starts itself — a `first` run, a
`rebase`, an old-board verb with no id — is `{key}.{n}`, its place in the
history. What a client asks for through the API is `op_` and twelve hex digits,
minted by the route. Minting `{key}.{n}` in the route as well was rejected: the
poller can append a `first` between the request and the drain, and the number
the `202` named would then belong to it. A superseded run keeps only its
envelope, its attempts and the brief it was asked with; its plan, `onto`,
`conflict` and classification lived on the `Fix` and went with it. Moving those
onto each operation is the whole refactor of `Fix`, and was rejected as more
than the ids needed.

**A verb's operation exists from the moment it is asked.** The route writes the
id and the moment into the intent, on an `@operation` line ahead of the
decision, and the drain passes them to `apply` as `Asked`, so the operation the
history records is the one the `202` named. Every read draws what is waiting in
the inbox as a `pending` operation, so the thread's `etag` moves when a verb is
queued, `Location` resolves at once, and `/api/operations` lists it. `:reply`
goes through the intent inbox with a `reply` decision of its own rather than
the composer's replies inbox, which carries no id. A verb the drain then
refuses is recorded `refused` under that id, because the client was told it
exists; a verb nobody holds an id for leaves nothing when it is refused.
Writing the pending operation onto the record from the route was rejected: the
drain holds the record's lock through GitHub calls, which is the reason phase
4a queued verbs in the first place.

**A second verb while one waits is still refused `operation-outstanding`, and
`stop` with it.** Phase 4b refused it by looking in the inboxes and said phase
5 should reconsider once pending operations were first class. They are, and
the thread's tag now moves when the first verb is queued, so a client still
holding the old tag is answered `412` and re-reads; the `409` is for a client
that re-read and asks anyway. `stop` does not withdraw the waiting verb. The
route cannot take the lock the drain holds while it applies an intent, and the
drain keeps an intent it finds rewritten under it rather than clearing it, so
deleting the file mid-apply would answer `withdrawn` for a verb that went
ahead. The domain adds the same rule against its own history: a verb is
refused while another is still posting to GitHub or an approve is waiting for
the drain. A run in flight does not block, because the table takes `stop`,
`defer` and `reply` over one state by state.

**Git and GitHub saying no settles the operation; it refuses no request.**
`PickRefused`, `PushFailed`, `AnswerFailed`, `ClosingFailed`,
`ThreadResolveFailed`, `ThreadUnresolveFailed` and `ReplyFailed` returned
`Refused` with an `ErrorCode`, and the pick conflict's two hand-backs did the
same with `git-failed`. All of them are now `Accepted`, and the operation they
answer settles `refused` with a `ReasonCode`: `push-failed`, `reply-failed`
for the approve's answer, a reply and a closing reply, `github-rejected` for a
delete, a resolve and an unresolve, `conflict` for a hand-back, and
`git-failed` for a pick git would not make. `git-failed` joins `ReasonCode` in
the domain, the generated contract and the record. `ReasonCode` is now a domain
enum beside `ErrorCode`.

Keeping `Refused` and letting it carry either vocabulary was rejected. The
transition table says a settle trigger cannot be refused, and the runner read
`Refused` as the signal to stop driving, which is a second meaning the type
should not carry. Two consequences follow. `resume` stops when the landing is
no longer under way rather than when an outcome was refused. A composer reply
GitHub turned down is cleared rather than posted again on every drain, which
the old board did; retrying would append a refused reply to the history on
every tick while GitHub stayed down. Its words are on the operation.

**`approve` asks and `Land` drives.** The table puts a thread in `landing` the
moment an approve is taken and refuses a second approve there
`operation-outstanding`, but the drain drove a landing by applying `Approve`
once per step, so a second approve could not be told from the next step.
`Approve` now moves the fix to `landing` when it is taken; `Land`, a subclass,
is what `resume` applies for every step after, and for the first one when a
restart left a landing under way. The answer is the last step, so posting it
lands the fix in the same step. An approve over a push or reply that failed is
taken again as a retry from where the landing stopped. The old board loses
"Push it" on a landing in progress, as it lost Reject in phase 4a; a landing
that sticks there has `stop` on the new API and no button on the old one until
phase 8.

**A comment is a comment, and the run it used to queue is a `first`.**
`Reopen` re-queued the fix in the same tick, which is why six `comment` rows
and nineteen `first` and `rebase` rows could not be driven. `Reopen` is now the
comment alone — it moves `waiting` and a removed thread to `ready` and nothing
else — and the poller applies `First` after it on the author's board. The
table's refusals follow: no run over one in flight, a parked thread or a closed
one. So a comment on a deferred, resolved, rejected or landed thread marks it
`reopened` and leaves it where it is, where before it reopened the thread and
ran the agent again. That is what phase 0 decided. What it costs is recorded
as a risk in the state machine: a landed thread that gets a new comment has no
verb that brings it back. Keeping the old reopen-from-closed was rejected
because it contradicts the table phase 0 argued for; changing the table is the
user's call, not this phase's.

**Three narrowings the table asked for.** `resolve` is refused while a run is
queued or a session is open, as it was while one was running; a thread GitHub
has lost is exempt, because `removed` is `ready` whatever its fix says. The old
board's queued and session cards lose Resolve. A reply that posts on a deferred
thread parks it on the other party, because you spoke last. A session can
settle declined, so the operator can tell Claude in the session that there is
nothing to do.

**`Rebase` is the table's trigger, and nothing sends it yet.** A rebase run
starts today only when an approve's pick conflicts. `Rebase` is the command the
`rebase` rows need, sharing the pick conflict's `_rebased`; the head moving
under a proposal does not send one. It is recorded as owed rather than wired
to the poller.

**Four `requeue` rows could not arise and now say so.** Driving the table found
nothing that puts back a pending run, a session or a verb posting to GitHub, so
`queued`, `in-session`, `waiting` and `deferred` plus `requeue` became `—` in
both columns. The harness drives each settle, requeue and pick-up row with the
command production sends for what is outstanding in that state, and counts
`Deferred` as taken for `requeue`, because putting work back for the next pass
is what `Deferred` means. The pick-up of a verb in `ready`, `waiting`,
`deferred`, `in-session` and `landing` is the drain applying a queued reply
under its asked id.

**A proposal names what produced it and when, and its id is that run's.**
`Proposal.operation` is the run or session that settled `applied` with the
fix's proposal, `created_at` is when it settled, and the id is that operation's
id with `.proposal` on the end, so a client holding an older proposal is told
it is gone rather than handed the new one. `SessionOperation.steer` and
`ApproveOperation.delete_comment` are what was asked, now that the history
keeps it, and the summary's `attempts` is null on kinds that do not attempt.

**The session's settling CLI already existed.** `thread ready`, which the
session prompt already hands Claude, reports through the same path as an agent
run. Nothing was built. The test drives `application.report`, which the command
calls, against fakes.

**The done criterion was born green.** An agent at work on one thread moves
`/api/operations` on every tick while a conditional read of the list stays
`304`. The shape phase 3 gave the summary already carried the right fields.
The test was checked by leaking a changing value onto the summary, which it
caught on the first tick. The session test and three write tests on the `202`
id — readable at once, recorded under the same id, moving the tag — were also
green on their first run, because the code was written before them.

## Phase 6

**`unpark` takes any `done` thread, and a landed one goes to `queued`.** Phase
5 split the comment from the run it used to queue, so a comment on a landed
thread marked it `reopened` and left it `done`, and `unpark` refused it
`not-parked` because a landing was never a park. Nothing brought the thread
back. `unpark` now accepts a `done` thread however it closed. A landed one is
treated as a rejected one is: the fix is reset, the worktree is cut again and
a `first` run is queued, because the landing dropped the worktree as a reject
does and a comment after a landing is most often asking for another fix. The
table's `done` plus `unpark (closed by approve)` row is `queued`.

Sending it to `ready` was rejected. A landed fix has no honest `ready` fix
state to fall back to: `absent` is `ready` but refuses `retry`, `rework` and
`start-session`, which the table allows from `ready`, and `declined` or
`failed` would claim a run said something it did not. `queued` costs one
`stop` when the comment wanted only a word, and `stop` leaves the thread
`ready` with a withdrawn run, which every `ready` row accepts. A thread GitHub
resolved after it landed keeps the behaviour its test pins, `open` with the fix
`landed`, so it still reads `done` after one `unpark`, and a second one
queues it.

**A draft is a record with three states of its own and kind `draft`.** The
record's `conversation_state` gains `draft`, `enrolled` and `discarded`, and
`comment_type` takes `draft`, which `ThreadKind` already had. `state_of` maps
the first two to the states of the same name and `discarded` to `done`. A
discarded draft has a record state of its own rather than borrowing
`resolved`, because `unpark` has to tell the two apart to know that one goes
back to `draft` and the other to `ready`, and borrowing it would have made
every reader of `resolved` ask which kind of thread it was looking at. The fix
of a draft is `absent`, as on a reviewer's thread, because no agent runs on
it.

Folding the draft states out of the operation history rather than a stored
state was rejected. Every other state is read off the record's state and fix,
and one function reading two kinds of source for one answer is the thing phase
1 collapsed.

**A thread verb on a draft is refused by one guard that reads the table.** The
table refuses the thirteen thread verbs on `draft` and `enrolled` with four
different codes (`still-a-draft`, `no-proposal`, `nothing-in-flight`,
`not-parked`), and `comment` with `not-found`. `apply` asks a dictionary of
command type to code before anything else, so the handlers never see a draft.
Teaching each of the thirteen handlers about drafts was rejected: it is
thirteen edits that each have to land on the table's exact code, where one
table in code sits beside the table in the document. A discarded draft needed
no guard: adding `discarded` to the parked and closed tuples was enough for
every `done` row to hold for it, and a comment reaching one, which cannot
happen because GitHub has no thread for it, leaves it where it is.

**`create-draft` writes the record; every per-thread draft verb goes through
the inbox.** The per-thread verbs reuse `_queued` exactly as phase 4a's verbs
do, so the `202`, the pending operation, the moving etag and `Location` are
unchanged. `:edit-draft` carries its anchor on the intent as JSON, the way
`:rework` carries its brief. `create-draft` has no thread to queue against,
nothing can hold the new key's lock, and nothing waits on the drain, so the
route mints the key, writes the record under the lock and answers `202` with
the `create-draft` operation already `applied`. The frozen contract says the
answer is "queued"; the generated one says it has applied. An inbox entry under
a key no record has yet was rejected: the drain loads the record first and
clears an intent it finds none for.

**Consecutive edits collapse onto the newest.** When an `edit-draft` is taken
and the newest operation is already an `edit-draft`, the older entry is
replaced by the newer, which keeps the newer's id. The older id then answers
`404`. Keeping the first edit's id and routing each later edit under it was
rejected: the route would have to predict an id the domain decides, and a
refusal from the drain would overwrite the entry of the edit that did apply.

**The anchor is checked in the route, after the domain says yes and before
anything is queued.** `:enrol` and `:post-now` read the pull request's diff
from the merge base of the base branch and the head to the head, with the
parser the proposal diff already uses, and accept an anchor only when every
line from `start_line` to `line` is a line of one hunk on the side it names:
old numbers for `LEFT`, new ones for `RIGHT`, context lines included, as
GitHub allows. A thread that is not a draft is refused by the domain first, so
no diff is read for it. When git cannot produce the diff the answer is `500 git-failed`, because saying the anchor is wrong would be a guess. The `Git`
port gains `pr_base`, over the resolver the context diff already uses.
Checking in the domain was rejected because the domain has no git, and
checking at the drain because the operator would learn a tick late that the
click did nothing.

**`Anchor.side` is stored.** The record gains `side`. A polled thread takes it
from the `diffSide` the GraphQL query already fetched, on its first poll and
on every refresh; a draft takes it from the composer, `RIGHT` by default.
`post-now` sends `side`, and `start_line` with `start_side` for a range, which
`docs/github/rest/pulls/comments.md` names as what a multi-line comment needs.
A thread polled before this keeps a null side until a refresh brings the
thread back in step.

**A draft's key is `draft_` and sixteen hex digits.** GitHub keys the three
thread kinds by the node ids of a `PullRequestReviewThread`, an `IssueComment`
and a `PullRequestReview`, which begin `PRRT_`, `IC_` and `PRR_`; ids minted
before those prefixes are base64, which has no underscore. A lower-case prefix
the board owns can be neither, and the minting retries if a record already
holds the key it drew. A ULID was rejected as a dependency for a property that
sixty-four random bits already have.

**A posted draft is a review thread parked on the other party.** When GitHub
takes the comment, the thread's kind becomes `review`, its node id is the
thread GitHub reports for the comment, its one comment is GitHub's copy, and
its state is `waiting`, because you spoke last. The posted comment's id joins
`panel_reply_ids`, which puts it in the set of comments the poller counts as
the board's own, so the next poll does not read the board's own post as
activity on the thread. The head the comment is posted against is read when
the drain posts it, not when it was asked. A GitHub refusal, or a pull request
with no head, settles the `post-now` refused `github-rejected` and leaves the
draft as it was.

**`draft` plus `requeue` cannot arise.** The only work outstanding on a draft
is a `post-now`, and it settles one way or the other in the pass that takes it.
The row is `—` in both columns, the same finding phase 5 made for `waiting`
and `deferred`.

**The `create-draft` and `send-review` rows are routing, not the domain.**
Both are custom methods on the pull request's collection, so asked of a
thread they are a path that does not exist, and no command applied to a
conversation could ever drive them. `NOT_YET_DRIVEN` names them as answered by
routing, and `test_contract_drafts` drives the `404` for both. Leaving them
attributed to a phase was rejected, because no phase will discharge them.
`test_a_declared_row_the_domain_could_drive_still_parts_from_the_table` has no
rows left to check and is skipped as an empty parameter set.

**The review run hands its findings back through `thread draft`.** The run
that fires on `review-requested` is a fire-and-forget Claude process that
nothing reads the end of, so a findings file parsed afterwards would need a
reader that does not exist. It already reports the way thread runs do: a CLI
verb, whose flags join the report contract in `adapters/prompts.py` and are
checked against the parser. `thread draft --path --line [--start-line] [--side] --body-file` opens a draft under a minted key and prints it. Both
review prompts now ask for one call per finding that belongs on a line, and
keep `agent-changes.md` for what does not. Whether the model follows the
prompt is not something a test here can show.

## Phase 7

**The drain sends the review; the route only asks for it.** `:send-review`
checks the body and writes the review as a pending operation, and the drain
sends it after it has taken every thread's intent, so a withdraw queued
before the send is taken first. Sending from the route was rejected. Every
other GitHub call is the drain's, the contract answers `202` for "queued",
and a click would otherwise hold six records' locks from the HTTP thread for
as long as GitHub takes. The drain holds each draft's lock from the moment it
reads it until its `posted` is written, so nothing moves a draft between
going out and being marked gone. The drafts it carries are the ones enrolled
when it sends, in the order the records list them; the pending operation's
`drafts` names the ones enrolled when it was asked. Freezing the set at the
request was rejected for the same withdraw.

**A review is a record of its own, not an entry on a thread.** It is the
pull request's operation, so it lives in its own `{id}.review` file beside
the threads, and the pending file is the inbox: the route writes it, the
drain rewrites it settled. `.review` rather than `.json` because the records
port reads every `.json` there as a thread. One file of every review was
rejected, because each settle would then need the read-modify-write lock the
route takes. Writing the review onto each draft's history was rejected: a
rejection would have to touch every draft the contract says it leaves alone,
and an approval with no drafts would have nowhere to live. `/operations`
lists a pending review after the threads' work.

**The frozen contract gave the review a `Location` and nowhere to read it.**
`GET /operations/{operation_id}` answers a review by its id, tagged like
every other read, and `404` for any other id. It is the one path the
generated contract has that the frozen one does not.

**One review at a time.** A second `:send-review` while one is pending is
`409 review-in-flight`, checked and written under a lock file of its own, so
two clicks cannot both find nothing pending and both queue a review.

**`body` is required for `REQUEST_CHANGES` and `COMMENT`, and nothing
enrolled is not refused.** A missing or blank body on either is `400 empty-body` before anything is written, and longer than GitHub takes is
`413`. The frozen contract refuses "when no draft is enrolled and the verdict
needs comments", but GitHub needs comments for no verdict: an approval on its
own is the commonest review there is, and a summary alone is a review
GitHub takes. `nothing-enrolled` stays the code for `posted` on a draft that
never joined the review.

**GitHub saying no settles the review and touches no draft.** A rejection,
or a pull request with no head, settles the review `refused` with
`github-rejected` and the words GitHub or `gh` gave, as `post-now` does, and
every draft is written back exactly as it was read. A drain that dies
between GitHub taking the review and the review being settled leaves it
pending, and the next drain sends it again; that is the reply's risk too,
and it is recorded as owed rather than built around.

**`posted` is a domain command, and the table already said what it does.**
`Posted` carries the comment, the node id and the review's id. It is refused
by the same guard as the other draft verbs with `ENROLLED` as the state it
wants, which answers the table's eleven rows as written: `nothing-enrolled`
on a draft, `already-closed` on `done`, `not-a-draft` everywhere else, and
`waiting` from `enrolled`. What it does to the thread is what an applied
`post-now` does. `Operation` gains `review` and `github_node_id` for it, and
the record stores both. `NOT_YET_DRIVEN` is down to the `create-draft` and
`send-review` routing rows.

**Each draft's comment is found by path and body.** GitHub's answer to a
review names the review and none of its comments, so the adapter lists the
review's comments and hands each draft the first unclaimed one with its path
and body, in the order sent, then looks the threads up once. Matching by
line was rejected: GitHub's own example of that listing has `line` null. The
GraphQL `addPullRequestReview` mutation was rejected because the plan names
the REST call and whether its comments reach their thread is not something
this build can check without calling GitHub.

**A posted draft GitHub had not listed yet is found by its root comment.**
Phase 6 looked for a posted comment's thread straight after the post and
left the node id null when it missed, and the poller then opened a second
record for the thread when someone replied on it. The poller now matches a
thread to a record with no node id whose root comment is the thread's root
comment and is the board's own post, and fills the node id in on that pass.
Both `post-now` and `send-review` are covered, because both leave the posted
comment's id as the record's root and in `panel_reply_ids`. Taking the node
id from the post's answer was rejected: REST names the comment's node id,
not the thread's. Retrying the lookup was rejected: it narrows the race
without closing it and costs a paginated GraphQL read per try. The
`panel_reply_ids` condition is what keeps a record that merely lacks a node
id from being taken for a posted draft.

**A posted draft is answered, resolved and reopened on GitHub's thread.** The
adapter named the thread by the record's key, which on a posted draft is the
board's `draft_` key. Reply, resolve and unresolve now name
`github_node_id`, and the key only where there is none.

## Phase 8a

**The prefix moved first, and the old JSON:API left `/api` rather than
standing beside it.** With the new API at `/api`, its catch-all answers every
path under the prefix it does not serve, so the old board's
`/api/conversations`, `/api/conversations/{key}`, `/diff`, `/context`,
`/expand`, `/decisions`, `/replies` and `/api/board` were unreachable the
moment the prefix moved, not only the two that collide by name. Nothing needs
any of them by the end of 8a, so their dispatch in `routes.py` and the old
board's POST path in `app.py` are deleted rather than moved to a second
prefix. The serialisers behind them (`api/conversations.py`, `RowView`,
`panel_view`, `render.py`'s fragments) are left in place, unreachable, for
phase 9's list. Moving the old routes aside under `/old-api` was rejected:
it keeps dead routes alive with tests that pin nothing anybody calls.

**The stylesheets moved out of the API.** `/api/palette.css` and
`/api/fonts.css` are page assets the old board happened to serve under `/api`;
the new catch-all swallowed them. They are `/palette.css` and `/fonts.css`
now, served by the same handler as the built app. Registering them as hidden
routes on the API's router was rejected: they are not the API.

**The loopback guard moved onto the new writes.** The old POST path refused a
request whose `Host` was not the board's own and one sent by another site's
page, and refused a body by its declared length before reading it. The new
custom methods had neither, so deleting the old path would have left the
only writes unguarded: a page in another tab could have approved a fix. A
middleware on every `POST` now does all three before the body is read, and
answers in the `Errors` shape. `foreign-origin` joins `ErrorCode` in the
domain and the record for the refusal; the length refusals reuse
`malformed-request` and `body-too-long`. A router dependency was rejected
because FastAPI reads the body before it runs one. Two of the length tests
were born green — the new route already answered a missing `If-Match` `400`
— and are kept because they pin the refusal the guard gives.

**Opening a card is what checks GitHub still has its comment.** The old
panel read ran `PRESENCE.check_later`; the new board opens a card by reading
its comments, so the check moved to `listComments`. Putting it on
`readConversation` was rejected because the front end never reads one thread
on its own: it has every thread from the collection.

**A classification the agent wrote in the CLI's words read as a `500`.** The
agent reports `conversational`, `ambiguous` or `risky`; the contract's
`Classification` has none of the first two, so `/operations` on any thread an
agent declined as conversational failed to serialise. Found by reading every
seeded preview thread through the reads its card makes. `projection` now maps
`conversational` to `not-a-change` and `ambiguous` to `unclear`, and drops a
word it does not know rather than failing the read.

**The front end left WarpDrive.** The store's JSON:API cache has nothing to
cache in a payload that is not JSON:API, and its request path turns a `304`
into an error. `data/http.ts` is a thin `fetch` with `If-None-Match` on reads
and `If-Match` on writes, and turns an `Errors` body into a `Refusal` with its
code. The normalisation is plain functions over the contract's types:
`data/thread.ts` reads the facts the table's qualifiers need off
`operations[]` (a proposal waiting, how a thread closed, what is outstanding,
and a `phase` that names the old standings the labels still need);
`data/groups.ts`, `data/rows.ts`, `data/verbs.ts` and `data/panel.ts` build
what the components draw. The components kept their shapes where they could,
so most of their tests only changed their fixtures. The WarpDrive packages
stay in `package.json` for phase 9; removing them means a lockfile change.

**Grouping reads `reopened` first and `state` second, and keeps the
collection's order.** Headings, their order, the reviewer's words for them,
the header counts, the five board columns and the squares are the front
end's. Drafts stand under Your review with no buttons until 8b. An unreadable
key is drawn as a row at the foot of Ready for you saying its record could
not be read, and opening it says so; it is not a `Conversation`, so it has no
state to group by.

**Two clocks.** `/api/operations` is read every second and the collection
every five, both conditionally. When the fast poll's set of operations or
their states changes — something was picked up or settled — the collection is
read at once, so a settled run does not wait five seconds to leave Agent
working. A plan ticking over changes only the fast poll. The route tree is no
longer refreshed: the routes load once and the views read a service. Five
seconds for the list was chosen rather than two because the fast poll already
triggers the list whenever work moves.

**A card's comments, operations and proposals are read when it opens and
again only when its `etag` moves.** The open card is re-asked on every list
poll, so a card whose reads failed recovers; one whose tag has not moved costs
nothing.

**Buttons come from the state and the table's qualifiers, drawn in
`data/verbs.ts`.** Stop is offered on `queued`, `working`, `in-session`,
`rework` and `landing`; Reject only where a proposal is waiting. A thread
outside the working states with anything pending or running offers nothing,
because a verb waiting for the drain refuses every other `operation- outstanding`, and its row and card say what is on its way instead. Rework and
Open a session are drawn whether or not Claude is enabled: the new API does
not say, and the `409 claude-disabled` is toasted in words. The reviewer's
board never draws an agent verb.

**Every verb sends the thread's `etag` as `If-Match`.** A `412` is toasted
and the collection read again, so the buttons redraw from what the thread has
become; nothing is retried. A `409` is toasted with a sentence of the front
end's for the codes an operator can act on (`operation-outstanding`,
`claude-disabled`, `precondition-failed`) and the domain's own sentence for the
rest, which is how `confirm-again` reaches the operator. A success reads the
collection at once so the pending operation shows.

**Bodies are plain text until 8b.** The new payload carries markdown, not
the old server-rendered HTML, so comments are drawn as escaped text with
`pre-wrap`. The diff is drawn from `/proposals/{id}/diff`'s hunks and the
comment's code from `/files`, both unhighlighted; the old delta HTML routes
are gone. The accept dialog lost its commit message: the commit carries the
agent's own message, which the contract does not ship, and composing one the
board will not use would be a lie. The not-fixed opener is a front-end
constant; the setting behind it is not on the API.

**Tests.** The acceptance suite runs against a fake of the new API
(`tests/helpers/fake-board.ts`) that answers `ETag`/`304` and records every
write with its `If-Match`. The unit tests for the data modules were written
first and went red on the missing modules. The acceptance tests were
rewritten after the services and components they drive, so most were born
green; the ones that went red on their first run found the fire-and-forget
reads the test waiters could not see, which now go through `waitForPromise`.

## Phase 8b

**Bodies are markdown parsed with raw HTML off, then sanitised, then put in
the page as nodes.** A comment body is written by anyone who can comment on
the pull request, and the board is a page on loopback whose every write is a
`POST` a script in that page could make with the operator's own `Origin`: a
script that runs in a body can approve a fix, post as the operator or send a
review. So the threat is a hostile body, and the thing to prevent is any
script, event handler, navigation to a `javascript:` or `data:` address, or
element that loads something on its own, reaching the document. The board
has three layers against it, and each one is tested alone. `markdown-it` runs
with `html: false`, so a tag in a body is text, and with `validateLink` taking
`http:` and `https:` only, so a link to anything else is never made. Its
output goes through a DOMPurify instance of the board's own, allowlisting the
tags the old pandoc sanitiser allowed plus `span` and `s`, the attributes
`href`, `class` and `start`, `http(s)` addresses only, and class names that
are highlight.js tokens or `language-*`; a hook sets `target="_blank"` and
`rel="noopener noreferrer"` on every link. DOMPurify returns a
`DocumentFragment`, and the `drawn` modifier appends it, so the sanitised tree
is never serialised to a string and parsed again, which is where mutation XSS
lives. `frontend/tests/unit/markdown-test.ts` runs thirty-two hostile bodies
(script, event attributes on disallowed and allowed tags, `javascript:` links
in capitals, split by a tab, by an entity and entity-encoded, `vbscript:`,
`data:`, autolinks, reference links, SVG and MathML payloads, three mXSS
nestings, iframes, `srcdoc`, forms, `meta` refresh, `base`, `link`, `style`,
`details ontoggle`, markup in a link's text and title, and fence info strings
carrying attributes or the board's own class names) through the whole
pipeline and again through the sanitiser alone, and asserts every element,
attribute, address and class that comes out is on the allowlist. A last test
puts all of them into the live document, fires `mouseover` on every element,
waits, and checks that nothing ran. Made to render without the sanitiser and
with every link valid, thirty of the forty tests went red, the live one
among them.

`marked` was rejected because it has no switch that turns raw HTML off, and
its own sanitiser was removed, so the parser would pass HTML through and the
sanitiser would be the only layer. Keeping the old hand-written allowlist in
the browser was rejected: `HTMLParser` was safe server-side because its
output was never re-parsed with namespaces, and a browser version has to
reason about SVG and MathML, which is what DOMPurify exists to do. Keeping
pandoc on the server was rejected because the contract ships markdown and
the plan moves rendering to the browser.

**An image is drawn as a link to it.** The old allowlist dropped `img`
entirely, so an image was its alt text. Fetching one would send the viewer's
address and the moment they opened the card to whoever wrote the comment,
with none of the camo proxy GitHub puts in front of its own pages. The link
keeps what the image was without fetching it. A `javascript:` or `data:`
image is its alt text.

**A single line break in a body is a break**, as GitHub draws a comment, and
the `pre-wrap` that 8a's plain-text bodies needed is gone. The old pandoc
`gfm` read them as soft breaks, so a body wrapped by hand now looks as it
does on GitHub rather than as it did on the old board.

**Syntax is highlighted line by line with highlight.js**, in the diff, the
code a comment sits in, and a fenced block in a body whose info string names
a language it knows. The language comes from the file's extension through
`hljs.getLanguage`; an unknown one draws plain text. Its HTML goes through a
second DOMPurify instance that allows only `span` with token classes, and in
as nodes by the same modifier. Highlighting whole files to carry a string
across lines was rejected: `/files` serves a window, not a file. Shiki was
rejected for its size and its WebAssembly; Prism for having no bundle of the
common languages. A `suggestion` fence is a plain code block, as it was.

**The syntax colours are the palette's.** Seven `syntax_*` fields join
`Palette` and the served variables, from GitHub's light and dark schemes,
and each is measured against the diff's ground, an added and a removed line,
the commented range and a comment's page. Two of GitHub's own failed AA
there and were moved: the light keyword to `#b31d28` from `#cf222e`, which
was 4.06:1 on a removed line, and the dark comment to `#9ea7b3` from
`#8b949e`, 4.28:1 on the commented range.

**The composer's working copy lives in a service, keyed by the thread.** It
survives the list being read again every five seconds and the operator
walking to another card and back. Save is a button that sends `edit-draft`
with the whole draft; Add to review and Post now are disabled while the copy
differs from what was saved, because they act on the saved draft and would
otherwise send one the operator is no longer looking at. Saving on every
keystroke was rejected: each is an operation behind the drain, the etag
moves under the next one and the operator meets a `412` in the middle of a
word. Saving and then enrolling in one click was rejected because the enrol
has to wait for the drain to apply the edit, and nothing tells the page when.

**The code beside the composer redraws on every change to the anchor**,
without a pause: the board is on loopback, and the code component already
drops an answer to a question it is no longer asking. A draft on the old
side draws nothing and says why. The contract gives the pull request's head
and no base, so drawing the head's lines for a `LEFT` anchor would show the
wrong code, and adding the merge base to `PullRequest` is a contract change
this phase did not need.

**A draft's buttons are drawn from its state**, on both boards, since
nothing refuses a draft on the author's: `draft` offers Add to review, Post
now and Discard; `enrolled` offers Leave out of review; a discarded draft
offers Bring back. Post now asks first, because it is public and cannot be
taken back; Discard does not, because Bring back undoes it. A draft with a
verb on its way offers nothing and its composer is locked, saying so, and a
Post now GitHub turned down leaves its words on the card.

**New draft is a route, `/conversations/new-draft`,** reached from a link in
the head on both boards. `create-draft` has no thread, so it goes without
`If-Match`, and the composer lands on the new card when the list has it.

**Send review sits in the head on both boards, with `S` as its key.** It
counts the enrolled drafts. The modal takes a verdict, Comment first, and a
summary it will not send empty for Comment or Request changes; an approval
with no summary sends `null`. It lists the enrolled drafts with where they
sit and what they say, reading each one's comments when it opens. Leave out
is `withdraw-from-review`. Edit opens the draft's card and leaves it in the
review, because `edit-draft` takes an enrolled draft (the PR diff tab spec,
item 7). A line under the list counts the
drafts not added and the operator's threads the author has not answered.

**The modal follows the review at its `Location` on the fast tick.** The
`202` names `/api/operations/{id}`, and the poll's one-second clock reads it
while it is pending or running. Applied closes the modal, toasts and reads
the list again; refused keeps it open with GitHub's words and the note that
every draft is still in it, and Send works again. A `409 review-in-flight`
or a `400 empty-body` is said in the modal rather than toasted. A clock of
its own was rejected because the fast tick exists for exactly this.

**Security review.** A separate review of 8b found nothing critical or
high, and six things worth fixing, all fixed. Reads answered any `Host`, so
a page on a name its owner points at 127.0.0.1, on a port from the board's
predictable range, could read every thread as its own origin: the `Host`
check now runs on every method, before the write-only `Origin` and
`Sec-Fetch-Site` checks, and covers the page, its assets and the
stylesheets, which all go through the same app. Nothing forbade framing:
every answer now carries `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` and a policy of `default-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`. The
built page needs nothing looser: the production build turns the source
page's inline module script into `/assets/main-*.js`, nothing sets an
inline style, and every script and stylesheet it names is the board's own,
which a test reads off the built page when `make build_frontend` has built
one. The class allowlist was wider than the renderer needs: a token class
is now kept only on a `span`, a scope suffix like `function_` only beside
one, and `language-*` only on `code` and only for a language highlight.js
knows. Input over 64 KB is drawn as plain words rather than highlighted.
The hostile tests gained id and name clobbering, protocol-relative and
slashless links, quote breakouts, a raw `target` and `rel`, classes
smuggled through the sanitiser alone, every payload through the token
sanitiser alone, and `focus`, `click` and `animationstart` beside
`mouseover` in the live test. The narrowing and the size cap went red
first; the new payloads were born green against the sanitiser as it was.

**`markdown.py` is unreachable from the running board.** Importing the
server and the API app loads neither it, `render.py`, nor
`api/conversations.py`; only their tests do. It stays for phase 9.

**No live server was run.** The preview server's ports read the pull
request through `gh`, and its drain posts, so the checks are the ember suite
against the fake API.

**Tests.** The markdown and highlight unit tests went red on the missing
modules, and the mutation above shows the hostile ones can fail. The
sanitiser-alone tests were born green: they were written after the
sanitiser, and went red only on the missing export. Born green as well: the
code context drawing markup in code as words, the author board's discarded
draft offering Bring back, a draft with a verb pending offering nothing, the
draft verbs' request bodies, the composer's code at the saved anchor, and
enrol under the thread's tag, each because the code under them was there
first.

## Phase 9

**`standing_of` and `keyed_standing` collapse into `state_of`, and
`standing.py` keeps its name.** What is left in it is `ConversationState`,
`ErrorCode`, `ReasonCode`, `state_of` and `is_yours`; the `Standing` enum,
`group_of`, `square_of`, `column_of`, `raised_by`, `ACTIONS`,
`REVIEWER_ACTIONS` and `allowed_decisions` went with the read model they
served. Renaming the module to `state.py` was rejected here: it is
twenty-five files touched for a name, and nothing about the change needs it.

**`is_yours` is `state_of` plus the reopened flag.** The drain still asks it
whether a reply posted from the board parks the thread on the other party. It
answered from `group_of`, whose Ready for you took in a reopened thread whose
first run was queued or running; `state_of` calls that `queued` or `working`.
It is now `ready`, or reopened and `queued` or `working`, which gives the
same answer on every open thread `test_decide`'s parking table walks. It
differs from `group_of` only where `ReplyPosted` ignores it: a thread that is
not open, and an unreadable record, which `records.load` never hands the
drain.

**`can_delete` moved into `app.py`**, beside the one caller that decides
whether a `resolve` or `reject` deletes the comment, and its tests moved into
`test_contract_writes.py`. **`sanitize_html` moved into `markdown_preview.py`**,
the only thing left that renders markdown on the server, and `pandoc` stays a
prerequisite for that preview alone.

**The server-side diff renderer went with the fragments that drew it.** Since
8b the browser highlights the diff it reads from `/proposals/{id}/diff`, so
nothing ran delta. `git/diff.py` keeps `raw_diff`, `DiffSource`, `is_sha`,
`is_branch_name`, `enclosing_function`, `diff_range` and `_resolve_pr_base`,
which the new reads use, and loses the delta pipeline, its row memo, the
folds and the context window. With it went `ansi_html.py`, the palette's
`mode`, `syntax_theme`, `of` and `THEMES`, the bat-built syntax theme in
`assets/themes`, `make install_syntax_theme` and its uninstall, and `delta` and
`bat` from the README's prerequisites; `node` and `npm` joined them, which
building the front end already needed. The `.syntax-cache/` line stays in
`.gitignore` so a cache an earlier install built stays out of `git status`.
Of `test_git_diff.py`'s hundred and four tests the five over what is kept
stay; the not-a-commit guard is now driven through `raw_diff` rather than the
fold that called it.

**`tests/recorded_subprocesses.json` is left alone.** The replay harness does
not complain about entries no test asks for, so the delta, pandoc and diff
recordings of deleted tests stay until the next `make record`.

**The page router lost its old-board name.** `old_board` and
`serve_the_old_board` are `page` and `serve_the_page`: they serve the built
app, its assets, the stylesheets and the fonts. The tests that pin the API's
catch-all against the old board's paths are kept and renamed for what they
pin.

**The empty state-machine skip is deleted, and so is the check beside it.**
`NOT_YET_DRIVEN` had come down to the `create-draft` and `send-review` rows,
which are routing and no phase will drive, so
`test_a_declared_row_the_domain_could_drive_still_parts_from_the_table` could
never have a parameter again. The test beside it, that the undriven rows are
exactly the declared ones, was true by construction once both sides were
built from the same list. `ROUTED` keeps the reason for the two rows, and
`DRIVEN` is every edge whose trigger is not one of them.

**The reply inbox stays, though nothing writes it.** The old board's composer
was its only writer; the new API sends a reply as a verb. The drain still
drains it, `/operations` and the `202` still draw what is in it, the preview
seeds it and the manager wakes on it. Taking it out changes the drain and the
projection, which is more than a deletion, so it is owed rather than done.

**Tests.** No behaviour changed, so nothing here was written red first. The
`is_yours` table and the rewritten not-a-commit test pin what was already
there and were born green.
