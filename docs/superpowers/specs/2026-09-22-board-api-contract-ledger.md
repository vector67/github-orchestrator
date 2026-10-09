# Board API contract ledger

Phase 3c of `2026-09-22-board-api-contract-plan.md`. One entry per
difference between the contract FastAPI now generates and
`2026-09-22-board-api-contract.openapi.yaml`, the record frozen on
2026-09-22.

**This document is written once and is not maintained.** The revisions
document asks for it in those terms: reconciliation is a single event, not
a standing check, because the code drifts from a frozen record by design.
A later reader who diffs the two documents again will find differences
this file does not name. That is the arrangement, not a gap here.

Six of the differences the first pass listed were defects in the generated
contract rather than differences worth recording. They were fixed and this
file was corrected against a second run of the same comparison, still
inside the one event. They are under *fixed in this pass*, with what is
left of each, so nothing the first pass found has gone unaccounted for.

The verdicts are the revisions document's. *Mechanical* is the generator's
idiom. *Record wins* is a change the code needs. *Code wins* is a place the
record was wrong. *Fixed in this pass* is a place the code was wrong and
now is not.

The two documents were compared mechanically: `app.openapi()` dumped to
JSON, the record parsed to JSON, then sorted-set diffs of paths, of schema
names, of each schema's properties with their resolved type, nullability,
enum, format and pattern, of each operation's responses, parameters and
headers, and of every description with whitespace collapsed. Where the two
use different notation for one thing — the record's named scalar aliases,
its `allOf` composition, its path-item parameters — the comparison
resolved the record's form before diffing, so those show up once as
notation rather than once per use.

It was run a second time after the six fixes, against the document before
them as well as the one after, so every count in this file that moved
moved by a measured amount and every count that did not is the first run's
own. Nothing outside those six changed: the paths, the schema names, the
property facts and the `anyOf`, `examples` and `format` counts are the
same in both runs.

Several entries name work later phases do. The phase is named where it is
known. Naming it is not scheduling it.

## Record wins

### The write side is not built

Seventeen paths in the record have no counterpart. Ten per-thread custom
methods are phase 4: `:stop`, `:approve`, `:rework`, `:start-session`,
`:retry`, `:resolve`, `:reject`, `:defer`, `:unpark`, `:reply`. Five more
are phase 6: `:edit-draft`, `:enrol`, `:withdraw-from-review`, `:discard`,
`:post-now`. `POST /api/operations:create-draft` is phase 6 and
`POST /api/operations:send-review` is phase 7. Phase 3 was the reads, so
nothing here is a surprise; it is the largest single difference between
the documents and it is listed first for that reason.

### Eight of the eleven operation variants have no model

`FixOperation`, `SessionOperation` and `ApproveOperation` are built. The
rest are the schemas the write side returns.

| Variant           | Kinds it carries                                                                     | Phase |
| ----------------- | ------------------------------------------------------------------------------------ | ----- |
| `StopOperation`   | `stop`                                                                               | 4     |
| `CloseOperation`  | `resolve`, `reject`                                                                  | 4     |
| `DeferOperation`  | `defer`                                                                              | 4     |
| `ReplyOperation`  | `reply`                                                                              | 4     |
| `UnparkOperation` | `unpark`                                                                             | 4     |
| `DraftOperation`  | `create-draft`, `edit-draft`, `enrol`, `withdraw-from-review`, `discard`, `post-now` | 6     |
| `ReviewOperation` | `send-review`                                                                        | 7     |
| `PostedOperation` | `posted`                                                                             | 7     |

### Nine request schemas have no model

`ApproveRequest`, `CloseRequest`, `DeferRequest`, `WakeCondition`,
`ReplyRequest` and `StartSessionRequest` are phase 4. `DraftBody` is
phase 6. `SendReviewRequest` and `ReviewVerdict` are phase 7. `Brief` is
already built, because `FixOperation` carries one; it is the body of
`:rework` as well and needs nothing further.

### `operations[]` holds at most one entry

A record holds a single `Fix`, and that one `Fix` carries a run, then a
session, then a landing in turn. `_operation_kind` answers with whichever
of those the fix is in the middle of, so nothing older than the current
step survives a rework. The record's `Conversation.operations` is
"everything ever asked of this thread"; the projection can supply the
present tense of it and nothing else. Phase 4 starts writing an entry per
verb.

### The operation id is synthesised, and it is not stable

Nothing on disk carries an operation id or a proposal id. The projection
mints them as `{key}.{kind}` and `{key}.proposal`.

`{key}.{kind}` changes under the operation it names. The kind is read off
the fix's current state, so one piece of work is `PRRT_x.rework` while the
agent runs and `PRRT_x.approve` once an approve starts landing it. A
client that holds an operation id across that moment holds a dangling one,
and `GET /conversations/{key}/operations/{operation_id}` answers it `404`.
`Proposal.operation` points at the same moving string, so a proposal read
before the landing names an operation that no longer answers. The record
describes an `OperationId` as a name the operation keeps. Real ids arrive
when phase 4 starts writing an operation per verb.

### `Anchor.side` is always null

`_anchor_of` passes `side=None` unconditionally, because the record has no
field for it. GitHub will not accept a posted review comment without a
side, so phase 6 has to store it before `post-now` can work at all. It is
the one always-null field with a phase blocked behind it, which is why it
is separate from the five below.

### Five more fields are null for want of a stored fact

| Field                                                        | Why                                                                                                                                                                           |
| ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `settled_at`, on the summary and on all three variants       | the record stamps `started_at` and nothing when work stops                                                                                                                    |
| `SessionOperation.steer`                                     | no field holds what the session was told on the way in                                                                                                                        |
| `ApproveOperation.delete_comment`                            | the approve's delete flag is not kept once the approve is written                                                                                                             |
| `Proposal.created_at`                                        | same gap as `settled_at`, seen from the artifact                                                                                                                              |
| `FileChange.status` and `old_path`, on a proposal's diffstat | `_counted` builds a `FileChange` from a `FileStat`, which counts lines and says nothing about how a file got there. `_changed` fills both on the diff, where git reports them |

These are the same fields as the entry under *code wins* on non-nullable
declarations, seen from the other side: that entry is about the type the
record declared, this one is about the value the code sends.

### Six enumerations are served whole and populated in part

Both documents declare the same members for every enumeration; the
generated one is served by a projection that can reach only some of them.
The unreachable members are not wrong, and narrowing the enums to what
phase 3 can produce would mean widening them again in phase 4.

| Enumeration         | Produced | Of  | What is missing                                                                                                                                                                                                                                      |
| ------------------- | -------- | --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `OperationKind`     | 5        | 20  | fourteen of the fifteen are the write verbs, phases 4 to 7. The fifteenth is `retry`, which no run ever carries: `_retry` re-queues the existing run with `attempts=0`, and the record's storage has three run kinds, `first`, `rebase` and `rework` |
| `ErrorCode`         | 9        | 33  | the reads raise `not-found`, `no-such-commit`, `no-such-path`, `not-text`, `range-inverted`, `range-too-wide`, `git-failed`, `unreadable-record` and `malformed-request`. The rest are the transition table's refusals, phases 4 to 7                |
| `ReasonCode`        | 4        | 13  | `_reason_code` derives `push-failed`, `reply-failed`, `agent-declined` and `conflict` from the fix. The other nine have no stored fact behind them                                                                                                   |
| `ConversationState` | 9        | 11  | `state_of` cannot return `draft` or `enrolled`; phase 6                                                                                                                                                                                              |
| `ThreadKind`        | 3        | 4   | `draft`; phase 6                                                                                                                                                                                                                                     |
| `OperationState`    | 4        | 5   | `requeued`; nothing puts an operation back yet                                                                                                                                                                                                       |

### `attempts_allowed` is a domain constant, not a stored fact

`MAX_ATTEMPTS = 3` in `conversation.py`, passed straight through by the
projection. It is not `settings.max_thread_runs`, which is 4 by default
and caps how many agents run at once rather than how many attempts one run
gets. A board configured for more concurrency still draws "attempt 2 of
3". The record describes the field as what the domain gives a run, which is
what the code sends; the difference is that it is a constant and not
configuration, and nothing in either document says so.

### `Conversation.kind` maps an empty `comment_type` to `review`

`comment_type` defaults to `""` on the record and `ThreadKind` has no
member for the empty string. `_kind_of` reads it as `review`. This is the
only place the projection chose a value rather than sending a null, so the
reasoning belongs here: the poller defaults an incoming thread to `review`
already, and the records the board makes for itself leave the field empty
rather than choosing a different kind, so the empty string means "the
usual" and not "unknown". Growing `ThreadKind` a member for it would put a
value on the wire that every consumer has to branch on to learn nothing.

### The document has no `servers` block

The record names `http://127.0.0.1:{port}` with the port as a variable and
says where the port comes from. The generated contract names no server, so
a client generated from it has no base URL for a board that binds to
loopback on a port allotted per pull request.

### The top-level `tags` list is absent

Every operation carries its tag, and the eight tags the record describes —
what "revisions" or "review" mean here — have no descriptions, because
nothing passes `openapi_tags`.

## Code wins

### Six fields are declared non-nullable for facts nothing produces

| Field                                                   | The record                 | The model                                                                                                                               |
| ------------------------------------------------------- | -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `Conversation.state_changed_at`                         | `string`, required         | nullable: no thread that has not moved since phase 2 started stamping it has a value, and `_ordered_at` is written to tolerate the null |
| `OperationSummary.requested_at`                         | `string`, required         | nullable: `fix.started_at` is unset until a run starts                                                                                  |
| `OperationEnvelope.requested_at`, on all three variants | `string`, required         | same fact, same fix                                                                                                                     |
| `Proposal.created_at`                                   | `string`, required         | nullable                                                                                                                                |
| `FileChange.status`                                     | `DiffFileStatus`, required | nullable: a diffstat has no status                                                                                                      |
| `ApproveOperation.delete_comment`                       | `boolean`, required        | nullable                                                                                                                                |

Each is required in both documents, so the field is always present; what
changed is that it may be null. Making the projection lie — a zero
timestamp, a `modified` status, a `false` flag — would have been the only
way to honour the record.

### `Brief` declares nothing required

The record gives `Brief` three properties and no `required` list, alone
among its object schemas. All three are always present, so the model
requires all three.

### `/api/files`'s `to_line` is off by one

The record says an omitted `to_line` runs to the file's end or to
"`from_line` plus 2000, whichever comes first". The ceiling is 2000 lines
inclusive, so `lines_of` stops at `first + MAX_FILE_LINES - 1`: asked for
line 1 with no end, the last line returned is 2000, not 2001. The
generated contract carries no descriptions on its query parameters at all,
so the sentence and its error both go.

### `FileLines.truncated` says two things that cannot both hold

"The file continues past `to_line`" and "Always false when the caller gave
an explicit range" are not compatible: asked for lines 1 to 10 of a
5000-line file, `lines_of` returns `truncated: false` and the file
plainly continues. The second sentence explains why an explicit range is
not clipped, which is true, and then states a value for a field whose
first sentence means something else.

This is the one entry where the two documents do not differ. The `Field`
description repeats the record's sentence verbatim, so the error is in
both. It is recorded here because this pass is the only one that will
compare them.

## Fixed in this pass

Six entries the first run produced described a generated contract that was
wrong about its own app rather than a document that had drifted. Each is
kept, describing what the code does now and what difference is left.

### The `422` the generator declared, and the `400` it did not

Ten of the fifteen routes — every one with a path or query parameter —
carried a `422` with `HTTPValidationError`, and the two schemas
`HTTPValidationError` and `ValidationError` existed only to serve it. No
route could return it. `add_refusal_handlers` installs a
`RequestValidationError` handler that answers `400` with `Errors` and the
`malformed-request` code, which is the phase 3 decision in
`2026-09-22-board-api-build-decisions.md`. Nine of the ten declared no
`400` either; only `/files` did.

`RefusingApp` overrides `openapi()`: every operation that carries the
generated `422` loses it and gains a `400` answering with `Errors`, and
the two schemas go with it. Rewriting the document is the only way to say
this. FastAPI leaves the `422` out for a route that declares a `422`, a
`4XX` or a `default` of its own, and each of those declares something else
that is not true. Doing it over the whole document rather than route by
route means a phase 4 route is covered without being told, and a route
that already has a sentence of its own for the `400` keeps it.

What is left is a difference the record does not carry: nine routes now
declare a `400` the record never gave them, because `malformed-request`
was decided after the record was frozen. The five routes that take neither
a parameter nor a body — `/pull-request`, `/viewer`, `/people`,
`/conversations`, `/operations` — declare no `400`, because nothing about
them can fail to validate.

### No read declared its `ETag` header

Thirteen of the fifteen reads answer with an `ETag` — every one except
`/viewer` and `/people/{login}`, which the record also leaves without one.
All thirteen declare `304`. None declared the header the `304` is
conditional on, because `etag.answered` sets it on the `Response` and
FastAPI documents only what the decorator is told.

`etag.TAGGED` is one definition of the header and of the `304`, spread
into the `responses` of each of the thirteen, so the header is declared
where it is sent and the routes that send no tag still declare none. The
description is the record's own, word for word.

What is left is that the code declares the header on the `304` as well as
on the `200`, and the record's shared `NotModified` response carries no
headers. The code does send it there — `etag.answered` puts the tag on the
`304` so a client that revalidates twice has one to send the second time —
so this is a place the record was silent rather than a drift.

### The header etag and the `etag` field are different strings

`conversation_of` hashes the conversation with its `etag` field empty and
then fills the field in with the result. `etag.answered` then hashes the
whole payload, which now contains that value, so
`GET /conversations/{key}` returns a header and a field that never match.
This is correct: they are different scopes, a representation tag for
`If-None-Match` and a precondition tag for `If-Match` on an operation. The
record says so, in the description of the shared `ETag` header, and with
that header now declared on every read that sends one, the generated
contract says so too. The first reader to notice two different hashes on
one response is told where to look.

### The `key` path parameter was a bare string

The record types it `ThreadKey`, with `^[A-Za-z0-9_-]+$`. The routes took
`key: str`, so the pattern reached the response bodies, where
`Conversation.key` is a `ThreadKey`, and not the path, while `sha` on
`/files` kept its pattern because that query parameter is annotated `Sha`.
The eight routes that take a key are annotated `ThreadKey` and the two
documents now agree on the parameter. `operation_id` and `proposal_id`
lose nothing, because the record constrains neither.

A key outside the pattern is now `400 malformed-request` rather than the
`404 not-found` it used to reach the domain to earn. That is the phase 3
decision applied where it was already written down: reusing `not-found`
for a bad path parameter was rejected in
`2026-09-22-board-api-build-decisions.md`, because `not-found` means the
thread is not there and a request that never got as far as a lookup has
not established that. It is also what `sha` already does. The two answers
call for different things from a client — a `404` sends it back to the
collection, a `400` tells it to fix the URL it built — and a key with a
dot in it is the second.

The narrowing is real: `is_thread_key` in `common/paths.py` accepts any
key that is non-empty and not all dots, which is wider than the record's
pattern. A thread whose key falls outside it was already unservable,
because `Conversation.key` would not validate on the way out; the
annotation moves that from a `500` at the end of the read to a `400` at
the start of it.

### Five descriptions did not move

The revisions document moves the record's prose into `Field` descriptions
and route docstrings. Five did not arrive: `Brief.note`, `Comment.id`,
`Comment.author`, `Comment.review_state`, and `ConversationState`'s own,
which had nowhere to go because the enum lives in `domain/standing.py` and
carried no docstring. All five are across, the enum's as its docstring and
the rest as `Field` descriptions. Four are word for word; `Comment.author`
reads `/people` for the record's `/api/people`, which is the prefix row
under *mechanical*.

Three of them land on `CommentSummary`, where the fields are declared and
`Comment` inherits them, rather than being written twice. The record
describes them on `Comment` only, so the generated contract now carries
three property descriptions the record has none for. They are in the
*mechanical* count of descriptions added.

### The error responses described the status, not the route

`errors.py` shared one description per status across every route that
declared it, so `/files` answered `400` with "The request does not say what
it needs to." where the record said "`to_line` is before `from_line`, or
the range is wider than 2000 lines", and `404` with "No such thing on this
pull request." where the record distinguished a missing commit from a
missing path, and a missing proposal from one that has committed nothing
yet. The shape was right and the sentences a client sees are the domain's
own; it was the documented `description` that had stopped telling a reader
which of several conditions a status covers.

Three are back, as `BAD_RANGE`, `NO_SUCH_FILE` and `NO_SUCH_DIFF`: the
`400` and the `404` on `/files`, and the `404` on the proposal's diff. The
rest stay shared, because the record shares them too. Every other `404` on
a read is the record's own `NotFound`, `/conversations/{key}`'s `500` is
its `UnreadableRecord`, and the diff's `500` and `/files`'s `415` are
already the record's sentence word for word, written once because one
route each declares them.

`/files`'s `400` says one thing more than the record's: it now also
answers a query parameter that will not parse, so it ends "or a parameter
is not what it says it is." That sentence is the one place the restored
prose and the record differ.

## Mechanical

The revisions document named four of these in advance. Two arrived as
described, the `anyOf` nullability and the injected `title`. One arrived
differently and is no longer here: the `422` went on every route with a
path or query parameter rather than on every route with a body, there
being no route with a body yet, and it is under *fixed in this pass*,
because the response it declared could not occur. The fourth did not
happen at all. Pydantic does reproduce
the `discriminator` mapping and does fold `first`, `rebase`, `rework` and
`retry` onto `FixOperation`, exactly as the record does. What it does not
do is name the union, which is the `Operation` row below.

| Difference                     | The record                                                                                                           | The generated contract                                                                                                                                                                                                                                                                                                                                                                  |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Path prefix                    | `/api`                                                                                                               | `/v2/api`, on all fifteen paths. Scaffolding so phase 3 does not collide with the old board's `/api/conversations`; phase 8 moves it back as its first act, per the commit that stood the new API up                                                                                                                                                                                    |
| The same prefix inside prose   | `/api/conversations/{key}/comments`, `/api/operations`                                                               | the same references without `/api`                                                                                                                                                                                                                                                                                                                                                      |
| Nullability                    | `type: [string, "null"]` 46 times and a `oneOf` with a `{"type": "null"}` branch 18 times, across the shared schemas | `anyOf` with a `{"type": "null"}` branch, 84 times. The count is higher because the flattened variants repeat the envelope's nullable fields and because of the six fields under *code wins*                                                                                                                                                                                            |
| `title`                        | never                                                                                                                | on 40 schemas and 140 properties. The 22 properties without one point at another schema, directly or through a nullable `anyOf`, and take no sibling keyword. Two schemas and six properties fewer than the first run counted, all of them `HTTPValidationError` and `ValidationError`                                                                                                  |
| `examples`                     | 24                                                                                                                   | none                                                                                                                                                                                                                                                                                                                                                                                    |
| `format`                       | 13: `date-time` on 11 timestamps, `uri` on `Comment.html_url` and `PullRequest.html_url`                             | none. The models type all thirteen as `str`                                                                                                                                                                                                                                                                                                                                             |
| Named scalar aliases           | `ThreadKey`, `Sha`, `OperationId`, `ProposalId`, `GithubNodeId`                                                      | inlined at every use. `Sha` and `ThreadKey` are `Annotated` types, so their patterns survive inline; the other three constrain nothing                                                                                                                                                                                                                                                  |
| `Operation`                    | a named `oneOf` over eleven variants with a twenty-entry `discriminator` mapping                                     | the union is inlined at each use — `OperationList.items` and `readOperation`'s `200` — over the three built variants, with a six-entry mapping. No schema is named `Operation`                                                                                                                                                                                                          |
| `OperationEnvelope`            | a named schema each variant composes with `allOf`                                                                    | flattened into each variant. No schema is named `OperationEnvelope`                                                                                                                                                                                                                                                                                                                     |
| Reusable components            | `components.responses` (8), `components.parameters` (6), `components.headers` (1)                                    | schemas only. Every response, parameter and header is written out at its use, the `ETag` header thirteen times over from one shared definition in the code                                                                                                                                                                                                                              |
| Path parameters                | on the path item, shared by its operations                                                                           | on each operation                                                                                                                                                                                                                                                                                                                                                                       |
| `200` description              | one sentence per route, "The thread.", "The lines."                                                                  | "Successful Response"                                                                                                                                                                                                                                                                                                                                                                   |
| `readOperation`'s `200` schema | `$ref` to `Operation`                                                                                                | the inline union, with a generated `title: "Response Readoperation"`                                                                                                                                                                                                                                                                                                                    |
| `info.description`             | the argument for the shape, at length                                                                                | six lines saying the document is generated and where the argument lives. The revisions document moved the prose into `Field` descriptions and docstrings on purpose                                                                                                                                                                                                                     |
| Descriptions                   | —                                                                                                                    | 54 carried across word for word, 24 reworded or trimmed, 6 schema descriptions and 4 property descriptions added where the record had none, none lost. The second run moved four into "word for word" and one into "reworded", and added the three `CommentSummary` properties; the rewording is mostly the prefix change above and the trimming of arguments that belong in the record |
| `Anchor.side`'s enum           | `["LEFT", "RIGHT", null]`, beside `type: [string, "null"]`                                                           | `["LEFT", "RIGHT"]` inside the non-null branch of the `anyOf`. The same value space, written where the notation puts it                                                                                                                                                                                                                                                                 |
