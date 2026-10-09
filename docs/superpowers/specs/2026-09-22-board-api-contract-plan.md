# Board API build plan

The build order `2026-09-22-board-api-decisions.md` deliberately left unwritten
until the contract was right. The contract was
`2026-09-22-board-api-contract.openapi.yaml`, retired on 2026-10-01 for the
one the board serves at `/api/openapi.json`; the decisions behind its current
shape are in `2026-09-22-board-api-contract-revisions.md`. This is how it gets
built.

## Shape of the work

One branch, one cutover. The new contract serves `/api/conversations` at the
same path the old JSON:API routes do, so the two cannot run side by side
without versioning one of them, and versioning a board that one person runs on
loopback buys nothing. The branch stays unmerged until the front end works
against the new API.

Inside the branch the order is chosen so each phase ends somewhere you can
check. Phases 1 and 2 need no HTTP. Phases 3 to 7 need no browser. Phase 8 is
the only one where both sides move at once, and by then the API is fixed.

`make lint` and `make test` pass at the end of every phase. Where a phase
changes what subprocesses the code runs, `make record` is part of that phase,
not a cleanup afterwards, and only the new entries are kept.

## Phase 0: the state machine

Produce `2026-09-22-board-state-machine.md`: a table of states, the transitions
between them, and a refusal code on every edge that is not allowed.

- States are `ConversationState` from the contract: `draft`, `enrolled`,
  `queued`, `working`, `in-session`, `rework`, `landing`, `ready`, `reopened`,
  `waiting`, `deferred`, `done`.
- Transitions are `OperationKind`, plus the board's own `first` and `rebase`,
  plus a comment arriving from the poller.
- Every disallowed edge names an `ErrorCode`. `stop` on a thread with nothing
  in flight is `nothing-in-flight`. `stop` on a thread with a finished proposal
  is `proposal-exists`. `reject` on a thread with work running is
  `work-in-flight`. `reject` with nothing to turn down is `no-proposal`.

**This phase is the contract's acceptance test.** Rewrite every group row from
`2026-09-12-review-board-redesign-design.md:80-97` and
`2026-09-21-reviewer-board-design.md:48-65` in terms of what the contract
actually ships. A row that rewrites cleanly proves the contract carries enough
for that heading. A row that will not rewrite is a named missing fact, and the
contract changes before any code is written.

Done when: every row rewrites, or the ones that do not have a contract change
behind them.

## Phase 1: the domain

The machine in code, as one function over a conversation's operation history,
and `apply` refusing anything the table does not allow.

- One function, not two. `standing_of` and `keyed_standing` collapse, and the
  result stops being shared over the wire in any form other than `state`.
- Every refusal returns a code and a sentence. The code comes from the table.
- The `resolve` and `defer` offered on a reviewer's parked cards that `apply`
  refuses is a real bug, currently parked as a strict `xfail`. The table
  settles it and the `xfail` goes.

Tests walk the table: every allowed edge applies, every disallowed edge refuses
with the code the table names. That test is generated from the table, so the
document and the code cannot drift.

Done when: the table's every cell is exercised and the `xfail` is deleted
rather than flipped.

## Phase 2: the record and the key

Two storage changes that everything later depends on.

- **The key becomes the board's.** Records are currently named by GitHub node
  id. New threads keep getting a key derived from the node id, so nothing has
  to be renamed; what changes is that `key` is no longer *defined* as the node
  id, and `github_node_id` becomes a field the poller matches on. Drafts get a
  minted key with no GitHub id at all.
- **`state_changed_at`** is stamped whenever the machine moves a thread.

Done when: a record round-trips with a minted key and a null node id, and the
poller matches an incoming GitHub thread to an existing record by
`github_node_id` rather than by filename.

## Phase 3: the DTOs and the generated contract

Pydantic models for every schema in the record, FastAPI routes for every path,
and the reads wired up: pull request, viewer, people, conversations, comments,
operations, proposals, diff, files.

- `ETag` on every read that the contract says carries one, and `If-None-Match`
  answered with 304. The conversation's `etag` is a field as well.
- The conversation collection comes back ordered, newest first, by whichever is
  later of `state_changed_at` and the newest comment's `created_at`.
- `/api/files` enforces its ceiling and refuses rather than clipping.

Then **the ledger**: `2026-09-22-board-api-contract-ledger.md`, one entry per
difference between the generated contract and the frozen record, each marked
*mechanical*, *record wins* or *code wins* with a reason. Expect the mechanical
section to be long. It is written once and not maintained afterwards.

Done when: the generated contract exists, every difference is accounted for,
and a conditional GET of the conversation list returns 304.

## Phase 4: the write side, per thread

Every custom method on `/api/conversations/{key}/operations` except the draft
ones: `stop`, `approve`, `rework`, `start-session`, `retry`, `resolve`,
`reject`, `defer`, `unpark`, `reply`.

- `If-Match` against the conversation's `etag`, 412 when it moved.
- `stop` replaces `cancel` and takes over halting a running agent. `reject`
  narrows to turning down a finished proposal.
- The old `status_token` and its `seen` echo go. They were categorical, so two
  edits leaving `state|fix.state|run.kind` unchanged were never detected as
  conflicting; the etag catches those.
- Three known back-end defects get fixed here rather than carried:
  `reject` with a reply or a delete has never worked, a second decision
  silently replaces the first, and an unreadable record does not 500.

Done when: every verb round-trips through HTTP, a stale `If-Match` gives 412,
and each refusal names the code its table row promises.

## Phase 5: work in flight

- The plan moves from `Proposal` onto the fix and session operations; the
  summary stays on the proposal.
- `OperationSummary` carries `steps_done`, `steps_total`, `requested_at`,
  `settled_at`, `reason_code`. `last_action` and `progress` stay off it.
- `GET /api/operations` returns everything pending or running across the pull
  request, with the fields that move while an agent works.
- `start-session` becomes `running` while the pane is open, and the CLI that
  Claude runs inside the session settles it and hands over a proposal. A
  proposal can now come from a session, so `Proposal.operation` points at
  whichever produced it.

Done when: an agent running on one thread changes `/api/operations` every
second while a conditional GET of the conversation list still returns 304.
That is the check that the summary is carrying the right fields.

## Phase 6: drafts

- `POST /api/operations:create-draft` mints a conversation with kind `draft`,
  state `draft`, a null node id and one comment with no GitHub id.
- `edit-draft` replaces body and anchor together, and consecutive edits
  collapse into one operation rather than appending.
- `enrol` validates the anchor against the pull request's diff and refuses
  `anchor-not-in-diff`. `withdraw-from-review` reverses it. `discard` moves the
  thread to `done` so `unpark` brings it back.
- `post-now` posts one standalone review comment, fills in `github_node_id`,
  and changes `kind` from `draft` to `review` without changing `key`.
- The `review-requested` run's findings become draft records. That needs the
  run to hand back structured findings with file, line and body instead of
  writing prose into `agent-changes.md`.

Done when: a draft can be made, edited, enrolled, withdrawn, discarded and
brought back, and `post-now` puts a real comment on GitHub against a thread
whose key never changed.

## Phase 7: sending a review

- `POST /api/operations:send-review` with a verdict and a body, posting every
  `enrolled` draft as `comments[]` through
  `POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews`.
- On success it writes a `posted` operation onto each draft it posted, so each
  thread's state is still readable from that thread's own history.
- On rejection every draft stays `enrolled` and the operation carries
  `github-rejected` with GitHub's words.
- `body` is required for `REQUEST_CHANGES` and `COMMENT`; a request without one
  is refused before the call.

Done when: six drafts go out as one review, the author gets one notification,
and each of the six has a `posted` operation and a node id.

## Phase 8: the front end

The only phase where both sides move together, and the API is fixed before it
starts.

- A normalisation layer, since the payload is no longer JSON:API with composed
  strings.
- Grouping by `state`, with group order and labels owned here. The order inside
  a group is the order the collection arrived in.
- Two-tier polling: the conversation list slowly with `If-None-Match`,
  `/api/operations` quickly. The current one-second refresh of the whole route
  tree goes, along with the second full pass that `/api/board` cost.
- Markdown rendering and sanitising, and syntax highlighting, both now in the
  browser. Sanitising is a security boundary, so it is reviewed as one.
- The draft composer: body in a textarea, anchor as a typed path and line, code
  beside it redrawing as the anchor changes.
- The Send review modal: verdict, summary, the enrolled drafts with edit and
  leave-out, and a note on what is being left open.
- Buttons come from `state`, drawn here. Nothing asks the server what is
  permitted.

Done when: the board draws, orders, and acts entirely off the new API, and the
dead `notes` field that shipped every second and was never rendered is gone.

## Phase 9: removing what it replaced

- The JSON:API serialisers, `RowView`, `meta_of`, `steps_text`, `sort_key`,
  `group_of`, `column_of`, `GROUP_ORDER`, `COLUMN_ORDER` and `/api/board`.
- `status_token` and the `seen` echo.
- The `panel_state` fingerprint that only a test calls.

Done when: nothing references them and the suite is green without them.

## Amendments owed

Three documents currently say the opposite of what was decided. Each needs a
line, not a rewrite, so a later reader does not follow a superseded rule:

- `2026-09-22-board-api-decisions.md:140`, "No structured error codes".
- `2026-09-22-board-api-decisions.md:16-30`, which deleted `situation` and the
  folds. The state and the ordering are back on the server; the buttons are
  not.
- `2026-09-07-comment-threads-design.md:29`, "the key is always a GitHub node
  id".

All three now carry that line, pointing at
`2026-09-22-board-api-contract-revisions.md`.

`2026-09-21-reviewer-board-design.md` is not superseded. It is the source for
phases 6 to 8 and neither 09-22 document referenced it, which is why drafts
were missing from the contract.

## Risks worth watching

**The state machine is the whole bet.** Everything downstream assumes a thread
has exactly one state and that every history maps to it. If phase 0 finds a
history that maps to two states or none, the contract changes before phase 1.

**Sanitising markdown in the browser** is the one change here that is a
security boundary rather than a layering one. It is on the Not settled list for
that reason and should not be waved through with the rest of phase 8.

**Anchors going stale.** A draft valid at `enrol` can be invalidated by a push
before `send-review`. Validating as the operator types was deliberately left
out of scope, and the gap between enrol and send is where it will show up
first.

**`make record`** rewrites machine state beyond the new test's entry. Revert
the tmux and dark-mode captures it touches and keep only what the change
needed.
