# Giving the board a generated contract

The board's HTTP layer has no interface. `conversation_document` calls
`dataclasses.asdict` on whatever `panel_view` returns, so the read model's
internal shape is the wire format, and `frontend/app/data/panel.ts` re-declares
all 47 of its fields by hand on the other side. Nothing checks that the two
agree. They do agree today, by inspection, and keeping them that way has already
cost real time: `88eccfd9` went looking for a 2.4 MB test log and found that the
acceptance mocks were serving one attribute bag as both the collection and the
panel, so WarpDrive's development build was annotating 72 unrecognised
attributes per response.

The field list is currently written down in at least nine places. `PanelView`
and `RowView` in Python, `PANEL_FIELDS` in TypeScript, and the fixture shapes in
seven frontend test files.

This spec replaces the serialised read model with a generated contract. FastAPI
and pydantic produce `openapi.json` from the route signatures and the DTO
models, the front end's types are generated from that document, and the
translation from domain object to DTO moves into assemblers that do nothing
else. The seam gets narrower on the way through, because a contract is the point
at which you have to say what actually crosses.

The decisions behind it were asked and answered on 2026-09-22 and are recorded
in the appendix.

## What the measurement showed

`PanelView` carries 47 fields. Every one of them is named somewhere in
`frontend/app`, so by the test that matters, every one is observable to another
module and none is dead. That reads at first like a defence of the current
shape. It is the opposite. The interface is wide because the read model takes 57
domain fields, 33 on `Conversation` and 24 on the nested `Fix`, and hands back
47 without deciding anything on the caller's behalf.

`RowView` is the counter-example in the same package. Same aggregate, 15 fields,
14 of them on the wire. It is narrower because someone made decisions in it:
`reference` bundles kind, text and url into one object, and `meta` and `notes`
are composed strings rather than the ingredients for strings.

Six of the 47 are the same fact six times. `group_of`, `word_of`, `square_of`,
`column_of`, `keyed_word` and `status_token` are pure functions of
`conversation.state`, `fix.state`, `fix.run.kind`, `reopened` and whether a
landing failed. They call each other: `word_of`, `square_of` and `column_of` all
call `group_of`, `keyed_word` calls `word_of`, and `decisions_for` is keyed off
`keyed_word`. Four of the six cross the seam twice, once on the row and once on
the panel. That is what 253 tests in `test_read_model.py` have been measuring.

`panel_view` also is not a projection. It runs `ports.git.progress`,
`ports.git.diff_range` and `ports.git.diff_stat`, and calls `ports.records.list`
to read every conversation file in the PR so it can number one card against the
others. The front end refetches it once a second.

## The stack

FastAPI, pydantic, uvicorn. These are the first runtime dependencies this
project has had; `dependencies = []` goes away and that is a deliberate trade,
not an accident. What it buys is the generated document, request and response
validation at the boundary, and a whole, common FastAPI pattern rather than half a
pattern ported by hand.

Nothing about starting and stopping the board changes. `is_board_running`,
`start_board`, `stop_board` and `open_in_browser` keep their signatures;
`start_board` runs `uvicorn.Server.run` on the daemon thread that currently runs
`ThreadingHTTPServer.serve_forever`, and `stop_board` sets `should_exit` and
joins. The `v` and `V` keystrokes, the sticky port from `common/board.py` and
the revive-from-flag-file path on loop restart all keep working unchanged.

## Assemblers

The thing that converts a domain object into a DTO is Fowler's Assembler, not
DDD's Data Mapper. A Data Mapper moves data between the domain and storage and
is bidirectional; an assembler moves it to the wire and must not be. Confusing
the two is how a `to_domain` method appears on something that should never have
one.

Seven rules, and the last three are the ones that actually change this codebase.

The domain does not know the DTO exists. The assembler imports both; the domain
imports neither. No `Conversation.to_dto()`, however convenient.

The assembler is pure. No clock, no filesystem, no subprocess, no ports. An
assembler that fetches is a query wearing the wrong name.

The assembler is total. Given a valid aggregate, mapping always succeeds. This
one indicts `UNREADABLE`, which is a conversation state synthesised by
`ConversationRecords.list` when a JSON file will not parse. A file that does not
parse is a repository failure, and the repository should say so, instead of
handing back a domain state that every downstream table has to carry a row for.

One assembler per aggregate root, never one per class. `Fix`, `Comment`,
`Step`, `Anchor` and `Brief` live inside `Conversation`, so they get private
methods on `ConversationAssembler`, not five public classes with five test
files.

One direction. Inbound is a command, not a DTO of the aggregate. The board
already gets this right without naming it: a POST writes an intent and `apply`
decides what it means. Nothing about this spec changes that.

The DTO's shape is driven by the consumer. A DTO with one field per aggregate
field is a serialised aggregate and the assembler in front of it is a no-op.
Multiple DTOs per aggregate is correct, one per use case.

Derived values split on one question: would the rule still be true if there were
no UI? "A conversation whose fix has landed is done" is true with no screen
anywhere, so it is domain behaviour. "Done cards are grey and sort last" is not,
so it belongs to the contract.

## Where classification goes

`application/read_model/standing.py` is already pure; its only import is the
domain. It holds two different kinds of thing, and they separate.

The rules move to `review/domain/standing.py`: a `Standing` enum,
`standing_of(conversation)` and `allowed_decisions(conversation)`. The deciding
argument is `decisions_for`, which answers "what may be done to this
conversation in this state". `apply` answers the same question from the other
side when it refuses a command, and today the two can disagree because they live
in different layers with no shared table. In the domain, one test holds both.

The labels do not move to the domain. `GROUP_LABELS`, `COLUMN_LABELS` and
`GROUP_ORDER` are copy, they change when the design changes, and they already
ship in `meta`. They belong to the API layer.

On the wire this collapses six fields to one. A conversation carries
`standing`, a value from a closed vocabulary, and the collection's `meta`
carries one row per standing with its label, its square and the column it stands
in. Shipped once per board load rather than six times per card per second.

## The repository, and where git belongs

If the assembler may not run git, something else must produce `files`, `fold`
and the progress line. The tempting answer is a read service. That dodges the
question.

Those values are projections of the fix's own commits. `Fix` already carries
`base_sha`, `thread_sha`, `landed_sha` and `landed_base`, and the file stats are
derived from exactly those. The git worktree is not a service the read model
consults. It is part of where the aggregate is stored: half of `Fix` lives in a
JSON file and half lives in git.

So it is repository work, and the cost goes in the method name:

```
ConversationRepository.load(key)          -> Conversation   JSON only
ConversationRepository.load_changes(key)  -> Conversation   plus the git-derived facts
```

The collection endpoint calls the cheap one. The detail endpoints call the
expensive one. Nobody has to read an assembler to discover that rendering a card
shells out three times.

## Layout

```
review/
  domain/
    conversation.py     the aggregate: Conversation, Fix, Comment, Anchor, Brief
    standing.py         Standing, standing_of, allowed_decisions      pure, no labels
    apply.py            commands; shares allowed_decisions
  application/
    conversations.py    use cases: load through the repository, assemble, return a DTO
    assemblers/
      conversation.py   ConversationAssembler                          pure, total
  adapters/
    api/
      routers/          FastAPI, HTTP and nothing else
      dto/              pydantic models; the published contract, labels included
    records/
      repository.py     both loads
```

The application layer's published language is the DTO. A router never receives
an aggregate. That is not fastidiousness: a router holding a `Conversation` can
call domain methods, and then presentation starts invoking domain behaviour.
Cutting it off at the application boundary makes that impossible rather than
merely discouraged.

## The resource model

The panel is wide partly because one endpoint stands in for several resources.

| Resource                            | Methods          | Returns                                           |
| ----------------------------------- | ---------------- | ------------------------------------------------- |
| `/api/pull-request`                 | GET              | repo, number, title, branch, role, claude_enabled |
| `/api/settings`                     | GET              | themes, fonts                                     |
| `/api/conversations`                | GET              | `ConversationListDTO[]` plus meta                 |
| `/api/conversations/{key}`          | GET              | `ConversationReadDTO`                             |
| `/api/conversations/{key}/comments` | GET              | `CommentDTO[]`, the transcript                    |
| `/api/conversations/{key}/fix`      | GET              | `FixReadDTO`                                      |
| `/api/conversations/{key}/fix/diff` | GET              | the rendered diff                                 |
| `/api/conversations/{key}/decision` | GET, PUT, DELETE | the queued intent                                 |
| `/api/conversations/{key}/replies`  | GET, POST        | `ReplyDTO`                                        |

Four consequences worth stating, because none of them is cosmetic.

`/api/board` stops being a bag. It currently carries title, counts, groups,
themes, fonts and a feature flag in one document. Themes and fonts are static
config fetched once. Counts already belong in the collection's `meta`.

The queued decision becomes a resource. Today a pending intent comes back as
`intent` and `queued_label` smuggled onto the panel, and there is no way to
cancel one. `DELETE /decision` means unqueue, which the board cannot currently
express.

`accept` and `rework` stop riding along on every poll. They are forms for an
action nobody has taken yet. They get fetched when a dialog opens.

`status_token` becomes an ETag. The server already computes
`state|fix.state|run.kind`, ships it as a field, has the client echo it back as
`seen`, and answers 409 on a mismatch. That is `ETag` and `If-Match` hand-rolled.
Making it a header also gives `If-None-Match` on the GET, which turns the
one-second refetch of three full documents into three 304s.

## DTO shapes

Following the common base, read and list split. The list variant is not a
subset of fields; it is the same fields with cheaper types.

```
ConversationBaseDTO   key, standing, role, author, reference, when, gist
ConversationListDTO   + marks, steps
ConversationReadDTO   + reviewer, anchor, provenance, comment_deleted,
                        can_delete, actions
FixReadDTO            state, label, summary, plan, confidence, tests,
                        banner, fold, files, notes, failure
```

Around 13 fields on the conversation and 11 on the fix, with the transcript, the
decision and the diff as their own resources fetched when they are needed.

## Testing

Four mechanisms replace what `test_read_model.py` is doing, and they are not the
same mechanism.

Generation removes duplicate artifacts. The TypeScript types and WarpDrive's
field list are generated from `openapi.json`, so the nine hand-maintained copies
of the field list become one definition. Note that this asserts nothing on its
own. Deleting a field regenerates a schema and a client that agree on the new,
broken contract.

`response_model` validates at the boundary. A handler that returns a body
missing a required field fails there instead of shipping.

A committed `openapi.json` catches unintended change. CI fails on an unreviewed
diff. This is the piece that generation does not give you.

Contract tests assert policy over the whole schema: every
operation addressing a resource by id declares 404, every error response uses
the standard envelope. One test covering every route, still covering route N+1.

What is left is assembler tests, and there are as many of those as there are
meaningfully distinct aggregate states, which is the size of the state matrix.
Around twenty. Construct an aggregate, assert the DTO, no ports and no mocks.
Which decisions are legal is tested in the domain against `apply`, sharing one
table. Whether git returns the right file stats is a repository test.

`test_a_row_carries_the_column_it_stands_in` asserts a declared field exists,
which is testing that pydantic assigns attributes. It goes.
`test_the_board_reads_newest_first_and_a_silent_thread_sorts_last` asserts an
ordering rule and stays.

## Build order

1. `standing` moves into the domain, labels stay behind in the read model.
   Behaviour unchanged, `apply` and `allowed_decisions` share one table.
2. `ConversationRepository.load_changes`, so git leaves the read model.
3. FastAPI and pydantic arrive; `start_board` runs uvicorn on the same thread it
   runs `ThreadingHTTPServer` on today. Routes port one at a time, behaviour
   unchanged, DTOs still 47 fields wide.
4. `openapi.json` committed, contract tests, front-end types generated. The nine
   copies of the field list become one.
5. The resource model splits, the DTOs narrow, `standing` collapses to one
   field, `accept` and `rework` move behind their own resource.
6. `status_token` becomes an ETag and the poll becomes conditional.

Each step ends green and the front end keeps working. Steps 1 and 2 are
behaviour-preserving refactors of Python only. Step 3 is the dependency change.
Nothing before step 5 narrows anything, which is deliberate: formalising a shape
is how it becomes permanent, so the contract is generated before it is narrowed,
never after.

## Choices made while writing this

Strict CQRS would skip the aggregate on the read side and project straight from
storage, which is a real argument for something polling once a second. Rejected
because the classification rules would then exist twice, once in the projection
and once in `apply`, and keeping those in step is the bug class step 1 closes.
CQRS pays when the read side asks a different question. This one asks the same
question the write side asks.

An explicit `HydratedConversation` carrying the git facts is the textbook
layering and was rejected on cost: a third type per resource, maintained
forever, to avoid a repository method whose name already says what it costs.

A separate versioned DTO package was rejected. Such a package is versioned
because several services share it. This one has a single
consumer in the same repository, and the CHANGELOG ceremony would be paperwork
for an audience of one.

Hand-writing `openapi.yaml` and validating both sides against it was rejected as
the worst of the options: a third artifact that can drift from the other two.

## Appendix: the decisions

Asked and answered on 2026-09-22.

**What is the refactor buying?** Test churn, comprehension, and confidence in
the suite, all three. Not suite runtime: 3,537 tests run in 4.17 seconds and the
whole `make test` is 23 seconds, most of it Chrome starting.

**What makes deleting tests safe?** Port fakes extended end to end, plus a live
smoke run by hand as a gate on each phase. Cycle replay was rejected because
`make record` already needs hand-reverting.

**Observable to whom?** To another module. Applied honestly that protects most
of `test_read_model.py`, since every panel field has a real consumer. The
conclusion is that the module boundary is too wide, not that the tests are
wrong. The test count is a measurement of the interface.

**Delete or rewrite the stranded tests?** Delete by default. Coverage tooling
was considered and rejected; the governing principle is one test per observable
difference.

**Which stack?** The full FastAPI stack. Taking only pydantic would mean writing
the mapper, DI and contract-test patterns by hand instead of taking them from
the framework.

**What lands first?** This work, with the visibility pass folded into it. The
five-module plan from the earlier session, Store, Windows, Watch and PrWindow,
is parked until it lands. The two bodies of work are nearly disjoint: this one
lives in `review`, that one in `common`, the watcher and the manager.
