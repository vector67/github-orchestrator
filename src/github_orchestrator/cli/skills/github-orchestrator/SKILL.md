---
name: github-orchestrator
description: Use when anything touches the GitHub orchestrator (github-orchestrator) - finding the worktree it cut for a PR or a review thread, handing it a branch, waiting for it to pick a PR up, reading its logs, state, queues or config, or running its CLI, including the agent-facing `thread` commands.
---

# GitHub orchestrator

The orchestrator watches PRs, queues an event per change and runs an agent per event in a worktree it cuts. Its own docs are the source of truth for everything this skill does not cache:

- [docs/how-to-use.md](https://github.com/vector67/github-orchestrator/blob/main/docs/how-to-use.md): processes, every setting, **Runtime data**, **Finding out what went wrong**, the board, thread states.
- `github-orchestrator <command> --help`, and `github-orchestrator thread <sub> --help` for the agent-facing commands.

This skill caches what those leave out: how to find things on the machine you are on, and the gotchas.

## Instances on this machine

One machine can run several instances, each a separate watcher, hub and data dir. Find them before you read anything else:

- `github-orchestrator config [--instance NAME]` prints the config path on its first line, then every effective setting and where it came from: the GitHub account, the hub's port and the `[[repos]]` it watches. Run it with no `--instance` for the default instance and trust the path it prints: the default config is usually `~/.config/github-orchestrator/config.toml`, but an older install keeps it elsewhere.
- Each other instance is a file `~/.config/github-orchestrator/<name>.toml`. Only a name ending exactly in `.toml` counts: `.bak`, `.retired` and `.lock` files beside them are not instances.
- `config` does not print the data dir. It is `$XDG_DATA_HOME/github-orchestrator`, or `~/.local/share/github-orchestrator` where that is unset (`printenv XDG_DATA_HOME` says which). A named instance's is `github-orchestrator-<name>` beside it.
- Each instance's watcher is a service: a LaunchAgent labelled `com.github-orchestrator.watcher[.<name>]` on macOS, a systemd user unit `github-orchestrator[-<name>].service` on Linux.
- Every command but `thread` takes `--instance NAME`. `thread` takes it before the command (`github-orchestrator --instance work thread list ...`) or from `GITHUB_ORCHESTRATOR_INSTANCE`.

## Worktrees

There are two kinds, and they live in different places.

**A PR's worktree** sits in a folder beside the repo's clone (`local_path`), named after the clone, and is itself named after the PR's head branch: `<local_path>-worktrees/<branch>`. For a clone at `~/code/widgets` that is `~/code/widgets-worktrees/<branch>`. When that folder is taken it tries `<branch>-pr<N>`, then `<branch>-1`, `<branch>-2`, and so on. It is checked out on the PR branch itself. A worktree cut by a release before this layout sits beside the clone instead, at `<parent of local_path>/<branch>`, and stays there.

- **Look it up rather than guess:** `<data dir>/pr_managers/<owner>/<repo>/<N>.json` holds `{"pid", "worktree"}` for the PR's running agent manager. The board's Dashboard shows it too. `git -C <local_path> worktree list` shows every worktree of the repo at once, PR and thread alike, whichever layout cut it.
- **Reuse:** before cutting one, the watcher reuses any existing worktree that already has the PR branch checked out, wherever it is, including a session worktree under `.claude/worktrees/`. If the main clone has the branch checked out, the watcher switches the clone to `main` and cuts a fresh worktree.
- **Reaping:** when the PR closes, the watcher removes whichever worktree holds the branch.
- **Handing a branch over:** push it, then free it before the watcher picks the PR up. Detach any session worktree that holds it (`git -C <worktree> checkout --detach`), or the watcher adopts that worktree and later deletes it.
- **Waiting for pickup:** poll for `pr_managers/<owner>/<repo>/<N>.json`, or for `git worktree list` showing a worktree on the branch. A poll is every 60 s.
- **Wrong branch:** a PR worktree switched to another branch freezes that PR's events until **Release** (`w` on its Dashboard). See "A PR on the wrong branch" in the docs.

**A review thread's worktree** is where an agent builds the fix for one review comment:

- Path: `<data dir>/thread-worktrees/<owner>/<repo>/<N>/<thread key>-<hash>`, for example `.../widgets/7/PRRT_kwDOAbCdEf5zXyZq-79f68`.
- Branch: `orchestrator/thread/<N>/<thread key>-<hash>`, cut from the PR head.
- The thread key is the GitHub node id: `PRRT_…` for a review thread, `IC_…` for a conversation comment. A key `request_<hex>` is a change asked for on the board alone, which GitHub never saw.

## Data dir

The docs' **Runtime data** section lists the top level. The parts worth knowing by path:

| Path (under the data dir)                       | Holds                                                                                                        |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `state/<owner>/<repo>/`                         | last-seen PR snapshots; a PR without one is not tracked                                                      |
| `queues/<owner>/<repo>/<N>/`                    | the PR's pending event JSON files; `github-orchestrator queue <N>` lists them                                |
| `threads/<owner>/<repo>/<N>/<key>-<hash>.json`  | one thread's record: `fix_state`, `thread_sha`, `rebase_onto`, `base_sha`, `tests`, `attempts`, the comments |
| `threads/.../<key>-<hash>.action` / `.lock`     | the thread's last action and its lock                                                                        |
| `threads/.../poll-<n>.cursor`                   | the comments the watcher has seen on that PR                                                                 |
| `thread-worktrees/`                             | thread worktrees, as above                                                                                   |
| `pr_managers/<owner>/<repo>/<N>.json`           | running agent manager: pid and PR worktree                                                                   |
| `summaries/<owner>/<repo>/<N>.json`, `<N>/`     | the PR's latest pr-summary and its working folder; `<N>.lock` / `<N>.run` mark a run in flight               |
| `transcripts/<owner>/<repo>/<N>.jsonl`          | every agent run's stream-json for that PR                                                                    |
| `runs.jsonl`                                    | one line per finished run, every PR                                                                          |
| `dismissed/`, `on_hold/`, `held.json`           | dismissals and holds                                                                                         |

## Logs

All are in `<data dir>/logs/`. `github-orchestrator logs watcher|agent|service|all -n 200 [-f]` tails the main ones without finding the folder; it does not tail `server.log`.

| File                                    | What to look for                                                                                            |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `watcher.log` (+ `.1`…`.5`)             | one `Polled N PRs` line per cycle, events queued, `Created worktree for PR …` / `Reusing existing worktree` |
| `agent-manager.log` (+ rotations)       | every PR's manager in one file; `grep '#7]' agent-manager.log` is one PR's history                          |
| `pr_managers/<owner>/<repo>/<N>.log`    | one manager's own output                                                                                    |
| `server.log`                            | the hub and boards: failed board actions, refused requests, browser errors                                  |
| `gh_calls.csv`                          | every `gh` request, with status and rate-limit headers on a 403                                             |
| `launchd.log`                           | the service's stdout and stderr: a watcher that died before it could log                                    |

Every log but `launchd.log` stamps each line in ISO 8601 with its UTC offset. When you filter by time, match the stamp at the start of the line: a traceback's unstamped lines otherwise look new.

## CLI

`github-orchestrator help` lists the public commands (`status`, `logs`, `runs`, `restart`, `config`, `doctor`, …). Two groups worth knowing:

- **Debugging:** `queue <N>` (pending events) and `undismiss --repo <owner/name> <N>`.
- **`thread`:** the commands an orchestrator-dispatched agent reports through (`open`, `plan`, `step`, `ready`, `reply`, `ask`, `fail`, `base`, `split`, …), plus `list` and `show` for reading. Each takes `--repo <owner/name> --pr <N>`.

Reading thread state:

- `thread list` prints a plain table: key, board state, location, gist. It is not JSON.
- `thread show --thread-id <key>` prints the board's JSON view: `state`, `sha`, `tests`, `note`, `summary`, `confidence`.
- `fix_state`, `thread_sha` and `rebase_onto` are only in the record file under `threads/`; read it with `jq`.

Reporting a fix (`thread ready`):

- It takes `--thread-id` with the key from the worktree path (`PRRT_…` / `IC_…`, without the `-<hash>` suffix), plus `--sha` and `--tests passed|failed|unverified`. It prints nothing on success.
- Re-read the record afterwards: a racing `ready` can exit 0 and leave `thread_sha` or `tests` null.
- `status` in the record is always null; `fix_state` is the field that moves.

## Gotchas

- **Two agents on one thread worktree.** The orchestrator sometimes dispatches a duplicate agent into the same thread worktree. Before editing, check `ps -eo pid,command` for another agent or test run whose command names the worktree path, and read the record:
  - `fix_state: proposed` with your sha means it is done; a second `ready` silently does nothing.
  - `fix_state: landed` means the worktree and branch are about to be deleted under you. Git then falls through to any repository that holds the data dir, such as a dotfiles repo, so check commits from the main clone with `git cat-file -t <sha>`.
  - `fix_state: running` with a null `thread_sha` may mean the duplicate already rebased and committed: compare `HEAD^` with `rebase_onto`.
- **A moved PR tip re-queues the thread.** When the PR head moves, the board rewrites `rebase_onto`, resets `fix_state` to `queued` and dispatches again, so `thread ready` is refused (`'open/queued' -> 'ready'`). Redo the rebase onto the new `rebase_onto`, never back to the older one.
- **Restarts confirm themselves.** `restart` / `restart-all` wait up to fifteen minutes for a poll and name managers that did not come back. A hold (`hold-restarts`, a `restarts-held` file in the data dir) makes them skip; `allow-restarts` clears it.
