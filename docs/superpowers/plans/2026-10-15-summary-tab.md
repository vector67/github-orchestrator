# The Summary tab: plan

Carries out [the Summary tab spec](../specs/2026-10-15-summary-tab-design.md).
The spec is the decision. This plan sets the order of the steps and how each one
is judged. Decision numbers (1–16) are the spec's. Issue #32.

## How to work

- Every change follows `.claude/skills/normal-workflow`. Load `tdd` for
  anything that changes behaviour and `frontend-work` for anything under
  `frontend/`.
- Each step gets its own branch in its own worktree, cut from local `main`. It
  is merged and restarted before the next step starts. The user approved
  running the steps straight through, without stopping to report between them.
- Run `make lint-python` and `make test-python` before each commit. When the
  commit touches `frontend/`, run the full `make lint` and `make test` as well,
  and report the pass counts.
- **The plugin stays standalone.** Nothing under `plugins/pr-summary/` imports
  `github_orchestrator`, and the board calls the plugin only as a command.
- **No real plugin run in tests.** Board tests use a fake plugin script that
  writes the folder layout and prints markdown. Nothing a step does may post
  to a real PR.
- **Budgets.** `make interface-report` must show no package with more exports
  than it has on `main` when the step starts, and no class with more methods,
  except the new summaries package, which starts its own budget. New
  operations go through the existing generic operation path.
- **The board holds each server fact once**, in `frontend/app/services/store.ts`;
  derived values live only in `frontend/app/data/summaries.ts`.
- Tests assert behaviour and structure, never colours, borders or widths.
- Code carries no comments.
- Check the look of any step that changes the board in both themes in the dev
  preview, with console logging on. Any `Uncaught` error fails the check.
- When the spec leaves a choice open, make it, and name it in the report.

## Steps

### 1. The plugin's `--work-dir` flag

**Done** (`cbea5153`, `bc0e4023` and the commit that records this, which makes
the temporary folder only after the GitHub calls when no `--work-dir` is given,
as before). The by-hand run used a local commit, because this repository has no
pull requests: five `output.json` files, with no `requested` folder, since a
local commit has no ticket key.

`plugins/pr-summary/scripts/summarise.py` and `pr_summary/inputs.py`: the flag
writes the witness folders into the given path, creating it if missing and
refusing a non-empty one. Without the flag, behaviour is unchanged. The README
documents the folder layout. A test pins the layout: one folder per witness
(including `alignment`), each holding `output.json` once that witness finishes.

Done when: the plugin's tests pass with the new ones, and a by-hand run with
`--work-dir` on a PR of this repository leaves the six `output.json` files where
the README says.

### 2. The summary record and the due rule

**Done** (`35cb1e1c` and the commit that records this, which sets `wanted`
from the PR manager's carry-out). The package is `pr_summaries`, since
`agent_runs` already exports a `Summaries` role. It exports only
`PrSummaries`: `want`, `load`, `save` and `due`. `save` keeps the stored
`wanted`, so a request made during a run is not lost.

A new package owns `<data_dir>/summaries/<owner>/<repo>/<n>.json` and its
fields (spec, "What is stored"). `ReviewRequested`
(`change_detection/_rules.py:288-292`, launched through
`pr_event_queue/interface.py:69`) sets `wanted` on PRs where your role is
reviewer. A pure function says which PRs are due: `wanted` newer than
`answered`, none in flight, oldest `wanted` first.

Done when: tests cover a first request, a re-request after a review, a push
between requests (not due), a restart with a run lost (due again), and an
author PR (never due by itself).

### 3. The lane and the run

**Done** (`c97e67ce`, `09d3196b`, which offers the lane its turn after each
watcher poll and has a dry run name the summary it would run, and the commit
that records this, which names the run in flight as soon as it takes the
slot). The lane is `SummaryLane` in `pr_summaries`: `poll`, `start(pr, use_github_api=)` for step 4's operations, which returns the reason when it
starts nothing, and `progress(pr)`, the run in flight with its witness flags.
The slot is an flock on `summaries/lane.lock`, which names the PR and when it
started, so the watcher and the server share it; the plugin inherits the lock.
A failed run keeps the earlier summary's `head_sha`, `markdown` and
`mismatches`. `head_sha` is the head the watcher last saw when the run started.
The package carries the plugin through the link
`src/github_orchestrator/plugins/pr-summary`, so a checkout and the wheel run
the same `summarise.py`. The live run on a PR in a watched repository took
about 80 seconds, exited 0 and stored the file with every field.

One slot (decision 6), kept apart from `agent_runs/_summaries.py`, whose 300 s
timeout is too short. Each poll asks step 2 for due PRs and starts the first
when the slot is free. A run follows the spec's "Running":

1. Delete the folder.
2. Run the plugin with `--config` and `--work-dir`, with the clone as the
   working directory.
3. Store stdout without its `Working files:` line, the exit status, stderr,
   `head_sha` and the mismatch count from `alignment/output.json`.
4. Set `answered`.

A run past 25 minutes is killed and stored as failed. A reader reports which
witnesses have an `output.json` while a run is in flight.

Done when: tests with the fake plugin cover a clean run, exit status 3, another
failure, a timeout, a missing or malformed `alignment/output.json`, and the
witness flags partway through. One live run on a PR in a watched repository
produces the stored file.

### 4. The board API

**Done** (`1f3331fe`, which adds `SummaryLane.behind(pr, head)`, `f5d1362d`,
and the commit that records this, which puts the witness flags back to step
3's rule and shares the summary test helpers). The board app serves
`PrSummary` at `GET /api/summary`: the stored fields, `running`, `since`,
`witnesses` (one `{witness, done}` per witness folder the plugin has made, in
the plugin's order, so `requested` is absent on a PR with no ticket and the
list is empty before the inputs are prepared), `behind` and `etag`. The operations are
`POST /api/summary/operations:summarise` and
`/api/summary/operations:summarise-with-github-api`, with the body's `etag` as
`If-Match`; they answer `202` with the summary running, `409 summary-refused`
with the lane's sentence when it starts nothing, and `412` on a moved tag.
`behind` lives in the lane, which holds the clones, because `PrCheckout` is
over its method cap. `pr_summaries` exports `Summary` too. The preview's lane
has agents disabled, so its buttons never run the real plugin.

The summary becomes an entity in `board_api/_contract.py`, projected in
`_projection.py` and served on its own feed in `_app.py`, with `running`,
`since` and the witness flags. The operations `summarise` and
`summarise-with-github-api` go through the existing operation path. Regenerate
`api.ts` and the contract copy through `tests/board_api/test_contract_copy.py`.
The "N commits behind" count is computed here with `git rev-list --count` in
the local clone.

Done when: API tests cover each field and both operations, including the
If-Match rule.

### 5–6. The store, the derived values and the tab

**Done** (`4a9b85c5`, and the commit that records this, which styles the strip
and the summary's tables after the look check and documents the tab and its
keys). The entity is `PrSummary` in the store, read through `prSummary`, which
gives `SummaryTab` from `summaryTabOf` in `data/summaries.ts`; only the Summary
route polls it, every five seconds. `summarise` and `summariseWithGithubApi`
return null when the run started, or the sentence to show: the lane's on a
409, a moved summary read again on a 412. No strip is drawn until the facts
say whose PR it is. The needs-the-GitHub-API strip shows stderr's first line
and the call count from its "about N API calls"; a failed one shows its last
line. The chip's count is left to step 7, which draws it. The preview has no
card for summaries, since its cards are threads; the look check wrote records
into the preview's data directory instead.

One step, not two. The front end has no unit-test path: a test reaches the
board only through its URL, its DOM and FakeBoard (`frontend/eslint.config.mjs`),
so the store and the derived values can only be tested once the tab draws them.

`store.ts` fetches the summary feed (`FEED_PATHS`) and holds one entity per
PR. `data/summaries.ts` derives the tab's state (the spec's seven), stale or
not, and the chip's count.

`pr-view.gts` gets the Summary tab first, with keys 1–5 in screen order in
`takes()`. `router.ts` gets the route, and `routes/pr/index.ts` opens Summary
for reviewer PRs. The tab is the strip and the markdown (`markdownOf`), with
the checklist while running and buttons wired to the step 4 operations.

Done when: acceptance tests cover each strip state, staleness and the key
mapping, and the preview shows each state in both themes.

### 7. The mismatch chip

A chip reading "N mismatches" on the wall row (`components/wall.gts`) and in
the PR header's `.prflags` when the count is above zero.

Done when: component tests cover zero, a count, a stale summary and a missing
count. The preview shows the chip in both themes.

## After the last step

Run one review request end to end on the live board:

1. The summary runs by itself.
2. The tab ticks off the witnesses as they finish.
3. A push marks it stale.
4. A re-request runs it again.

Update the pr-summary plugin's handoff notes and close #32.
