# Commits on the diff tab: plan

Carries out [the diff tab commits spec](../specs/2026-10-22-diff-tab-commits-design.md).
The spec is the decision. This plan sets the order of the steps and how each one
is judged. Decision numbers (1–16) are the spec's. Issue #145.

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
- **Budgets.** `make interface-report` must show no package with more exports
  than it has on `main` when the step starts, and no class with more methods.
  New writes go through the existing generic operation path.
- **The board holds each server fact once**, in `frontend/app/services/store.ts`;
  derived values (the current commit, the pips, the range, the graph's layout)
  live only in `frontend/app/data/summaries.ts` or a pure module it calls.
- **Preferences stay in the browser, facts on the server.** Commit box sizing,
  the skip-merges box and a dismissed note are localStorage, read and written
  in one service each place they are owned. Read marks are server state.
- **A new API read or field** goes through `board_api/_contract.py`, and the
  contract copy rewrites `frontend/app/data/api.ts` and
  `frontend/tests/helpers/board-api-contract.json`; commit both. A new real-git
  test is recorded with `uv run pytest tests/ -k '<tests>' --record`, never by
  file path, and only its own entries are kept.
- **The graph is drawn from data, not from cases.** One layout function turns
  lanes and commits into positions; each situation in the spec is a test of
  its output, not a branch of code named after it.
- Tests assert behaviour and structure, never colours, borders or widths.
- Code carries no comments.
- Check the look of any step that changes the board in both themes in the dev
  preview (`uv run python -m github_orchestrator.preview --port <free port> --agents-disabled`
  after `make build_frontend`, PR at `/pr/acme/widgets/7/diff`), with console
  logging on. Any `Uncaught` error fails the check. Give the preview's fake
  enough commits to show the step's situations.
- When the spec leaves a choice open, make it, and name it in the report.

## Steps

### 1. API: the PR's commits

**Done** (`f8a8d367`). `GET /pull-request/commits?source=origin|local` returns
`{fork, commits:[{sha, parents, subject, author, authored_at}]}`, oldest first.

### 2. The stepper (Full), with Read on the server

**Done** (`b9d4ce47`, and the commit that marks this). `GET /pull-request/read-marks`
and `operations:mark-read`/`mark-unread` keep the marks beside the thread records.

Decisions 1, 2 and 3. The diff tab gets the commit bar and pips over the diff,
`[` and `]`, and the diff and tree scoped to the current commit. Read marks are
stored per PR on the server with each commit's subject, served with the PR's
commits or beside them, and written through an operation. The store holds the
commits and the marks once.

Done when: tests cover opening on the first unread commit, opening on the last
when all are read, `[` at the first and `]` at the last commit doing nothing,
ticking Read surviving a reload, and the diff request naming one commit's
range.

### 3. Commit box sizing and the note

**Done** (`48cda600`, and the commit that marks this). The review's commit is
`my_review_sha` in the pull request's facts; sizing and dismissed notes are
localStorage in `services/commit-box.ts`.

Decisions 4 and 5. The setting in the gear menu, Minimal and Hidden, and the
"picked up" note with its ×. The note needs your review's commit and time; serve
them with the commits if the board does not already hold them.

Done when: tests cover each size's controls and keys, the note showing only
after a review with commits since, × lasting until the head changes, and Hidden
showing the whole PR.

### 4. The timeline for simple shapes

Decisions 6 to 10. Add the base tip, the behind count and main's commits since
the fork (subjects for hover; `PrCheckout.base_standing` has the count) to the
API. The graph for "main hasn't moved" and "main moved on", one-commit and range
picking, the presets, range mode and Escape.

Done when: tests cover the layout for both shapes, each preset's range, click,
shift-click and handle drags, range mode's text, and Escape returning to the
commit you were on.

### 5. The timeline for merges, stacks, long main, long PRs and local commits

Decisions 11 to 15. The working-copies fake's `FakeCommit` takes more than one
parent. A merge's own diff (its conflict fixes) is a new read or a mode of the
diff read. Stacking needs the base PR's number and commits.

Done when: tests cover each shape's layout, stepping past merges with the box
ticked and stopping on them unticked, a merge's own diff, the collapse and tick
thresholds, and local commits drawn only on local.

### 6. Rebased since your review

Decision 16. The server keeps what your review saw (shas, subjects, the old
fork) so a later push can tell a rebase. The ghost lane, `≈ read` matching by
subject, Since my review leaving out matched commits, and the note's rebase text.

Done when: tests cover a rebase with some commits matched and some new, a
rebase where nothing matches, and a plain push (no ghost lane).
