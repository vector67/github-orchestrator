---
name: frontend-work
description: Must be invoked for any requested front-end change in this repository — anything under `frontend/`, the board's look, layout, styles or behaviour in the browser — and for mockups or design drafts of a board screen
---

# Frontend work

- **Server data lives once, in the store.** Only `services/store.ts` talks to
  the server and imports `data/summaries.ts`; views read the store and never
  inject the loader, `services/poll`. ESLint refuses the imports; a copy kept
  elsewhere drifts and the page contradicts itself.

- **Prove every front-end change in a real browser, with screenshots.** Use the
  Claude in Chrome plugin. When its tools are not in the session, drive headless
  Chrome with [`helper.sh`](helper.sh), whose commands mirror the plugin's tools:

  ```bash
  H=.claude/skills/frontend-work/helper.sh
  $H start                                  # headless Chrome on port 9333
  $H navigate http://127.0.0.1:8791/pr/acme/widgets/7/diff
  $H hover '[data-test-file-path]'
  $H js 'document.title'
  $H screenshot "$SCRATCH/diff.png"         # then Read the PNG to look at it
  $H stop
  ```

  `helper.sh` with no arguments lists every command. Each one prints the console
  and any `Uncaught` error raised while it ran, and exits 1 on an uncaught error:
  that is a failed check even when the screenshot looks right.

  Check each popup, menu or picker in its worst position (the last item of a
  scrolling box, the window's edges) everywhere the component renders: compare
  its `getBoundingClientRect` with its container's and take a full screenshot,
  never only a crop of where you expect it. A crop shows what you expected.

  Check what only reads (opening, layout, scrolling) on the live board's real
  threads; the preview's made-up data hides the shapes layout bugs live in. Keep
  the preview for the steps that write to GitHub.

- **A temporary overlay goes in the top layer.** Open a picker or menu as a
  popover placed at its trigger, never in the page flow (it pushes everything
  down) or inside a box that clips it. Its test asserts it is fully visible and
  that nothing else moved.

- **A named reference UI is the spec.** When the ask is "like GitHub" or another
  product, list how the reference behaves (overlays or pushes, what moves, how it
  closes) and assert each, not only the symptom reported; a fix that passes the
  symptom test can still break the reference.

- **Mock up from the running board.** A mockup or design draft of a board screen
  starts from `helper.sh` screenshots of the live board (each PR at
  `/pr/<owner>/<repo>/<n>/` on the hub) and reuses only treatments the board
  already has. The hub generates its colours and fonts at runtime and serves
  them at `/palette.css` and `/fonts.css`; `frontend/app/styles` holds none.
