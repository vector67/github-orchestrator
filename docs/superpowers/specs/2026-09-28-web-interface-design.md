# The web interface

The design is the page beside this file,
[2026-09-28-web-interface-design.html](2026-09-28-web-interface-design.html),
version 3 of a design artifact (private design page). Open it in a
browser. Its mockups, hierarchy rules, keys, the table of where each dashboard
field sits, and the plumbing section are the decision. Its PRs, CI states,
timings, notes and transcripts are made up; the real interface shows real data.
This file records what the user settled on top of the page and what the page
leaves to the implementation.

It replaces the browser layer built on 2026-09-26 (the hub's PR list, the
per-PR board on its own address, the board's Manager page). The background
managers and the `pr_windows` setting from that work stay.

README and `docs/how-to-use.md` describe the wall, the PR view, its tabs, the
Runs page and notification clicks, and no longer describe the hub's PR list,
the Manager page or browser mode's refused splits. **Done** (the commit that
records this).

## Settled by the user (2026-09-27/28)

- The wall is home. Clicking a PR makes the wall disappear; the PR view takes
  the whole screen with the tabs **Board | Dashboard | Terminal**. A PR always
  opens on Board.
- A left switcher, closed by default, shows each PR's verb stepped down by
  urgency group and slides away once a PR is picked.
- Grouping by urgency wins over rows staying put. A row that moved is tagged
  until opened.
- Yellow is information or a possible warning; red is an error or urgent.
  "You are the detailed reviewer" is yellow text on a grey box. Faint text stays
  legible, even when that means a row wraps.
- tmux mode stays. The dashboard's fields and the "your move" verb are computed
  once, as data, and both the tmux dashboard and the web dashboard draw from
  that one definition. Since the architecture review of 2026-10-01
  (candidate 3), the data is facts and codes: the server picks the move's
  branch (`move`) with its group, and each front end words what it draws, the
  web one in `frontend/app/data/dashboard.ts` and the tmux one in
  `pr_manager/_dashboard.py`.
- Clicking a desktop notification opens that PR on its Board. **Done**
  (`c0d7168d` and the commit that records this): in browser mode a
  notification about one PR opens `/pr/<number>` on the instance's own hub,
  from `hub_port`. One about no PR, a closed one, or Claude skipping events on several,
  opens nothing. In tmux mode no notification carries a link.
- The terminal is an embedded tab in the page (a pty in the worktree), not an
  external app. `add -p`, commit, `rebase -i`, `g r`, the free shell and the
  board's steered session run there. **Done** (`f5ce0302`, `8dc09865`,
  `0423a471`, `049f8d35`): in browser mode, where the terminal replaces
  `split`. In tmux mode they still open tmux panes and the tab lists no
  session for them.
- Draft review comments sit in the thread with the other comments, as the board
  does today.
- A fourth tab, **Diff**, key `4`, route `pr.diff`, draws the PR's diff from
  its merge base to head the way GitHub's Files changed does, and a draft is
  anchored by selecting lines in it or in the one diff component the board's
  draft panel draws beside the comment. The page's file, from line, line and
  side form in #41's composer, and the head-only excerpt beside it, are gone;
  so is withdrawing a draft from the review to edit it. Settled in
  [the PR diff tab spec](2026-09-28-pr-diff-tab-design.md). **Done** (steps 1–5
  of [its plan](../plans/2026-09-28-pr-diff-tab.md)); README and
  `docs/how-to-use.md` describe the tab, selecting and editing in place (the
  commit that records step 6).
- The board is the existing board, unchanged, given the full width. Its header
  gives way to the PR bar; its counts, New draft and Send review stay in a thin
  strip at the top of the Board tab. That strip removes no other counts: the PR
  bar and the tabs keep theirs.
- Draft PRs have no place of their own. They are grouped by their state like
  any other PR; the page's Drafts group goes.
- A Terminal tab session outlives the page and the board: the pty lives as long
  as its command, in the manager's process, and a page that lost its connection
  reattaches when the board lists the session again, replaying its kept output.
  One started by a split still ends when no page connects within 30 seconds.
  (Was: a session ended when its last connection closed, `f5ce0302` — a board
  stopping mid-`/rebase-on-main` hung up the Claude run inside it.)
- Switching tmux and browser mode swaps whole modules, chosen in one place in
  wiring. No other code branches on the mode, and no mode flag crosses into the
  PR manager's code or its command line.

## The Runs page

**Done** (`37974fd2`, `eece68db`, `08438b69`, `27e95110` and the commit that records this). The hub
serves `GET /api/runs` from the instance's own run ledger and watcher files,
so each hub shows only its own instance's runs. The page left these open, and
the implementation settled them:

- The page lists the runs that ended in the last seven days, newest first;
  the top bar's count and cost are today's, since local midnight, as the CLI's
  `runs` counts them.
- Each row opens its PR's Dashboard on Claude's output
  (`/pr/<number>/dashboard?pane=claude`). Transcripts are kept one per PR, not
  per run, so that pane's tail is the transcript there is. A run on a PR the
  watcher no longer holds opens nothing.
- A failed run (an exit code other than 0, or a result Claude reported as an
  error) is red the way the wall's alarms are: a red square and bold type. A
  run Claude reported as an error that exited 0 says `errored`.
- The health line reads `polled <time>, next in <n>` while polls keep time;
  `polling now` once the next is due; and, as an alarm, `no poll since <time>`
  when overdue, `polls failing: <error>` while cycles fail, and
  `watcher not running` when no watcher holds the lock. It moves on with the
  wall's five-second refresh.
- The top bar of the wall and of the Runs page names the repository the
  instance watches, beside `Wall | Runs`, as the page's bar does. The hub's
  list carries it as `watching`, from that instance's own settings, so the hub
  on 8721 names `acme/gadgets`.
- Above the table the page shows the watcher's health in full: whether it
  runs, the last and next poll, the last error while cycles fail, and today's
  count, cost and how many runs reported no cost.

## One origin

Everything is served from the hub's address. The hub proxies each PR's API
(`/pr/<number>/api/...`) to that PR's board port, and the PR view is a route of
the same Ember app, so opening a PR loads no new page and a notification can
link to `/pr/<number>`. The per-PR board API itself does not change shape for
the move; the boards stay reachable on their own ports.

## Out of scope

Anything off `127.0.0.1`, more than one watched repo, and changes to the board's
own behaviour.
