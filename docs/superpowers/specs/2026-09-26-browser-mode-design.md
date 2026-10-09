# Browser mode

The orchestrator needs tmux today. The watcher opens a tmux window per PR. The
PR manager runs in pane 0 of that window, draws its dashboard there and reads
its keys there. The only way to reach the review board is to press `v` in that
pane. This spec makes tmux optional. With `pr_windows = "browser"`, no tmux is
started: each PR manager runs as a background process, and everything the
dashboard showed or took as a key is in the browser.

The user asked for this on 2026-09-26 and then went to bed, so the decisions
below were made without a grilling session. Each one is a sentence the user
can overrule in the morning.

## Decisions

**One setting, default tmux.** `pr_windows = "tmux" | "browser"` in
`config.toml`, with `"tmux"` as the default, so the running setup stays as it
is until the user switches. Settings parses it into an enum and refuses any
other word at load, as it does for every other key. Only wiring reads it: it
chooses which `PrWindows` implementation to build. No other module branches on
the mode.

**A second `PrWindows`: background processes.** `BackgroundPrWindows` sits in
`pr_windows/` beside `TmuxPrWindows` and passes the same contract tests.

- `open` starts `python -m github_orchestrator.pr_manager --repo … --pr … --headless` in the worktree, with settings' child environment. The manager's
  stdout and stderr go to a per-PR file under the logs folder. The manager is
  detached so that it is not a child of the watcher: a child that has exited
  stays a zombie until its parent reaps it, and a zombie still answers
  `kill(pid, 0)`. It survives the watcher restarting, as a tmux window does.
- A per-PR record under `data_dir/pr_managers/` holds the pid and the
  worktree. `manager` answers `NO_WINDOW` when there is no record, `RUNNING`
  when the pid is alive and its command line is that PR's manager, `EXITED`
  when it is not, and `UNREADABLE` when the record cannot be read. A pid that
  was reused by another program reads as `EXITED`.
- `revive` starts the manager again in the recorded worktree when it has
  exited. `manager_path` answers the recorded worktree.
- `stop_managers` sends SIGTERM to every running manager and answers those
  PRs. `close` stops the manager and deletes the record. `detach` stops the
  manager, deletes the record and answers `<name>-defunct`, the same words the
  tmux version gives working copies.
- `split` answers a refusal: browser mode has no terminal to open a pane in.
  Superseded on 2026-09-28 by the web interface's Terminal tab: `split` starts
  a terminal session there.
  The git palette's split commands, the `g r` rebase session and the board's
  interactive rework session are therefore refused in browser mode, with that
  reason, through the paths that already report a refused split.
- `sync_theme` does nothing. `close_other_repos` closes the records of every
  other repo.

**A headless PR manager.** `--headless` builds the manager with a terminal that
draws nothing and reads no keys: its `read_char` waits out the timeout and
answers `None`. Everything else in the loop runs unchanged: taking events,
carrying them out, pumping runs, thread upkeep, freezing on the wrong branch.
In headless mode the manager always wants its board. It starts it at start-up
and, if whose PR this is is not yet known, tries again on each tick until a
poll says. The tmux manager does not change.

**The manager's controls move to the board.** The board is served by the PR
manager process, so the board API can reach that manager directly. Board API
defines the port it needs, `ManagerPanel`, and `BoardApi.start` takes one.
The PR manager implements it.

- It answers a status snapshot: what Claude is doing (idle, or working on an
  event, with elapsed and silent seconds), the queued event count, paused,
  unpushed commits, the last run's line, the thread counts, whether Claude is
  enabled, the PR's URL, and the notice the dashboard would show.
- It answers the `agent-changes.md` text and the tail of the Claude transcript.
- It takes the dashboard's commands: pause and resume (`p`), carry on (`r`),
  and dismiss until the next event or forever (`x u`, `x f`).
- The board's HTTP thread never touches the manager's loop state. A command is
  put on a thread-safe queue that the loop drains each tick, as it would read
  a key. The status is a frozen snapshot the loop replaces each tick. A command
  answers `202 Accepted`, and the page polls the status to see it land.
- The board web app gets a manager panel: the status, the buttons, the
  rendered `agent-changes.md` and the Claude output. This works in tmux mode
  too, so the same page serves both modes.
- The board API contract (`2026-09-22-board-api-contract.openapi.yaml`) gains
  the new routes and schemas, and the contract tests cover them.
- The dashboard's `m` preview and `v` board keys have no browser equivalent:
  the panel is the preview, and the board is where the panel is. `y` and `o`
  become a link to the PR.

**A hub page, served by the watcher.** Each board is bound to one PR on its
own port, so there is no one address to open. The resident watcher
(`--loop`, which is how launchd runs it) serves a hub on `hub_port` (a new
setting, with a default outside the board port range) on `127.0.0.1`. The hub
is a second role of the board API module, since that module hides HTTP and the
app files. It serves the same Ember build, whose new `prs` route lists every PR
the watcher holds after its last cycle: the PR, its title, author or reviewer,
the manager's state, paused, the queued count, what it wants next, and a link
to its board when one is wanted. The hub also takes pause and resume, which are
switches on disk, and release, for a PR frozen on the wrong branch, which is
working copies' `request_release`. Release has to be on the hub because a
frozen manager stops its board. Each board links back to the hub. The CLI's
`status` prints the hub's address. The hub runs in both modes. A one-cycle run
of the watcher (cron, `--dry-run`) serves no hub.

## Out of scope

- A terminal in the browser (xterm.js over a pty) for the interactive
  sessions and the git palette's split commands. In browser mode those are
  refused with a reason.
- The git palette's captured commands (push, pull, status) from the browser.
- Anything that needs the machine the manager runs on to differ from the one
  the browser runs on: everything stays on `127.0.0.1`.
