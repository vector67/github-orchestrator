# One-command install

Date: 2026-10-08. Decided. Everything in "Already decided" came from the owner,
either before the first draft or as answers to its open questions, and is not
reopened here. The rest of the spec is the design that follows from it. The
questions the edits raised are listed at the end.

## Problem

Installing github-orchestrator today means cloning the repo, running
`uv sync`, answering `setup` in a terminal and running `make install`, which
builds the front end with node, builds the Swift notifier apps, writes a
LaunchAgent (or a cron job on Linux) and links a command into `~/.local/bin`.
Every step assumes the checkout stays where it was cloned and that the shell it
ran from has the right `PATH`.

What goes wrong along the way:

- **Nothing runs until three keys are set.** `_parse` refuses a missing config
  file or one with any of `gh_account`, `watch_repo`, `local_path` at its
  placeholder (`settings/_config.py:154-167`). The CLI checks it before every
  command but `config` and `setup` (`cli/_cli.py:97-98`) and the watcher exits 2
  (`watcher/__main__.py:43-47`). There is no state in which the hub runs and a
  person can be shown what to do next.
- **`setup` crashes without gh.** It calls `access.check_access`
  (`cli/_setup.py:98`), which runs `gh auth token` (`github/_gh_cli.py:60`), and
  a missing `gh` surfaces as `FileNotFoundError`. The requirement checks that
  would have caught it live in `cli/_install_checks.py:61-77` and only run inside
  `make install`, after `setup` (`Makefile`, the `install` target).
- **Requirements assume Homebrew.** Every fix the requirement checks print is a
  `brew install` line (`cli/_install_checks.py`), so a machine without Homebrew,
  and every Linux machine, gets advice it cannot follow.
- **The LaunchAgent runs uv against the checkout.** The plist's
  `ProgramArguments` are `@UV@ run --project @REPO_ROOT@ python -m github_orchestrator.watcher --loop`
  (`launchd/com.github-orchestrator.watcher.plist.template`), filled in by
  `_render` (`cli/_scheduler.py:35-47`). `PATH` is frozen at install time with
  uv's directory first (`cli/_scheduler.py:27-32`). When Homebrew upgrades uv,
  the next spawn is killed with `OS_REASON_CODESIGNING` until the job is booted
  out and bootstrapped again.
- **Linux gets a cron job.** `make install` on Linux installs a crontab line
  instead (`Makefile`, `install_cron`; `cron/github-orchestrator.cron.template`),
  which runs one cycle at a time rather than a resident watcher, so there is no
  hub to serve the board between cycles.
- **The checkout is load-bearing at runtime.** `REPO_ROOT` is three parents up
  from `settings/_config.py` (`settings/_config.py:42`). The default config file
  is `<checkout>/config.toml` (`settings/_config.py:28-32`), its seed is
  `<checkout>/config.toml.example` (`settings/_config.py:252`), the plist and
  cron templates are read from the checkout (`cli/_scheduler.py:7-10, 67`), the
  rebase skill is copied from `<checkout>/skills` (`cli/_install_checks.py:81`),
  and every command line handed to an agent starts
  `uv run --directory <checkout> python -m github_orchestrator.cli`
  (`cli/_report_commands.py:26`, `cli/_command_lines.py:4`). Inside an installed
  wheel none of those paths exist.
- **One repo per instance.** Config holds one `watch_repo` and one `local_path`
  (`settings/_config.py:74-76`). The watcher searches that repo
  (`watcher/_cycle.py:180-200`), placement and teardown cut worktrees from that
  clone (`watcher/_placing.py:28`, `watcher/_teardown.py:31`), working copies are
  wired to it (`wiring.py:440`), and the hub's wall and top bar name it
  (`board_api/_wall.py:79-98`, `frontend/app/components/hub-bar.gts:45-46`). A
  second repo means a second instance with its own config, port, data dir and
  LaunchAgent, or `switch-repo` to trade one repo for another
  (`cli/_switch_repo.py`).
- **Without gh auth the wall waits forever.** The hub answers
  `/api/pull-requests` with 503 `watcher-starting` until the watcher finishes a
  cycle (`board_api/_hub.py:119-122`). If every cycle fails on auth, the page
  says "starting" for good and never says why.

`status` already asks the hub whether it is up: it probes
`<hub_url>/api/health` (`cli/_hub.py:10-15`) and only falls back to the
watcher's lock when nothing answers (`cli/_status.py:65-72`). This spec builds
on that probe rather than replacing it.

## Already decided

- The repo goes public as `vector67/github-orchestrator`, after a squash to a
  fresh history, under the MIT licence already in `LICENSE`.
- Distribution is a release wheel built in CI, with the built board bundle
  inside. Users run
  `curl -LsSf https://github.com/vector67/github-orchestrator/releases/latest/download/install.sh | sh`,
  which installs uv if missing and runs `uv tool install`. An `update` command
  fetches the newest release.
- macOS and Linux are both supported. macOS runs the watcher as a LaunchAgent,
  Linux as a systemd user unit. The installer, `start`, `stop`, `restart`,
  `doctor`, `uninstall` and the CI smoke job cover both. Cron mode goes.
- No Homebrew. The installer installs uv, gh and claude from their own official
  installers or release downloads, without sudo.
- tmux mode is removed. Browser mode is the only mode, and `pr_windows` goes.
  pandoc goes with it.
- Instances stay first-class. Migration never merges instances: each keeps its
  config, its data dir and its service.
- One hub watches N repos, with a repo filter in the top bar: all, one, or a
  selection. The filter applies to the wall, the top bar's "N need you" and the
  PR switcher. Notifications ignore it and always cover every watched repo.
- Setup moves to the browser. The terminal installer checks requirements, lists
  what is missing, asks consent, installs what the user approves, runs
  `gh auth login` when gh has no token, installs the wheel, starts the service,
  opens the board and prints "If your browser didn't open, go to
  http://127.0.0.1:8720". The board then shows a setup screen: GitHub username,
  then that account's repositories at once, then a multi-select, then other
  options, then the board.
- The setup screen lists the repos the account can push to, with a "Show
  read-only" toggle that adds the rest, and takes an `owner/name` typed by hand
  for a repo in neither list.
- On Linux the installer asks whether to enable lingering, and runs
  `loginctl enable-linger` when the user agrees and the distribution allows it.
- The daily release check can be turned off with `check_for_updates = false`;
  it is on by default.
- A tutorial in both places: the terminal for machine setup, the board for a
  first-run tour.
- Desktop notifications are optional. On macOS the installer always asks whether
  the user wants them; a yes builds the notifier apps, installing Apple's
  Command Line Tools first if they are missing and the user agrees. On Linux
  notifications go through `notify-send` when it is installed.
- The hub checks for a new release once a day and shows a quiet "Update
  available" badge on the board; `status` prints it; `update` installs it.
- The CLI explains itself and has `open`, `start`, `stop`, `restart`,
  `restart-all`, `status`, `help`, `update`, `tutorial`, `doctor`, `logs`,
  `uninstall`, `config` and `runs`. `queue` and `undismiss` stay but are left
  out of the command list, and appear in `--help` under a last section titled
  "debugging". `switch-repo` is deleted; the setup screen's repo list replaces
  it.

## Goals

- A person with a Mac or a Linux desktop and a GitHub account goes from nothing
  to a board showing their PRs with one pasted command and a few clicks.
- Nothing at runtime depends on a checkout, on uv's binary, on Homebrew, or on
  the shell the install ran from.
- Running the installer again repairs an install rather than failing on one.
- An existing install (today's checkout, its config, its instances, its data)
  moves over without losing state.
- Each step of the plan merges on its own and leaves `make test` green.

## Non-goals

- The squash and the scrub of history and fixtures before going public. That is
  a checklist of its own.
- PyPI or Homebrew distribution.
- Windows, and Linux without systemd.
- Installing anything with sudo or a system package manager. git on Linux is the
  one requirement the installer cannot install; it prints the distribution's
  command and stops.
- Merging instances, in migration or anywhere else.
- Changing what the watcher, the PR managers or the boards do once configured.
- A settings page for every config key. The setup screen covers the account,
  the repos and a short list of options; the rest stays in the TOML file.

## The journey

### Install

On a Mac:

```text
$ curl -LsSf https://github.com/vector67/github-orchestrator/releases/latest/download/install.sh | sh

github-orchestrator installer

Checking this Mac:
  ok       macOS 15.5 (arm64)
  ok       git 2.50.1 (Command Line Tools)
  missing  uv          runs the install; from astral.sh
  missing  gh          talks to GitHub; from github.com/cli/cli releases
  ok       claude 2.1.4

Install uv and gh now? [Y/n] y
==> Installing uv
==> Installing gh 2.81.0 into ~/.local/bin
==> gh has no login yet. Logging in to GitHub
    (gh auth login runs here; it opens github.com in your browser)
==> Installing github-orchestrator 0.4.0
==> Starting the watcher
==> Waiting for the board

Would you like desktop notifications when a PR needs you? [Y/n] y
==> Building the notification apps (about a minute)

Opening http://127.0.0.1:8720
If your browser didn't open, go to http://127.0.0.1:8720
```

On Linux the survey reads "Checking this machine", names the distribution, and
there is no notifier question: notifications use `notify-send` when it is on
`PATH`, and the survey prints it as optional with the package that provides it.

### Setup screen

The board opens on `/setup` because the hub is in setup mode. gh is already
logged in, because the installer did that before opening the browser.

1. **Your GitHub username.** One field, filled with gh's active account. On
   submit the hub checks `gh auth token --user <name>`. If gh has no token for
   that account (a different account was typed, or the token was revoked since),
   the screen says so and shows the command to run in a terminal,
   `gh auth login`, then checks again.
2. **Your repositories.** Listed as soon as the token works, newest push first,
   with a filter box: every repo the account can push to as owner, collaborator
   or organisation member. A "Show read-only" toggle adds the repos it can only
   read. Each row shows whether you have open PRs or review requests there, so
   the likely picks stand out. Below the list, "Add a repo by name" takes an
   `owner/name` for a repo the account reaches in neither list, such as a public
   open-source repo you only review.
3. **Pick any number.** A checkbox per row. Each picked repo gets a clone line
   below the list: "Found a clone at ~/repositories/widgets" or "Will clone into
   ~/repositories/widgets", editable.
4. **Other options.** A short list with today's defaults: the Claude model,
   whether agents start automatically (`claude_enabled`), concurrent thread
   agents (`max_thread_runs`) and the per-worktree command per repo
   (`new_worktree_command`). Everything is optional.
5. **Start watching.** The hub writes the config, clones what it said it would,
   and the watcher restarts into watching mode. The page shows each clone's
   progress, then the wall.

### First run

The wall shows "Waiting for the first poll" per the next-move rules (G3 in
`2026-10-01-next-move-design.md`) until the first cycle lands. The first time
the wall has rows, the tour starts: the wall groups, the repo filter, a PR page
and its Board, Dashboard, Terminal and Diff tabs, and what "Needs you" means. It
can be skipped and replayed with `github-orchestrator tutorial`.

### Day to day

`github-orchestrator open` opens the board. `status` says whether the watcher
and the hub are up and what they hold. Repos are added or removed from the same
setup screen, reached from the top bar at `/setup`.

### Update

Once a day the hub asks GitHub for the newest release. When it is newer than
the running version, the top bar shows a quiet "Update available" badge whose
tooltip names the version and the command, and `status` prints a line for it.
Nothing installs on its own.

```text
$ github-orchestrator update
Installed 0.4.0, newest 0.5.0.
==> Installing 0.5.0
==> Restarting the default instance and work
Updated to 0.5.0.
```

### Uninstall

```text
$ github-orchestrator uninstall
This stops every instance and removes:
  the LaunchAgents for the default instance and work
  the github-orchestrator command (uv tool uninstall)
It keeps, unless you say otherwise:
  ~/.config/github-orchestrator          config for 2 instances
  ~/.local/share/github-orchestrator     2.1 GB, 14 PR worktrees
  ~/Applications/GitHub Orchestrator*.app
Your clones are never touched.
Remove the config and data too? [y/N]
```

On Linux the first list names the systemd units, and there are no apps. uv, gh
and claude stay installed either way; the installer may have put them there,
but other tools use them too.

## The installer script

`install.sh` is a POSIX `sh` script published as a release asset, so
`https://github.com/vector67/github-orchestrator/releases/latest/download/install.sh`
is a stable anonymous URL once the repo is public. It follows rustup's and uv's
installers where they solved the same problem.

**Prompts.** Under `curl | sh` stdin is the script, so every question reads from
`/dev/tty`. With no terminal at all and no `-y`, the script prints what it would
install and the commands to do it by hand, and exits 1 without changing
anything.

**Flags and environment.**

| Flag                | Environment                      | Effect                                                             |
| ------------------- | -------------------------------- | ------------------------------------------------------------------ |
| `-y`, `--yes`       | `GITHUB_ORCHESTRATOR_YES=1`      | Answer yes to every install question; notifications stay off.      |
| `--notifier`        | `GITHUB_ORCHESTRATOR_NOTIFIER=1` | Build the notifier apps without asking (macOS).                    |
| `--version X`       | `GITHUB_ORCHESTRATOR_VERSION=X`  | Install that release, not the newest.                              |
| `--no-modify-path`  | `GITHUB_ORCHESTRATOR_NO_PATH=1`  | Never edit shell profiles; print the line to add.                  |
| `--no-open`         | `GITHUB_ORCHESTRATOR_NO_OPEN=1`  | Start the service but do not open the browser.                     |
| `--wheel URL\|PATH` | `GITHUB_ORCHESTRATOR_WHEEL=...`  | Install this wheel. CI uses it to test the script against a build. |
| `--skill`           | `GITHUB_ORCHESTRATOR_SKILL=yes`  | Install a missing `rebase-on-main` skill without asking.           |
| `--no-skill`        | `GITHUB_ORCHESTRATOR_SKILL=no`   | Leave the skill out; `github-orchestrator skill` adds it later.    |

**Where each requirement comes from.** Every source installs into the user's
home and needs no sudo. Tools land in `~/.local/bin`, which the script puts at
the front of its own `PATH` once it has installed anything there, so later steps
and the service's recorded `PATH` find them.

| Requirement | macOS                                                                                                                           | Linux                                                                                                        |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| git         | Apple's Command Line Tools, `xcode-select --install`.                                                                           | Not installed. The script prints the distribution's command (`sudo apt install git` and the like) and stops. |
| uv          | astral's installer, `curl -LsSf https://astral.sh/uv/install.sh \| sh`.                                                         | The same installer.                                                                                          |
| gh          | The `macOS` zip from the newest `cli/cli` release, checked against the release's `checksums.txt`, `bin/gh` into `~/.local/bin`. | The `linux_amd64` or `linux_arm64` tarball from the same release, checked the same way, into `~/.local/bin`. |
| claude      | Anthropic's native installer, `curl -fsSL https://claude.ai/install.sh \| bash`.                                                | The same installer.                                                                                          |
| Python      | uv-managed, fetched by `uv tool install`.                                                                                       | The same.                                                                                                    |
| node, npm   | Not needed; the board ships built.                                                                                              | Not needed.                                                                                                  |
| pandoc      | Not needed; its only caller goes with tmux mode (see "Removing tmux mode").                                                     | Not needed.                                                                                                  |

gh installed from a release download does not update itself. `doctor` reports
its version, and running the installer again replaces it with the newest
release when the user agrees.

**Order.** Each step is safe to repeat.

01. **Platform.** Darwin on arm64 or x86_64, or Linux on x86_64 or aarch64 where
    `systemctl --user` reaches a user manager. Anything else stops with a
    message; a Linux without a user manager is told so and pointed at running the
    watcher by hand (`github-orchestrator start --foreground`).
02. **Survey.** Look for: on macOS the Command Line Tools (`xcode-select -p`);
    `git`, `uv`, `gh`, and `claude` (or the configured `claude_command` when a
    config already exists); on Linux, `notify-send`. Print one line per item: ok,
    missing, or optional.
03. **Ask once.** "Install X, Y and Z now? [Y/n]". The list says where each
    comes from, per the table above. Declined items print their commands and the
    script stops, since every listed item is required.
04. **Install.** uv first, so the rest can use it. On macOS the Command Line
    Tools open Apple's own dialog; the script waits, polling `xcode-select -p`
    every five seconds for up to 30 minutes, and says it is waiting.
05. **gh login.** If `gh auth status` fails, say why and run `gh auth login --web --git-protocol https` on the terminal. The script does not go on until
    `gh auth status` passes, so the setup screen always starts with a token. A
    declined or failed login prints the command and stops. With no terminal and
    `-y`, a token in `GH_TOKEN` counts; without one the script stops.
06. **Find an older install.** If `~/.local/bin/github-orchestrator` is a symlink
    into a checkout's `.venv` (what `make install_command` made), the LaunchAgent
    runs `uv run --project <dir>`, or the crontab holds a `github_orchestrator`
    line, say so and ask to replace it. Without `--force`, `uv tool install`
    refuses to overwrite an executable it did not create; with it, the link
    would be replaced without a word, so the script asks first. The checkout path
    is kept for the config migration.
07. **Install the wheel.** `uv tool install --force --python 3.12 <wheel URL>`.
    uv fetches a managed Python if there is none.
08. **PATH.** If `uv tool dir --bin` (which is `~/.local/bin`, where gh and
    claude went too) is not on the shell's `PATH`, ask to run
    `uv tool update-shell` (unless `--no-modify-path`). Either way, the rest of
    the script calls the shim by its absolute path.
09. **Start.** `github-orchestrator start --from-installer`. `start` migrates an
    old config if step 6 found one, writes the LaunchAgent or the systemd unit,
    loads it and waits for `/api/health` (see "The CLI").
10. **Notifications.** On macOS, always ask "Would you like desktop
    notifications when a PR needs you? [Y/n]". On a yes, check for `swiftc` and
    `codesign` (`xcrun --find`). When they are there, build the apps. When they
    are not, say the build needs Apple's Command Line Tools and ask "Install
    them now? [Y/n]"; a yes runs `xcode-select --install`, waits as in step 4,
    then builds. A no at either question prints how to add notifications later
    (`github-orchestrator doctor` names the command). The Command Line Tools
    usually came with git already, so the second question is rare. On Linux
    there is no question about notifications; the survey line for `notify-send`
    is all. Linux asks one question here instead: "Keep the watcher running
    after you log out? [y/N]", which runs `loginctl enable-linger` on a yes
    (see "The systemd user unit").
11. **Open.** `github-orchestrator open`, then always print "If your browser
    didn't open, go to http://127.0.0.1:8720" with the instance's real port.
    On Linux, a machine with no graphical session gets the same line and no
    attempt to open.

The terminal half of the tutorial is the script's own narration: one sentence
under each step saying what it is for, as above.

## The hub in setup mode

### Three states

The watcher process runs the hub in every state. `ConfigFile.check()` no longer
stops it; it chooses the state.

| State      | When                                                            | What runs                                                     |
| ---------- | --------------------------------------------------------------- | ------------------------------------------------------------- |
| `setup`    | No config file, no `gh_account`, or no repos.                   | The hub only. No polling, no managers.                        |
| `watching` | A complete config.                                              | Today's loop: the hub, polling, managers.                     |
| `broken`   | A config that does not parse (bad TOML, unknown key, bad type). | The hub only, serving the error on `/setup` and `/api/setup`. |

A broken config is not overwritten from the page. The page shows the error and
the file's path, and offers "Move it aside and start again", which renames it
to `config.toml.broken-<time>` and drops to `setup`.

### Leaving setup

The simplest switch is a restart. When the setup write lands, the hub writes the
config, finishes any clones, then the watcher exits 0 and the service manager
starts it again in `watching`: launchd because the plist sets `KeepAlive`,
systemd because the unit sets `Restart=always`. The page polls `/api/health`
until `state` is `watching`. launchd waits at least `ThrottleInterval` (10s by
default) between spawns, so the plist sets it to 1; the unit sets
`RestartSec=1` for the same reason.

Hot-reloading the container was considered and not proposed: the container is
built once from settings (`wiring.py:1217-1264`), and rebuilding it inside a
running loop touches every module for one transition that happens rarely.

### Health

`/api/health` (`board_api/_hub.py:138-142`) gains:

- `state`: `setup`, `watching` or `broken`;
- `version`: the installed version;
- `watcher`: `{last_poll_at, last_error}` from the same files `status` reads;
- `newest_release`: `{version, checked_at}` from the daily release check, or
  null before the first check or when it fails.

`status`, `doctor`, `start` and the page all read this one answer. `status`
already probes the route to decide whether the hub answers (`cli/_hub.py:10-15`);
the probe now returns the body, so the hub line, the state, the version and the
update line all come from the hub.

### The daily release check

The hub, in every state, asks
`https://api.github.com/repos/vector67/github-orchestrator/releases/latest`
anonymously at start and then every 24 hours, and keeps the answer in the data
dir (`newest_release.json`) so a restart does not ask again early. A failed
check is logged and leaves the last answer in place. `check_for_updates = false`
stops the check entirely: the hub never calls the releases API, `newest_release`
is null, and `status` and `update` still check when run, since the user asked. The top bar shows "Update
available" when `newest_release.version` is newer than `version`; the badge
reads `/api/health` through the store like the setup data, since it is hub
state and not a summary of a PR.

### The wall when polling fails

While `state` is `watching` and no cycle has succeeded, `/api/pull-requests`
keeps answering 503, now with the watcher's last error in the body. The wall
shows that error and its fix in place of "starting". The common ones get plain
words:

- gh has no token for the account: "Log in with `gh auth login`, then this page
  retries."
- The account cannot see a repo: "You can't see owner/name as login. Remove it
  from your repos, or ask for access."
- A clone is missing or not a clone of that repo: "No clone of owner/name at
  path."

### The setup API

Under the hub's `/api` prefix, behind the same loopback guard as every other
route (`board_api/_hub.py:292`, `board_api/_guarded.py:92`). These routes write
files and run `git clone`, so the guard's host and origin checks matter more
here than anywhere else in the hub.

| Route                                   | Does                                                                                                                                                                                       |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `GET /api/setup`                        | The state, the config as it stands (account, repos with clone paths, options), the config file's path, any parse error, gh's active account, and the requirement check results. With etag. |
| `GET /api/setup/accounts/{login}`       | Whether gh holds a token for the login, and the token's scopes. 404 `no-gh-token` with the fix when not.                                                                                   |
| `GET /api/setup/accounts/{login}/repos` | The repos the login can see, newest push first, each with `can_push`, `has_my_prs` and `default_branch`. Paginated server side; cached for a minute.                                       |
| `GET /api/setup/repos/{owner}/{name}`   | One repo typed by hand: whether the login can see it, with `can_push` and `default_branch`. 404 `repo-not-visible` with the fix when not.                                                  |
| `GET /api/setup/clones/{owner}/{name}`  | A suggested path, whether something is there, and whether it is a clone of that repo.                                                                                                      |
| `PUT /api/setup`                        | Write the whole config. `If-Match` with the body's etag, like the board's operations. Answers 202 with an operation to poll.                                                               |
| `GET /api/setup/operations/{id}`        | Progress of a write: each clone's state, then `restarting`.                                                                                                                                |
| `POST /api/setup:move-aside`            | Rename a broken config and drop to `setup`.                                                                                                                                                |

The repo list returns every repo with `can_push` from the `permissions.push`
field GitHub's `GET /user/repos` already carries; the page shows only the
pushable ones until "Show read-only" is on. A repo already in the config shows
whatever its permission, so a read-only repo picked earlier does not vanish from
the list. A repo typed by hand is checked with `gh api repos/{owner}/{name}`
before it joins the picks, and stays in the list from then on like any repo in
the config.

`PUT /api/setup` refuses with 422 and a message per field when a repo is not
`owner/name`, the account cannot see a repo (`Access.check_access`), a clone
path holds something that is not a clone of that repo, or `hub_port` collides
with the boards' 8730-8829 (`settings/_switches.py:11`).

Removing a repo through `PUT` stops its managers, closes its PRs' boards and
archives its state, queues and flags the way `switch-repo` does today
(`cli/_switch_repo.py:15-27`, `settings/_switches.py:79-97`). That code moves
from the CLI to the setup write, and `switch-repo` is deleted. The removed repo's
worktrees stay; the response lists them.

### The setup screen in the store's terms

The front-end store spec says only `store.ts` imports `data/http`, enforced by
lint in its step 6 (`2026-10-08-front-end-store-design.md`, "The rule"). The
setup screen keeps to that: setup data is one more entity in the store, not a
PR record, and the screen reads and writes it through the store. It is not a
summary, so the summaries module is not involved.

The `/setup` route sits beside `wall` and `runs` in `frontend/app/router.ts`.
The application route redirects to it whenever `/api/health` says `setup` or
`broken`.

## Many repos in one hub

### Config shape

The default config moves to `~/.config/github-orchestrator/config.toml`.

```toml
gh_account = "octocat"
claude_model = "opus"
hub_port = 8720
check_for_updates = true

[[repos]]
repo = "acme/widgets"
local_path = "~/repositories/widgets"
new_worktree_command = "cp $GITHUB_ORCHESTRATOR_SOURCE_REPO/.env ."

[[repos]]
repo = "acme/gadgets"
local_path = "~/repositories/gadgets"
```

- `gh_account` stays top level. One account per instance; a second account is
  what instances are for.
- `[[repos]]` replaces `watch_repo` and `local_path`. Each entry has `repo`,
  `local_path`, and optionally `new_worktree_command`, which is repo-specific in
  practice (copying that repo's `.env`). A top-level `new_worktree_command`
  stays as the default for entries without one.
- `pr_windows` is gone. A config that still sets it fails to load until it is
  migrated (see Migration), so nobody is left believing tmux is still on.
- Top-level keys come before the first `[[repos]]`, since TOML puts every key
  after a table header into that table.
- `check_for_updates` is new, a boolean defaulting to true.
- `idle_threshold`, which nothing reads (`config.toml.example`), goes in the
  same migration.

`tomllib` reads arrays of tables, but today's writer only updates top-level
string keys in place (`settings/_config.py:192`). Writing `[[repos]]` needs a
writer: either the `tomli-w` dependency or a small renderer for this one shape.
Keeping the comments that `config.toml.example` seeds is not a goal once the
page writes the file; the example ships as a reference in the docs.

### What changes in the code

- **Settings.** `Settings.watch_repo` and `Settings.local_path`
  (`settings/_settings.py:110-116`) become `Settings.repos`, a mapping from
  `Repo` to its entry. `REPO_ROOT` goes from runtime code
  (`settings/_config.py:42`, `settings/_settings.py:22-24`).
- **Watcher.** `_discover_prs` (`watcher/_cycle.py:180-200`) runs the same three
  searches, each with one `repo:` qualifier per watched repo, so the request
  count stays flat as repos are added. GitHub's search allows about 30 requests
  a minute; three searches per repo would hit that at ten repos. It seems like
  several `repo:` qualifiers are ORed, which needs checking against the API
  before step 5 relies on it. A search error names the repo it failed for when
  GitHub says.
- **Placement, teardown and the dry run** (`watcher/_placing.py:28`,
  `watcher/_teardown.py:31`, `watcher/_would.py:15`) look up `local_path` by
  `pr.repo` instead of holding one.
- **Working copies** are wired with a mapping instead of one `repo_dir`
  (`wiring.py:440`). Most of their methods already take the clone as an
  argument (`watcher/_placing.py:62-67`).
- **PR managers** already carry the repo: `manager_argv` passes `--repo`
  (`pr_windows/_layout.py:21-23`), and `manager_config` finds the clone through
  the same mapping.
- **The CLI's thread commands** default `--repo` to `watch_repo`
  (`cli/_threads.py:187-188`). With N repos there is no default. Agents always
  pass `--repo` already (`cli/_report_commands.py:27`), so `--repo` becomes
  required.
- **The hub.** `ServedHub` and `Wall` drop `watching: Repo`
  (`board_api/_hub.py:299`, `board_api/_wall.py:79-98`); the wall payload lists
  the watched repos instead.
- **Notifications** need no change for the filter: they come from thread news
  on the server, across every PR the watcher holds, and the filter lives only in
  the browser.

### Data dir

Most per-PR state is already filed under `owner/name`: state
(`change_detection/_disk.py:30`), queues (`pr_event_queue/_disk.py:44`), flags
and board ports (`settings/_paths.py:6-7`, `settings/_switches.py:56, 154`). The
layout does not change. What changes is that "other repos" stops meaning
"stale": the archive sweeps that keep only `watch_repo`
(`settings/_switches.py:79-97`, `change_detection/_disk.py:163`,
`pr_event_queue/_disk.py:395`) take the set of watched repos.

The boards' port range is 100 wide (`settings/_switches.py:11`). One board runs
per PR the watcher holds, so more repos means more boards. It seems unlikely to
bind soon, but `doctor` reports how many of the 100 are in use.

### PR URLs

The PR page is `/pr/:number` (`frontend/app/router.ts:11`, `board_api/_pages.py:6`)
and the hub proxies by number alone, taking the first held PR with that number
(`board_api/_hub.py:209-213, 259-267`). Two repos can both have a #42. The page
becomes `/pr/:owner/:name/:number` and the proxy
`/pr/{owner}/{name}/{number}/api/...`. An old `/pr/:number` link redirects when
exactly one held PR has that number and shows a chooser otherwise, so existing
notifications keep working.

### The repo filter

The top bar's repo name (`hub-bar.gts:45-46`) becomes a filter menu: All repos,
then each watched repo with a checkbox. One click on a name selects only it;
the checkboxes build a selection.

The filter covers everything on the page that lists or counts PRs: the wall's
sections, the top bar's "N need you", and the PR switcher. Desktop
notifications are the one exception: they are sent by the server for every
watched repo whatever the browser has selected, so a PR in a repo filtered out
of view can still call for attention.

In the store's terms the selection is view state, not a summary. Store records
are already keyed by repo and number (`frontend/app/services/store.ts:27`). The
store spec allows a count to be computed in one place only and stored
(`2026-10-08-front-end-store-design.md`, "The rule"), so the store takes the
selection as an input: it filters the wall's sections after computing them, and
computes "N need you" and the switcher's list over the selected repos. No
component filters or counts on its own. The selection lives in the URL
(`?repos=acme/widgets,acme/gadgets`) so it survives a reload and can be
bookmarked, and the last one is remembered in the browser for the next visit
without a query.

With one repo watched, the filter menu still shows, holding one name, so the
place to add a second repo is visible.

## Instances

Today an instance is any `~/.config/github-orchestrator/<name>.toml`
(`settings/_load.py:13-28`), with its data dir beside the default one as
`github-orchestrator-<name>` and its LaunchAgent labelled
`com.github-orchestrator.watcher.<name>` (`cli/_config.py:12-18`).

Moving the default config into the same folder would make
`config.toml` look like an instance named `config`. The proposal reserves that
name: `other_instances` skips `config.toml`, and `--instance config` is
refused. The alternative, moving instances to an `instances/` subfolder, is a
bigger migration for the same result.

Every command takes `--instance NAME` (or `GITHUB_ORCHESTRATOR_INSTANCE`), and
defaults to the default instance. `GITHUB_ORCHESTRATOR_CONFIG` and
`GITHUB_ORCHESTRATOR_DATA_DIR` keep working as overrides for tests and odd
setups.

A new instance is made with `github-orchestrator start --instance NAME --port PORT`: it writes an empty config with that port, starts its service,
and opens its setup screen.

Instances stay as they are through migration and multi-repo. Two instances that
share an account and differ only by repo keep running as two; nothing offers to
fold them into one.

## Removing tmux mode

Deleted, by module:

- **settings.** `PrWindowsMode` and the `pr_windows` field
  (`settings/_config.py:54-56, 80`); `window_ids_dir` and `glow_theme_marker`
  (`settings/_settings.py:58-60, 82-84`); the `pr_windows` block in
  `config.toml.example`.
- **pr_windows.** `_tmux.py`, `_windows.py` (`TmuxPrWindows`),
  `_window_ids.py`, the pane layout in `_layout.py`, and the tmux half of
  `fake.py`. `BackgroundPrWindows` (`pr_windows/_background.py`) becomes the
  only implementation; it currently imports its `Run` type from `_tmux.py`
  (`pr_windows/_background.py:12`), which moves. `sync_theme` and `ManagerPane`
  leave the interface if nothing else reads them. The package is renamed,
  since there are no windows left; `pr_processes` is a placeholder name.
- **pr_manager.** `_terminal_front.py`, `_screens.py`, `TtyTerminal` in
  `_terminal.py` (keeping `sigterm_ends_the_session`, which `_browser_front.py:8`
  uses), the drawing in `_dashboard.py` (keeping `claude_status` and
  `exit_word`, used by `_manager.py:15` and `_carry_out.py:23`), and
  `_preview.py`, whose `MarkdownPreview` only `_terminal_front.py` uses
  (`pr_manager/_terminal_front.py:23, 66`). The git palette's commands stay;
  they run in the Terminal tab.
- **wiring.** `TmuxPrWindowsWiring` and its provider (`wiring.py:481-493`),
  `EveryModeManagers` (`wiring.py:512-540`), the mode `match`
  (`wiring.py:1204-1214`), `NoBoardPages` and `TerminalFrontProvider`.
- **cli.** `tmux_mode` in `CliConfig` (`cli/_config.py:42`), the `tmux_only`
  requirements (`cli/_install_checks.py:30-33`), tmux text in `watcher/__main__.py:16-27`
  and `board_api/_app.py:702, 885`.
- **Requirements.** tmux, zsh, glow and entr go. pandoc goes too: its only
  caller is `_preview.py` (`pr_manager/_preview.py:171`), and a search of `src`
  finds no other, so its requirement line (`cli/_install_checks.py:27`) is
  deleted with it. node and npm stop being user requirements because the bundle
  ships built.
- **Tests and docs.** The tmux tests under `tests/pr_windows` and
  `tests/pr_manager`, the recorded tmux and pandoc subprocess entries, and the
  tmux sections of `README.md` and `docs/how-to-use.md`.

The front-end store plan already drops the terminal dashboard's move line
(plan step 3); this removes the rest of that dashboard, so whichever lands
second deletes less.

## Removing cron mode

Linux moves to a systemd user unit (see "The services"), so cron goes:
`cron/github-orchestrator.cron.template`, `_cron_environment` and the cron
branch of `install_scheduler` (`cli/_scheduler.py:20, 50`), the `install_cron`
and `uninstall_cron` make targets, and `cron` as a choice of `logs`
(`cli/_parser.py:34-41`). Migration removes an old crontab line (see
Migration).

## The CLI

`github-orchestrator` with no arguments prints the short help, not a usage
error. Each command's help says what it does in one line and shows an example;
since 8d36455a each command's page already carries its description. `help COMMAND` is the same as `COMMAND --help`. Every command takes `--instance NAME`.

| Command       | Does                                                                                                                                                                                                                                                                                               |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `open`        | Open the instance's board in the browser (`Desktop.open_url`: `open` on macOS, `desktop/_macos.py:35`; `xdg-open` on Linux). Starts the service first if it is not running. Always prints the URL.                                                                                                 |
| `start`       | Migrate an old config if one is found, write the LaunchAgent or systemd unit, load and start it, wait up to 30s for `/api/health`, print the URL and the state. Already running: says so and exits 0. `--foreground` runs the watcher in the terminal instead, for a Linux without a user manager. |
| `stop`        | Stop this instance's service (`launchctl bootout`, or `systemctl --user stop`), stop its PR managers, ask to close its terminal sessions (`-f` closes them unasked). `--all` for every instance. Today `stop` always covers every instance (`cli/_parser.py:56-63`).                               |
| `restart`     | Stop then start this instance, then confirm the managers came back (`cli/_restart.py`).                                                                                                                                                                                                            |
| `restart-all` | `restart` for every instance, under the restart lock. No sync or rebuild stages (`cli/_restart_all.py:37-41`); those move to a developer make target.                                                                                                                                              |
| `status`      | Version, state, hub URL from `/api/health`, watcher health, tracked PRs per repo, queues, and an "Update available" line when the hub has seen a newer release. Exit 0 when watching and healthy, 1 otherwise.                                                                                     |
| `logs`        | `logs [watcher\|agent\|service\|all] [-n N]`, plus `-f` to follow. `service` is launchd's log file on macOS and `journalctl --user -u <unit>` on Linux; it replaces today's `launchd` and `cron` choices (`cli/_parser.py:34-41`).                                                                 |
| `runs`        | Today's summary of the day's Claude runs: count, total time, longest (`cli/_parser.py:43`).                                                                                                                                                                                                        |
| `config`      | Today's listing of every setting's effective value and where it came from (`cli/_parser.py:22`), for the new config shape.                                                                                                                                                                         |
| `update`      | Look up the newest release, install it with `uv tool install --force`, re-render every instance's service, `restart-all`. `--check` only reports. `--version X` installs that one, including older.                                                                                                |
| `tutorial`    | Open the board's tour. `--terminal` reprints the machine-setup walkthrough.                                                                                                                                                                                                                        |
| `doctor`      | Run every check below and print one line each, with the fix for each failure. Exit 1 on any failure. Read-only.                                                                                                                                                                                    |
| `uninstall`   | Stop every instance, remove their services, offer to remove config, data and the notifier apps, then `uv tool uninstall github-orchestrator`. Never touches clones, and leaves uv, gh and claude installed.                                                                                        |
| `help`        | The command list, grouped: everyday (`open`, `status`, `logs`, `runs`), service (`start`, `stop`, `restart`, `restart-all`), maintenance (`update`, `doctor`, `config`, `uninstall`), learning (`tutorial`).                                                                                       |

**Debugging commands.** `queue PR` and `undismiss PR` (`cli/_parser.py:31-32, 45-47`) keep working as today. They are left out of the short help and of
`help`, and appear in `github-orchestrator --help` under a last section titled
"debugging", after the four groups above, each with its one line.

**Deleted.** `switch-repo` (`cli/_parser.py:65-73`, `cli/_switch_repo.py`).
Adding and removing repos is the setup screen's job, and the archiving it did
moves to the setup write (see "The setup API").

`thread ...` stays, for agents, and is already left out of the command list
(`cli/_parser.py:75`, since 8d36455a); it does not appear under "debugging"
either. Its command lines become
`<the tool's python> -m github_orchestrator.cli thread ...` instead of
`uv run --directory <checkout> ...` (`cli/_report_commands.py:26`,
`cli/_command_lines.py:4`), so agents need neither uv nor a checkout. `setup`
is replaced by the setup screen; `setup` as a command prints "Setup is on the
board now" and runs `open`.

Example `status`:

```text
github-orchestrator 0.5.0 (default instance)
Update available: 0.6.0. Run github-orchestrator update.
Hub: http://127.0.0.1:8720, watching 2 repos
Watcher: alive, last polled 34s ago

acme/widgets  6 PRs  queues empty
acme/gadgets  2 PRs  1 event pending on #88
```

## doctor

Each check prints `ok`, `warn` or `FAIL`, a short reason, and for anything not
ok the command or click that fixes it.

01. **Install.** Version, the uv tool directory, the install's receipt (where it
    was installed from), and whether a newer release exists (warn).
02. **Command.** `github-orchestrator` on `PATH` resolves to the uv tool shim,
    not a leftover link into a checkout.
03. **Requirements.** `git`, `gh` and the configured `claude_command` resolve,
    both on the current `PATH` and on the `PATH` written into the service, since
    that is the one the watcher and the agents get. gh's version is printed.
    Each fix names the source from the installer's table, never `brew`.
04. **GitHub.** `gh auth token --user <account>` works; the token's scopes cover
    private repos when any watched repo is private.
05. **Each repo.** The account can see it (`Access.check_access`); the clone
    exists, is a git repo, and its remote is that repo.
06. **Config.** Parses, has no legacy keys, `hub_port` is free or held by this
    instance.
07. **Service.** On macOS: the plist exists and is loaded (`launchctl print`),
    its program file exists, and launchd's last exit reason is not a code-signing
    kill. On Linux: the unit file exists, `systemctl --user is-enabled` and
    `is-active` agree it is running, its `ExecStart` program exists, and
    `NRestarts` is not climbing. A missing program file, a code-signing kill or
    a restart loop says to run `github-orchestrator restart`. On Linux it also
    reports, as a warn, when lingering is off (`loginctl show-user`), since the
    watcher then stops at logout.
08. **Hub.** `/api/health` answers, from the process the service manager says it
    started, in the expected state.
09. **Watcher.** The last good poll is recent; the last error if not.
10. **Claude extras** (warn only). The `rebase-on-main` skill is in
    `~/.claude/skills`; the Atlassian MCP server is connected (today's check,
    `cli/_install_checks.py:103-120`).
11. **Notifications** (warn only). On macOS, the notifier apps are present in
    `~/Applications` (`wiring.py:1230`) and built from this version's sources,
    and how to build them when not, including `xcode-select --install` when
    `swiftc` or `codesign` is missing. On Linux, `notify-send` is on the
    service's `PATH`, and which package provides it when not.
12. **Boards.** How many of the 100 board ports are in use.
13. **Instances.** The checks above for each instance, under its name.

`doctor` stays read-only so it is safe to run anywhere and paste into an issue.
Fixes go through the named commands.

## The services

The install moves out of the Makefile into the CLI. One `Service` seam in the
CLI has two implementations, launchd and systemd, chosen by `sys.platform`; it
writes the definition, loads it, starts, stops, reports whether it is loaded
and running, and reports the last exit. `start`, `stop`, `restart`, `update`,
`doctor` and `uninstall` use only the seam.

Both share these rules:

- The program is the tool venv's `python`, taken from `sys.executable` when
  `start` runs. Run from a checkout's `.venv` (as `make restart-all` does), it
  is the uv tool's `python` instead when the tool's receipt names that checkout
  as editable; a tool installed from anywhere else is left alone, and both cases
  print which `python` the service got (`cli/_tool_install.py`). uv is never on the path to the watcher, so upgrading uv cannot
  kill it. The venv's `python` is a link to a uv-managed Python, which
  `uv python upgrade` or `uv python uninstall` can remove; `doctor` check 7
  catches that and `restart` re-renders the definition.
- PATH comes from the shell `start` runs in, as today, without uv's directory
  forced to the front (`cli/_scheduler.py:27-32`). The installer puts
  `~/.local/bin` on its own `PATH` before calling `start`, so gh and claude are
  on the recorded one. `start`, `restart` and `update` re-render it, so fixing
  `PATH` and restarting is the cure.
- The templates become strings in the package, since there is no checkout to
  read `launchd/` from (`cli/_scheduler.py:67`).
- The watcher restarts on any exit, including the clean exit that leaves setup
  mode, about a second later.

### The LaunchAgent (macOS)

```xml
<key>ProgramArguments</key>
<array>
  <string>/Users/me/.local/share/uv/tools/github-orchestrator/bin/python</string>
  <string>-m</string>
  <string>github_orchestrator.watcher</string>
  <string>--loop</string>
</array>
<key>EnvironmentVariables</key>
<dict>
  <key>PATH</key><string>(the PATH start was run with)</string>
  <key>GITHUB_ORCHESTRATOR_INSTANCE</key><string>work</string>
</dict>
<key>KeepAlive</key><true/>
<key>ThrottleInterval</key><integer>1</integer>
```

- Files: `~/Library/LaunchAgents/com.github-orchestrator.watcher.plist` and
  `com.github-orchestrator.watcher.<name>.plist`. Labels stay as today, so old
  plists are replaced, not duplicated.
- `start` and `restart` always boot out and bootstrap
  (`launchctl bootout`/`bootstrap gui/<uid>`), never only kickstart, so a
  code-signing-killed job comes back.

### The systemd user unit (Linux)

```ini
[Unit]
Description=github-orchestrator watcher (work)

[Service]
ExecStart=/home/me/.local/share/uv/tools/github-orchestrator/bin/python -m github_orchestrator.watcher --loop
Environment=PATH=(the PATH start was run with)
Environment=GITHUB_ORCHESTRATOR_INSTANCE=work
Restart=always
RestartSec=1

[Install]
WantedBy=default.target
```

- Files: `~/.config/systemd/user/github-orchestrator.service` for the default
  instance and `github-orchestrator-<name>.service` for each other one.
- `start` writes the unit, runs `systemctl --user daemon-reload`, then
  `systemctl --user enable --now <unit>` (or `restart` when it was already
  running, so a re-rendered unit takes effect). `stop` runs
  `systemctl --user stop`; `uninstall` runs `disable --now`, removes the file
  and reloads.
- An explicit `stop` is not undone by `Restart=always`; only exits the unit did
  not ask for are restarted. systemd's default start limit (5 starts in 10s)
  stops a crash loop; `doctor` reports it and `restart` clears it with
  `systemctl --user reset-failed`.
- **Lingering.** A user unit runs while its user has a session. On a desktop
  that is the whole working day, and the watcher stops at logout like any other
  user program. To keep it running without a session (a server reached over
  ssh), the user runs `loginctl enable-linger`, which some distributions let a
  user do for themselves and others only with sudo. The installer asks "Keep
  the watcher running after you log out?" and, on yes, runs
  `loginctl enable-linger`. When that needs sudo and fails, it prints the
  command to run and carries on. `-y` answers no, `--linger` answers yes, and
  `doctor` warns while lingering is off.
- `systemctl --user` needs a user manager and `XDG_RUNTIME_DIR`. Without them
  (some containers, some ssh sessions), `start` says so and offers
  `github-orchestrator start --foreground`, which runs the watcher in the
  terminal.
- Logs go to the journal (stdout and stderr), read with `logs service`; the
  watcher's and agents' own log files stay where they are.

### Linux desktop

`MacDesktop` (`desktop/_macos.py:20-47`) gets a sibling, chosen by
`sys.platform` in wiring:

- `open_url` runs `xdg-open`.
- `announce` runs `notify-send --app-name github-orchestrator <title> <body>`
  when it is on `PATH`, and does nothing otherwise. No click action: clicking a
  notification does not open the PR, which the board's own list covers. The
  macOS badges have no Linux counterpart.
- `copy_to_clipboard` uses `wl-copy` under Wayland, `xclip` otherwise, and
  reports which is missing.
- `appearance` reads `gsettings get org.gnome.desktop.interface color-scheme`
  and falls back to light, as the macOS one does on any failure.

### The Makefile

The make targets `install_launchagent`, `install_instance_launchagent`,
`install_cron`, `install_command`, `uninstall*` and `restart-all` go. For
development, `make dev-install` runs `uv tool install --editable .` and
`make build_frontend`, so the service runs the checkout's code through the same
layout as a user's install.

## The wheel and releases

### What the wheel carries

`[tool.hatch.build.targets.wheel]` gains:

```toml
artifacts = ["src/github_orchestrator/board_api/static/app/**"]
```

so the gitignored bundle (`.gitignore`, `src/github_orchestrator/board_api/static/app/`)
is included once CI has built it. `APP_ROOT` already resolves inside the
package (`board_api/_app_files.py:4`).

Four things outside `src/` are read at runtime and move into the package as
package data, read with `importlib.resources`: `skills/rebase-on-main`, the
`notifier/` Swift sources and badges, the LaunchAgent template and the new
systemd unit template. The cron template is deleted.

The wheel is pure Python (`py3-none-any`) and serves both platforms.

### Versioning

SemVer, starting at `0.1.0` on the fresh history. The version lives in
`pyproject.toml`; a release is a tag `vX.Y.Z` that must equal it, and the
workflow fails when they differ. `github-orchestrator --version` and
`/api/health` report it.

### The release workflow

`.github/workflows/release.yml`, on a pushed `v*` tag:

1. **Test.** Today's `ci.yml` jobs.
2. **Build.** On `ubuntu-latest`: node, `npm ci`, the production front-end build
   into `static/app`, then `uv build --wheel`. Fail when the wheel lacks
   `static/app/index.html`, the skill, the notifier sources or either service
   template.
3. **Smoke, macOS.** On `macos-latest`, with a scratch `HOME` and `GH_TOKEN`
   set so the gh login step passes: run `install.sh -y --no-open --wheel dist/*.whl`, then check `/api/health` says `setup`, `GET /setup` serves the
   page, `doctor` runs, and `uninstall` with yes leaves nothing behind.
4. **Smoke, Linux.** On `ubuntu-latest`, the same run and checks. The runner's
   own `HOME` is used, not a scratch one, because the user manager reads units
   from the real `~/.config/systemd/user`; the runner is thrown away after. The
   job first runs `sudo loginctl enable-linger runner` and exports
   `XDG_RUNTIME_DIR=/run/user/$(id -u)` so `systemctl --user` has a manager to
   talk to. The `uninstall` check also confirms the unit file is gone and
   `systemctl --user list-units` no longer shows it.
5. **Publish.** `gh release create` with the wheel and `install.sh` as assets
   and generated notes.

The two smoke jobs are the only place the script and the wheel meet before a
user does.

`update`, `install.sh` and the hub's daily check find the newest release through
`https://api.github.com/repos/vector67/github-orchestrator/releases/latest`,
anonymously, and install the wheel asset's URL. Wheel filenames carry the
version, so `releases/latest/download/` cannot name the wheel directly; it
works for `install.sh`, whose name does not change.

## Migration

`start` runs it, so the installer, `update` and a hand-run `start` all migrate.
It is idempotent and keeps a `.bak` of every file it rewrites.

1. **Find the old config.** Read the existing LaunchAgent's `ProgramArguments`
   or the crontab's `github_orchestrator` line; if it runs
   `uv run --project <dir>`, the old default config is `<dir>/config.toml`, the
   checkout `make install` ran from.
2. **Move it** to `~/.config/github-orchestrator/config.toml` unless one is
   already there.
3. **Rewrite every config** (default and each instance): `watch_repo` and
   `local_path` become one `[[repos]]` entry carrying the top-level
   `new_worktree_command`; `pr_windows` and `idle_threshold` are dropped. Each
   instance stays an instance with its one repo; none are merged.
4. **Tidy the data dir.** Remove `tmux_window_ids/` and `glow_theme`. Leave
   everything else; it is already filed by repo.
5. **Stop tmux managers.** If a `prs` tmux session holds manager windows, stop
   those managers so the watcher restarts them in the background.
6. **Replace the services**, one per instance: on macOS the LaunchAgents in the
   new layout; on Linux remove the crontab line and write the systemd units.

The data dir default does not move. `resolve_data_dir`'s order
(`settings/_config.py:15-25`) stays, including the legacy
`~/.config/local/share` path some installs use.

## Order

Each step merges on its own, keeps `make test` green, and ends in something a
person can check.

01. **Run without a checkout.** Remove `REPO_ROOT` from runtime code: the default
    config moves to `~/.config/github-orchestrator/config.toml` (with the
    reserved instance name), the skill, notifier sources and plist template
    become package data, and agent command lines use `sys.executable -m github_orchestrator.cli`. Add `artifacts` to the wheel config. Check: a wheel
    built by hand, installed with `uv tool install`, runs `status` from `/tmp`.
02. **The LaunchAgent runs the tool's Python.** The `Service` seam with its
    launchd implementation, the new template, `ThrottleInterval`, PATH without
    uv forced first, boot-out-and-bootstrap in `restart`. Ported into the CLI as
    `start`, `stop` (this instance; `--all`), `restart`, `restart-all` without
    build stages. Check: `brew upgrade uv` no longer kills the watcher.
03. **Linux as a systemd user unit.** The systemd implementation of the seam,
    its template as package data, the Linux desktop, `logs service`, and the
    removal of cron mode. Check: on a Linux machine with a user manager, `start`
    brings the hub up, `stop` takes it down, and killing the watcher brings it
    back a second later.
04. **Remove tmux mode.** Everything in "Removing tmux mode", plus migration
    steps 3 to 5 for `pr_windows`. Check: the suite passes with no tmux or
    pandoc on `PATH`, and a config with `pr_windows` gets a clear error until
    migrated.
05. **Many repos.** The `[[repos]]` config and its writer, `Settings.repos`, the
    watcher's combined searches, placement, teardown and working copies by repo,
    the archive sweeps taking a set, `--repo` required on thread commands, and
    the migration of `watch_repo`. The board shows the union; no filter yet.
    Check: one hub with two repos shows PRs from both.
06. **PR URLs by repo.** `/pr/:owner/:name/:number` in the router, the pages and
    the proxy, with the old-link redirect. Check: two PRs with the same number in
    two repos open their own pages.
07. **The repo filter.** The top-bar menu and the URL selection, with the store
    filtering the wall's sections and computing "N need you" and the PR switcher
    over the selection. Lands after the store plan's step 3, which makes the
    store order the wall. Check: selecting one repo hides the other's rows,
    lowers the count to that repo's, and drops its PRs from the switcher, while
    a notification still arrives for a PR in the hidden repo.
08. **The hub in setup mode.** The three states, `/api/health`'s new fields, the
    wall's error in place of "starting", `status` reading the state and version
    from the health answer it already probes. The watcher no longer exits 2 on an
    incomplete config. Check: deleting the config and restarting leaves the hub
    up, saying `setup`.
09. **The setup screen.** The setup API and the `/setup` route through the store,
    the push-only repo list with its read-only toggle and a repo typed by name, clones with progress, the
    restart into watching, adding and removing repos later. `setup` the command
    points at the board; `switch-repo` is deleted. Check: from an empty config,
    the page alone gets to a wall, and removing a repo there archives it the way
    `switch-repo` did.
10. **The CLI's help.** The grouped `help`, the "debugging" section of
    `--help` with `queue` and `undismiss`. Check: `help` leaves them out and
    `--help` ends with them.
11. **doctor.** Every check above, on both platforms. Check: each failure,
    provoked by hand, prints its fix.
12. **Releases.** `release.yml` with both smoke jobs, `install.sh` with its
    sources table, gh login and notifier question, `update`, `uninstall`, the
    hub's daily release check and its badge, and migration steps 1, 2 and 6.
    Check: a tag produces a release whose script installs on clean macOS and
    Ubuntu runners, and a hub whose recorded newest release is newer shows the
    badge.
13. **The tour.** `tutorial`, the board's first-run tour and its "seen" flag.
    Check: a fresh install shows it once; `tutorial` shows it again.
14. **Docs.** README's install becomes the one line; `docs/how-to-use.md`
    loses tmux, cron and `make install`; CLAUDE.md's dev loop points at
    `make dev-install`.

Steps 1, 2 and 4 can go in any order. Step 3 needs step 2 (the seam). Step 5
needs step 1 (the config moves first). Step 9 needs 5 and 8. Step 12 needs 1,
2, 3 and 9 to be worth releasing.
