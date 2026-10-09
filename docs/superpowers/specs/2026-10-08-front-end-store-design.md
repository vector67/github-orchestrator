# One front-end store

Date: 2026-10-08. Issue #218. Grilled on, with every answer recorded, at
(private design page).

## Problem

The board shows the same fact in several places. Each copy reaches the browser
through its own request on its own timer, and some copies are computed by
different rules, so the page contradicts itself.

- **Human comments on widgets#56.** Once a fix had landed, the conversation
  list showed every thread Done. The header still said "Human comments · 6/7
  done", the PRs menu "3 need you" and the Board tab "1 ready, 2 answered". One
  hub poll later they flipped to "Waiting on reviewers", 7/7, 2 need you. The list
  comes from `/api/conversations`. The four lagging pieces come from the hub's
  copy of the dashboard, `/api/pull-requests`. Nothing refreshes that copy after
  a board action, and the hub may reuse a board's answer for up to 30s.
- **The proposed diff on the same PR.** After `thread base --sha` moved a fix's
  base, the fold header kept saying "Proposed diff · 47 files" over the new 1-file
  diff until a reload. The count comes from the conversation's details, which are
  refetched only when the conversation etag moves, and that etag does not hash
  `base_sha`. The diff body revalidates on its own.

A survey found 21 facts shown in more than one place. The table is on the
grilling page. They drift for six reasons:

- **Two copies of PR state.** The hub copy and the board copy are separate
  documents. Which one a view shows depends on the route and on whether a stream
  is open.
- **Counts computed twice.** Python's `_tally` and the browser's
  `groupOf`/`phaseOf` count the same threads by different rules. Some "ready" and
  "working" numbers count the run queue rather than threads.
- **A server copy that lags by design.** The manager draws the dashboard before
  it applies thread news in the same tick.
- **Actions refresh only part of the page.** A board write refreshes the
  conversation list and nothing else.
- **Invalidation keys that miss fields.** The details follow an etag that does
  not cover everything they depend on.
- **No way to order two copies.** ETags hash bodies, and nothing else on the
  server is stamped or numbered, so the browser cannot tell which copy is newer.

## The rule

**One source for every piece of information.** Each thing the server knows about
(a PR, a thread, an operation, a proposal, a diff) exists in exactly one place
in the store. Every view reads that one entity. Nothing holds a second copy of
it, whole or in part, under another name.

A summary is a value derived from entities: a count, a badge, the next move, a
wall group, a file count. Summaries are not sources. Keep them as few as
possible: a view reads the entities as they are, and a summary exists only where
a view needs a derived value. Each one is defined once, as a memoized function
of the entities it reads, so it is recomputed only when they change. No
component, helper or service computes its own copy.

The rule is enforced two ways:

- **An ESLint boundary on `app/`.** Only the store imports `data/http`.
  Components and helpers do not inject loaders. Summary functions live in one
  summaries module that only the store imports. This uses the
  `no-restricted-imports` mechanism the tests already have in
  `frontend/eslint.config.mjs`.
- **A stated rule.** A line in CLAUDE.md and in the `frontend-work` skill.

Amended on 2026-10-08, during step 3, by the owner: an earlier version kept one
record per PR holding a thread's board read and its hub row side by side, and
stored summaries on the record. That held two copies of each thread and turned
the summaries into a second source. This version replaces it.

## The store

The store holds entities, one place each:

- **PRs**, keyed `repo#number`. The GitHub facts and manager flags are fields of
  the PR, not separate records.
- **Threads**, keyed by thread key, each naming its PR.
- **Operations**, keyed by id, each naming its thread.
- **Proposals**, keyed by id, each naming its thread.
- **Diffs**, keyed `base..head`.

A PR's threads are the threads that name it. They are found, not copied onto
the PR.

**Information in.** Every response from the server writes into the store,
whichever request brought it: hub rows, board reads and write responses alike.
The store does not wait to be told something changed. It takes in whatever
arrives. A response is never kept whole. It is taken apart into the entities it
carries, and each part merges into that one entity. A hub row's compact view of
a thread and the board's full read of it land in the same thread.

**Newer wins.** Every entity carries the time it last changed. An arriving copy
that is not older than the entity overlays the fields it carries and moves the
entity's stamp. One that is older is dropped.

- Threads already stamp `updated_at` on every save (`record_schema.py:514-518`).
- GitHub facts gain a `polled_at` written with the snapshot.
- Manager flags gain a `changed_at`.

Everything runs on one machine, so stamps from different processes share a
clock.

**Fetching.** Today's timers stay, a 1s operations poll and 5s list, hub and
dashboard polls, and every one of them writes into the store. A change made
elsewhere (an agent's step, the watcher's GitHub poll) can take up to 5s to
show. That is the accepted cost of not adding a stream.

`PrScope` no longer throws per-PR state away on navigation. Entities outlive
leaving a PR's page, because the hub keeps writing into them.

## The next move

`next_move` (`pr_manager/_next_move.py`) moves into the front end as one of the
store's summaries. Its only Python caller is `dashboard_of`, and no server code
acts on the move: notifications come from thread news, and `start_review` does
not check it. `reviewed_before` stays in Python, because it reads `my_review`
alone to choose review or re-review when an agent launches.

This reverses one choice in `2026-10-01-next-move-design.md`. That spec put the
decision in the back end so that any interface could word it. Its rules,
precedence and wall groups stand. The code that decides them now lives in
TypeScript.

To compute the move for every PR on the wall, each hub row ships:

- the 14 GitHub facts the move reads. These six are not sent today: the full
  `merge_state`, `viewer_requested`, `ended`, `draft`, `mentions` and
  `my_review_at`.
- the manager flags.
- one compact row per thread: `{standing, state, author_kind}`.

The port is proven by porting the 35 cases in
`tests/pr_manager/test_your_move.py` to front-end unit tests. The acceptance
fixtures in `tests/helpers/fake-board.ts` stop hard-coding `move` and `group`
(about 105 literals, 70 of them in wall-test) and supply facts instead.

**What leaves Python with it:**

- The terminal dashboard drops its action label, the READY TO MERGE banner and
  the detail line (`pr_manager/_dashboard.py:771-810`). Everything else it shows
  stays.
- The hub's `Moves` (`board_api/_wall.py:62-96`) goes. The store orders the wall
  and stamps "moved here" itself when a PR's computed group changes. Like today,
  that history is lost on a reload.

## Proposals and diffs

A diff is addressed by its commits, `base..head`, through a new endpoint, so a
diff never changes and is stored for good. The proposal entity carries its
`commits`. The fold's file count becomes a summary computed from the stored diff.
A moved base is new commits, so it means a new diff. The count and the diff
cannot disagree, because they come from the same stored diff.

The proposal itself is refetched when its stamp moves, and moving the base saves
the record, which moves the stamp. This replaces relying on the conversation etag
to cover the shas.

## Clicks

A conversation write answers 202 with the conversation as the server's dry run
says it will become. The server already dry-runs `apply` to detect refusals
(`conversation/_application/asking.py:239-275`) and today throws the result away.
The store writes the projection in at once, marked provisional, so counts and the
move change on the click itself. The next server copy with a later stamp replaces
it, whatever it says.

On hold, or when a verb that touches GitHub fails, the projection shows a state
that arrives late or never, then corrects.

## Order

Each step ends in something checkable on the board.

1. The store and PR records, with every fetch writing into them. The counts
   summary, header and badges read from the store. This fixes the first
   incident.
2. Port the move, with the 35 cases.
3. Hub rows into the same records. The wall's order and "moved here" come from
   the store, and the terminal drops its move line.
4. Proposals and diffs by commits. This fixes the second incident.
5. Optimistic outcomes from the dry run.
6. The lint boundary and stated rule go on, and the old holders are deleted.

## Decisions

The grilling's record, one line per question. The page holds each question's
evidence and the options weighed.

| #   | Question                                         | Answer                                                                                                                                                                                      |
| --- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Q1  | Where do summaries come from?                    | The front end, against a recommended server snapshot. "The frontend mustn't compute any summary information in more than one place, and once computed it must be stored back in the store." |
| Q2  | Does the next move move into the browser?        | Yes, the whole move. A shared rule table that both Python and TypeScript interpret was also weighed.                                                                                        |
| Q3  | The server's displays of the move                | Drop the move line from the terminal; the store orders the wall.                                                                                                                            |
| Q4  | Proving the port                                 | Port the 35 cases. No shadow run.                                                                                                                                                           |
| Q5  | Store shape                                      | One record per PR.                                                                                                                                                                          |
| Q6  | Newer versus older                               | A stamp on each entity.                                                                                                                                                                     |
| Q7  | Proposal and diff                                | Address diffs by commits; the file count is a summary of the diff.                                                                                                                          |
| Q8  | How the store learns of changes                  | It doesn't: "It is updated as soon as any information comes in from the server no matter where that information comes from."                                                                |
| Q9  | A click before the server settles it             | Move the state in the store at once.                                                                                                                                                        |
| Q10 | What stops a component computing its own copy    | The lint boundary, plus a stated rule.                                                                                                                                                      |
| Q11 | Order                                            | Tracer bullet first.                                                                                                                                                                        |
| Q12 | What triggers fetches for changes made elsewhere | Keep the timers. A change stream was weighed.                                                                                                                                               |
| Q13 | Where a click's expected outcome comes from      | The server's dry run, in the 202 answer.                                                                                                                                                    |
