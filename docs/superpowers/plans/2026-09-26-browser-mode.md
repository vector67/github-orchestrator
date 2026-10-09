# Browser mode: plan

Carries out [the browser mode spec](../specs/2026-09-26-browser-mode-design.md).
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
  touched module within its export budget and method cap. A new port a module
  needs is defined by that module (as notifications defines `Standing`), and
  the module that answers it implements it.
- Nothing outside wiring branches on the mode. A module that would need to ask
  "am I in browser mode" is given the thing that differs instead.
- The tmux mode keeps working exactly as before. A step that changes what the
  tmux dashboard shows or does has gone beyond the spec.
- Code carries no comments (the user's rule). Tests assert behaviour, never
  colours, borders or widths.
- A subprocess a new test spawns for real is recorded with
  `uv run pytest tests/ -k '<tests>' --record`, never by file path, and only
  the new entries are kept: revert whatever else `--record` rewrote.
- When the spec leaves a choice open, make it, record it in the decision log
  with the reason, and name it in the report.

## Steps

1. **Done** (`a38d5e7a`..`062411f2`). **Headless PR manager.** `--headless` on `github_orchestrator.pr_manager`: a
   terminal that draws nothing and reads no keys, the board always wanted,
   started at start-up and retried each tick until whose PR this is is known.
   Proven by a test that runs the manager's loop headless through its
   interface, and by running the real process headless against a scratch data
   dir.
2. **Done** (`3d492cab`..`333d1139`). **Background PR windows and the setting.** `pr_windows` in settings,
   `BackgroundPrWindows` in `pr_windows/` passing the shared contract tests
   (with the real process spawning covered by a test that spawns something
   real in a temporary directory), wiring choosing between the two, `split`'s
   refusal, and `config.toml.example` documenting the key.
3. **Done** (`8d7d823f`..`bb4bab1f`). **The manager panel in the board API.** `ManagerPanel` defined by the board
   API and implemented by the PR manager, the command queue and status
   snapshot, the new routes in the OpenAPI contract and their contract tests,
   and the fake board and preview updated to serve them.
4. **Done** (`f35fa9ea`..`c5632a23`). **The manager panel in the board web app.** The status, the buttons, the
   rendered `agent-changes.md` and the Claude output, with front-end tests.
   Checked in the preview in Chrome in both themes, loaded headless with
   console logging and no `Uncaught` error.
5. **Done** (`4cea3038`..`3d8e7bfe`). **The hub.** `hub_port`, the hub role in the board API, the watcher serving
   it in `--loop` and telling it each cycle which PRs it holds, the `prs`
   route in the web app with pause, resume and release, the board's link back,
   and `status` printing the address.
6. **Done** (this commit). **Documentation.** README's requirements (tmux, glow and entr needed only
   in tmux mode), and a browser mode section in `docs/how-to-use.md`.
