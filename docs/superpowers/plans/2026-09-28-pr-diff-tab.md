# The PR's diff tab: plan

Carries out [the PR diff tab spec](../specs/2026-09-28-pr-diff-tab-design.md).
The spec is the decision; this plan says in what order, and how each step is
judged.

## How to work

- Every change follows `.claude/skills/normal-workflow`. Load `tdd` for
  anything that changes behaviour and `refactor` for reshaping. The user has
  approved running the steps straight through without stopping to confirm.
- Each step is its own branch in its own worktree, cut from local `main`, and
  is merged and restarted before the next step starts.
- Run `make lint-python` and `make test-python` before each commit, the full
  `make lint` and `make test` when `frontend/` changed and once before
  reporting, and report the pass counts. A count that falls fails the check
  unless the commit message names each deleted test and what made it
  impossible.
- The module map's rules hold
  ([2026-09-23-module-map-design.md](../specs/2026-09-23-module-map-design.md)):
  one interface per module, injected by wiring; tests only through interfaces;
  each module's fake passes the same contract tests as the real one; only
  wiring constructs an implementation. `make interface-report` must show every
  touched module within its export budget and method cap.
- Reuse before adding: the proposal diff's parsing (`working_copies`), its
  contract types, and the front end's `DiffSlot` rows, gaps, reveal and
  highlighting. A second copy of any of these fails the step.
- Records already on disk keep reading: a draft without `start_side` reads its
  `side`. The translation lives in one place in the owning module.
- Tests assert behaviour and structure, never colours, borders or widths.
  Code carries no comments (the user's rule).
- Nothing a step does may approve, reject, reply, post, push or dismiss on a
  real PR. Check against scratch data dirs and the dev preview
  (`python -m github_orchestrator.preview`).
- A subprocess a new test spawns for real is recorded with
  `uv run pytest tests/ -k '<tests>' --record`, never by file path, and only
  the new entries are kept.
- When the spec leaves a choice open, make it, record it in the decision log
  with the reason, and name it in the report.

## Steps

1. **The PR's diff served.** Spec items 1–3: the base fetched, and
   `GET /api/pull-request/diff` from the merge base to head, with its OpenAPI
   record, contract tests and the front end's type. **Done** (`f2ddd2b9`,
   `7fe5627f` and the commit that records this).
2. **`start_side` and one-hunk ranges.** Spec items 4–6 end to end: domain,
   store with old records read, `DraftBody`, the anchor, GitHub's
   `startDiffSide`, the review and post-now payloads, the CLI and the agent
   prompt, and the in-diff check. **Done** (`6d63ce7f`, `c488ab18` and the
   commit that records this).
3. **Enrolled drafts edit in place.** Spec item 7, in the state machine, the
   API, its spec rows, the composer's note and the send-review dialog's Edit.
   **Done** (`f8dcb2f1`, `0108c564` and the commit that records this).
4. **The Diff tab.** Spec items 8–15: the tab, the tree, the stacked files,
   selection, the inline comment box and the inline conversations, built as
   the one selectable diff component step 5 reuses. **Done** (`a6edbfeb`,
   `710efd9e`, `0af57980`, `e3cee54d`, `d4437db4` and the commit that records
   this).
5. **The draft panel anchors by selection.** Spec items 16–17: the anchor form
   and the head-only code excerpt go; the panel's right is the component from
   step 4. **Done** (`eb2c3ffc`, `5831339a`, `f2a5dc85`, `7e799c82` and the
   commit that records this).
6. **Documentation.** README, `docs/how-to-use.md` and the web interface
   spec's module map describe the Diff tab and anchoring by selection.
   **Done** (the commit that records this).
