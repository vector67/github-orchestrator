# GitHub Orchestrator

Watches your PRs on GitHub, notices what changed (CI status, comments,
mergeability, review requests), and puts an agent on it in the background
(Claude Code or the Codex CLI, chosen per instance), with everything in the
browser.

## What it does

- Polls GitHub for the PRs you own and the PRs you have been asked to review.
- Diffs every poll against the last and queues an event for what changed: CI
  status, review threads, mergeability, review requests, pushes since your
  review.
- Lists every PR on a wall in the browser by who has to move next, and opens
  each on a page with its review board, its dashboard, a terminal in its
  worktree and its diff.
- Drafts review comments by selecting lines in the PR's diff, the way GitHub's
  Files changed does, and edits a draft in place while it sits in your review.
- Spawns an agent run per event, in a worktree cut for that PR — a full
  analysis on a review request, a re-review of what changed when you are asked
  again after reviewing, a fix per failing check, `/rebase-on-main` when the
  branch stops merging.
- Serves a review board: one row per review thread on your PR, each with a fix
  an agent wrote for it in its own worktree, approved or rejected one at a time.
- Lands an approved fix as a single commit on the PR branch and replies on the
  thread in your words.
- Notifies on the desktop for the events that need telling rather than doing:
  macOS notifications whose click opens the PR, or `notify-send` on Linux.
- Records every run, so `status`, `logs` and `runs` say what happened.

Full documentation is in [docs/how-to-use.md](docs/how-to-use.md).

## Install

```bash
curl -LsSf https://github.com/vector67/github-orchestrator/releases/latest/download/install.sh | sh
```

It runs on macOS and Linux. The installer checks the machine and offers to
install what is missing:

- `git`, for worktrees and commits (Apple's Command Line Tools on macOS, your
  distribution's package on Linux)
- `uv`, which installs github-orchestrator and the Python it runs on
- `gh`, which talks to GitHub; the installer logs it in when it has no login yet
- the agent that runs the reviews and fixes: `claude` (Claude Code), the
  default, which it installs, or `codex` (the Codex CLI), which it finds on
  `PATH` or in the ChatGPT app and otherwise says where to get

It asks which agent to use; `--agent codex` (or `GITHUB_ORCHESTRATOR_AGENT=codex`)
chooses Codex without asking, `-y` keeps Claude, and the choice goes into the
config as `agent = "codex"`. It also offers to copy the `rebase-on-main` skill
into that agent's skills folder (`~/.claude/skills` or `~/.agents/skills`),
which the agents run when a branch stops merging; `github-orchestrator skill`
installs it later.

Desktop notifications are optional. On macOS the installer asks whether to
build the notification apps, which needs the Command Line Tools. On Linux they
go through `notify-send` when it is on `PATH`.

The installer then installs the newest release with `uv tool install`, starts
the watcher as a service (a LaunchAgent on macOS, a systemd user unit on Linux)
and opens the board. `install.sh --help` lists its options, such as `-y` to
answer yes to everything and `--version X` for an older release. An install
from an older checkout is found and replaced, with its config and data moved
over.

The board opens on its setup screen: your GitHub account, the repos to watch,
where their clones are, and a few options. **Start watching** writes the config,
clones what is missing and restarts the watcher into watching. The first time
the wall has pull requests it shows a short tour, which
`github-orchestrator tutorial` shows again.

`github-orchestrator doctor` checks the install, the requirements on your
`PATH` and on the service's, the service itself, GitHub, each repo's clone, the
hub and the watcher, and prints the fix for anything that is not ok. It changes
nothing.

## Configuration

The board's setup screen (`/setup` on the hub; `github-orchestrator setup` opens
it, and so does the top bar's repo menu) asks for your account and the repos to
watch, checks `gh` can see each as that account, and writes them into
`~/.config/github-orchestrator/config.toml`. Repos are added and removed there
too: a removed repo's state, queues and holds are archived, its managers stopped,
and its worktrees left where they are. Writing the file by hand from
[the example](src/github_orchestrator/settings/config.toml.example) does the same
job and keeps its comments. These have no default:

- `gh_account`, your GitHub username, at the top of the file
- one `[[repos]]` table per repo to watch, after every top-level key, each with
  `repo` as `owner/name` and `local_path`, your clone of it, which that repo's
  per-PR worktrees are cut from

```toml
gh_account = "octocat"

[[repos]]
repo = "acme/widgets"
local_path = "~/repositories/widgets"

[[repos]]
repo = "acme/gadgets"
local_path = "~/repositories/gadgets"
```

A config an older release wrote is rewritten in the current shape the next time
the watcher is started or restarted; the old file stays beside it as `.bak`.
[Upgrading an older config](docs/how-to-use.md#upgrading-an-older-config) says
what that changes.

Every other key is commented at its default in that example, and
`github-orchestrator config` prints each setting's effective value and where it
came from. [Configuration](docs/how-to-use.md#configuration) covers the settings
that matter: the two that bound how hard this hits your machine, the board's
fonts, and the environment variables that move the config and data files.

## Day to day

`github-orchestrator help` lists the commands in four groups:

```text
everyday     open, status, logs, runs
service      start, stop, restart, restart-all
maintenance  update, doctor, config, uninstall, setup
learning     tutorial
```

```bash
github-orchestrator open                # the board in your browser
github-orchestrator status              # version, the hub, the watcher's health, PRs and queues per repo
github-orchestrator logs agent -n 50    # watcher | agent | service | all; -f follows
github-orchestrator runs                # today: count, total time, longest run
github-orchestrator restart             # rewrite and reload this instance's service, restart its managers
github-orchestrator stop                # stop this instance (--all: every instance); -f closes its terminal sessions unasked
```

`help COMMAND` is the same as `COMMAND --help`, which says what it does and
shows an example. Every command takes `--instance NAME`. `github-orchestrator --help` ends with a
**debugging** section, `queue PR` and `undismiss PR`, which the short list
leaves out.

`runs` totals cost as `~$8.14 API-equivalent` rather than as money, because
every run bills against your subscription and none of it is a charge.

Runtime state lives under the resolved data dir; see
[Runtime data](docs/how-to-use.md#runtime-data) for what is in it.

`http://127.0.0.1:8720` is the hub, and where you start. Its home is the wall,
every PR grouped by who has to move next. Opening one gives that PR's page with
**Board | Dashboard | Terminal | Diff** tabs, and **Runs** lists the week's Claude runs
under the watcher's health. [The hub](docs/how-to-use.md#the-hub) has the keys
and the rest.

## Updating

When a newer release is out, the board's top bar shows **Update available** and
`status` says so. Nothing installs on its own:

```bash
github-orchestrator update           # install the newest release, then restart every instance on it
github-orchestrator update --check   # only say whether there is one
```

## Uninstall

```bash
github-orchestrator uninstall
```

It stops every instance, removes their services and the command, and asks
before removing the config, the data and the notification apps too. It never
touches your clones, and leaves uv, gh and claude installed.
[Removing it](docs/how-to-use.md#removing-it) has the details.

## Developing

This repository is the source of truth; a release is a tag of it. To run your
checkout as the installed tool:

```bash
make dev-install   # uv tool install --force --editable ., then build the front end
github-orchestrator start
```

The service then runs the checkout's code through the same layout as a user's
install. `make restart-all` syncs, rebuilds the front end and the notification
apps, and restarts every instance on what you merged. The service's program is
the uv tool's Python when `make dev-install` installed this checkout, and the
checkout's `.venv` Python otherwise; the restart says which when a uv tool is
installed. `make install_hooks` turns on the pre-commit hook.

## Tests

`make test` runs them all and `make lint` runs every linter. CLAUDE.md has the
rest: the stages behind each one, the fixer, and how the suite replays
subprocesses.
