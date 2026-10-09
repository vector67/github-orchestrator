# Motion on the board: plan

Carries out [the board motion spec](../specs/2026-09-29-board-motion-design.md).
The spec is the decision; this plan says in what order, and how each step is
judged.

## How to work

- Every change follows `.claude/skills/normal-workflow`. Load `tdd` for
  anything that changes behaviour and `refactor` for reshaping. The user has
  approved running the steps straight through without stopping to confirm.
- Each step is its own branch in its own worktree, cut from local `main`, and
  is merged and restarted before the next step starts.
- Run `make lint-python` and `make test-python` before each commit. Every step
  here changes `frontend/`, so also run the full `make lint` and `make test`
  before each commit, and report the pass counts. A count that falls fails the
  check unless the commit message names each deleted test and what made it
  impossible.
- Tests assert behaviour and structure, never colours, borders, widths,
  keyframes, durations or easing. What a test asserts is the state that drives
  the motion: which row is marked as having moved, when a label or toast
  arrives and leaves, whether a screen stays, where `scrollTop` ends. From step
  2 on, the test build runs every duration at 0, so the end state is in place
  at `settled()`.
- One motion module. Step 2 puts the duration tokens' JavaScript side, the
  test switch, the reduced-motion check, the FLIP and the collapse in one
  place under `frontend/app/`, and every later step calls it. A second FLIP,
  a second collapse or a duration written as a literal outside it fails the
  step. Durations in CSS come from the `--motion-*` tokens.
- Time-based behaviour (the 10-second "moved here", the toast's wait, the live
  dot's 5 seconds, the banner's two failed polls) is driven so a test can
  advance it. `tests/helpers/fake-clock.ts` swaps `setInterval` and `Date.now`
  but not `setTimeout`; extend the helper rather than sleeping on real time in
  a test.
- No smooth scrolling anywhere. Tests read `scrollTop` synchronously.
- Reuse before adding: the rail's `data-square` edges, the existing
  `.diff-slot[data-updated]` flash and `live-dot`, the toasts service, the
  terminal service. A second copy of any of these fails the step.
- Code carries no comments (the user's rule).
- Check the look of what the step changed, in both themes, in the dev preview
  (`python -m github_orchestrator.preview`, after `make build_frontend`) or
  against the running hub. Take headless Chrome screenshots, look at them, and
  load the page with console logging on: any `Uncaught` error fails the check.
- Nothing a step does may approve, reject, reply, post, push or dismiss on a
  real PR.
- When the spec leaves a choice open, make it, record it in the decision log
  with the reason, and name it in the report.
- Bound every long command with `timeout` (a suite with `timeout 300`), so a
  hang shows as a failure rather than silence.

## Steps

1. **The wall and the rail share their parts.** Spec items 1–4: the wall's rows
   take the rail's edge with the section mapping, the squares go, both lists'
   headers put the count right after the name, and "moved here" shows for 10
   seconds, then fades out. No motion beyond that fade yet.
2. **Tokens, reduced motion and the test switch.** Spec items 5–8: the
   `--motion-*` tokens, the easing, the reduced-motion rules, the one motion
   module with its FLIP and collapse, and the switch that zeroes every duration
   in the test build.
3. **Moves.** Spec items 9–11: rail regroup, wall section change and columns,
   each with its flash.
4. **Decisions and toasts.** Spec items 12–13.
5. **Collapses.** Spec items 14 and 17: draft discard, and a resolved thread you
   are reading staying open with its chip.
6. **j and k.** Spec items 15 and 21: the sliding highlight on the rail and the
   wall, and keeping the selection in view.
7. **Behaviour fixes.** Spec items 16 and 18–20: the banner, the live dot,
   Claude's output keeping your place, and a terminal session keeping its
   screen after its command exits.
