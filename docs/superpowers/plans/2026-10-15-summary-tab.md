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

The summary becomes an entity in `board_api/_contract.py`, projected in
`_projection.py` and served on its own feed in `_app.py`, with `running`,
`since` and the witness flags. The operations `summarise` and
`summarise-with-github-api` go through the existing operation path. Regenerate
`api.ts` and the contract copy through `tests/board_api/test_contract_copy.py`.
The "N commits behind" count is computed here with `git rev-list --count` in
the local clone.

Done when: API tests cover each field and both operations, including the
If-Match rule.

### 5. The store and derived values

`store.ts` fetches the summaries feed (`FEED_PATHS`) and holds one entity per
PR. `data/summaries.ts` derives the tab's state (the spec's seven), stale or
not, and the chip's count.

Done when: unit tests cover each state and staleness.

### 6. The tab

`pr-view.gts` gets the Summary tab first, with keys 1–5 in screen order in
`takes()`. `router.ts` gets the route, and `routes/pr/index.ts` opens Summary
for reviewer PRs. The tab is the strip and the markdown (`markdownOf`), with
the checklist while running and buttons wired to the step 4 operations.

Done when: component tests cover each strip state and the key mapping, and the
preview shows each state in both themes. Add preview cards for them.

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
