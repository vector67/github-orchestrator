# The web interface: plan

Carries out [the web interface spec](../specs/2026-09-28-web-interface-design.md)
and the design page beside it. The spec and the page are the decision; this
plan says in what order, and how each step is judged.

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
  touched module within its export budget and method cap. A port a module needs
  is defined by that module, and the module that answers it implements it.
- Nothing outside wiring branches on tmux versus browser mode.
- The tmux mode keeps working. The tmux dashboard's frames stay as they are
  unless a step says otherwise.
- The web interface matches the design page: layout, hierarchy rules, words and
  keys. Where the page is silent, follow its hierarchy rules and record the
  choice. Tests assert behaviour and structure, never colours, borders or
  widths.
- Code carries no comments (the user's rule).
- The machine runs in browser mode on the user's real PRs. Nothing a step does
  may approve, reject, reply, post, push or dismiss on a real PR. Check against
  scratch data dirs and the dev preview (`python -m github_orchestrator.preview`).
- A subprocess a new test spawns for real is recorded with
  `uv run pytest tests/ -k '<tests>' --record`, never by file path, and only
  the new entries are kept.
- When the spec leaves a choice open, make it, record it in the decision log
  with the reason, and name it in the report.

## Steps

01. **One module swap for the mode.** Split the PR manager into its loop (the
    same in both modes) and a front behind one interface: the terminal front
    draws the dashboard and reads keys, the browser front draws nothing and keeps
    the board up. Drop `--headless`; each process's wiring reads `pr_windows` and
    picks a matching pair (tmux windows with the terminal front, background
    managers with the browser front). The five mode checks from 2026-09-26 go.
02. **The dashboard as data.** One typed snapshot holding every field the
    terminal dashboard shows (PR, status, action and its detail, system, since
    you last acted, the freeze screen, the dismiss wording) and the "your move"
    verb, computed once. The terminal dashboard renders from it with its frames
    unchanged. The board API serves it in place of `/api/manager`'s status, and
    the OpenAPI record and contract tests follow.
03. **One origin.** The hub proxies `/pr/<number>/api/...` to that PR's board
    and serves the app for `/pr/<number>/...`. The Ember app takes its API base
    from the route, so one build serves the wall and every PR.
04. **The wall feed.** The hub's list carries, per PR, the wall's fields from the
    step 2 snapshot, its urgency group and verb (computed once, server-side,
    following the page's grouping), and whether it changed group since the last
    read.
05. **The wall, the PR view and the Board tab.** The wall as the home page, the
    PR view with its PR bar and Board | Dashboard | Terminal tabs, the wall
    disappearing, the switcher, the hierarchy rules, and the existing board
    inside the Board tab at full width with its counts strip. The old PR list and
    the board's own header go.
06. **The Dashboard tab.** The full dashboard from the step 2 snapshot, the live
    notes and Claude output beside it, pause, carry on, dismiss with its
    confirmation, release on a frozen PR, and the git palette's captured commands
    run in the page with log and diff read-only. The Manager page goes.
07. **Live streams.** Notes and Claude output stream to the page (server-sent
    events) instead of being polled.
08. **The Terminal tab.** A pty per worktree in the PR manager, carried over a
    websocket to xterm.js, living as long as the page's connection. In
    browser mode the terminal replaces `split`: the git palette's split commands,
    `g r` and the board's steered session open there. **Done** (`f5ce0302`,
    `8dc09865`, `0423a471`, `049f8d35` and the commit that records this).
09. **Notifications open the PR** on its Board, at `/pr/<number>` on the hub.
    **Done** (`c0d7168d` and the commit that records this).
10. **The Runs page** from the design: the run ledger and the watcher's health.
    **Done** (`37974fd2`, `eece68db`, `08438b69`, `27e95110` and the commit that records this).
11. **Documentation.** README and `docs/how-to-use.md` describe the wall, the
    PR view and the Terminal tab, and drop what went. **Done** (the commit that
    records this).
