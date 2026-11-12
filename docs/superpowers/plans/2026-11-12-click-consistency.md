# Click consistency: plan

Carries out [the click consistency spec](../specs/2026-11-12-click-consistency-design.md).
The spec is the decision. This plan sets the order of the steps, how each one
is judged, and the choices the spec left to the build. Rule numbers (01–15)
are the spec's. Issue #366.

## How to work

- Every change follows `.claude/skills/normal-workflow`. Load `tdd` for
  anything that changes behaviour, `refactor` for reshaping, `frontend-work`
  for anything under `frontend/`, and `unslop` for labels and dialog copy.
- Each step gets its own branch in its own worktree, cut from local `main`. It
  is merged and restarted before the next step starts. The user approved
  running the steps straight through, without stopping between them.
- Each step is a vertical slice that is safe to merge alone: server, API
  contract, store and component together. A step never leaves a button whose
  label promises what the server does not do yet.
- Run `make lint-python` and `make test-python` before each commit. When the
  commit touches `frontend/`, run the full `make lint` and `make test` as well,
  and report the pass counts. Run every test command under `timeout`.
- **Proof is tests and fakes.** Domain, application, board API and ember
  acceptance tests against the existing fakes. No step writes to a real PR.
  Step 11 is the one live check.
- **One table for every thread button.** Labels, weights, dialogs, glyphs and
  undos for thread actions live in `frontend/app/data/decisions.ts`; PR-level
  ones in the same file's `PR_WRITES` or beside it. A label written in two
  places is a miss.
- **The board holds each server fact once**, in `frontend/app/services/store.ts`;
  derived values live only in `frontend/app/data/summaries.ts` (or the
  existing `data/panel.ts` / `data/decisions.ts` derivations).
- **Follow the board's look.** Reuse its button weights, `decide-dialog.gts`
  and the toast rail. Check every front-end step in a real browser in both
  themes with the console open; any `Uncaught` error fails the check.
- **Tests** assert behaviour and structure: labels, which actions are offered,
  whether a press opens a dialog, which request goes out, which attributes are
  present (`data-opens-dialog`, `data-runs-agent`). Never colours, borders or
  widths.
- **Data on disk.** Thread records written before a step lack its new fields.
  Read them with the empty default in one place inside the owning adapter
  (`conversation/_adapters/conversation_document.py`); always write the new
  form.
- **Budgets are advisory.** Report `make interface-report` for touched
  packages. Do not split modules to meet a budget.
- **Nothing internal.** Examples use `acme/*`, `octocat` and `PROJ-12`.
- Code carries no comments.
- When the spec leaves a choice open and this plan does not settle it, make it,
  and name it in the report.

## Choices this plan settles

- **The glyphs are derived, never hand-set.** An `Offer` gains `opensDialog`
  and `runsAgent`. `opensDialog` is true when the press opens a dialog, which
  `decisions.ts` already knows from `asks`, minus the red are-you-sure (rule
  03), plus the two maybe-dialogs when the board knows they will open (rule
  05). `runsAgent` comes from one list of decisions and PR verbs that start a
  run. One component draws both glyphs after the label, star first.
- **Red is one plain dialog.** Stop, Drop, Close PR #N and Take over use one
  are-you-sure spec shape (title, one sentence, submit = the button's label,
  Cancel), drawn by the existing dialog. Reject's weight becomes `secondary`.
- **A toast can carry one undo.** `ToastsService.say` takes an optional
  `{ label, run }`. A toast with an undo stays up 8 s, and pausing on hover is
  not required. The undo label is the reverse's own name from rule 04.
- **Bring back remembers where the card came from.** The server records the
  state before each finishing or parking move (Mark done, Resolve, Confirm,
  Defer, Discard, Reject, Move) in one new field on the conversation, and
  `unpark` returns there. A record without it falls back to today's
  behaviour (your move). Rejected and landed still re-run the agent (rule 08).
- **Resolve on a thread GitHub cannot resolve.** An issue comment or a mention
  has no GitHub thread to resolve, so it offers **Reply and mark done ⧉**
  where a review thread offers Resolve. A board-only request offers Mark done
  alone. That keeps rule 11 true without a Resolve that cannot reach GitHub.
- **Author Unresolve on GitHub** widens `_unresolves_on_github` in
  `conversation/_domain/apply.py` to the author role; the effect, failure
  text ("reopen failed: …") and landing (`_thread_unresolved`) are the
  reviewer's, already built. The board learns `github_resolved` through the
  API contract if it does not carry it yet.
- **Drop** (rule 03, author table) returns the thread to the no-agent state:
  fix cleared to its initial value, worktree dropped (`DropWorkspace`), no
  outcome choice. The old `droppedOutcomes` dialog goes.
- **PR undos are new manager commands.** `reopen`, `convert-to-draft` and
  `hand-back` join `pr_manager/_command_file.py`'s `Command`, each with its
  GitHub call behind `github/interface.py` and the fake (hand back ends the
  take-over through `change_detection`'s `end_take_over`).
- **Reset to origin** stays where the commit timeline has it today; the dialog
  replaces the in-place Reset / Cancel. The spec's open question about its
  position is left for the live check.

## Steps

### 1. The glyphs, the underline rule and the tick

Rules 02, 06, 07. The glyph component; `opensDialog` / `runsAgent` on every
thread `Offer` and on the dashboard, wall, strip, diff and commit-timeline
controls listed in the spec; ghost actions become quiet filled buttons and
only links stay underlined; a ticked checkbox draws a tick. No label changes
yet. Proof: acceptance tests that a dialog opener carries
`data-opens-dialog`, an agent starter `data-runs-agent`, an action is a
`<button>` and a link an `<a>`.

### 2. Red are-you-sure

Rule 03. Stop, Close PR #N and Take over get the plain red dialog and lose the
window icon; Reject turns secondary and keeps its dialog. (Drop joins in step
6, with its new behaviour.) Proof: each red button opens the plain dialog
whose submit repeats its label; Reject is not destructive.

### 3. Names

Rule 15 and rule 01: every rename in the list, each dialog's submit repeating
its opener, sentence case, and the reviewer's footer Reply moved beside the
comment as "Reply to <name>" (rule 13). Includes keyboard legend entries in
`data/shortcuts.ts`. Proof: tests assert the new labels per state (never an
absence test for an old one), and the report shows `rg` for each old name in
`frontend/app` coming back empty.

### 4. Resolve reaches GitHub, Mark done stays on the board

Rule 11 (first paragraph) and rule 05's hold warning. Author and reviewer
Resolve resolve on GitHub through a dialog with an optional reply and no
resolve tick box; Mark done finishes on the board at once (today's
`resolve-on-board` / `resolve-here` with nothing typed). Non-review threads
per this plan's choice. Mark done carries the window icon only on the card
where it opens the hold warning. Footers match the spec's tables for these
buttons, including Waiting: Stop waiting, Mark done, Resolve, Defer (rule 09).

### 5. Toast undos and Bring back to the previous state

Rules 04 and 08. The toast undo, the server's remembered state, and the
toasts: Mark done → Bring back, author Confirm (acts at once) → Bring back,
Resolve → Unresolve on GitHub, Discard → Bring back, Add to review → Leave out
of review. The card's Bring back and the toast's do the same request. Bring
back after Reject or a landed fix carries the star.

### 6. Unresolve on GitHub for the author, and Drop

Rule 11 (second paragraph) and the author table's Drop. Author Unresolve on
GitHub on a Done review thread GitHub shows resolved, Bring back otherwise.
Drop with the red are-you-sure "Drop the agent's question?" and the no-agent
landing, offering Write a fix, Resolve, Mark done, Defer.

### 7. The agent's line on an assumed-done thread

Rule 10. The agent's reason, then `Agent proposal: <what Confirm does>`,
derived from what Confirm's request will do; "Claude suggests" and the
"Addressed" heading go. The reviewer's Confirm opens its dialog with the
GitHub steps ticked.

### 8. Posting to GitHub…

Rule 12. Post now acts at once (its dialog goes); Post now, a reply and a
reaction show "Posting to GitHub…" in place of the card's buttons until the
fact arrives, through the pending-states design's `data-pending`.

### 9. PR undos

Rule 04 on the dashboard. Close PR #N → toast Reopen PR #N; Ready for review
→ toast Convert to draft; Take over → toast Hand back. Server commands per
this plan's choice. Ready for review's dialog keeps Assign reviewers on top.

### 10. Everything else in the spec's tables

Agent sessions-driven window icon on Request change, the mention's Ask the
agent and the answer buttons (rule 05); Dismiss ⧉ on the dashboard and wall
row; Release asks first; Check all threads for fixes ✦; the commit timeline's
Reset to origin dialog naming the commits it drops; the git palette's Force
push row that asks first; Settings' Harvest toggle and "Set up Harvest" link;
the diff's local-draft and new-comment controls; Send review · N ⧉. Each
spec table row is checked off in the report.

### 11. Live check

On the testbed (`vector67/acme-widgets`, the `testbed` instance), walk each
spec table in Chrome in both themes: every glyph, every red dialog, each toast
undo, Unresolve on GitHub, Drop, Posting to GitHub…, and the PR undos on a
throwaway PR. File what fails and fix it before closing #366.
