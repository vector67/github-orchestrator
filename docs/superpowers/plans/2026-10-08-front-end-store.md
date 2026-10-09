# One front-end store: plan

Carries out [the front-end store spec](../specs/2026-10-08-front-end-store-design.md).
The spec is the decision. This plan sets the order of the steps and how each one
is judged. Its step list splits the spec's "Port the move" in two: the server
first ships the move's inputs, then the browser computes the move from them. The
port can't be checked on a page until the inputs arrive.

## How to work

- Every change follows `.claude/skills/normal-workflow`. Load `tdd` for
  anything that changes behaviour and `refactor` for reshaping. The user has
  approved running the steps straight through without stopping to confirm.
- Each step gets its own branch in its own worktree, cut from local `main`. It
  is merged and restarted before the next step starts.
- Run `make lint-python` and `make test-python` before each commit. When the
  commit touches `frontend/`, run the full `make lint` and `make test` as well,
  and report the pass counts. A falling count fails the check unless the commit
  message names each deleted test and what made it impossible.
- **One source for every piece of information.** The store is one service,
  `frontend/app/services/store.ts`, holding entities, one place each: PRs by
  `repo#number` (GitHub facts and manager flags are PR fields), threads by key,
  operations by id, proposals by id, diffs by `base..head`. Any of these fails
  the step:
  - a second copy of an entity, whole or partial, anywhere: a stored response
    (such as a whole `Dashboard`), a side table of rows beside the threads, a
    service keeping a body for itself;
  - a response that is not taken apart into the entities it carries and merged
    into each;
  - a summary stored as state, or computed outside the store's summaries module
    `frontend/app/data/summaries.ts`. A summary is a memoized function of the
    entities, and only exists where a view needs a derived value; a view that
    can read an entity reads it;
  - a count, move or group taken from the server's `Dashboard` for a view the
    step has moved onto the store.
- **Newer wins.** An arriving copy of an entity that is not older than the
  entity overlays the fields it carries and moves the stamp; an older one is
  dropped. Threads use `updated_at`, PR facts `polled_at`, PR flags
  `changed_at`. An entity with no stamp yet takes whatever arrives.
- **One copy of every rule.** No second copy of the bot list (`claude`, `codex`,
  `copilot`): the server sends each thread's author kind (`mine`, `human`,
  `bot`). No second copy of the move's rules: once step 3 lands, the move lives
  only in `summaries.ts`, and `pr_manager/_next_move.py` keeps nothing but
  `reviewed_before`. Wording stays where it is today, in
  `frontend/app/data/dashboard.ts`.
- **Tests go through the page.** The front end's test lint allows a test to
  import only `frontend/tests/`, the app entry and `data/api` types. So the
  move's 35 cases become acceptance tests: each builds facts in
  `tests/helpers/fake-board.ts`, visits the page and reads the move code from
  the DOM. Expose the code as a `data-move` attribute on the NEXT box and on
  each wall row if it isn't there already. Don't loosen the test lint.
- **The contract.** Contract changes go into `board_api/_contract.py`, then
  `api.ts` and the contract copy are regenerated through
  `tests/board_api/test_contract_copy.py`. `fake-board.ts` checks itself
  against the contract (`driftFromTheContract`), so the fixtures change shape
  in the same commit. A new field that a disk record lacks reads as null.
- **Budgets.** `make interface-report` must show no package with more exports
  than it has on `main` when the step starts, and no class with more methods.
  `board_api` is at its budget, so a new export there replaces one. Data fields
  on a dataclass or model are not methods.
- **Data on disk.** Snapshots, thread records and queue files written before a
  step still load. Read a missing key as its old meaning, write the new form,
  and keep the translation in one place inside the module that owns the file.
- **No GitHub writes.** Nothing a step does may approve, reject, reply, post,
  push, resolve or dismiss on a real PR.
- Tests assert behaviour and structure, never colours, borders or widths.
- Code carries no comments (the user's rule).
- Check the look of any step that changes the board, in both themes, against
  the running hub after `make restart-all`, or in the dev preview
  (`python -m github_orchestrator.preview`, after `make build_frontend`). Take
  headless Chrome screenshots, look at them, and load the page with console
  logging on. Any `Uncaught` error fails the check.
- When the spec leaves a choice open, make it, record it in the decision log
  with the reason, and name it in the report.
- Bound every long command with `timeout` (a suite with `timeout 300`), so a
  hang shows up as a failure rather than silence.
- When a step finishes, mark it **Done** below with its last commit hash, in
  the same commit as its last code change.

## Steps

1. **The store, fed by every fetch; the open PR's counts from it.** **Done**
   (`a459ed5d`, `c90607fd` and the commit that records this)

   - Add `store.ts` and `summaries.ts`.
   - `ThreadsService`, `HubService`, `DashboardService`, `ReviewService` and
     `BoardService` write every response they get into the store: the
     conversation list, operations, pull request, the hub's rows, the dashboard
     poll and stream, and write answers.
   - `PrScope` stops discarding per-PR data on navigation.
   - The conversation contract gains what the counts need, where it's missing:
     `updated_at` and the author kind.
   - The summaries module computes, per PR, from the record's threads:
     - the thread counts per group;
     - threads waiting on you ("ready", "answered", drafts);
     - your threads answered;
     - the human and bot tallies the move reads: to decide, agent on, done and
       total. Port these from `_tally` and `counts()` in
       `conversation/_threads.py`, own and unsent threads left out, bots by
       the server's author kind.
   - These views read them from the store for the open PR:
     - the header's "Human comments x/y done" and "Bot comments" chips;
     - the Board tab badge;
     - the board strip's chips.
   - The page no longer shows the incident's mismatch between the list and the
     chips after an accept.
   - The NEXT label still comes from the server's move until step 3.

2. **The server ships the move's inputs.** **Done** (`56759d29`, `c697ce5d`,
   `4e5eb39a` and the commit that records this) Ship them on the `Dashboard`, which
   both the board's `/api/dashboard` and every hub row carry:

   - the 14 GitHub facts `next_move` reads (`ended`, `is_author`,
     `changes_requested_by`, `pending_reviewers`, `ci_status`, the full
     `merge_state`, `draft`, `review_decision`, `my_review`, `my_review_at`,
     `viewer_requested`, `mentioned`, `mentions` and `unresolved_threads`), with
     the snapshot's `polled_at`;
   - the manager flags `frozen_on`, `on_hold`, `working_on`, `hidden` and
     `threads_live`, with a `changed_at`;
   - one compact row per thread, `{key, standing, state, author_kind, updated_at}`.

   The watcher writes `polled_at` into the snapshot, and the manager stamps
   `changed_at` when a flag changes. Snapshots written before this step load
   with a null `polled_at`. The store takes all of it into the PR records, so a
   hub row's thread rows fill the record of a PR whose page isn't open. The
   existing move fields stay for now, so nothing on the page changes.

3. **The move in the browser, on one entity per thing.** **Done** (`66014069`,
   `f48abc60`, superseded by `9e0b27c3`, `3fb7c28c` and the commit that records
   this)

   - **One source first.** Rebuild the store from steps 1 and 2 into entities,
     one place each, as "How to work" says: no `rows` beside `threads`, no
     stored `dashboard`, no `facts` or `flags` records apart from the PR, no
     `summaries` field. Hub rows and board reads merge into the same thread.
     The existing summaries become memoized functions in `summaries.ts`, and
     only those a view needs stay.

   - **Port and test.** Port `next_move`, `_on_top`, `_of_pr` and `_group` into
     `summaries.ts` as a per-PR summary over the record. Port the 35 cases of
     `tests/pr_manager/test_your_move.py` as acceptance tests (see "Tests go
     through the page").

   - **Views read the stored move.** Every view of a move or group reads the
     store: the NEXT box, the Dashboard band, the wall rows and sections, the
     PRs menu's "need you", the switcher, and the review-button gate.

   - **The wall.** The store orders the wall by group and join order, and
     stamps "moved here" when a PR's computed group changes. The tag shows
     until you open that PR, as the web spec intended.

   - **Server removals.** Delete the hub's `Moves`, and the `move*`, `group`
     and `flags` fields from the contract and `dashboard_of`. Drop the
     terminal dashboard's action label, READY TO MERGE banner and detail line.
     Delete `next_move` and its Python tests, keeping `reviewed_before` and
     its tests.

   - **Fixtures.** They supply facts instead of `move` and `group`.

4. **Proposals and diffs by commits.** **Done** (`c9fd3c70` and the commit
   that records this; with step 3's review fixes `371c7c85`, `8a9421df`,
   `0f128c78`, `e854ee73`)

   - Add a diff endpoint addressed by base and head shas. The proposal in the
     contract carries its `commits` and an `updated_at`. `MoveBase` saving the
     record moves that stamp.
   - The store keeps diffs by `base..head`, for good. The fold's file count is
     a summary of the stored diff, and the diff slot reads the same stored
     diff.
   - Delete the proposal-id diff route and `ReadsService`'s proposal-diff use.
   - The page no longer shows the "47 files" mismatch after a base moves.

5. **Optimistic outcomes.** **Done** (`bc70e162` and the commit that records
   this)

   - A conversation write's 202 answer carries the conversation as `ask`'s dry
     run says it will become. `asking.py` already computes it to check for
     refusals.
   - The store writes it in at once, marked provisional, and the next copy
     with a later stamp replaces it.
   - Counts, the move and the thread's row change on the click.
   - A refused write leaves the store as it was.

6. **The boundary, the stated rule, the old holders gone.** **Done** (`4f848937`,
   `42f554d2`, `f4c32142`, `98cf23b7`, `2b5b2805` and the commit that records this)

   - An ESLint rule on `app/`:
     - only `store.ts` imports `data/http` and `data/stream`;
     - only `store.ts` imports `summaries.ts`;
     - components and helpers inject no service that fetches.
   - A line in CLAUDE.md and in `.claude/skills/frontend-work/SKILL.md` states
     the rule.
   - Delete what the store replaced: `Polled` bodies kept outside the store,
     per-service copies of server data, and the server's thread tallies in
     `Dashboard.status` that no view reads any more.
   - The browser-side holders listed in the spec's survey are gone or reduced
     to loaders that write into the store.
