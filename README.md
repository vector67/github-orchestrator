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
  each on a page with its pr-summary, its review board, its dashboard, a
  terminal in its worktree and its diff.
- Drafts review comments by selecting lines in the PR's diff, the way GitHub's
  Files changed does, and edits a draft in place while it sits in your review.
- Spawns an agent run per event, in a worktree cut for that PR — a full
  analysis on a review request, a re-review of what changed when you are asked
  again after reviewing, a fix per failing check, `/rebase-on-main` when the
  branch stops merging.
- Serves a review board, from one server process for every PR: one row per
  review thread on your PR, each with a fix
  an agent wrote for it in its own worktree, accepted or rejected one at a time.
- Lands an accepted fix as a single commit on the PR branch and replies on the
  thread in your words.
- Notifies on the desktop for the events that need telling rather than doing:
  macOS notifications whose click opens the PR, or `notify-send` on Linux.
- Records every run, so `status`, `logs` and `runs` say what happened.

Before you install, know what it does on your machine and your branches:

- It cuts a git worktree for each pull request it watches, yours and the ones
  you review, as a folder beside that repo's clone named after the branch, and
  the git palette leaves a `<worktree>.git-palette.lock` file beside it.
- Agents run in their tool's own auto mode (`--permission-mode auto` for Claude
  Code, `--approve-for-me` for Codex), with no one asked about each command.
- A CI-fix run commits its fix and pushes it to your PR branch without asking,
  with `git push --force-with-lease` when history was rewritten. A rebase run
  rebases in the worktree and stops short of the force-push the
  `rebase-on-main` skill wants you to approve. Review-thread fixes are the ones
  that wait: nothing reaches the branch until you press Accept.

For a first look with nothing at stake, `make preview` in a checkout serves the
board at `http://127.0.0.1:8791/pr/acme/widgets/7/` from made-up pull requests:
a fake GitHub, agents disabled, and its state in a temporary folder. It builds
the front end first, so it needs uv, Node and npm.

Full documentation is in [docs/how-to-use.md](docs/how-to-use.md).

## Install

```bash
curl -LsSf https://github.com/vector67/github-orchestrator/releases/latest/download/install.sh | sh
```

The installer's options go after `sh -s --`, which hands them to the script
rather than to `sh`:

```bash
curl -LsSf https://github.com/vector67/github-orchestrator/releases/latest/download/install.sh | sh -s -- --agent codex
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
config as `agent = "codex"`. It also offers to copy the skills it ships into
that agent's skills folder (`~/.claude/skills`, or `<CLAUDE_CONFIG_DIR>/skills`
when the config's `agent_command` sets `CLAUDE_CONFIG_DIR`, or
`~/.agents/skills` for Codex):
`rebase-on-main`, which the agents run when a branch stops merging, and
`create-pr`, which opens a new PR; `github-orchestrator skill` installs them
later, and [Updating](#updating) says what `update` does with them. Leaving
them out writes `pr_skill = ""` into the config, so the agents open new PRs
themselves with `gh pr create` instead of looking for a skill that is not there.

Desktop notifications are optional. On macOS the installer asks whether to
build the notification apps, which needs the Command Line Tools. On Linux they
go through `notify-send` when it is on `PATH`.

The installer then installs the newest release with `uv tool install`, starts
the watcher as a service (a LaunchAgent on macOS, a systemd user unit on Linux)
and opens the board. `sh -s -- --help` in place of `sh` lists its options, such as `-y` to
answer yes to every install question and `--version X` for an older release.
Under `-y` the agent is Claude unless you chose another, the macOS notification
apps are not built, the Linux watcher does not keep running after logout,
missing skills are installed, and a skill that differs from this version's is
left alone. An install
from an older checkout is found and replaced, with its config and data moved
over.

The board opens on its setup screen: your GitHub account, the repos to watch,
where their clones are, and a few options. **Start watching** writes the config,
clones what is missing and restarts the watcher into watching; once it is
watching, the same button reads **Save and restart**. The first time
the wall has pull requests it shows a short tour, which
`github-orchestrator tutorial` shows again.

`github-orchestrator doctor` checks the machine first: the install, whether a
newer release is out, the command on your `PATH`, the skill, the agent (for
Claude, whether the Atlassian MCP server is connected; for Codex, whether it is
logged in) and desktop notifications. Then, for every instance, it checks the
config, the hub's port, the requirements on your `PATH` and on the service's, the
service itself, GitHub, each repo's clone, the hub and the watcher. It prints the
fix for anything that is not ok, and changes nothing.

## Configuration

The board's setup screen (`/setup` on the hub; `github-orchestrator setup` opens
it, and so does the top bar's **Setup** link) asks for your account and the repos to
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

A `[[repos]]` entry may also set:

- `new_worktree_command`, which replaces the top-level one for that repo's
  worktrees
- `has_tests = false`, when the repo has no tests an agent can run, so a
  rebased fix that reports its tests unverified lands on the first Accept
- `pr_skill`, the skill an agent runs to open a new PR, such as the one a split
  carries code into, so a repo can name its own team's PR skill; it wins over
  the top-level `pr_skill`, which is `create-pr`, the skill the orchestrator
  ships, unless the skills were left out, when it is `""` and the agent opens
  the PR itself with `gh pr create`
- `draft`, whether that new PR is a draft: left unset, the skill decides
  (`create-pr` opens a draft); set to `true` or `false`, it wins, and the
  orchestrator flips the PR to match once the skill returns

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

`github-orchestrator help`, like `--help`, lists every command under its group,
each with one line on what it does:

```text
everyday:
  open            Open this instance's board in the browser.
  status          Show overall system status.
  logs            Tail the watcher's, the agent managers' or the service's log.
  runs            Summarise today's agent runs: count, total time, longest.

service:
  start           Start this instance's watcher as a service and wait for its hub.
  stop            Stop this instance's watcher and agent managers.
  restart         Restart this instance's watcher and agent managers.
  restart-all     Restart every instance's watcher and agent managers.
  hold-restarts   Make every restart skip until allow-restarts.
  allow-restarts  Let restarts through again after hold-restarts.

maintenance:
  update          Install the newest release and restart every instance on it.
  doctor          Check the install, the service, GitHub and each repo, and say how to fix what fails.
  config          Print every setting's effective value and where it came from.
  uninstall       Stop every instance, remove their services and the command.
  setup           Open the board's setup page, where the account, the repos and the options are chosen.
  skill           Install the skills the orchestrator ships (rebase-on-main, create-pr) where this instance's agent reads its skills.

learning:
  tutorial        Open the board's tour of the wall and a pull request's page.
  help            List the commands, or show one command's help.

agents:
  thread          Report on and act on a pull request's comment threads: the agents' side of the board.

debugging:
  queue           Show pending events for a PR.
  undismiss       Clear a PR's dismissal so it comes back to the wall.
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
shows an example. Every command but `thread` takes `--instance NAME`; for
`thread`, put it before the command (`github-orchestrator --instance work thread list ...`) or set `GITHUB_ORCHESTRATOR_INSTANCE`.

`runs` totals cost as `~$8.14 API-equivalent` rather than as money, because
every run bills against your subscription and none of it is a charge.

Runtime state lives under the resolved data dir; see
[Runtime data](docs/how-to-use.md#runtime-data) for what is in it.

`http://127.0.0.1:8720` is the hub, and where you start. Its home is the wall,
every PR grouped by who has to move next. Opening one gives that PR's page with
**Summary | Board | Dashboard | Terminal | Diff** tabs, and **Runs** lists the week's Claude runs
under the watcher's health. [The hub](docs/how-to-use.md#the-hub) has the keys
and the rest. When a PR's worktree has diverged from origin, the Diff tab's
timeline offers **Reset to origin**, or **Reset when the agent finishes** while
an agent is working in it.

## Updating

When a newer release is out, the board's top bar shows **Update available** and
`status` says so. Nothing installs on its own:

```bash
github-orchestrator update           # install the newest release, then restart every instance on it
github-orchestrator update --check   # only say whether there is one
github-orchestrator update --force   # close, without asking, any terminal session in a folder the upgrade renames
```

An upgrade can rename the folders of review threads' worktrees. A terminal
session left open in one of them holds that up: `update` names each one and
asks before closing them. Until they close the watcher waits, and the board
lists them with a **Close sessions and migrate** button.

`update` also updates the shipped skills in the default instance's skills
folder. When some are missing and it runs in a terminal, it names each one and
what the agents use it for, and asks whether to install them; a no writes
`pr_skill = ""`, and later updates take that as the answer and ask nothing.
With no terminal to ask on it does what the installer does under `-y`: a
missing skill is installed. Either way, one that differs from this version's
is left alone (`github-orchestrator skill --replace` replaces it), and
`github-orchestrator skill` installs the skills and writes `create-pr` back.

## Uninstall

```bash
github-orchestrator uninstall
```

It stops every instance, removes their services and the command, and asks
before removing the config, the data and the notification apps too. It never
touches your clones, and leaves uv, gh and claude installed, and the shipped
skills in the agent's skills folder.
[Removing it](docs/how-to-use.md#removing-it) has the details.

## Developing

This repository is the source of truth; a release is a tag of it. Building the
front end needs Node and npm besides uv. To run your checkout as the installed
tool:

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
