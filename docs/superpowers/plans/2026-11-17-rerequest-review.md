# Re-request review prompt: plan

Carries out [the re-request review spec](../specs/2026-11-17-rerequest-review-design.md).
The spec is the decision. This plan sets the order of the steps, how each one
is judged, and the choices the spec left to the build. Section numbers (1–6)
are the spec's requirements. Issue #428.

## How to work

- Every change follows `.claude/skills/normal-workflow`. Load `tdd` for
  anything that changes behaviour and `refactor` for reshaping. Steps 6 to 10
  touch `frontend/` and load `frontend-work` first.
- Each step gets its own branch in its own worktree, cut from local `main`,
  and is merged and restarted before the next step starts.
- Run `make lint-python` and `make test-python` before each commit, under
  `timeout`, and report the pass counts. A step that touches `frontend/` runs
  the full `make lint` and `make test`. A step that changes the API runs
  `make contract` and commits the regenerated `frontend/app/data/api.ts` and
  `frontend/tests/helpers/board-api-contract.json` with it.
- **Recorded subprocesses.** A step whose tests change what git or `gh` runs
  re-records only those tests with `uv run pytest tests/ -k '<tests>' --record`.
- **Proof is tests and fakes.** Python tests drive change detection, the
  settings stores, the manager and the board API through their fakes
  (`github/fake.py`, `settings/fake.py`, `board_api/fake.py`). Front-end tests
  are acceptance tests against `frontend/tests/helpers/fake-board.ts`. Assert
  what was asked of GitHub, what the dashboard says, and what the page shows
  and posts. No step writes to a real PR.
- **No CSS pinning.** Tests assert words, structure, order, focus and what is
  posted, never colours, borders or widths. The dialog reuses the hold
  warning's, the ready dialog's and the state chip's classes.
- **Server facts once, derived values in `summaries.ts`.** The store keeps
  the new facts as the server sends them; rounds, owed reviewers, outcome
  counts and the prompt's question are computed only in
  `frontend/app/data/summaries.ts`. A second copy anywhere is a miss.
- **Data on disk.** Snapshots written before step 1 have no
  `review_requested_at`; read its absence as an empty map in `_facts.py`
  only. `Rerequests` is new and owned by `settings/`.
- **New files.** A new front-end test file gets an entry in
  `frontend/tests/partition-weights.ts`. A new data directory gets its
  helper in `tests/disk_layout.py`. A new settings export goes in
  `tests/test_layering.py`'s list beside `ReviewerPicks`.
- **Codex parity.** Nothing here depends on which agent ran.
- **Budgets are advisory.** Report `make interface-report` for touched
  packages. Do not split modules to meet a budget.
- **Nothing internal.** Examples use `acme/widgets`, `octocat` and `carol`.
- Code carries no comments.
- When the spec leaves a choice open and this plan does not settle it, make
  it and name it in the report.

## Choices this plan settles

- **Where the due check lives.** One pure function in a new module,
  `pr_manager/_rerequest.py`: `due(facts, conversations, queued, now)`
  returns the logins to ask and the logins to drop. `ManagerCommands` gains
  `rerequest_once_due(facts, conversations)`, called from `_tick` beside
  `assign_once_ready`.
- **"Polled after the last Accept settled"** compares `Facts.polled_at` with
  the newest `settled_at` of an applied `approve` operation on any of the PR's
  conversations. No Accept at all satisfies it.
- **"Review body" and "PR comment".** A `review-summary` thread is "review
  body"; an `issue` thread the reviewer opened is "PR comment" and is part of
  their round.
- **What a comment said.** The gist; where there is none, the first line of
  the reviewer's first comment once loaded, else nothing.
- **Keys.** `r` and `o` on the decision prompt; `r` and `n` on the
  Dashboard's.
- **Labels.** The primary is the decision's own `Offer.label` followed by
  " and re-request"; the secondary is the label followed by " only".
- **One prompt per click.** The reviewer is the opener of the thread being
  closed (`opened_by`).

## Steps

### 1. Commented reviewers and when each was asked

`change_detection/_rules.py` writes `review_requested_at` in `snapshot_of`
from the old snapshot and the poll's `pending_reviewers`, stamped with the
poll time. `_facts.py` reads it and `commented_by`; `interface.py`'s `Facts`
gains both. Tests in `tests/change_detection/test_facts.py` and
`test_changes.py`: a commented reviewer is in `commented_by` and not in
`changes_requested_by`; a comment after a change request leaves them in
`changes_requested_by`; a login newly pending is stamped with the poll time;
one still pending keeps its stamp; one that left and came back is
re-stamped; a snapshot without the field reads as an empty map.

### 2. Who opened each thread, on every row

`domain.ThreadRow` gains `opened_by` and `opened_at`; `conversation/_threads.py`
`counts()` fills them from the conversation's author and first comment. The
contract's `ThreadRow` and `Conversation` gain both, `_projection.py` maps
them, and `make contract` regenerates the front end's copy. Tests: a row and
a conversation carry the opener's login and first comment time
(`tests/board_api/test_contract_reads.py` or the nearest existing reads
test), and a draft's row has the viewer and its creation time.

### 3. Facts on the board

`board_api/interface.py`'s `Dashboard` gains `commented_by` and
`review_requested_at`; `_snapshot.py` fills them from `Facts`; the
contract's `PrFacts` gains both and `_projection.py` maps them. `make contract`. The store's facts mapping in `frontend/app/services/store.ts`
lists `commented_by` as it lists `changes_requested_by`, and
`fake-board.ts` defaults both. Tests: `tests/pr_manager/test_dashboard_snapshot.py`
and `tests/board_api/test_contract_manager.py` show both on a PR with a
commented reviewer; `make test` stays green.

### 4. The `Rerequests` store

`settings/interface.py` (protocol), `_switches.py` (`JsonFileRerequests` under
`rerequest_review/`), `fake.py`, `__init__.py`, `wiring.py`. The watcher's
teardown (`watcher/_teardown.py`) forgets a PR's queue beside its reviewer
pick. Contract tests in `tests/settings/test_contract.py` run against disk
and fake: nothing queued at first; a queued login waits until dropped; a
login queued twice is held once; queues are per PR; forgetting an empty PR
succeeds. A teardown test asserts the queue is forgotten.

### 5. Queue and send

`Command.REREQUEST_REVIEW` in `_command_file.py`; `ManagerPanel.rerequest_review`
in `board_api/interface.py`, `pr_manager/_panel.py` and `board_api/fake.py`;
`ManagerCommands._rerequest_review` (refused with `not-yours-to-assign` as
assigning is) and `rerequest_once_due`; `pr_manager/_rerequest.py`;
`_dashboard_source.py` and `Dashboard.rerequest_queued`; the route
`POST /manager:rerequest-review` in `_app.py` with a `RerequestReviewRequest`
body and `DashboardSystem.rerequest_queued` in `_contract.py`. `make contract`. Tests:

- `tests/pr_manager/test_rerequest.py` (new), a table over `due`: CI
  passing and nothing in flight asks; CI pending, failing, an Accept pending
  or running, facts polled before the last Accept settled, an open thread
  from the reviewer, each waits; `none` waits under five minutes after the
  last Accept and asks after; a pending login is dropped, not asked.
- `tests/pr_manager/test_manager_panel.py`: a re-request from the board is
  queued, shows on the dashboard, and is asked on GitHub (through
  `github/fake.py`'s `assign_reviewers`) on the first tick it is due, then
  leaves the queue; refused on someone else's PR; a GitHub refusal shows the
  `assign-reviewers-refused` notice and leaves the queue.
- `tests/board_api/test_contract_manager.py`: the route hands the reviewer
  to the panel and answers 202; an empty reviewer is a 422.

### 6. The next move

`summaries.ts`: rounds per qualifying reviewer from the stored threads
(`opened_by`, `opened_at`, `state`, `record_state`, `author_kind`) and the
facts; owed reviewers; the `rerequest-review` and `rerequest-queued` moves and
the narrowed `address-feedback`, in the spec's order, with
`rerequest-review` in Needs you and `rerequest-queued` in Waiting on others.
`dashboard.ts`: labels, details and reasons for both moves, and both in
`REVIEW_NAMED`. `fake-board.ts` can serve commented reviewers, request stamps,
row openers and a queue. Tests in `frontend/tests/acceptance/next-move-test.ts`
and `wall-test.ts`:

- changes requested with an open thread: "Address changes from carol";
- changes requested, every thread closed: "Re-request review from carol";
- commented, every thread closed: "Re-request review from carol";
- commented with no threads in the round: no re-request move;
- threads opened before `review_requested_at` are not in the round;
- pending, approved, bot: no re-request move;
- queued: "Re-request queued for carol", in Waiting on others;
- a thread waiting on you comes before "Re-request review".

Update the A-table in `docs/superpowers/specs/2026-10-01-next-move-design.md`
in the same commit.

### 7. The prompt on a closing decision

`rerequest-prompt.gts` (new) with kicker, question, badge, summary line, flag
line and buttons; the accordion row stays empty until step 8.
`summaries.ts` gains the prompt's question for a thread and a decision with
what it gathered. `panel-actions.gts` opens it for the six closing decisions
after any decision dialog, posts on a button, queues the re-request through
`pr-controls`' new `rerequestReview` only after the post is accepted, and
cancels the whole click on × or Escape. `decisions.ts` gains the
`rerequest-review` PR write. The glyph that marks a button as opening a
dialog shows on those decisions when the prompt would open. Tests in a new
`frontend/tests/acceptance/rerequest-test.ts`:

- Mark done on carol's last open thread opens the prompt and posts nothing;
- "Mark done and re-request" posts `mark-done`, then `manager:rerequest-review`
  with `carol`;
- "Mark done only" posts `mark-done` alone, and the next move reads
  "Re-request review from carol";
- × posts nothing and the thread stays open;
- Accept, Resolve, Reject, Defer and Reply and mark done show their own dialog
  first, then the prompt, and post what was gathered;
- the labels follow the decision ("Resolve and re-request");
- the badge reads "Changes requested" or "Commented";
- the summary line counts the closing thread's outcome with the others', and
  leaves out zero counts;
- the flag line appears for rejected and for no-reply-no-push comments, and
  not otherwise;
- not the last open thread, pending, approved, a bot: no prompt;
- a refused decision queues nothing.

### 8. The comment list and its history

The accordion row "N comments from <reviewer>" in the ready dialog's
`outstanding-kind` treatment, each comment with where, what, outcome chips
and a closed History row. Opening History calls `store.readThread` for that
thread; the timeline is derived in `summaries.ts` from comments and
operations. Tests in `rerequest-test.ts`: the row is closed by default and
counts the round; where reads `file:line`, "review body" and "PR comment";
chips for pushed, replied, ticket filed, resolved, marked done, rejected and
deferred; History lists the reviewer's comment, the fix, the rework with its
note, the push with its short sha, the reply and the close, oldest first,
with times.

### 9. The Dashboard control

`dashboard-tab.gts` shows "Re-request review" for the `rerequest-review` move;
it opens the prompt without a decision, with "Re-request review" and "Not yet".
Tests: the control is shown only for that move; "Re-request review" posts
`manager:rerequest-review` and the move becomes "Re-request queued for
carol"; "Not yet" posts nothing.

### 10. With the hold warning

`panel-actions.gts`: the hold warning first; "Resume this PR" opens the
prompt, whose buttons post, queue where asked, then resume; × there cancels
the click and the resume; "Back on hold" posts and opens nothing. Tests in
`rerequest-test.ts` on a fake-board PR that is both held with one open
mention and the reviewer's last open thread, since real data does not
produce one (spec section 6).

### 11. Live check

The coordinator restarts every instance and, on
[vector67/acme-widgets](https://github.com/vector67/acme-widgets) under the
`testbed` instance, has a second account leave a commented review with two
comments on a testbed PR, closes one, then the other with "and re-request",
and watches the next move read "Re-request queued for <reviewer>" until CI
passes and GitHub lists the reviewer as requested. Then the same with
"only", checking the Dashboard control. Both themes, console open.

## For the user to decide

- **CI with no checks.** The plan treats `none` as green only five minutes
  after the last Accept settled, because a fresh head has no checks until CI
  starts. Is five minutes right, or should `none` never count as green on a
  repo that has had checks?
- **Taking a queued re-request back.** The spec leaves no way to cancel one.
  Should "Re-request queued" offer one in this version?
