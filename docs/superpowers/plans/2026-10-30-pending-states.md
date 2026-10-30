# Pending states: plan

Carries out [the pending states spec](../specs/2026-10-30-pending-states-design.md).
The spec is the decision. This plan sets the order of the steps and how each one
is judged. Decision numbers (1–11) are the spec's. Issue #227.

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
- **The board holds each server fact once**, in `frontend/app/services/store.ts`;
  derived values live only in `frontend/app/data/summaries.ts`. A pending
  write is a local operation in the store (decision 1), never a flag in a
  component or another service.
- **One look.** Every pending element uses `data-pending`, the one CSS block,
  and the ring from decision 4. No step adds a second class, attribute or
  spinner.
- **Tests** are acceptance or unit tests that assert `data-pending`,
  `data-refused`, the word, the ring's presence, the text shown early and the
  controls held. Never colours, borders, opacity or widths. Hold a request
  open in the test to see the pending state, then answer or refuse it.
- **Budgets.** `make interface-report` must show no package with more exports
  than it has on `main` when the step starts, and no class with more methods.
  A flag or map a step replaces is deleted in that step.
- Code carries no comments.
- Check the look of every step in a real browser in both themes, with console
  logging on, with the request held long enough to see the pending state. Any
  `Uncaught` error fails the check.
- When the spec leaves a choice open, make it, and name it in the report.

## Steps

### 1. The foundation and the draft edit

**Done** in 204b8b69, 0155bdc1 and the commit that adds this line.

Decisions 1, 2, 3, 4 (CSS and tokens only), 6, 7, 8, 9. The store's local
operation (`sent`, `refused`, replacement by `takeOutcome`), `thread.ts`
treating `sent` as `pending`, the `data-pending` and `data-refused` CSS block,
the `--motion-spin` token and the ring element, `http.sent()` registering in
`asking`, and the draft edit moved onto them: `drafts.saving` goes.

Done when: saving an edited draft closes the box at once and the card shows
the new text pending with "Saving"; an answer flashes it; a refusal shows the
old text, the red line and "Edit again", which reopens the box with the typed
text.

### 2. Thread writes: reply, enrol, discard, leave out, send review

**Done** in 669a6d3c, 5296c42e and the commit that adds this line.

Decisions 2, 5 (send review), 6 (reply text), 7. `reply-box.gts`,
`inline-card.gts` (Add to review, Discard, Ask the agent's thread side),
`review-dialog.gts` (Add, Leave out, Send), `comment-box.gts` (Add to review on
a new draft). Their component flags go. Send review gets the ring and lasts
until the operation settles; the enrolled cards and rows carry
`data-pending` while it does.

Done when: each of these shows pending from the click, cannot be clicked twice,
and shows a refusal on the element.

### 3. The panel footer

**Done** in the commit that adds this line.

Decisions 1, 3. `board.acting` moves into the store, so the footer, the rail
row and the inline card for a thread all read one record. `board.acting` and
`isActing` go.

Done when: a decision in the footer marks its rail row and inline card pending
too, and `board.acting` no longer exists.

### 4. PR controls on the dashboard and the wall

Decisions 1, 3, 4, 5, 7. `pr-controls.sent` moves to the PR's store record and
widens to every manager verb, from buttons and keys on `dashboard-tab.gts` and
`wall.gts`. Close PR and Ready for review get the ring and last until the
dashboard shows the fact. Toasts stay only for close and dismiss.

Done when: every manager verb shows pending from the click on both pages, and
`pr-controls.sent` no longer exists.

### 5. The diff page: fetch, reset, mark read, git palette

Decisions 3, 4, 6, 7. `pull-request-diff.ts` `fetching` and the reset's wait
move to the store; the mark-read checkbox shows the ticked value pending;
the git palette's `running` uses the same look. Fetch, reset and the palette
get the ring.

Done when: each shows pending from the click with the ring where decision 4
lists it, and a refusal lands on the element rather than `reportError`.

### 6. Terminal launchers, rebase, ask the agent, harvest

Decisions 3, 4, 5, 7. `rebase-button.gts`, `terminal-tab.gts`,
`comment-box.gts` Ask the agent, `harvest-setup.gts`. All get the ring; a
session the drain opens stays pending until it is listed.

Done when: each launcher shows pending with the ring from the click until the
session is listed or the request is refused.

### 7. Summary and setup

Decisions 3, 4, 10. `summary-tab.gts` (`summarising`) and the setup page's
Check, Start watching and Move aside buttons (`checking`, `writing`,
`moving`). Setup's buttons get the ring; the summary strip's own running state
takes over once the server lists the run.

Done when: those flags no longer exist and each button shows pending with the
word from the click.

### 8. Clean-up

Decision 11. Drop `provisional`. Search the front end for any pending flag
left from the thirteen the spec names and either move it onto the store or
name the constraint that holds it.

Done when: `rg` finds none of the old flags outside the store and the spec
marks every decision Done.
