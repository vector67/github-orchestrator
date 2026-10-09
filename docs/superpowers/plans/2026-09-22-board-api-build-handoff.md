# Board API build: where it ended

Finished 2026-09-23, after phase 9 of
`docs/superpowers/specs/2026-09-22-board-api-contract-plan.md`. Phases 0 to 9
are done. This says what is built, what was decided along the way, what is
owed, and how the work was run.

It is a handoff, not a document about the board. Whether to delete it now the
build has finished is still to decide.

## Where the branch is

Branch `worktree-board-api-contract`, in the worktree at
`.claude/worktrees/board-api-contract`, rebased on `main` at `0401c0b3`.

`make lint` passes. At phase 9 `make test` is green at **python 3808 passed, 1
skipped, 1 xfailed** and **frontend 463 passed**. The one skip is
`test_chaos_extended.py`'s probabilistic soak test, run by hand; the xfail is
the tmux keystroke-injection race in `test_race_conditions.py`. Neither is the
board's. Every phase boundary below was green before it was committed.

| phase | what it did                                              | commit      |
| ----- | -------------------------------------------------------- | ----------- |
| 0     | the state machine written down as a table                | `e5ba27f9`  |
| 0     | the contract changed where the table proved it short     | `ae9f2230`  |
| 1     | `state_of`, one function for a thread's contract state   | `62492b87`  |
| 1     | every refusal carries the table's error code             | `5c67e375`  |
| 2     | the board owns the key; `github_node_id` is a field      | `f6caade1`  |
| 3     | FastAPI beside the old board, one read end to end        | `73198a60`  |
| 3     | every read the contract declares                         | `7a25d461`  |
| 3     | the ledger, and the defects it found                     | `437c9365`  |
| 4     | the ten per-thread verbs over HTTP                       | `e8be2301`  |
| 4     | the three write defects fixed, `status_token` removed    | `369b219f`  |
| 5     | operations first class, work in flight served            | `2c38d9fe`  |
| 6     | drafts, and unpark bringing a landed thread back         | `61f00df9`  |
| 7     | enrolled drafts sent as one review                       | `6c0ff628`  |
| 8a    | the board moved onto the new API                         | `3e68ae96`  |
| 8b    | markdown in the browser, the draft composer, Send review | `08102c1f`  |
| 8b    | what the security review of the board found              | `b8c7d964`  |
| 9     | the read model, serialisers, renderer and WarpDrive gone | uncommitted |

An untracked `scripts/serve_api_preview.py` predates this work. It was left
alone throughout and imports nothing phase 9 removed. Decide what it is for
before deleting it.

## What phase 9 removed

The old board's read model (`application/read_model/`, with `RowView`,
`panel_view`, `PanelState`, `panel_state`, `meta_of`, `steps_text`,
`sort_key`, `GROUP_ORDER` and `COLUMN_ORDER`), the JSON:API serialisers in
`api/conversations.py`, `render.py` and `markdown.py`, the `Standing` vocabulary
with `standing_of`, `keyed_standing`, `group_of`, `column_of` and the old
`ACTIONS` tables, the server-side delta diff renderer and everything that
existed for it (`ansi_html.py`, the bat syntax theme, `make install_syntax_theme`), the WarpDrive packages and their build config, and the
tests and test helpers that only covered those. What stayed and why is in the
build decisions under Phase 9.

## What was decided while building

The contract's own decisions live in
`2026-09-22-board-api-contract-revisions.md`. Decisions taken while building it
live in `2026-09-22-board-api-build-decisions.md`, in prose, with what was
found, what was decided and what was rejected. **There is no numbered decision
register** — an earlier draft of this handoff invented D-numbers and they exist
nowhere in the repository.

The ones that shape everything after them:

**`reopened` left `ConversationState` and became a boolean beside it.**
`apply.py` re-queues the fix whenever a comment arrives on the author's board,
so a thread is reopened and queued in the same tick and the enum member would
have been overwritten before it was ever drawn. The two facts are orthogonal,
which is why the redesign's Ready for you row would not rewrite against an enum
that merged them.

**The trigger set gained the board's own transitions** — `pick-up`,
`settle-applied`, `settle-refused`, `requeue`. Every trigger in the first draft
moved a thread *into* a working state and only `stop` moved it out, so five
transitions the machine has to make could not be named.

**A verb that touches GitHub does not move the thread until it applies.** Every
operation is accepted with `202` and settles later, so `reply`, `resolve`,
`reject` and `post-now` reached `waiting` or `done` before GitHub had anything,
and a reply that failed to post had no edge back. The run verbs never had the
bug, because the state they move to *is* the operation being in flight.

**A comment on a `waiting` thread discharges the wait.** Leaving it parked
refused every work verb behind a manual unpark on a thread that was plainly the
operator's move again.

**An unparseable record answers in an `unreadable` array on the collection**,
which made `ConversationList` an envelope rather than a bare array. The
alternatives were a `ConversationState` member every downstream table carries a
row for, or dropping the record silently where the board draws a card today.

**The project stopped being dependency-free.** `pyproject.toml` was
`dependencies = []`; phase 3 added `fastapi`, `pydantic` and `uvicorn`, twelve
packages with transitives. The revisions document turns on FastAPI's generated
output being the live contract, and phase 3's done-criterion is that the
generated contract exists. Pydantic alone with the hand-rolled router still
leaves every path, parameter, response and 304 hand-written. **This is the
decision to reverse if the dependency-free property matters more.**

**The new API mounted at `/v2/api` until phase 8a moved it to `/api`.** The plan rejected versioning,
but it rejected shipping two versions of a board one person runs on loopback;
this is scaffolding inside one unmerged branch. `/api/conversations` and
`/api/conversations/{key}` collide with the old board, so without the prefix
phase 3 breaks it, drags phase 9's deletions forward, and leaves no phase
between 3 and 8 able to end green. **Phase 8 moves the prefix as its first
act.**

**Phase 5 gave the record an operation history.** Phase 1 had none: the
record held a single `Fix`, and it still does, with the history beside it.
`domain/operations.py` writes it from `apply`, syncing the run, session or
landing from the fix and settling every other verb by the outcome that answers
its effect.

**`standing_of` and `keyed_standing` stayed until phase 9.** The plan put
their collapse in phase 1, but it also asked for a green suite at every phase
boundary, and the old JSON:API board and its tests ran on them until 8a. Phase
9 collapsed them into `state_of`.

**`UnreadableRecord` moved from `application/ports.py` into the domain**, because
the domain cannot import from application without inverting the layering, and
phase 3 needed one exception type to catch. A fix state outside the known nine
used to fall through to `ready`, drawing a corrupt record as an ordinary card.

**Five members joined `ErrorCode`** beyond the contract's original list, each for
a refusal that had no honest code: `parked` and `still-a-draft` (the converses
of `not-parked` and `not-a-draft`), `claude-disabled`, `internal-refusal`,
`malformed-request` and `confirm-again`. Each is recorded with what it replaced
and why.

## The two artifacts the tests depend on

**The transition table** in `2026-09-22-board-state-machine.md` is parsed by
`tests/review/domain/test_state_machine.py`. The four columns are
`from | trigger | to | code`, one backticked enum member or an em dash per
cell, exactly one of `to` and `code` filled on an edge that exists, both empty
only where the event cannot arise, and qualifiers as a parenthesised phrase on
the trigger. A cell that breaks the convention breaks the test. `mdformat`
re-aligns the whole table whenever the widest cell changes, so the parser is
whitespace-tolerant and the diff is often the whole table.

**`ROUTED`** in that test file names the only rows the test does not drive,
the `create-draft` and `send-review` rows, which are routing rather than the
domain; `test_contract_drafts` drives their `404`. `NOT_YET_DRIVEN`, which
declared rows a later phase would make drivable, went in phase 9 once every
such row had been driven. A row added to the table is driven from then on, or
the test fails.

## Owed, and easy to lose

### Needs real GitHub

None of these has been run against GitHub; every test here uses a fake.

- **`post-now`** has only been proved against a fake GitHub. The done-criterion
  is a real comment on a thread whose key never changed.
- **`send-review`** likewise: six drafts as one real review with one
  notification to the author, each with a `posted` operation and a node id.
  It is also the first time the review's comments are matched back to their
  drafts against GitHub's real listing, by path and body.
- **A posted draft found by its root comment.** The poller's match of a thread
  GitHub had not listed yet, by its root comment, has only met a fake listing.
- **Whether the review run actually calls `thread draft`.** The prompts ask for
  it and the CLI verb is tested; a live `review-requested` run is what would
  show the model does it.

### Needs a real browser against the real server

The ember suite runs in Chrome, but against the fake API in
`tests/helpers/fake-board.ts`. No live server was run from 8a on, because the
preview server reads the pull request through `gh` and its drain posts.

- **The whole board after phase 9.** The production build succeeds without
  WarpDrive and the suite passes, but the built bundle has not been loaded in
  a browser against the real server.
- **The Send review modal** has never met the real API.
- **The built page under its policy.** `test_the_built_page_loads_under_its_policy`
  only runs when `make build_frontend` has built a page; the CSP has not been
  watched in a browser's console.
- **Markdown and highlighting on real comments.** The sanitiser's hostile tests
  run in the browser; real review bodies, and real diffs through highlight.js,
  have not been looked at.

### Known gaps in behaviour

- **`apply(conversation, command, at=None, asked=None)` stamps only when `at`
  is passed.** Without it the thread moves unstamped and its operations settle
  with no `settled_at`. Every caller phase 5 added passes it; the route's dry
  run is the one that should not.
- **The rebase flavour of `landing` is barely exercised.** The state machine
  has a rebase-run card for `landing` plus `settle-applied (the kind is rebase)`, but every unqualified `landing` row still runs only on the approve
  flavour, and `_defer` and `_reject` still cannot tell the rebase flavour from
  a queued fix. On it a fresh `approve` is `Deferred` rather than refused
  `operation-outstanding`, because the domain cannot tell it from the approve
  the drain keeps re-applying behind the rebase.
- **Nothing sends `Rebase`.** The command exists for the table's `rebase`
  trigger; a rebase starts only when an approve's pick conflicts. The poller
  starting one when the head moves under a proposal is unbuilt.
- **A superseded run keeps only its envelope.** Its plan, `onto`, `conflict`
  and classification lived on the `Fix` and are gone once the next run starts,
  so `/conversations/{key}/operations` draws them empty for every run but the
  current one.
- **Two buttons the table refuses are gone.** Resolve on queued and session
  cards, and Push it on a landing in progress. The composer no longer retries a
  reply GitHub refused; it settles refused with the words on the operation.
- **Claude being switched off is not on the API.** Rework and Open a session
  are drawn regardless and the `409 claude-disabled` is toasted.
- **A verb in the air hides the buttons only outside the working states.** On
  a working thread a second verb while one waits is answered `409` and
  toasted rather than hidden.
- **A review comment the listing does not match leaves its draft with no
  comment id.** One the adapter cannot match is still posted, with a comment of
  no id, and the poller cannot then find its thread by the comment, so a reply
  on it opens a second record.
- **A drain that dies mid-send sends the review again.** The review stays
  pending until it is settled, so a crash after GitHub took it and before the
  file was rewritten posts it twice. A reply has the same risk.
- **An anchor that goes stale between `enrol` and `send-review` fails the whole
  review.** GitHub refuses it as one call and the operation carries GitHub's
  words, but nothing says which draft was at fault.
- **A draft on an author's board behaves like the author's own thread once
  posted.** Nothing refuses `create-draft` there. A reply to a posted draft
  reopens it and the poller asks for a `first` run on it, as on any thread of
  the author's.
- **A draft on the old side draws no code.** The contract gives the pull
  request's head and not its base. Adding the merge base to `PullRequest`
  would close it.
- **The backend's `is_yours` and the front end's Ready for you disagree on a
  reopened rework or rebase.** The front end draws every reopened thread under
  Ready for you; a reply posted on a reopened `rework` or `landing` thread
  does not park it, because `is_yours` keeps `group_of`'s old answer there.

### Left behind on purpose

- **The reply inbox has no writer.** The old board's composer wrote it; the new
  API sends a reply as a verb. The drain, `/operations`, the `202`, the preview
  seed and the manager's wake still read it. Removing it changes the drain and
  the projection.
- **`tests/recorded_subprocesses.json` still holds the delta, pandoc and diff
  recordings of tests phase 9 deleted.** The harness does not complain about
  unused entries; the next `make record` drops them. Until then `CLAUDE.md`'s
  "replays recorded git, delta and pandoc output" is true of the file and of
  nothing the code runs but pandoc.
- **`.syntax-cache/`** stays in `.gitignore` for a cache an earlier `make install` built; nothing builds or reads it any more, and nothing removes it.
- **`standing.py` keeps its name** with nothing called a standing left in it.

## Reusable pieces not to rebuild

- `api/etag.py` — `etag_of(body)`, `answered(request, payload)`, and `TAGGED`,
  the shared `ETag` header and `304` declaration to spread into a new read's
  `responses`.
- `api/errors.py` — `RefusingApp`, a `FastAPI` subclass overriding `openapi()`
  that strips the generator's unreachable `422` and injects the `400` with
  `Errors` on any route that can fail validation. A new route with a body gets
  this for free.
- `api/projection.py` — record to contract, including the per-thread `etag`
  field that `If-Match` is checked against. Do not compute that hash a second
  way.
- `app.py`'s `_queued` — loads the record, applies the command, throws the
  outcome away so a `Refused` becomes the HTTP answer, and writes an intent only
  for an accepted verb, carrying the operation id it mints.
- `domain/operations.py` — the history. `apply` calls its `accepted`,
  `refused` and `deferred`; `adopted` gives a record written before the history
  its fix as an operation; `Asked` carries a client's id to the drain. A new
  verb has to join `VERB_KINDS` there, `OPERATION_KINDS` in `document.py` and
  `KIND_OF_DECISION` in `projection.py`.
- The records port's `reviews`, `save_review` and `review_lock`, and
  `projection.review_of` — the pull request's own operations, which belong
  to no thread. The Send review modal reads them at `/operations/{id}`.
- `projection.pending_of` — the inbox drawn as pending operations. The `202`,
  every per-thread read, the collection and `/operations` all go through it, so
  they agree about what is waiting.

## How the work was run

Sequentially, one Opus subagent per phase or half-phase, each briefed with the
plan section, the decisions so far, the house rules and an explicit TDD
instruction, and each reporting back before the next was dispatched. Subagents
share this one worktree, so they cannot be run in parallel.

Every phase ended the same way: read the agent's report, verify the claims that
mattered independently rather than taking them on trust, decide anything it
flagged rather than letting it decide, then commit with the reasoning in the
message. That verification caught real things — a contract table that needed
its own parser run over it, an agent's honest note that a test had been born
green, and a subagent that briefly repointed the parent checkout's virtualenv
at this worktree.

House rules that bit repeatedly: `rg` never `grep -r`; `ReadAST` before a
bounded read of a `.py` file; never a write and a source read in one Bash call,
because a compound command is refused whole and the write is dropped silently;
plain `uv run`, never `uv run --active`; `git add` a new `.md` before `make lint`, because mdformat only checks tracked files.
