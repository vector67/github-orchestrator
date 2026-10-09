---
name: frontend-work
description: Must be invoked for any requested front-end change in this repository — anything under `frontend/`, the board's look, layout, styles or behaviour in the browser
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
