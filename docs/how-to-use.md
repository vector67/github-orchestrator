# How to use GitHub Orchestrator

Everything the [README](../README.md) does not need to get you running: how
the three processes fit together, every setting, and what each screen does.

## How it works

Three processes:

- **Watcher** (`watcher`) polls the GitHub API, diffs state, queues events.
  Run resident (`--loop`, as launchd runs it), it also keeps the server running:
  on every cycle, in every state, it starts the server when nothing holds
  `server.lock` in the data dir.
- **Server** (`server`) serves the [hub](#the-hub) and every held PR's board on
  `hub_port`, from a few worker processes. It logs to `server.log` and writes its
  pid to `server.pid`.
- **Agent manager** (`pr_manager`) runs one per PR as a background process,
  consumes that PR's queue and spawns Claude runs. It writes a status file each
  tick, which the board reads, and carries out the commands the board writes.

The managers and the server outlive a watcher restart; the watcher stops
nothing when it exits.

Events are JSON files in per-PR queue directories. The watcher writes them, the
agent manager reads them one at a time.

`CLAUDE.md` holds the rules to follow when changing the code, and
`CODE_ARCHITECTURE.md` the choices about its shape that are meant to stay.

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

The installer then offers to copy the skills the orchestrator ships into the
agent's skills folder, `~/.claude/skills` for Claude Code or `~/.agents/skills`
for Codex (`<CLAUDE_CONFIG_DIR>/skills` when `agent_command` sets
`CLAUDE_CONFIG_DIR`): `rebase-on-main`, which the agents run when a branch stops merging,
and `create-pr`, which opens a new PR from a branch, such as one a split carries
code into. It runs `github-orchestrator skill`, which copies this version's
skills there, and `doctor` names the same command for each skill that is
missing. `-y` installs them, `--no-skill` (or `GITHUB_ORCHESTRATOR_SKILL=no`)
leaves them out, and `--skill` installs them without asking. A skill already
there that differs from this version's, because you edited it or an older
release put it there, is never overwritten unasked: the installer asks, `-y`
leaves it alone, and `github-orchestrator skill --replace` puts this version's
in its place. `github-orchestrator skill --status` prints one line per skill,
its name and then `missing`, `current` or `different`.

`github-orchestrator update` brings the skills along under an **Updating the
orchestrator's skills** heading. A shipped skill that is missing is installed.
One that differs from this version's is left alone, and the output names
`github-orchestrator skill --replace`. When none of the shipped skills is
installed, they stay left out, and `github-orchestrator skill` installs them
later. It updates only the default instance's skills folder; for another
instance whose agent reads its skills elsewhere, run
`github-orchestrator skill --instance <name>`.

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
manager and the server, rewrites and reloads the daemon, waits for the hub's
`/api/health` to answer from the new server's pid (the one in `server.pid`), and
the fresh daemon's first cycle relaunches the managers straight away rather than
a minute later. `stop` and `uninstall` stop the server too, after the watcher, so
nothing starts it again. In a checkout,
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

`hold-restarts` makes every `restart` and `restart-all` skip and say why until
`allow-restarts`. A release's stress test holds them while the board runs from
the release branch, so a merge into `main` elsewhere cannot swap the board back
mid-test. The hold is a `restarts-held` file in the data directory and never
expires; when no stress test is running, `allow-restarts` clears a hold left
behind.

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
rather than being retired. `github-orchestrator status` and `runs` both say the flag is off,
so an empty ledger reads as the setting rather than a fault.

`board_font_dir` points at a directory holding one typeface's `.otf` files. The
review board serves them itself at `/fonts/<name>.otf` and declares one
`@font-face` per file under the family name `Board Face`; only names matching
`<Family>-<Style>.otf` are served and nothing else in the directory is reachable.
No typeface ships in this repo — point the key at your own copy. Leave it unset
and the board still asks for `Board Face`, the browser falls back to Helvetica
Neue and Arial, and every size and spacing rule is the same, so the layout does
not move. Set it to a directory that cannot be listed or holds no
`<Family>-<Style>.otf` face and `github-orchestrator status` prints a `Font:` line saying which,
and every page's top bar says `Board font missing`, with the reason in its
tooltip.

`hub_port` (default 8720) is the port of the [hub](#the-hub), which serves the
wall, each PR's page with its board, and the Runs page.

`hub_host` (default `"127.0.0.1"`) is the address the hub listens on. Set it to
`"0.0.0.0"` to open the board from another device on your network, such as a
phone. The board has no login, so anyone on that network can then use it.

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
board shows them all; the top bar's repo filter narrows the wall to some of them.
Add and remove repos on the setup screen.

A separate instance is a separate watcher, hub and data dir: a config file
`~/.config/github-orchestrator/<name>.toml` with a `hub_port` of its own. Every
command but `thread` takes `--instance <name>` to act on it; `thread` takes it
before the command (`github-orchestrator --instance work thread list ...`) or
from `GITHUB_ORCHESTRATOR_INSTANCE`. So
`github-orchestrator start --instance work` writes and loads its service,
labelled `com.github-orchestrator.watcher.work` on macOS and
`github-orchestrator-work.service` on Linux, and comes back after a reboot.
`restart-all` restarts and confirms the default instance followed by each of the
others in name order, under headings ending `for <name>`; `stop --all` and
`uninstall` cover every instance. Each instance's watcher starts that instance's
server, with the instance's config and data dir, on its own `hub_port`.

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
summaries/        each PR's latest pr-summary, <n>.json, beside <n>/, the working
                  folder its newest run left; lane.lock names the run in flight
pr_managers/      one <n>.json per running agent manager: its pid and worktree
harvest-extension/ the board's copy of the Harvest extension, once you set it up
logs/             watcher.log, agent-manager.log, server.log, launchd.log,
                  gh_calls.csv, and pr_managers/, each manager's own output
```

## Finding out what went wrong

Everything the orchestrator knows about a failure is in `logs/` under the data
dir. `github-orchestrator logs watcher|agent|service|all -n 200` tails them
without having to find the directory, and `github-orchestrator status` gives the
watcher's health in one line.

- `watcher.log`: one `Polled N PRs…` line per cycle, every event queued, each
  failed cycle with its traceback, the line that says it recovered and from how
  many failures, and a config that stopped it starting.
- `agent-manager.log`: every PR's agent manager, one file for all of them. Each
  line reads `[<pid> <owner/repo>#<pr>]`, so `grep '#23]' agent-manager.log` is
  one PR's history. It holds what Claude printed that was not JSON (its stderr,
  mostly) and every git or GitHub call that failed and what it said.
- `server.log`: the server, which serves the hub and every PR's board. Each line
  reads `[<pid>]`, the worker that wrote it. It holds each board action that
  failed with its traceback, each request refused (INFO) or failed (WARNING),
  and errors the board's page hit in the browser, as
  `board page error in <where>`. `logs` does not tail it.
- `gh_calls.csv`: one row per request `gh` made, with the time, the account,
  the method, the URL, `gh`'s exit code, the HTTP status and the body's size,
  and on a 403 the `retry-after` and `x-ratelimit-*` headers.
- `launchd.log`: the LaunchAgent's stdout and stderr. That is where
  a watcher that died before it could log goes. The watcher trims it to
  `.1` when it starts past 10 MB. On Linux the unit's stdout and stderr go to
  the journal instead; `logs service` reads `launchd.log` on macOS and
  `journalctl --user -u <unit>` on Linux.
- `runs.jsonl` and `transcripts/<owner>/<repo>/<pr>.jsonl`: one line per
  finished Claude run with its exit code, cost and duration, and the full
  stream of what each run did.

Set `log_level = "DEBUG"` to add every board request and every `gh` call's
timing. `curl 127.0.0.1:8720/pr/<owner>/<name>/<number>/api/health` answers
the pid of the server worker that served it, which is the pid on its lines in
`server.log`.

## The hub

Each PR's agent manager runs as a background process with no terminal, and you
work in the browser. A manager's own output goes to
`logs/pr_managers/<owner>/<repo>/<pr>.log` under the data dir, beside the lines
it writes to `agent-manager.log`.

Start at the hub, `http://127.0.0.1:8720` (`hub_port`).
`github-orchestrator status` prints its address. The server serves it, and the
resident watcher keeps the server running. Everything is on that one address:
each held PR's board answers under `/pr/<owner>/<name>/<number>/api/...`, so
opening a PR loads no new page, and a board keeps answering while its manager
is stopped, saying so. A PR the watcher does not hold is not found.

### The wall

The wall is the hub's home page, one row per PR the watcher holds, grouped by
who moves next: **Needs you**, **Agent working**, **Waiting on others** and
**Parked**. Your own draft PRs join Needs you when they hold fixes to decide;
otherwise they are parked, with PRs on hold. Someone else's PR you don't review
that named you waits on others once you have answered every mention; a mention
you have not answered, since your review if you gave one, needs you. The
watcher looks for PRs that mention you at most once a minute and keeps one until
it is merged or closed. The list behind the top bar's mention count is a
separate search, run at most every 30 minutes. On your own PR, changes a reviewer asked for and was
not asked to review again come first, then human comments waiting on you or an
agent, then bot comments (from `claude`, `codex` or `copilot`), then CI, a
rebase and the merge; a draft with nothing else in its way is marked ready for
review. A PR you dismissed until its next event is off the wall, and out of the
PR switcher, until that event comes, unless its worktree holds the wrong
branch. So is someone else's PR you were never asked to review, never reviewed
and were never mentioned on. A merged or closed PR leaves the wall, unless the
wall still holds it, as it does one you added from a mention: that one sits
under Parked. A group with no
PRs is not drawn, and a group's heading stays in view while its rows scroll.
Grouping wins over rows staying put, so a row moves when its PR changes group,
and it carries a **moved here** chip until you open that PR. The tab title
counts the PRs that need you.

Each row leads with its move line: your move, a red dot when the PR's
importance is not set, the reason for that move, and chips for the facts that
matter. Below it are the title, the number, whose PR it is and the branch.
Clicking a row only opens the PR, whatever its move says; hovering it adds
**Open →** to its last line. Hovering, focusing or selecting a row also shows
its buttons, and only then: **Hold** (or **Resume**) and **Dismiss**, which do
what the keys do, **Release** on a worktree frozen on the wrong branch, **I
nudged them** while the move is Nudge, and **Set importance**, which carries
the same red dot while importance is not set.
The selected row, the one the keys act on, is framed; tabbing to a row selects
it, and `j` or `k` take the focus off the row they leave.

A chip shows a fact only when it is away from its quiet default (CI passing, no
conflicts, no review yet, the agent idle, nothing unpushed or queued), and only
when the move or its reason doesn't already say it. Chips are ordered by
severity. On your own PR, the one fact standing in the way of the PR, when your
move is something else, is red; on a PR you review nothing is. The chips are
**CI failing**, **conflicts with** or **behind** the base branch, who
**requested changes**, failed agent runs, what the agent is doing when that is
not the move, **N fixes to decide**, **N unsent** review comments, **N
unresolved** GitHub threads, **N answered** of your threads, **N unpushed**
commits (**diverged from origin** instead, with no count, when origin also holds
commits the worktree lacks), **N queued** events, **approved**, **mentioned**, **detailed
reviewer** (the PR description's `Detailed reviewer: @<login>` line names you),
**N mismatches** and **draft**. Hovering a chip says what it means. A run is
named for what started it: CI fix, rebase on main, review, re-review, thread
fix, clean-up, or **carry on**, which is Claude started again with `--continue`
to pick up its last conversation in the worktree, with no new instructions. A
row's **Release** asks first.

Inside a group, PRs you marked Important come first, then those whose
importance is not set, then Normal, then Someday, and within each rank the one
that joined the group first leads; Someday rows are greyed. **Set importance**, on the row or the
Dashboard, sets it. An Important PR that has waited on others for a day since
its last event moves to Needs you, its move reading **Nudge** and the people it
waits on. **I nudged them**, on the row or the Dashboard, puts the next nudge a
day off.

| Key       | What it does                                                            |
| --------- | ----------------------------------------------------------------------- |
| `j` / `k` | move the selection down / up                                            |
| `Enter`   | open the selected PR                                                    |
| `h`       | put the selected PR on hold, or resume one on hold                      |
| `c`       | carry on its agent's last run                                           |
| `r`       | ask to mark your draft ready for review: `y` marks it, `Esc` cancels    |
| `d`       | ask to dismiss it: `u` until the next event, `f` forever, `Esc` cancels |
| `o`       | open the PR on GitHub                                                   |
| `y`       | copy the PR's link                                                      |

On a draft, `d` also offers `r`, until it is ready for review: the PR stays off
the wall whatever events arrive, and comes back once GitHub says it is no longer
a draft.

Hold `/` to show the key on every button and link, on every page; releasing it
hides them again.

The bar at the top has **Wall**, **Runs** and **Setup**, the repo filter, and
the watcher's health. That reads `polled 14:02:11, 40s ago` while polls keep
time and `no poll yet` before the first. In red it reads
`no poll since <time>, <age> ago`, `polls failing: <error>`,
`in setup, polling nothing` or `config broken, polling nothing`. When the hub
stops answering it reads `the board server is not answering`, or
`the system is under heavy load` while the health check still answers. Beside
it are today's runs,
since local midnight, and what they cost. The wall reads the hub every five
seconds.

The bar also counts the mentions of you, made since the hub first ran this
version, that the board has not closed; a PR's title bar shows the same count.
Clicking the number lists each mention, with its author, PR and text. Each row
is a link: it opens the PR at the mention's thread, building the PR's cards
first when the board does not hold it, or opens the comment on GitHub when
there is no thread to open. A note beside an off-board mention says which:
**opens on GitHub**, **card being built**, **card built when opened**, or, for a
PR that ended, that its page is rebuilt when opened. The row's **▾** menu has
**See in context**, **See on GitHub**, **Defer…** (or **Stop deferring**) and
**Dismiss**. Defer… waits for a time, or until a PR you pick lands in Needs
you, is approved, gets a new commit, is merged, is closed or has any new
activity; a deferred mention is greyed with when it comes back, and left out of
the count. A merged or closed PR you opened for a mention, and that is not on
your wall, shows a banner with **Add to Wall** and **Dismiss mention**.

### A PR's page

Clicking a row, or `Enter`, opens `/pr/<owner>/<name>/<number>`: on its Summary
when you review it, on its Board when it is yours. The wall goes
and the PR takes the whole screen. Its title bar has the three-line PRs
button, the title, whose PR it is, the branch, the PR's number linking to it on
GitHub, your move, the chips its wall row shows and the settings gear. The PRs
button opens the switcher, whose first entry is **Wall**. The gear, on the
wall's bar too, holds the theme, the [Harvest timer](#harvest-timer) switch,
**Commit box sizing** for the Diff tab (Full, Minimal or Hidden),
**Auto read** for marking commits read on their own,
**Agent sessions** (below),
**Terminal colours** for the Terminal tab and
the watcher's last poll: a green dot, **Polled successfully** and how long ago,
or a red dot and what went wrong when polls fail. **N mismatches** is the
Alignment judge's count in the PR's latest summary, shown even once the summary
is stale. A draft has a grey **Draft** pill before its title, and
its move is outlined in grey, never yellow, since yellow means it needs you now.

**Agent sessions** decides where an agent works when you start it from
**Request change** in the Diff tab, **Ask the agent** on a mention card, or an
answer to an agent's question: **Ask me each time** (the default), **Always
visible**, which opens a session in the Terminal tab you can watch and type
into, or **Always invisible**, which runs it unwatched. Either way the result
comes back to the board for you to decide. Asking each time opens a dialog
with **Visible session** and **Without a session**, and its **Remember my
choice** tick sets this setting. The choice is kept in this browser.

| Key       | What it does                              |
| --------- | ----------------------------------------- |
| `1`       | Summary tab                               |
| `2`       | Board tab                                 |
| `3`       | Dashboard tab                             |
| `4`       | Terminal tab                              |
| `5`       | Diff tab                                  |
| `\`       | open the switcher; `\` or `Esc` closes it |
| `[` / `]` | previous / next PR, in the wall's order   |
| `Esc`     | back to the wall                          |
| `o` / `y` | open the PR on GitHub / copy its link     |

On the Diff tab, `[` and `]` step to the previous and next commit instead while
the commit stepper shows, and `t` opens and closes the timeline. `Esc` there
first closes the comment box, then drops a picked range, and only then goes
back to the wall.

The Summary tab is headed by the PR's title, how long ago it was opened, its
commits, and the lines added and removed beside five squares, green and red
for their shares and grey for the rest. Under that, the pr-summary plugin's latest summary of the PR
sits below a one-line strip. The strip says which state it is in: waiting for
its turn (a PR you review) or a **Summarise** button (your own); running, with
the head it reads, how long it has run and each witness ticked off as it
finishes; ready, with the head it read, when it finished and **Summarise**; stale
after a push, naming both heads and how many commits behind, with **Summarise**;
needing the GitHub API, with the plugin's reason and a button that runs it over
the API; or failed, with the exit status, the end of what it printed and
**Summarise**. While a rerun runs, the old summary stays, and the strip says when
the rerun started and how many of its agents have finished. Press **Summarise**
while another PR's summary is running and yours is queued: the strip says
**Waiting for another summary to finish** where the button was, and the run
starts by itself when the other one ends, ahead of the summaries the watcher
starts on its own. A refused run says why in the strip.

The summary opens with **Before you review**, the primer: the concepts the diff
cannot be judged without, each a folded section with the concepts it leans on
folded inside it. Click a concept's name to open it. The tab draws the
summary's Mermaid diagrams in place, in the page's theme.

The switcher slides in from the left with every PR's verb, grouped as on the
wall, and slides away once you pick one.

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
(`2`) when threads wait for you, **Hold** or **Resume**
(`h`), **Carry on** (`c`), **Start a review agent** (`a`) when your move is to
review or re-review, which starts the review agent a review request would, for
when the automatic one went wrong, **Ready for review** (`r`, then `y`) on your
own draft, which first lists what is still outstanding (nobody asked to review,
unsent drafts, Board threads waiting on you, threads unresolved on GitHub that
the Board has not resolved or does not track, failing CI, a needed rebase,
unpushed commits and agent work) and then marks it ready on GitHub; while
nobody is asked to review and no pick waits, that item holds an Assign
reviewers button (`⇧R`), which opens the same dialog over it, **Assign
reviewers** (`⇧R`) on your own PR, which lists the people the
repository usually asks first, most asked on top, then everyone else by login:
type to find someone, `↑` and `↓` move, `Space` picks, `*` stars the detailed
reviewer and `↵` asks them to review on GitHub, writing the starred one as
`Detailed reviewer: @<login>` in the description, replacing a line already
there; on a draft `↵` is **Assign when ready for review**, which the manager
keeps on disk and assigns as soon as the PR leaves draft, however it was marked
ready, and **Assign now** asks them at once; opening it again starts from the
waiting pick, and assigning when ready again replaces it, **Take over**
(`⇧T`, then `y`) on someone else's PR, after which the orchestrator treats it as yours:
agents fix CI, rebase and answer its comments, the author's buttons appear, and
the reviewer threads you had become your move, **Dismiss #N** (`d`, then `u`, `f`, or on a draft
`r` until it is ready for review), which takes the PR off the wall, and **Close PR #N** (`⇧Q`, then `y`), which closes the PR on
GitHub. On a PR you review with threads waiting on the author, **Check all
threads for fixes** (`⇧F`) asks an agent, for each of them, whether the
changes since your comment address it: Assumed done if they do, My move if
not. **Set importance** opens Important (`i`), Normal (`n`) and Someday (`s`),
which rank the PR on the wall (see [The wall](#the-wall)); until one is set
the button carries a dot and the Dashboard tab's problem count includes it. **I nudged them** shows
while the move is Nudge. Each button's tooltip says what
it does, or why it is held back. After Close, Ready for review and Take over,
the toast offers the way back for eight seconds: **Reopen PR #N**, **Convert to
draft** or **Hand back**. From the press, by button or key, the band is
faded, the pressed button says what it is doing and the others wait; Ready for
review and Close stay that way, with a turning ring, until the dashboard shows
the PR ready or closed. A command the manager refuses says why on the band, in
red; a refused Close or Dismiss says so in a toast instead. The wall's rows do
the same, with the word among the row's chips. `github-orchestrator undismiss --repo <owner/name> <pr>`
reverses a dismissal. Under it are the Status, Since you last acted, System and Git blocks.
Unpushed in the System block is the count behind the wall's unpushed chip,
which reads **diverged from origin** instead when the worktree has diverged.
The right pane shows the agent's notes from `agent-changes.md`, or Claude's
output, newest last; `⇧C` flips between them. Both follow the board's streams,
so they change as the files do. When the manager's board is not answering, the
page shows the watcher's view from disk marked **Not live**, and carry on,
dismiss and git wait for the board to come back. On a PR frozen on the wrong
branch only `w`, **Release**, does anything, and it asks first; see
[A PR on the wrong branch](#a-pr-on-the-wrong-branch).

Two keys have no button. `t` opens the Terminal tab, and `g` opens the
[git palette](#git-palette) in the page. Push, force-push, pull
and status run in the worktree and show their output; force-push asks for a
second `Enter`. `l` and `d` show the log and the diff, read-only. `a`, `c`,
`i<N>` and `r` open in the Terminal tab.

**Terminal** is a real terminal in the page: a pty in the PR's worktree, drawn
by xterm.js. The left side lists this PR's sessions, each with its command, its
worktree and how it ended, and starts new ones: a login shell (`$SHELL -l`),
`git add -p`, `git commit`, `git rebase -i HEAD~<N>`, which asks for the count
(3 unless you change it), and `claude "/rebase-on-main"` for you to steer. The
board's **Steer it yourself** opens its Claude session here, in the thread's
own worktree, and the page switches to this tab. **Open a shell** (`q`), on
your own thread with no fix, opens a login shell there instead, cutting the
thread's worktree first; it runs no agent, so it works with agents disabled,
which is when your new threads arrive with no fix. **Send back for rework** runs
unattended: the agent re-runs with your note and nothing opens here, unless you
tick **Do rework in visible terminal session** in its dialog, which turns its
button into **Start a steered session** and opens the session here. A thread whose panel says
**Session open** offers **Go to the session in the Terminal tab**, which
switches here and picks the session running in that thread's worktree.

Inside the terminal every key goes to the shell, `Tab` and `Esc` included.
`Ctrl`+`Shift`+`←` leaves it for the session list, where the page's own keys
work again. The screen is also written to an accessibility tree for screen
readers.

The **⤢** at the screen's top right makes the terminal fill the whole page;
the **×** in its place puts it back. The terminal draws in MesloLGS Nerd Font
at 12px when it is installed, so nvim's icons show. Its border takes the
background the program paints. **Terminal colours** in the settings gear opens
a dialog: **Mode** is System, Light or Dark, and **Light theme** and **Dark
theme** pick what each mode draws in (Default, Solarized, Tokyo Night, Monokai,
One, Gruvbox, Catppuccin, Dracula or Nord). The choices are kept in this
browser.

A session outlives the page: it lives as long as its command. Moving between
tabs or PRs, reloading or closing the browser tab leaves it running, and the
page reattaches when the board lists it again. One started from the tab's own
list, the git palette, **Rebase on main** or the comment box's **Ask the agent** ends if
no page connects within 30 seconds. A thread's **Steer it yourself** session
and **Open a shell** wait however long the page takes, since the board opens
them after it answers. Each connection is sent the session's last megabyte of
output first.

**Diff** steps through the pull request one commit at a time. A bar over the
files reads **Commit N of M** with the commit's sha, subject, author and age,
and a **merge** or **not pushed** pill when one applies (**not on origin** on a
worktree diverged from origin). **‹ Prev** and
**Next ›** step, the **Read** checkbox marks the commit read, and a row of pips
under the bar, one per commit, shows which are read and jumps to the one you
click. The tab opens on **All**, every commit of the pull request as one
change. Escape or **This commit** in the timeline starts stepping on
the first unread commit after your review, or on the first unread one when you
have not reviewed, or the last when all are read.
After a review a note says **Picked up at
the first new commit** and how many were pushed since your review, or, after a
force-push, **Rebased since your review**, how many of your read commits were
matched by message onto the newer base branch and how many are new. Its `×` hides it
until the PR has a new head.

On a merge commit the diff shows only what the merge changed on its own; a note
says how many files came in from the base branch and are hidden, and its **Skip merges
when stepping** checkbox, on unless you clear it, steps past merges.

**Timeline** opens a graph of the branch over the diff: its commits against the
base branch, how far behind it is, the commits not pushed yet, and what your
review saw once the branch was rewritten. Click a dot for one commit;
shift-click another, or drag the band's handles, to pick a range, which the bar
then shows as `from → to` with its commit and file counts and
**Back to stepping**. **All**, **Since my review** and **This commit** pick
the common ranges. The commits are dots while the pane has room for them, ticks
when it is narrower, and narrower still the timeline turns vertical: one row
per commit, oldest on top, with its short sha and subject, and the commit bar
stays at the top of the pane while you scroll past it.

When the worktree has diverged from origin, the timeline's header counts the
commits in the worktree and the ones origin has since the fork, and a **Reset
to origin** button sits beside them. It asks first, listing each commit that
isn't on origin and will be dropped, by short sha and subject, and the
dialog's **Reset to origin** moves the worktree to origin's head. A reset is
refused, with the reason under the header, when the worktree has uncommitted
changes, holds another branch, or moved since the page showed it. While an
agent is working in the worktree the refusal offers **Reset when the agent
finishes**, which asks again with the same list, warns that any commits the
agent makes before then are dropped too, and confirms with **Reset when the
agent finishes**. The queued reset shows as **Reset
queued until the agent finishes** with a **Cancel** button. When the run ends
the manager fetches origin and resets, and a note says **Reset to origin when
the agent finished.**, or why the queued reset didn't run, such as a fix picked
onto the branch and not pushed yet. Its `×` clears the note.

**Auto read** in the settings gear ticks Read for you: Off (the default),
Instantly when the commit opens, after 2, 5, 10 or 30 seconds on it, or once
you scroll to the bottom of its diff. Untick a commit it marked and it stays
unread while you are on it.

**Commit box sizing** in the settings gear sets how much of this shows. Full is
all of it; Minimal keeps only the pips; Hidden drops the stepper and shows the
whole diff from the merge base to the head, which is what GitHub's Files
changed shows, with a **Timeline** button beside the toggle. The
**origin | local** toggle above the tree
picks the head: origin is the PR branch on GitHub as last fetched, local is the
commit the PR's worktree has checked out, with any commits not pushed yet. The tree on the left has a filter box, each
file's status and how many conversations sit on it, and clicking a file scrolls
to it. The files stack on the right, each under a header with its path, a copy
button, `+added −removed`, and `N outdated` linking to the board when outdated
threads sit on the file. A binary file, or one with more than 400 lines added
and removed, starts folded; click its header to open it. Context expands up,
down or all, as in a proposed fix's diff. The tab reads the diff again when the
PR's head moves.

You can comment on any commit, any range, or the whole diff. GitHub anchors a
comment to the PR's head, so a comment on an earlier commit is posted on the
same line of the head. A line changed or deleted by a later commit, or in a file
deleted or renamed since, has no such line: the box says "This line doesn't
exist in the latest commit" instead and nothing is posted. Threads show on an
earlier commit at the line they sit on there, and a line above the diff counts
those on lines the commit doesn't have. Hovering a line in a hunk shows a `+`
in its gutter. Click the `+` or a line
number to select that line, then drag or shift-click to stretch the selection.
It can take in − and + lines together but stays in the hunk it started in,
because GitHub refuses a comment whose lines span two hunks. Lines shown by
expanding context cannot be selected. The comment box opens under the last
selected line, saying which lines it is on ("Commenting on lines −19 to +20").
**Save draft** makes a draft that stays on the board, out of your
review, and **Add to review** makes it and puts it in your review; either leaves
the tab where it was. `Esc` or **Cancel** closes the box and keeps what you
typed for the next new draft.

On your own pull request the box also has **Request change**, which hands what
you typed to an agent as a change to make on the selected lines. It becomes a
card on the Board, with the fix the agent writes to accept or turn down like
any other, and nothing about it is posted to GitHub: Accept lands the commit
with no reply, and the card offers Mark done where a review thread offers
Resolve. Whether the agent works in a visible session is the gear's **Agent
sessions** setting.

**Ask the agent** in the box sends what you typed as a question about the
selected lines instead. The agent starts on it in a new session in the
Terminal tab, in the PR's worktree, and the page switches to that tab. Its
prompt names the file and the lines and asks for an answer that changes no
files. While agents are disabled the board refuses the question.

Conversations sit under the last line they are on: posted threads with their
comments, fix proposals as their thread, and drafts as cards. A thread resolved
or deleted on GitHub, or one Waiting or Done on the board, is folded to one
line with its place and a tag: **Resolved**, **Deleted**, or the name of its
group on the board. Click it to open it; its header then says **Resolved on
GitHub** or **Deleted on GitHub** where one applies. Each card links to its conversation on the board.
The one thing the tab changes is a draft: **Edit** on a draft card, open or in
your review, turns the card into the comment box with its lines selected, and
you can select others. A local draft's card also has **Add to review** and
**Discard**. **Ask the agent** on a draft's card opens a question box in the
card; its own **Ask the agent** opens the agent in the Terminal tab as above,
with the draft's text in its prompt.

Every posted comment, in the Diff tab and on the Board, has a smiley under it
that opens GitHub's eight reactions, and the reactions it already has sit beside
it with their counts. Clicking one adds yours, or takes it off when it is
already yours. A reaction posts to
GitHub straight away, with no dialog. Outdated threads are not drawn; the file header counts
them.

Every box whose text goes to GitHub (a new or edited draft, a reply, a decision
on the board and the review's summary) completes emoji as GitHub does. Type `:`
and part of a name, and the box offers up to five of GitHub's emoji, those whose
name starts with what you typed first. `↑` and `↓` move through them, `Tab`,
`Enter` or a click puts the chosen one in place of what you typed, and `Esc`
closes the list. An emoji with a Unicode character goes in as that character;
one of GitHub's own, such as `:shipit:`, goes in as its name. The page draws a
comment's `:name:` as the character, or as GitHub's picture for its own.

The same boxes complete people after `@`. The list starts with the pull
request's own people (its author, the reviewers still asked or asking for
changes, and everyone who has commented), then everyone else GitHub lets the
repository assign, asked of GitHub once per repository until the server
restarts. What you type after `@` narrows it by login or display name, and the
chosen login goes in with a space after it.

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

Clicking a desktop notification about one PR opens that PR at
`/pr/<owner>/<name>/<number>` on the hub: on its Summary when you review it, on
its Board when it is yours. One about no PR, about a closed PR, or about Claude
skipping events on several PRs opens nothing.

A notification from before PR pages named their repo opens `/pr/<number>`. That
opens the one PR the hub holds with that number. When several repos hold one,
it lists them to pick from; when none does, it says so.

### Harvest timer

**Harvest timer: Off** in the gear turns it on, and **Harvest timer: On** turns
it off; the browser remembers the choice. With it on, each PR's title bar has a stopwatch button beside the gear,
which the Harvest Time Tracker Chrome extension turns into its own timer: the
entry is named `#<number>: <title>`, filed under the repo's name, and links to
the PR on GitHub.

The extension from the Chrome Web Store does not know the board, so while the
board's copy is not loaded the gear has a **Set up Harvest** item under the
switch, which opens **Set up Harvest on the board**. **Set up
the extension** copies the newest Harvest Time Tracker Chrome has installed to
`harvest-extension/` under the data dir, tells that copy about the hub's port,
opens `chrome://extensions`, shows the folder in Finder and puts its path on
your clipboard. The setup is macOS only. Then, as the dialog lists: turn on Developer mode, **Load unpacked**
the folder, turn off the Web Store's copy and reload the page. With no Harvest
Time Tracker installed, the dialog says to add it from the Web Store first.

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
Dashboard says so. Only `w`, **Release**, does anything. It asks first
(**Release the worktree?**, confirmed with `y`), then tells the watcher to set
this worktree aside on its next poll and build a fresh one. The
PR is left alone for an hour first (`mismatch_grace_seconds`), because
releasing it stops whatever was moving the branch, usually a Claude session
you were steering in the Terminal tab. `w` is you saying the work is finished,
which nothing on disk can tell.

When the watcher does release it, it stops that PR's agent manager and closes
its terminal sessions, and leaves the old worktree where it is. That worktree
is yours to clean up.

### A PR from a fork

A PR whose head lives in another repository gets a worktree and a branch both
named `orchestrator/pr/<n>`, and every fetch reads the PR's head from origin
(`refs/pull/<n>/head`), so the worktree follows what the contributor pushes.
Nothing is pushed to it from the board: the palette's `git push` and
force-push answer **This pull request comes from a fork, so it is pushed from
the fork, never from here.**, Accept refuses before landing with **… comes
from another repository, so nothing is pushed to it from here: push from the
fork**, and a plain `git push` in the worktree fails.

## Review board

The board is always up, and it is the Board tab of each PR's page on the hub. It is
two panes: a list of rows on
the left, **one per review thread**, and a panel on the right holding the one
thread you opened, with the fix an agent proposed for it. Nothing on the board
reaches the PR until you accept it, which lands the fix on the PR branch and
replies on the thread.

The server serves every board, at `/pr/<owner>/<name>/<number>/` on the hub,
so a board has no port of its own and nothing starts or stops it. A manager that
restarts leaves its board's URL as it was.

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
generated in parallel. That is what makes accepting a subset possible without
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

Outcomes arrive as a toast: a black bar at the top right for three seconds,
one when the board queues a decision, one when that decision lands, and one when
an agent finishes and a row moves into Ready for you. A move you can take back
keeps its toast up for eight seconds with the way back on it: Mark done, the
author's Confirm and Discard offer Bring back, Resolve on a review thread offers
Unresolve on GitHub, and Add to review offers Leave out of review. It sends what
the card's own button sends, once the move has landed, and Bring back puts the
card where it stood before (Waiting stays Waiting). A Done review thread that
GitHub shows resolved offers Unresolve on GitHub on its card too: the card stays
Done until GitHub answers, then comes back to your move, or says "reopen failed"
with GitHub's error. Any other Done thread offers Bring back, which touches
nothing on GitHub. Most refusals stay off the
toasts and say why in red on what you pressed, as below. A failure toasts only when that place cannot say it: a held control you
press anyway gives its reason, a refused Close or Dismiss, a session from the
git palette that did not open, and a **Go to the session** whose session is no
longer running, with a second toast that the comment is back where it was. The
banner under the header says when the board cannot be reached.

While a decision is on its way, the button you pressed says what it is doing,
the other buttons wait, and the footer, the thread's row and its card in the diff
are faded until the board answers. One that posts to GitHub (a reply, Post now,
Not fixed, Reply and mark done, a reaction, or a Resolve or Reject that carries
a reply) shows no buttons at all while it goes: the footer reads only
**Posting to GitHub…**. A decision the board refuses says why on the
footer, in red, with the buttons as they were.

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
is `⇧R`, because `r` is Ready for review on the Dashboard, and post now is `⇧G`, because
`g` is the git palette there. `?` shows the keys, with a capital written `⇧R`.

The rail is grouped, under a heading that carries the group's name and how many
rows are in it. A group with no rows is not drawn at all. The groups come in one
order, and the header repeats the counts: **Ready for you**, **Agent working**,
**Queued for agent**, **Sent back for rework**, **Landing**, **Waiting on
reviewer**, **Assumed done**, **Deferred**, **Done**, with Assumed done in the
Done column. On a PR you review, Waiting on reviewer is **Waiting on author**,
in the Columns view too, and **Not my
conversation** follows Assumed done, in the Done column as well.

On a PR you wrote, a run the agent declines lands by what it says the comment
was. The branch already does what was asked (`already-done`), or the comment
only thanks you, approves or says LGTM (`acknowledgement`): Assumed done. A
question for you (`question`), or anything unclear, risky, out of scope or only
yours to decide: Needs a look, as does a run that failed. A reviewer's new
comment on an Assumed done or confirmed thread brings it back and the agent runs
again, as a new comment on a resolved thread does.

On a PR you review, an agent reads each thread whenever a new comment arrives
and says whose move it is: yours (Ready for you), someone else's (Waiting on author),
settled for you to confirm (Assumed done), or nothing to do with you (Not my
conversation). Until it has answered, the thread sits in Ready for you and its card
says "not yet read". A reply you post from the board moves it to Waiting on
author at once, and the agent reads it again. A Waiting on author card on a
line, whose last comment is yours, also offers **Check for fixes**: an agent
reads the changes since your comment and puts the card in Assumed done if they
address it, or My move if not. The Dashboard's **Check all threads for fixes**
does that for every such card. Only you move a thread to Done:
an Assumed done card's footer is **Confirm** (`g`) and **Move** (`m`), which
asks where it stands instead. On a review thread, one left on a line, Confirm
moves the card to Done and asks first, with two ticks, both on: resolve the
thread on GitHub, and put 👍 on the newest reply from someone else. Untick
either to leave it undone on GitHub. Confirm posts no reply. A mention in a
review thread gets the same Confirm, with **Reply and mark done** and **Mark
done** after Move. On a conversation comment, a review summary or the PR
description, mention or not, and on a PR you wrote, Confirm asks nothing: it
moves the card to Done and touches nothing on GitHub. A Not my conversation card offers the same question as **Move**. It
lists My move, Their move and Not my conversation, leaving out the group the
card is in; Defer is its own button. On a PR you wrote it lists
Needs a fix, which starts a fresh agent run, Needs a reply from me, which puts
it in Needs a look, and Their move. Placing a card by hand posts nothing,
and the next new comment is read again. Hovering a heading, a column head, or the state word on a card or in
the panel gives its one-line definition, the same as the table below. Inside a group the thread replied to most
recently comes first, except in Ready for you: there a conversation you replied
to sits at the top until you act on it, and the rest read by the moment their fix
became yours to decide.

| Word             | Meaning                                                                         |
| ---------------- | ------------------------------------------------------------------------------- |
| `draft`          | a comment you wrote here, not on GitHub yet                                     |
| `enrolled`       | a draft in your review; it posts when you send the review                       |
| `proposed`       | there is a fix to decide on                                                     |
| `asking`         | an agent stopped to ask you something before it goes on                         |
| `answered`       | someone answered; yours to reply to or resolve                                  |
| `reopened`       | you replied, and it is yours again whatever the agent is doing                  |
| `declined`       | the agent declined to write a fix, and said why                                 |
| `failed`         | three attempts failed                                                           |
| `stopped`        | you stopped the agent before it finished                                        |
| `removed`        | the comment was deleted on GitHub before this row was finished                  |
| `queued`         | waiting for an agent                                                            |
| `working`        | an agent is running                                                             |
| `rework`         | an agent is working from your rework note                                       |
| `session`        | a session you steer is open in the Terminal tab                                 |
| `landing`        | accepted: the fix is on its way to the PR branch, then the reply                |
| `filing`         | accepted: an agent is filing the ticket, and the reply follows once it is filed |
| `rebasing`       | the fix conflicted on accept; an agent is rebasing it onto the PR head          |
| `push failed`    | accepted, but pushing the fix to the PR branch failed                           |
| `landing failed` | accepted, but the landing stopped before anything was pushed, and said why      |
| `reply failed`   | pushed, but posting the reply on GitHub failed                                  |
| `filing failed`  | accepted, but filing the ticket failed; nothing was posted to GitHub            |
| `waiting`        | their move; parked until the other side answers                                 |
| `assumed-done`   | an agent read it as settled; only you can move it to Done                       |
| `not-mine`       | an agent read it as asking nothing of you                                       |
| `deferred`       | parked until something wakes it                                                 |
| `rejected`       | you turned it down                                                              |
| `landed`         | on the PR branch                                                                |
| `resolved`       | closed, worktree and branch gone                                                |
| `marked done`    | closed on the board alone; GitHub was not asked to resolve it                   |
| `confirmed`      | you confirmed it was settled; nothing was posted to GitHub                      |
| `discarded`      | a draft thrown away with nothing posted                                         |

A closed card reads `resolved` only where GitHub resolved the thread; one closed
on the board alone reads `marked done`. Everything in Done is struck through.

On a PR you wrote, every new reply on a thread starts an agent, whatever you had
decided before it: a rejected, resolved, landed or deferred thread comes back and
is worked on again, and the agent is told how the thread had ended up. A reply
that arrives while an agent, a session or a push is under way queues a rework on
top of it once it finishes.

Buttons say what they do rather than naming the state machine, so a rework
renders as **Send back for rework**, and opening a session you steer as **Steer it yourself**. Almost every button that posts to GitHub, drops a worktree or stops
an agent asks in a dialog that says what it is about to do, and Resolve, Reject,
Accept and opening a session give you a box to type in. **Stop** (`x`) asks
before it halts the run. Three post at once with no dialog: **Post now**,
**Unresolve on GitHub** and a reaction. Accept takes the reply you
want on the thread; leave it blank and the thread gets the commit link alone.
Opening a session takes what the rework should do differently, which is the
difference between steering the next attempt and starting it over blind; leave it
blank and the session starts unsteered.

On your own PR, which agent buttons a card offers depends on whether an agent
has run on it yet. **Write a fix** (`i`) shows only where none has, such as a
thread that arrived while agents were disabled. Once one has, a card with no
fix waiting offers **Try again** (`t`), a fresh attempt; **Send back for
rework** (`w`), a re-run from the commit it already wrote, carrying your note;
and **Steer it yourself** (`o`). A proposed fix offers only Send back for
rework of the three, as does a declined one; after a stopped or failed run all
three show, and after a landing that failed, Send back for rework and Steer it
yourself. On a merged or closed PR none of them shows, nor **Open a shell** or
**Ask the agent**. On a Waiting card, Bring back reads **Stop waiting** (`u`):
it brings the card back to Ready for you, with nothing posted.

An agent working on your thread can stop and ask instead of guessing, when
the comment cannot be done as stated or the way forward goes beyond it, such as
a production change for a comment on a test. The card turns `asking` and the
PR's move reads **Your move: an agent is asking you a question**. The panel
shows **Agent question**, with how many of its planned steps it finished, then
the question and one button per answer the agent offered, and **Other…**, which
opens a box for your own words and **Answer**. An answer carries on the
agent's own conversation, in a visible session or not as the gear's **Agent
sessions** says, and comes back as a proposal or another question. The footer
has **Answer in a session** (`o`), which opens that conversation in the
Terminal tab for you to answer there, **Defer**, and **Drop** (`⇧D`), which
asks first and then deletes the question, any proposal before it and the
agent's worktree, as if no agent had run. None of this posts to GitHub. A note
beside the heading says when the PR has moved since the question.

When a comment asks for code already in the PR's diff to go elsewhere ("not
part of this ticket", "move this to another PR"), the agent can propose a split
instead of a fix. The panel shows a card per part, in the order they run:
**Ticket**, when the agent proposes one; **Changes to this PR**, the commit
that takes the code out; **New PR**, the branch that carries it and its base;
and **Reply**, which names the new PR. Each part not yet run has **Accept**; the ticket and
the reply also have **Edit**, which saves new words and accepts nothing, and
each has **Rework**, which sends that part back to the agent with your note
while the others keep theirs. **Accept all** in the footer accepts every part
not yet accepted, one at a time in that order. A part that has run cannot be
undone, and once one has, Reject and Send back for rework leave the footer. An
agent files the ticket and opens the new PR, with the skill the repo's
`[[repos]]` entry names as `pr_skill` (`create-pr` by default); a `draft` set
on the entry decides whether the new PR is a draft, whatever the skill chose.

**Resolve** (`s`) always resolves the thread on GitHub. Its dialog takes an
optional reply, posted first. On a reviewer's card an empty Resolve puts 👍 on
the newest reply as well, a tick that starts on. **Mark done** (`h`) moves the
card to Done on the board at once and sends GitHub nothing: no reply, no 👍, no
resolve. An issue comment or a mention in the PR description has no thread for
GitHub to resolve, so it offers **Reply and mark done** (`v`) where a review
thread offers Resolve. Its dialog will not post until you write a reply. A change
you asked for on the board alone offers Mark done and no Resolve. Where the agent had something to
say about the comment, the reason it skipped one or the note it left on a fix,
the dialog offers **Use the agent's words**, which pastes that into the box
for you to edit before it posts.

On someone else's PR, a comment that mentions you and that you have not answered
is a card of its own, and so is a mention in the PR description. A reply naming
you on a review thread you started is not a mention: that thread is yours
already. A mention card offers
**Reply and mark done** (`v`), **Ask the agent** (`⇧A`) and **Mark done** (`h`), with **Defer** at the bottom right, and no
reply link. Reply and mark done will not post until you write a reply. Ask the
agent puts an agent on the mention to draft your reply, in a visible session or
not as the gear's **Agent sessions** says; the draft comes back to the card for
you to accept, change or turn down, and nothing posts before you accept. A
mention on your own PR is a card too, with the author's buttons rather than
these. The reply goes on
the thread for a review comment, or to the PR's conversation quoting the comment
for anything else (a mention in the description gets an @ to its author and no
quote), and the card moves to Done on the board only: nothing is resolved on
GitHub. **Mark done** moves the card to Done with nothing posted at
all.

On a comment you wrote yourself, and that nobody else has replied to, the same
dialog offers **Delete the comment** under "On GitHub, also:". Tick it and the verb posts nothing:
Accept lands and pushes the fix and then takes your comment off GitHub, and
Resolve closes the card the same way, with no thread left to resolve. In the
Accept dialog, **Resolve the thread** greys out while delete
is ticked and keeps whatever you had set, so unticking delete gives it back. It is the note you left for an
agent rather than a question anybody is waiting on an answer to, so there is
nothing to reply to once the fix is in. The tick is clear every time the dialog
opens, it never appears on a reviewer's comment or a review summary, and the row
settles in Done; in the Diff tab its card folds under **Deleted**. The board keeps the comment's text and
everything said under it for the life of the PR.

Confirming a decision walks on to the next thread the way `j` would, in the order
the list was in before the decision moved anything, and leaves the panel open on
it. On the last thread it stays where it is, and the panel follows the thread you
just decided.

Accept cherry-picks the thread's whole commit range, squashes it into one
commit carrying the last one's message, pushes, and replies on the thread with
the landed SHA. A reply you typed yourself posts in your words, with the commit
link under it and no `🤖`. Every reply the board sends joins the panel's
transcript, and none of them comes back to the board as a new comment.
One Accept is one commit and one push, so one CI run per accepted comment.
Every step is recorded before the next runs, and accepting again resumes at the one
that failed. Once it has landed and replied the row drops to Done carrying the
SHA that landed; a row whose reply failed is still `landing`, under that
heading, with the button that retries the step that failed. A resolved row settles the
same way, behind the line that says whether it replied, and the reply you typed
never comes back to the board as a new comment — including the ones posted on the
pull request itself, which the poller knows by the node id GitHub hands back.

A cherry-pick that conflicts, because the PR branch moved since the fix was
written, does not come back to you. The row turns `rebasing`, an agent rebases
the fix onto the current head in the thread's own worktree, and your Accept
waits: once the rebased fix reports its tests passed it lands, pushes and
replies on its own. If its tests failed, or a second attempt against the same
head still conflicts, the row comes back `proposed` with the reason and the
decision is yours again.

Resolve is how you close a comment without landing a fix, whether you agreed
with the agent's skip or decided the fix is not needed at all. Its reply posts in
your own words with no robot prefix on the comment's thread, and then the thread
is resolved on GitHub. Leave the reply blank and it resolves without one. Mark
done closes the card on the board and leaves GitHub as it is.

While a comment is open in the panel, the board asks GitHub whether it is still
there. A comment deleted while its row still wanted work turns that row
`removed`, its line reading **comment removed from GitHub**: it offers Mark
done, and Accept where there is a commit worth keeping, because the worktree
holds real work that a deletion should not quietly bin. One that had already
landed or been resolved keeps its status, and in the Diff tab its card folds
under **Deleted**: somebody tidied the comment away after the work was done and
nothing is wrong. Neither can reply, because the thread is gone with the
comment, so the dialog drops its reply box.

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
tools use them too. It also leaves each skill it shipped, `rebase-on-main` and
`create-pr`, in the agent's skills folder, since the agent can use them without
the orchestrator: `~/.claude/skills` for Claude Code, `~/.agents/skills` for
Codex, or `<CLAUDE_CONFIG_DIR>/skills` when `agent_command` sets
`CLAUDE_CONFIG_DIR`. It names each one it finds with the `rm -rf` that removes
it. The worktrees the watcher cut next to your clones are yours to remove.
