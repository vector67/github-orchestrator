# How to use GitHub Orchestrator

Everything the [README](../README.md) does not need to get you running: how
the two processes fit together, every setting, and what each screen does.

## How it works

Two processes:

- **Watcher** (`watcher`) polls the GitHub API, diffs state, queues events.
  Run resident (`--loop`, as launchd runs it), it also serves the
  [hub](#the-hub).
- **Agent manager** (`pr_manager`) runs one per PR as a background process,
  consumes that PR's queue, spawns Claude runs and serves that PR's board.

Events are JSON files in per-PR queue directories. The watcher writes them, the
agent manager reads them one at a time.

`CLAUDE.md` is the other half of the docs: architecture, invariants, and the
rules to follow when changing the code.

## Platform

It runs on macOS and Linux, and is mostly tested on macOS. Two things differ by
platform. The watcher runs as a LaunchAgent on macOS and a systemd user unit on
Linux (see [The scheduler](#the-scheduler)). Notifications on macOS are the
`GHO` notification apps the installer offers to build into `~/Applications`;
clicking one opens its PR. On Linux they go through `notify-send` when it is on
`PATH` and are skipped quietly when it is not; clicking one does nothing, since
the board's own list covers it, and the badges have no Linux counterpart.

On macOS the notification apps need the Xcode Command Line Tools to build. Without
them, or when you answer no, each notification is dropped without a log line
until the apps are built; `github-orchestrator doctor` names the command that
builds them.

## The install

The installer puts `github-orchestrator` in uv's tool directory
(`uv tool dir --bin`, usually `~/.local/bin`) and offers to add that to your
shell's `PATH`; `--no-modify-path` prints the line to add instead. The service it
starts runs the tool's own Python, so neither uv nor a checkout is needed at run
time.

An older install, a `github-orchestrator` linked into a checkout's `.venv` or a
service that runs a checkout, is found and replaced after asking. Its
config moves to `~/.config/github-orchestrator/` and its data stays where it is.

Each instance runs one agent, `agent = "claude"` (Claude Code, the default) or
`agent = "codex"` (the Codex CLI), and the installer asks which, writing a
choice of Codex into the config; `--agent` and `GITHUB_ORCHESTRATOR_AGENT` choose
without asking. It installs claude when it is missing, but never codex: it
uses the `codex` on `PATH` or the one the ChatGPT app carries, and otherwise
says where to get it and stops.

The installer then offers to copy the `rebase-on-main` skill into the agent's
skills folder, `~/.claude/skills/rebase-on-main` for Claude Code or
`~/.agents/skills/rebase-on-main` for Codex; the agents run it when a branch
stops merging. It runs `github-orchestrator skill`, which
copies this version's skill there, and `doctor` names the same command while
the skill is missing. `-y` installs it, `--no-skill` (or
`GITHUB_ORCHESTRATOR_SKILL=no`) leaves it out, and `--skill` installs it without
asking. A skill already there that differs from this version's, because you
edited it or an older release put it there, is never overwritten unasked: the
installer asks, `-y` leaves it alone, and `github-orchestrator skill --replace`
puts this version's in its place. `github-orchestrator skill --status` prints
`missing`, `current` or `different`.

A dry run names every consequence a real cycle would have: each event it would
queue, which of them would launch a Claude run, and the worktrees it would cut
and the agent managers it would start:

```bash
"$(uv tool dir)/github-orchestrator/bin/python" -m github_orchestrator.watcher --dry-run
```

It writes nothing, so it is safe to run next to the daemon. It is not cheap,
though. Only the writes are skipped, so it costs a full cycle's GitHub traffic
including both PR searches, and that is a 30 request per minute budget it shares
with the daemon. Run it, do not loop it.

## The scheduler

The CLI picks by platform: a LaunchAgent on macOS, a systemd user unit
everywhere else.

`start` and `restart` on macOS boot the old job out and then retry the
bootstrap until launchd has let go of the label, which takes a moment after
`bootout` returns. A bootstrap launchd keeps refusing stops
the command with launchd's own reason and the `launchctl print` command that
shows what is loaded.

On macOS you get a LaunchAgent, and the watcher runs as a long-lived daemon:
launchd starts `watcher --loop` once with `KeepAlive`, and the process
sleeps between polls on its own. It is deliberately not a `StartInterval` job.
launchd coalesces and power-manages that timer, and on an idle machine it gets
deferred for tens of minutes, so the watcher silently stops polling.
`ProcessType=Interactive` and `LegacyTimers` do not fix it, because launchd
creates the spawn timer, not the job. `KeepAlive` only relaunches the daemon if
it dies, and the polling cadence lives in the process where coalescing cannot
reach it.

The LaunchAgent also runs inside the Aqua login session, where the login
keychain that holds the `gh` OAuth token is unlocked.

On Linux the watcher is the systemd user unit
`~/.config/systemd/user/github-orchestrator.service`
(`github-orchestrator-<name>.service` for another instance), running the same
`watcher --loop` with `Restart=always` and `RestartSec=1`. `start` writes it,
runs `systemctl --user daemon-reload` and then `enable --now`, or `restart` when
it was already running; `stop` runs `systemctl --user stop`. A user unit runs
while its user has a session; `loginctl enable-linger` keeps it running after
logout. Without a user manager (some containers and ssh sessions), `start` says
so and points at `start --foreground`.

The CLI writes the LaunchAgent itself each time it restarts the watcher. Its
program is the Python that ran the restart, never uv, and its `PATH` is the
`PATH` of the shell that ran it, in its order, keeping only absolute folders
that exist and each one once. Fixing `PATH` and restarting is the cure for a
watcher that cannot find `gh` or `claude`. The systemd unit gets the same
program and `PATH`.

`github-orchestrator restart-all` restarts every instance: it migrates each
instance's config if an older release wrote it (see
[Upgrading an older config](#upgrading-an-older-config)), stops every agent
manager, rewrites and reloads the daemon, and the fresh daemon's first cycle
relaunches the managers straight away rather than a minute later. In a checkout,
`make restart-all` first runs `uv sync`, `make build_frontend` and
`make notifier_apps`, then the same restart with the checkout's `.venv` python.
A stage that fails stops the run with its exit code.

The daemon reload rewrites the plist, then runs `launchctl bootout`,
`bootstrap` and `kickstart`, a full reload rather than `kickstart -k`, because
a job launchd has killed with `OS_REASON_CODESIGNING` stays dead until it is
reloaded. That used to follow every upgrade of uv, when the program was uv; now that
it is the tool's own Python, upgrading uv leaves the watcher alone.
`ThrottleInterval` is 1, so launchd brings the watcher back a second after any
exit. On Linux it rewrites the unit, reloads the user manager, clears a hit
start limit with `reset-failed`, and restarts the unit.

Two runs never overlap. `restart-all` holds a lock on `restart-all.lock` in the
data directory from the first stop through the confirm, and prints which run it
is waiting for. `make restart-all` also holds `.restart-all.lock` in the checkout
from the sync through the restart, so a second one waits and then builds what was
merged meanwhile. Both are `flock`s, so the system drops them when the holder
dies, however it dies.

It ends by confirming the restart: it first waits up to fifteen minutes for the
watcher to finish a poll since the kill, then up to two minutes more for every
manager it killed to be running again, saying which it is still waiting for. It exits non-zero if the watcher never polled, naming any
manager that did not come back and any queue event marked failed since the kill. A
handler that raises only marks its event failed, so without this check a broken
handler would look like a clean restart.

## Configuration

The settings with no default — `gh_account` and the `[[repos]]` tables — are
the ones the [README](../README.md#configuration) sets up.

Until they name your own account, repos and clones, the watcher serves only the
board's setup page and polls nothing, and most commands exit 2 with a message
naming the keys and the file it looked in. That includes a config
file that does not exist, and a copy of the example nobody edited: the
placeholders it ships are not values. A tool that filled them in for you would
be polling somebody else's repo as somebody else's identity every 60 seconds
without saying so.

Two commands stay useful while it is unset, because refusing to say anything is
no help on the install where you need to know. `setup` is the one that fixes it,
by opening the board's setup page.
`config` prints the whole table first, marking those `unset`, and only
then exits 2 — so you can see every other setting while you are stuck.

Every other key is commented at its default in the example file.
`github-orchestrator config` prints each setting's effective value and where it
came from: the file, the built-in default, or `unset` for a key still showing its
placeholder. An unknown key, a wrong type, a `[[repos]]` repo that is not
`owner/name`, or the same repo twice is refused at load, with a message naming the file, and `config`
reports that one instead of the table.

Two settings bound how hard this hits your machine, and they multiply.
`max_thread_runs` (default 4) caps concurrent per-thread agents, and
`pytest_workers` (default 2) is what those agents are told to give their own test
runner. Total test workers is roughly the product, so keep it at or under your
core count. Four agents each running `pytest -n auto` will lock the machine up.

`agents_enabled = false` runs everything except the Claude subprocesses. Events
still queue, drain, and notify. Queued review-board threads wait for the flag
rather than being retired. `cli status` and `cli runs` both say the flag is off,
so an empty ledger reads as the setting rather than a fault.

`board_font_dir` points at a directory holding one typeface's `.otf` files. The
review board serves them itself at `/fonts/<name>.otf` and declares one
`@font-face` per file under the family name `Board Face`; only names matching
`<Family>-<Style>.otf` are served and nothing else in the directory is reachable.
No typeface ships in this repo — point the key at your own copy. Leave it unset
and the board still asks for `Board Face`, the browser falls back to Helvetica
Neue and Arial, and every size and spacing rule is the same, so the layout does
not move. Set it to a directory that cannot be listed or holds no
`<Family>-<Style>.otf` face and `cli status` prints a `Font:` line saying which,
and every page's top bar says `Board font missing`, with the reason in its
tooltip.

`hub_port` (default 8720) is the port of the [hub](#the-hub), which serves the
wall, each PR's page and the Runs page. It has to sit outside 8730-8829, where
the boards' ports come from.

`tracker` says where the comment agent looks for and proposes tickets when a
comment asks for work that belongs outside the pull request: `"github"` for
issues on the pull request's repo, `"jira"` for a Jira project, or `"none"`, the default,
which proposes a reply saying the work belongs elsewhere and never a ticket.
`tracker_project` is the Jira project key tickets go to by default; it is
required with `"jira"` and refused with any other tracker.

Two environment variables move the files themselves:

- `GITHUB_ORCHESTRATOR_CONFIG`, the config file's path. Default:
  `~/.config/github-orchestrator/config.toml`, or the checkout's `config.toml`
  while that file is missing and an older install left one there. The name
  `config.toml` is reserved for this default, so it is never another instance.
- `GITHUB_ORCHESTRATOR_DATA_DIR`, where runtime state lives. Default:
  `$XDG_DATA_HOME/github-orchestrator`, falling back to
  `~/.local/share/github-orchestrator`.

### Watching more than one repo

One config watches any number of repos, one `[[repos]]` table each, and the
board shows them all; the top bar's repo menu narrows the wall to some of them.
Add and remove repos on the setup screen.

A separate instance is a separate watcher, hub and data dir: a config file
`~/.config/github-orchestrator/<name>.toml` with a `hub_port` of its own. Every
command takes `--instance <name>` to act on it, so
`github-orchestrator start --instance work` writes and loads its service,
labelled `com.github-orchestrator.watcher.work` on macOS and
`github-orchestrator-work.service` on Linux, and comes back after a reboot.
`restart-all` restarts and confirms the default instance followed by each of the
others in name order, under headings ending `for <name>`; `stop --all` and
`uninstall` cover every instance. All instances take their boards' ports from
the same 8730-8829 range.

Auth goes through `gh auth token --user <account>`, so there are no token files
to manage. The installer runs `gh auth login` when gh has no login yet. A
watcher whose `gh` cannot reach a repo repeats gh's own error on stderr with the
path to `watcher.log`.

### Upgrading an older config

A config an older release wrote is refused until it is migrated: every command
that needs it exits 2 naming the keys and `github-orchestrator restart`, and the
hub shows the same on its wall. `start`, `restart` and `restart-all` migrate each
instance before they restart it, and say what they did under a
`Migrating the config` heading:

- the config is rewritten without the keys this release no longer reads; a
  `watch_repo` and `local_path` at the top level become one `[[repos]]` entry,
  which takes the top-level `new_worktree_command` with it. The rewrite drops
  the file's comments. The old file stays beside it as `config.toml.bak` (or
  `<name>.toml.bak`), and an earlier backup is never written over: the next one
  is `.bak.1`, then `.bak.2`.
- files only an older release used are removed from the instance's data dir.
  Nothing else there is touched.
- agent managers an older release ran in terminal windows are stopped, so the
  watcher starts them again in the background.

A config this release already reads is left alone, so running any of them again
changes nothing. To go back, stop the watcher, copy the `.bak` over the config,
and run the older release.

## Runtime data

Runtime data lives under the resolved data dir:

```
state/            last-seen PR snapshots
queues/           per-PR event queues
threads/          one record per review thread, with its lock and pending decisions,
                  and each PR's poll.cursor: the comments the watcher has seen
thread-worktrees/ the worktree each thread's fix is built in
transcripts/      append-only Claude stream-json, per PR
runs.jsonl        one line per finished run, every PR
logs/             watcher.log, agent-manager.log, launchd.log
```

## Finding out what went wrong

Everything the orchestrator knows about a failure is in `logs/` under the data
dir. `github-orchestrator logs watcher|agent|service|all -n 200` tails them
without having to find the directory, and `github-orchestrator status` gives the
watcher's health in one line.

- `watcher.log`: one `Polled N PRs…` line per cycle, every event queued, each
  failed cycle with its traceback, the line that says it recovered and from how
  many failures, and a config that stopped it starting.
- `agent-manager.log`: every PR's agent manager and review board, one file for
  all of them. Each line reads `[<pid> <owner/repo>#<pr>]`, so
  `grep '#23]' agent-manager.log` is one PR's history. It holds what Claude
  printed that was not JSON (its stderr, mostly), every git or GitHub call that
  failed and what it said, each board action that failed with its traceback,
  each board request refused (INFO) or failed (WARNING), and errors the board's
  page hit in the browser, as `board page error in <where>`.
- `launchd.log`: the LaunchAgent's stdout and stderr. That is where
  a watcher that died before it could log goes. The watcher trims it to
  `.1` when it starts past 10 MB. On Linux the unit's stdout and stderr go to
  the journal instead; `logs service` reads `launchd.log` on macOS and
  `journalctl --user -u <unit>` on Linux.
- `runs.jsonl` and `transcripts/<owner>/<repo>/<pr>.jsonl`: one line per
  finished Claude run with its exit code, cost and duration, and the full
  stream of what each run did.

Set `log_level = "DEBUG"` to add every board request and every `gh` call's
timing. `curl 127.0.0.1:<port>/api/health` answers the pid of the manager
serving a board, which is the pid on that board's lines.

## The hub

Each PR's agent manager runs as a background process with no terminal, its
board is always up, and you work in the browser. A manager's own output goes to
`logs/pr_managers/<owner>/<repo>/<pr>.log` under the data dir, beside the lines
it writes to `agent-manager.log`.

Start at the hub, `http://127.0.0.1:8720` (`hub_port`).
`github-orchestrator status` prints its address. The resident watcher serves
it. Everything is on that one address: the hub passes `/pr/<owner>/<name>/<number>/api/...`
on to that PR's board, so opening a PR loads no new page. The boards still
answer on their own ports too.

### The wall

The wall is the hub's home page, one row per PR the watcher holds, grouped by
who has to move next: **Needs you**, **Draft**, **Agent working**, **Waiting on
others**, **On hold** and **Mentioned**. Draft holds your own draft PRs, whatever
their next move. Mentioned holds someone else's PR you don't review that named
you, once you have answered every mention; a mention you have not answered,
since your review if you gave one, needs you. The watcher looks for PRs that
mention you at most once a minute and keeps one until it is merged or closed. On your own PR, changes a reviewer asked for and was not asked to review
again come first, then human comments waiting on you or an agent, then bot
comments (from `claude`, `codex` or `copilot`), then CI, a rebase and the merge.
A PR you dismissed until its next event is off the wall, and
out of the PR switcher, until that event comes, unless its worktree holds the
wrong branch. So is a merged or closed PR, and someone else's PR you were
never asked to review, never reviewed and were never mentioned on. A group with no PRs is not drawn. Grouping wins over rows staying put,
so a row moves when its PR changes group, and it carries a tag saying where it
came from until you open that PR.

Each row leads with your move, the one verb for what you have to do next, with
the flags **Draft**, **Fix CI**, **Rebase** and **N unresolved threads** beside
it whenever they hold, then the title, the number, whose PR it is and the branch. Clicking a row only opens
the PR, whatever its verb says; hovering it adds **Open →** to its last line.
The columns after it are Why, CI, Conflicts, Review, Claude, Threads, Unpushed
and Queue, and hovering a header gives its definition:

| Column    | What it shows                                                                                |
| --------- | -------------------------------------------------------------------------------------------- |
| Why       | what makes that your move                                                                    |
| CI        | GitHub's checks on the head commit: passing, failing or pending                              |
| Conflicts | `none`, or `yes` where the branch conflicts with its base; a draft still needs marking ready |
| Review    | the review decision on GitHub                                                                |
| Claude    | what this PR's Claude agent is doing, or how its last run ended                              |
| Threads   | review-board threads waiting on you: fixes ready, local drafts, answers                      |
| Unpushed  | commits in the PR's worktree not yet pushed to origin                                        |
| Queue     | events the watcher queued for this PR's agent                                                |

A `·` in Threads, Unpushed or Queue means none. A Claude run is named for what
started it: CI fix, rebase on main, review, re-review, thread fix, clean-up, or
**carry on**, which is Claude started again with `--continue` to pick up its
last conversation in the worktree, with no new instructions. A red square marks
something broken or urgent, such as failing CI. "You are the detailed
reviewer" shows beside the verb when the PR description's `Detailed reviewer: @<login>` line names you: the reviewer the PR asks to read the whole change in
detail. A PR frozen on the wrong branch has a **Release** button in its Why
cell.

| Key       | What it does                                                            |
| --------- | ----------------------------------------------------------------------- |
| `j` / `k` | move the selection down / up                                            |
| `Enter`   | open the selected PR                                                    |
| `p`       | put the selected PR on hold, or resume one on hold                      |
| `x`       | ask to dismiss it: `u` until the next event, `f` forever, `Esc` cancels |
| `o`       | open the PR on GitHub                                                   |
| `y`       | copy the PR's link                                                      |

Hold `/` to show the key on every button and link, on every page; releasing it
hides them again.

The bar at the top has **Wall | Runs**, the repository this instance watches,
and the watcher's health: `polled <time>, next in <n>` while polls keep time,
`polling now` once the next is due, and in red `no poll since <time>`,
`polls failing: <error>` or `watcher not running`. Beside it are today's runs,
since local midnight, and what they cost. The wall reads the hub every five
seconds.

### A PR's page

Clicking a row, or `Enter`, opens `/pr/<owner>/<name>/<number>` on its Board. The wall goes
and the PR takes the whole screen. Its bar has the PRs button with how many
need you, **Wall**, the title, whose PR it is, the branch, a link to it on
GitHub, your move, the counts, the flags and the detailed-reviewer flag. On
your own PR the counts are **Human comments M/N done** and **Bot comments M/N
done**; on someone else's, **Your threads M/N answered**. The flags are
**Fix CI**, **Rebase** and **N unresolved threads**, shown whenever they hold,
whatever your move. A draft has a grey **Draft** pill before its title, and
its move is outlined in grey, never yellow, since yellow means it needs you now.

| Key       | What it does                              |
| --------- | ----------------------------------------- |
| `1`       | Board tab                                 |
| `2`       | Dashboard tab                             |
| `3`       | Terminal tab                              |
| `4`       | Diff tab                                  |
| `\`       | open the switcher; `\` or `Esc` closes it |
| `[` / `]` | previous / next PR, in the wall's order   |
| `Esc`     | back to the wall                          |
| `o` / `y` | open the PR on GitHub / copy its link     |

The switcher slides in from the left with every PR's verb, grouped as on the
wall, and slides away once you pick one. A board opened on its own port shows
the same page without the switcher, and its **Wall** link goes to the hub.

**Board** is the [review board](#review-board) at full width. A thin strip at
the top holds its counts, **New draft** and **Send review**.

**New draft** opens the draft panel with the comment on the left and one changed
file's whole diff on the right, drawn as in the Diff tab. It starts on the list
of changed files; pick one, then select the lines the comment is on, the way the
Diff tab selects them. Other conversations on the file are marks in the gutter.
A button over the diff switches to another file, and the line under the comment
names the selection, `changes.py −19 to +20`. A draft in
your review opens the same way and stays in the review while you change it. Its
note says the changes go out when you send the review, and a save that moves it
onto lines off the diff is refused, leaving its old text and lines. A draft whose lines have left the
diff shows its file with "These lines are no longer in the diff. Select new
ones." A draft on its way to GitHub cannot change.

**Dashboard** is the PR's state as its agent manager last saw it.
The band at the top has your move and why, and the buttons: **Open the Board**
(`1`) when threads wait for you, **Put on hold** or **Resume the agent**
(`p`), **Carry on** (`r`), **Start a review agent** (`a`) when your move is to
review or re-review, which starts the review agent a review request would, for
when the automatic one went wrong, **Git** (`g`), **Terminal** (`t`), **Close PR #N**
(`⇧Q`, then `y`), which closes the PR on GitHub, and **Dismiss #N** (`x`, then
`u` or `f`), which takes the PR off the wall. Each button's tooltip says what
it does, or why it is held back. `cli undismiss --repo <owner/name> <pr>`
reverses a dismissal. Under it are the Status, Since you last acted, System and Git blocks.
Unpushed in the System block is the wall's Unpushed column.
The right pane shows the agent's notes from `agent-changes.md`, or Claude's
output, newest last; `⇧C` flips between them. Both follow the board's streams,
so they change as the files do. When the manager's board is not answering, the
page shows the watcher's view from disk marked **Not live**, and carry on,
dismiss and git wait for the board to come back. On a PR frozen on the wrong
branch only `w`, **Release now**, does anything; see
[A PR on the wrong branch](#a-pr-on-the-wrong-branch).

`g` opens the [git palette](#git-palette) in the page. Push, force-push, pull
and status run in the worktree and show their output; force-push asks for a
second `Enter`. `l` and `d` show the log and the diff, read-only. `a`, `c`,
`i<N>` and `r` open in the Terminal tab.

**Terminal** is a real terminal in the page: a pty in the PR's worktree, drawn
by xterm.js. The left side lists this PR's sessions, each with its command, its
worktree and how it ended, and starts new ones: a login shell (`$SHELL -l`),
`git add -p`, `git commit`, `git rebase -i HEAD~<N>`, which asks for the count
(3 unless you change it), and `claude "/rebase-on-main"` for you to steer. The
board's **Steer it yourself** opens its Claude session here, in the thread's
own worktree, and the page switches to this tab. **Send back for rework** is the
unattended one: the agent re-runs with your note and nothing opens here. A thread whose panel says
**Session open** offers **Go to the session in the Terminal tab**, which
switches here and picks the session running in that thread's worktree.

Inside the terminal every key goes to the shell, `Tab` and `Esc` included.
`Ctrl`+`Shift`+`←` leaves it for the session list, where the page's own keys
work again. The screen is also written to an accessibility tree for screen
readers.

A session lives as long as the page's connection to it. Moving between tabs or
PRs keeps it; reloading or closing the browser tab ends it. One started from
the palette or the board waits 30 seconds for the page to connect. Each
connection is sent the session's last megabyte of output first.

**Diff** is the pull request's diff from its merge base to its head, which is
what GitHub's Files changed shows. The **origin | local** toggle above the tree
picks the head: origin is the PR branch on GitHub as last fetched, local is the
commit the PR's worktree has checked out, with any commits not pushed yet. The tree on the left has a filter box, each
file's status and how many conversations sit on it, and clicking a file scrolls
to it. The files stack on the right, each under a header with its path, a copy
button, `+added −removed`, and `N outdated` linking to the board when outdated
threads sit on the file. A binary file, or one with more than 400 lines added
and removed, starts folded; click its header to open it. Context expands up,
down or all, as in a proposed fix's diff. The tab reads the diff again when the
PR's head moves.

Hovering a line in a hunk shows a `+` in its gutter. Click the `+` or a line
number to select that line, then drag or shift-click to stretch the selection.
It can take in − and + lines together but stays in the hunk it started in,
because GitHub refuses a comment whose lines span two hunks. Lines shown by
expanding context cannot be selected. The comment box opens under the last
selected line, saying which lines it is on ("Commenting on lines −19 to +20").
**Save draft** makes the draft and leaves the tab where it was. `Esc` or
**Cancel** closes the box and keeps what you typed for the next new draft.

Conversations sit under the last line they are on: posted threads with their
comments, resolved ones folded behind **Show resolved**, fix proposals as their
thread, and drafts as cards. Each card links to its conversation on the board.
The one thing the tab changes is a draft: **Edit** on a draft card, open or in
your review, turns the card into the comment box with its lines selected, and
you can select others. Outdated threads are not drawn; the file header counts
them.

### The Runs page

`/runs` on the hub, the **Runs** link in the top bar, shows the watcher's
health in full: whether it runs, the last and next poll, the last error while
cycles fail, and today's count, cost and how many runs reported no cost. Under
that is every Claude run that ended in the last seven days, newest first, with
when it ended, its PR, the event it was for, how long it took, its exit and
what it cost. A failed run, one that exited non-zero or that Claude reported as
an error, is red; one Claude reported as an error that still exited 0 says
`errored`. Clicking a run's PR opens that PR's Dashboard on Claude's output.
A run on a PR the watcher no longer holds has no link.

### Notifications

Clicking a desktop notification about one PR opens that PR on its Board, at
`/pr/<owner>/<name>/<number>` on the hub. One about no PR, about a closed PR, or about Claude
skipping events on several PRs opens nothing.

A notification from before PR pages named their repo opens `/pr/<number>`. That
opens the one PR the hub holds with that number. When several repos hold one,
it lists them to pick from; when none does, it says so.

### Git palette

`g` on the Dashboard opens the palette. Keys accumulate into a buffer, and
**Enter** runs whatever the buffer names exactly. A prefix never runs on its
own, which is the only thing that can tell `g p` from `g p r a`.

| Keys   | Where        | Command                         |
| ------ | ------------ | ------------------------------- |
| `f`    | the page     | `git push --force-with-lease`   |
| `p`    | the page     | `git push`                      |
| `pra`  | the page     | `git pull --rebase --autostash` |
| `s`    | the page     | `git status`                    |
| `l`    | the page     | `git log`                       |
| `d`    | the page     | `git diff HEAD`                 |
| `a`    | Terminal tab | `git add -p`                    |
| `c`    | Terminal tab | `git commit`                    |
| `i<N>` | Terminal tab | `git rebase -i HEAD~<N>`        |
| `r`    | Terminal tab | `claude "/rebase-on-main"`      |

The ones on the page run in the worktree with a 60s timeout and cannot prompt;
their output shows in the palette. The others want a real TTY, so each opens a
session in the Terminal tab.

### A PR on the wrong branch

When the worktree ends up holding a different branch than the PR it manages,
the usual state after a stacked-PR split, event dispatch freezes and the
Dashboard says so. Only `w`, **Release now**, does anything: it tells the
watcher to set this worktree aside on its next poll and build a fresh one. The
PR is left alone for an hour first (`mismatch_grace_seconds`), because
releasing it stops whatever was moving the branch, usually a Claude session
you were steering in the Terminal tab. `w` is you saying the work is finished,
which nothing on disk can tell.

When the watcher does release it, it stops that PR's agent manager and closes
its terminal sessions, and leaves the old worktree where it is. That worktree
is yours to clean up.

## Review board

The board is always up, and it is the Board tab of each PR's page on the hub. It is
two panes: a list of rows on
the left, **one per review thread**, and a panel on the right holding the one
thread you opened, with the fix an agent proposed for it. Nothing on the board
reaches the PR until you approve it, which lands the fix on the PR branch and
replies on the thread.

The board keeps its port for the life of the PR: the window it belongs to is
given one when the watcher builds it, and `v` is recorded, so a manager that
restarts brings the board back on the same URL without being asked. A tab left
open on it says it lost contact while nothing is listening and picks the board up
again the moment it is — at worst one watcher poll later. `V` stops the board and
says it should stay down.

A thread is a reviewer's comment and every reply under it, which is how GitHub
groups them and how you read them. A reply does not open a second row: it lands
on the row that is already there, puts it back in front of you, and sets an agent
working again from what the whole thread now says. Conversation comments and
review summaries have no thread on GitHub, so they appear as threads of one.

What a row shows is what GitHub has, not what GitHub had when the row opened. A
comment edited or deleted on GitHub changes on the board within a poll, quietly:
the row does not move and no agent runs. The exception is the reviewer's opening
comment, since that is the instruction the fix was built against — edit that and
the thread comes back to you like a new reply would.

Each safe thread gets its own branch and its own worktree, cut from the PR head,
generated in parallel. That is what makes approving a subset possible without
rewriting history. Threads an agent will not touch arrive as `declined` rows with
no fix, and those are exactly the ones worth a human.

A row is a square and three lines, in a rail 300px wide. The square is the state:
yellow when the thread is ready for you, a black outline while an agent works on
it, a dashed outline while it waits for one, blue for rework, grey while it waits
on a reviewer, black once you have replied to it, green when it has landed. The
first line never wraps: where the thread points, a link that opens it on GitHub,
and how long ago the thread was last replied to, pinned right so the ages line up
down the list. Where it points is the last two segments of the path with the rest
an ellipsis — the front of a path is the same on every thread of one PR, and the
filename is what you are looking for — or what kind of comment it is, for the
conversation comments and review summaries that have no path. Every row shows
that, however narrow the window.
The second line is a one-line gist of what the reviewer wants, written by a small
model (`summary_model`, `haiku` by default; with `agents_enabled = false` the row
shows the comment's own first line instead). A card appears with that first line
and the gist replaces it when the model answers, however long it takes: the pane
never waits on it, so keys stay live while gists are being written. The third
line says who opened the thread — their display name where GitHub has one — and
what the row is doing: that it is outdated or how many replies it carries, what
it is waiting for, how long the agent has been running and how many of its
planned changes are done, the commit that landed, or a reply that would not
post.

Rows are for scanning. Reading and deciding happen in the panel, top to bottom:
the square, the state and where the comment points, then the reviewer's name and
how they left their review — requested changes, commented, approved; the
whole thread, oldest first; a link to reply behind, which opens a box with a line
under it saying where the reply goes; the code in the PR's own diff at the line
the thread was left on;
what the agent proposed — the state it is in and how many of its planned changes
are done, its one-line summary, the steps with the file each touched, how
confident it is and why, the files the fix touches with their plus and minus
counts, and what it says of the tests — and the diff it wrote; and the buttons,
pinned to the bottom over a rule, the first of them filled black.

The board wears its own design system: the face `board_font_dir` names where it
names one, black type on white, no radii and no shadows, hairlines between rows and
2px rules between regions, and colour only as the status squares, the selected
row's yellow fill and the diff. No word on the board is coloured, links included —
a link in a reviewer's comment is underlined instead. The one hue that is not a
fill is the focus ring, which is the design's own blue and deliberately so: a
focus ring is a graphic element, not type. Dark mode is the same black and white
turned over: near-black grounds, dialogs a step lighter than the page they dim,
rules a mid grey rather than the type's own white, and a ready card a yellow tint
edged in yellow rather than a solid slab; it follows the system setting, and `?theme=light` or `?theme=dark` on
the board's URL forces one, which is how the two are compared without touching
the machine's own setting.

Outcomes arrive as a toast: a black bar at the top right for about four seconds,
one when the board queues a decision, one when that decision lands, and one when
an agent finishes and a row moves into Ready for you. Failures never go there —
the banner under the header keeps those.

The reply box is the one way to answer a reviewer without deciding anything. It
stays a **Reply to Anna** link until you click it, and folds back to the link
once the reply is away. The link names the last person on the thread other than
you, and a thread only you have written on offers a plain **Reply**. What you type posts in your own words, joins the
transcript above the box as soon as it posts, and the row does not move. It
posts to GitHub the moment you send it, on its own rather than with a review you
are writing, and the note under a reviewer's box says so. A comment that has no thread — a
conversation comment, a review summary — is answered on the pull request itself,
in a comment that tags its author and quotes what they said, the way GitHub's own
**Quote reply** does.

`j` and `k` open a thread and walk the list, stepping over the group headings,
and a click opens one too. Clicking the open row again, pressing Escape, or the
panel's `×` closes it. The decision keys act on the open thread and do nothing
while the panel is closed, and `c` opens its reply box. A letter that reaches
GitHub or stops work here never does something harmless on another tab: reject
is `⇧R`, because `r` is Carry on on the Dashboard, and post now is `⇧G`, because
`g` is the git palette there. `?` shows the keys, with a capital written `⇧R`.

The rail is grouped, under a heading that carries the group's name and how many
rows are in it. A group with no rows is not drawn at all. The groups come in one
order, and the header repeats the counts: **Ready for you**, **Agent working**,
**Queued for agent**, **Sent back for rework**, **Landing**, **Waiting on
reviewer**, **Assumed done**, **Deferred**, **Done**, with Assumed done in the
Done column. On a PR you review, Ready for you is **Answered** and Waiting on
reviewer is **Waiting on author**, in the Columns view too, and **Not my
conversation** follows Assumed done, in the Done column as well.

On a PR you wrote, a run the agent declines lands by what it says the comment
was. The branch already does what was asked (`already-done`), or the comment
only thanks you, approves or says LGTM (`acknowledgement`): Assumed done. A
question for you (`question`), or anything unclear, risky, out of scope or only
yours to decide: Needs a look, as does a run that failed. A reviewer's new
comment on an Assumed done or confirmed thread brings it back and the agent runs
again, as a new comment on a resolved thread does.

On a PR you review, an agent reads each thread whenever a new comment arrives
and says whose move it is: yours (Answered), someone else's (Waiting on author),
settled for you to confirm (Assumed done), or nothing to do with you (Not my
conversation). Until it has answered, the thread sits in Answered and its card
says "not yet read". A reply you post from the board moves it to Waiting on
author at once, and the agent reads it again. Only you move a thread to Done:
an Assumed done card offers **Confirm** (`g`), which moves it to Done and
touches nothing on GitHub, and **Not confirm** (`m`), which asks where it stands
instead. A Not my conversation card offers the same question as **Move…**. It
lists My move, Their move, Not my conversation and Later…, leaving out the group
the card is in, and Later… opens the Defer dialog. On a PR you wrote it lists
Needs a fix, which starts a fresh agent run, Needs a reply from me, which puts
it in Needs a look, Their move and Later…. Placing a card by hand posts nothing,
and the next new comment is read again. Hovering a heading, a column head, or the state word on a card or in
the panel gives its one-line definition, the same as the table below. Inside a group the thread replied to most
recently comes first, except in Ready for you: there a conversation you replied
to sits at the top until you act on it, and the rest read by the moment their fix
became yours to decide.

| Word           | Meaning                                                                 |
| -------------- | ----------------------------------------------------------------------- |
| `draft`        | a comment you wrote here, not on GitHub yet                             |
| `enrolled`     | a draft in your review; it posts when you send the review               |
| `proposed`     | there is a fix to decide on                                             |
| `answered`     | someone answered; yours to reply to or resolve                          |
| `reopened`     | you replied, and it is yours again whatever the agent is doing          |
| `declined`     | the agent declined to write a fix, and said why                         |
| `failed`       | three attempts failed                                                   |
| `removed`      | the comment was deleted on GitHub before this row was finished          |
| `queued`       | waiting for an agent                                                    |
| `working`      | an agent is running                                                     |
| `rework`       | an agent is working from your rework note                               |
| `session`      | a session you steer is open in the Terminal tab                         |
| `landing`      | accepted: the fix is on its way to the PR branch, then the reply        |
| `push failed`  | accepted, but pushing the fix to the PR branch failed                   |
| `reply failed` | pushed, but posting the reply on GitHub failed                          |
| `rebasing`     | the fix conflicted on approve; an agent is rebasing it onto the PR head |
| `waiting`      | their move; parked until the other side answers                         |
| `assumed-done` | an agent read it as settled; only you can move it to Done               |
| `not-mine`     | an agent read it as asking nothing of you                               |
| `deferred`     | parked until something wakes it                                         |
| `rejected`     | you turned it down                                                      |
| `landed`       | on the PR branch                                                        |
| `resolved`     | closed, worktree and branch gone; the row says whether it replied       |
| `confirmed`    | you confirmed it was settled; nothing was posted to GitHub              |
| `discarded`    | a draft thrown away with nothing posted                                 |

Everything in Done is struck through.

On a PR you wrote, every new reply on a thread starts an agent, whatever you had
decided before it: a rejected, resolved, landed or deferred thread comes back and
is worked on again, and the agent is told how the thread had ended up. A reply
that arrives while an agent, a session or a push is under way queues a rework on
top of it once it finishes.

Buttons say what they do rather than naming the state machine, so a rework
renders as **send back for rework**, or **disagree, try a fix anyway** on a
skipped comment, and opening a session you steer as **Steer it yourself**. Every button that posts to GitHub, drops a worktree or stops
an agent asks in a dialog that says what it is about to do, and resolve, reject,
approve and opening a session give you a box to type in. **Stop** (`x`) asks
before it halts the run. Approve takes the reply you
want on the thread; leave it blank and the thread gets the commit link alone.
Opening a session takes what the rework should do differently, which is the
difference between steering the next attempt and starting it over blind; leave it
blank and the session starts unsteered. Resolve takes the reply that closes the
comment; leave it blank and it closes with nothing posted, which its button
says. On a reviewer's card an empty resolve puts 👍 on the newest reply instead,
and its button says that too. Where the agent had something to
say about the comment, the reason it skipped one or the note it left on a fix,
the dialog offers **use the agent's own words**, which pastes that into the box
for you to edit before it posts.

On someone else's PR, a comment that mentions you and that you have not answered
is a card of its own, and so is a mention in the PR description. It offers
**Reply and resolve** (`v`) and **Resolve on board** (`h`), with **Defer** at the bottom right, and no
reply link. Its dialog will not post until you write a reply. The reply goes on
the thread for a review comment, or to the PR's conversation quoting the comment
for anything else (a mention in the description gets an @ to its author and no
quote), and the card moves to Done on the board only: nothing is resolved on
GitHub. **Resolve on board** (`h`) moves the card to Done with nothing posted at
all: no reply, no 👍, nothing resolved on GitHub.

On a comment you wrote yourself, and that nobody else has replied to, the same
dialog offers **Delete the comment** under "On GitHub, also:". Tick it and the verb posts nothing:
approve lands and pushes the fix and then takes your comment off GitHub, and
resolve closes the card the same way. **Resolve the thread** greys out while it
is ticked and keeps whatever you had set, so unticking delete gives it back. It is the note you left for an
agent rather than a question anybody is waiting on an answer to, so there is
nothing to reply to once the fix is in. The tick is clear every time the dialog
opens, it never appears on a reviewer's comment or a review summary, and the row
settles in Done with **comment deleted** on its line. The board keeps the comment's text and
everything said under it for the life of the PR.

Confirming a decision walks on to the next thread the way `j` would, in the order
the list was in before the decision moved anything, and leaves the panel open on
it. On the last thread it stays where it is, and the panel follows the thread you
just decided.

Approve cherry-picks the thread's whole commit range, squashes it into one
commit carrying the last one's message, pushes, and replies on the thread with
the landed SHA. A reply you typed yourself posts in your words, with the commit
link under it and no `🤖`. Every reply the board sends joins the panel's
transcript, and none of them comes back to the board as a new comment.
One approval is one commit and one push, so one CI run per approved comment.
Every step is recorded before the next runs, and re-approving resumes at the one
that failed. Once it has landed and replied the row drops to Done carrying the
SHA that landed; a row whose reply failed is still `landing`, under that
heading, with the button that retries the step that failed. A resolved row settles the
same way, behind the line that says whether it replied, and the reply you typed
never comes back to the board as a new comment — including the ones posted on the
pull request itself, which the poller knows by the node id GitHub hands back.

A cherry-pick that conflicts, because the PR branch moved since the fix was
written, does not come back to you. The row turns `rebasing`, an agent rebases
the fix onto the current head in the thread's own worktree, and your approve
waits: once the rebased fix reports its tests passed it lands, pushes and
replies on its own. If its tests failed, or a second attempt against the same
head still conflicts, the row comes back `proposed` with the reason and the
decision is yours again.

Resolve is how you close a comment without landing a fix, whether you agreed
with the agent's skip or decided the fix is not needed at all. Its reply posts in
your own words with no robot prefix — on the comment's thread, or on the pull
request quoting the comment where there is no thread. Leave it blank and it
closes without a reply.

While a comment is open in the panel, the board asks GitHub whether it is still
there. A comment deleted while its row still wanted work turns that row
`removed`: it offers resolve, and approve where there is a commit worth
keeping, because the worktree holds real work that a deletion should not quietly
bin. One that had already landed or been resolved keeps its status and says
**GitHub no longer has this comment** at the top of the panel, which means
somebody tidied the comment away after the work was done and nothing is wrong.
Neither can reply, because the thread is gone with the comment, so the dialog
drops its reply box.

At PR close, the thread worktrees and branches go with everything else.

## Events

### PRs you are reviewing

- `review-requested`, a full PR analysis
- `thread-activity`, appended to `agent-changes.md`
- `ci-succeeded` / `ci-failed`, status summary
- `became-unmergeable` / `became-mergeable`, status update
- `pushed-since-review`, the author pushed or force-pushed since you reviewed

### Your own PRs

- `thread-activity`, materialises review-board threads
- `ci-failed`, one Claude run per failing check
- `became-unmergeable`, triggers `/rebase-on-main`
- `ci-succeeded` / `became-mergeable` / `review-decision-changed`, macOS notification

## Removing it

```bash
github-orchestrator uninstall
```

It says what it will remove and what it keeps before it does anything. It stops
every instance, boots out and deletes each LaunchAgent (or disables and deletes
each systemd unit), and removes the command with `uv tool uninstall`. Then it asks
whether to remove the config folder, the data dir and the notification apps too;
`-y` removes them without asking. Without uv on `PATH` it says how to remove the
command once uv is back.

It never touches your clones, and leaves uv, gh and claude installed, since other
tools use them too. It also leaves the `rebase-on-main` skill in
`~/.claude/skills`, which Claude Code can use without the orchestrator, and says
so; `rm -rf ~/.claude/skills/rebase-on-main` removes it. The worktrees the watcher
cut next to your clones are yours to remove.
