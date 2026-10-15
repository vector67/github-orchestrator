# One server process for the hub and every board

Date: 2026-10-09. Issue #3.

## Problem

Under CPU load, board requests stall for tens of seconds. Each PR manager serves
its board from a uvicorn thread inside the manager process, so request threads,
the event loop and the manager's tick share one GIL. The hub runs the same way
inside the watcher, and it proxies every `/pr/.../api` request to a manager's
port. Each proxied request holds one of the hub's threads until the board answers,
for up to 75 s.

Measured with 70 CPU spinners on a 10-core machine (load average 100–150),
sampling one manager that had a dozen threads in flight:

|                                                              | median | p90    | max   |
| ------------------------------------------------------------ | ------ | ------ | ----- |
| a separate one-thread process, late waking from a 5 ms sleep | 1.3 ms | 1.3 ms | 15 ms |
| a thread inside the manager, late waking from the same sleep | 221 ms | 743 ms | 5.4 s |
| proposal diff, through the hub                               | 24 s   | 46 s   | 46 s  |
| `/health`, which is async and reads nothing                  | 9 s    | 30 s   | 30 s  |

During the slowest requests, the separate process stayed at 1.3 ms. Native
samples (`sample`) of the manager showed its request threads waiting in
`take_gil` 0–62% of the time, and its event-loop thread 33–86%. A sample taken
before the Python sampler was attached already showed 62% and 69%, so the
sampler did not cause it. The same diff takes 10 ms at a load average of 6.

The holder of the GIL is doing ordinary Python work: the manager's tick,
serialising responses, the garbage collector. When the CPU scheduler preempts it,
every other thread in the process waits until it runs again. A trivial request
needs several handoffs, and each one costs a wait for a core.

The pool is not what fills up. The manager had five worker threads against a
limit of 40.

## Decisions

1. **One server process serves the hub and every PR's board.** The managers and
   the watcher stop serving HTTP. `/pr/<owner>/<name>/<n>/api/...` stops being a
   proxy and becomes the server's own route.
2. **A fixed pool of worker processes shares the listening socket.** Independent
   requests run in different processes and do not share a GIL with each other or
   with any manager.
3. **Commands reach a manager through a command file it drains each tick.** The
   manager writes the state that today lives only in its memory to a status file
   each tick.
4. **The watcher starts the server as a detached child and revives it each
   cycle**, as it does managers. There is still one service per instance.

Out of scope here, and worth doing on their own: the board's polls that do not
wait for an answer before sending the next, and event streams that re-read their
source every 0.5 s.

## What the board depends on today

Almost every board route already reads only disk, git or `gh`:

- **Disk only:** thread records and their `.intent`/`.reply`/`.action` files,
  change-detection facts, the manager's changes file, agent transcripts, terminal
  holder records, static files.
- **Git or gh:** every diff, file and proposal read, `pull-request:fetch`, and the
  presence check behind comment reads.
- **Writes:** every thread verb, draft write, send-review and `seen` writes a record
  under `fcntl.flock` on `<key>.lock` and saves with an atomic replace. Two
  processes writing is already safe.
- **Terminals:** each session is a detached holder process with a record file and
  a unix socket. Any process can list and attach.

Only these are held in the manager's memory:

- `_drawn`, the dashboard each tick publishes. Most of it can be rebuilt from disk:
  `DashboardSource.dashboard(pr)` does that already, and the hub's wall falls back
  to it. Only `active_run` (event, start, last output), `notice`, the live thread
  runs, `frozen_on` and `flags_changed_at` are memory-only.
- `_crossing`, the queue that hold, resume, carry-on, start-review, dismiss and
  close go through. Their refusals read `_drawn` and `active_run`.
- `_git_lock`, a `threading.Lock` around the git palette's commands.

And these are held in the watcher's memory:

- the held list and its "told" flag, set by `Desk.show` each cycle
- `HubState` (setup, watching, broken), fixed when the hub starts
- the setup page's `_progress` and `_listed`
- `Leaving`, the event that makes the watcher exit after setup writes the config
- the wall's last-answer cache and its 32-thread pool, which ask each board's
  `/dashboard`

Per-process caches (presence memo, thread progress, `Conversations._decoded`) are
safe to duplicate: each worker keeps its own and does some extra work.

## Design

### The server process

`python -m github_orchestrator.server` binds the instance's hub port (8720 by
default) and runs uvicorn's `Multiprocess` supervisor with `server_workers`
workers (default 4). Workers start with `spawn`, so each builds its container
after it starts and inherits no threads or held locks. The supervisor restarts a
worker that dies.

Each worker serves one app:

- the hub's routes as today, minus the proxy;
- the board routes for any PR, mounted at `/pr/{owner}/{name}/{n}/api`. A worker
  builds a PR's `Board` on its first request and keeps it: the conversation
  manager from the factory, `working_copies.checkout(pr)`, `PtyTerminals.of(pr)`,
  and a `ManagerPanel` backed by files (below);
- the page.

The server answers for PRs the watcher holds. A request for any other PR is 404.

Every app is guarded by the hub port. The proxy's `Origin` rewrite and the
websocket relay go away: the browser attaches to a terminal holder through the
server directly.

Logging gets a `SERVER` process writing `server.log`, with the same flock-safe
rotation.

### The manager's status file

Each tick, after it draws the dashboard, the manager writes
`<data>/status/<owner>/<name>/<n>.json` with an atomic replace:

- `written_at`
- `active_run`: event, started at, last output at, or null
- `notice`
- `threads_live`: the keys with a live thread run
- `frozen_on` and the fields that go with it
- `flags_changed_at`

The board's dashboard is `DashboardSource.dashboard(pr)` with these fields laid
over it. The hub's wall reads the same, for every row, with no HTTP and no
last-answer cache.

What the board shows about the manager follows from the file:

- **starting:** no status file yet for this manager's run
- **answering:** the file is younger than `status_stale_seconds` (default 10)
- **gone:** older than that, or the manager is not running

### The command file

Hold, resume, carry-on, start-review, dismiss and close write
`<data>/commands/<owner>/<name>/<n>/<id>.json` with an atomic replace and answer
202 with `Location: .../api/dashboard`, as today. Each tick, the manager reads the
directory in order of id, carries out each command, deletes its file, and
reports the outcome in `notice`. This replaces `_crossing`.

The server refuses what the status file already rules out, using the same rules
as `_refusal` and `_agent_refusal`. The manager checks again when it drains,
because the file can be a tick old.

`run_git` takes a flock on `<worktree>.git-palette.lock` instead of
`_git_lock`. Its frozen check, and `open_terminal`'s, read the status file.

### What leaves the watcher's memory

- **Held list.** The watcher writes `<data>/held.json` (the PRs and the told flag)
  each cycle, where `Desk.show` sets it today.
- **Hub state.** The watcher writes `<data>/hub_state` when the state changes.
  `/api/health` reads it.
- **Setup.** Progress and the listing move to `<data>/setup/`. Setup's write
  runs in the server. Instead of setting `Leaving`, it writes
  `<data>/setup/leave`. The watcher checks for that file on each wait, deletes it
  and exits, and the service restarts it as before.

### Supervision

On every loop iteration, in every state (setup, watching, broken), the watcher
makes sure the server is running. The server holds a flock on
`<data>/server.lock` and writes its pid to `<data>/server.pid`. If the lock is
free, the watcher spawns the server detached (`start_new_session`) and does not
wait for it. A server whose port is taken exits with a log line, and the watcher
tries again next cycle.

The watcher no longer stops anything when it exits. Managers and the server
outlive watcher restarts.

`make restart-all` stops the server, together with the managers, before it
restarts the watcher. It then waits for `/api/health` to answer from a new server
pid, then for the managers, as it does today.

`doctor` checks that the pid `/api/health` reports is the one in `server.pid`,
instead of the watcher's pid.

### What goes away

- the uvicorn thread in each manager: `ServedBoardApi`, `BrowserFront.serve_board`
- board ports: the port files, `PORT_RANGE` and the `want_board` flag files
- `_proxy.py`, the websocket relay, `open_streams`
- the wall's per-board HTTP asks, last-answer cache and thread pool
- `doctor`'s report of board ports in use

### Front end

Every board is under the hub origin, so `HereService` always uses the
`/pr/<repo>/<n>` prefix. Board routes write their `Location` headers with the
prefix themselves, which the proxy used to do. `/api/health` always reports
`serves: "hub"`. The board's standing reads starting, answering and gone from the
dashboard's status fields. The `manager-starting` refusal is no longer needed.

## Specs this changes

- **Browser mode (2026-09-26):** "the board is served by the PR manager
  process", and release living on the hub "because a frozen manager stops its
  board". The 202-and-snapshot behaviour of commands stays.
- **Web interface (2026-09-28):** the hub proxies `/pr/<n>/api` and "boards stay
  reachable on their own ports". Its note that the terminal pty lives in the
  manager is already out of date.
- **One-command install (2026-10-08):** "the watcher process runs the hub in every
  state". Setup's leave becomes a file. `/api/health` keeps its fields; `pid` is
  the server's. Still one service per instance.

Each gets a line pointing here.

## Testing

- The board tests that use `TestClient` on a built `Board` keep working. Their
  `FakeManagerPanel` becomes the file-backed panel over a temp dir.
- New tests: the status file round trip and its starting/answering/gone rules;
  the command file's write, ordered drain, delete and refusals; the server's
  routing of `/pr/.../api` to a lazily built board; held-list and setup-leave
  files; supervision reviving a dead server.
- Tests that assume the board runs in the manager (`test_browser_front.py`, the
  manager-panel tests, `test_review_board.py`, `FakeBoardApi`) move to the file
  seams or go with the code they cover.

## Acceptance

Repeat the load test: 70 CPU spinners for 7 minutes, a probe outside the
server, and a loop timing diff, `/viewer` and `/health` through the hub port.
With the load average above 80, the proposal diff's p90 is under 1 s and
`/health`'s max is under 1 s. A board keeps answering while its manager is
stopped, and shows it as gone.

### Result, 2026-10-09: not met

Measured after step 6, through the hub port, with the load average above 80:

|                                                               | median | p90    | max    |
| ------------------------------------------------------------- | ------ | ------ | ------ |
| spinners at normal priority (peak load 182): `/health`        | 0.87 s | 2.9 s  | 12.7 s |
| the same: `/viewer` on a board                                | 2.3 s  | 10 s   | 29 s   |
| spinners at `nice 20` (peak load 146): `/health`              | 1.3 s  | 5.3 s  | 5.3 s  |
| the same: `/viewer`                                           | 2.8 s  | 13 s   | 13 s   |
| the same: a proposal's diff (`/diffs/<base>..<head>`)         | 50 s   | 81 s   | 81 s   |
| a one-thread probe outside the server, late from a 5 ms sleep | 1–3 ms | 1–3 ms | 65 ms  |

At a load average of 3, the same requests take 1–5 ms, and the diff 137 ms.

Compared with before the change (`/health` median 9 s, max 30 s; `/viewer`
median 23 s, max 40 s), medians fell by about ten times, but the targets are
missed. The probe outside stayed fast throughout, so the delay is inside the
server's workers. Lowering the spinners' priority did not help, so CPU priority
alone does not explain it. The diff run at normal priority used a route that no
longer exists and is not in the table.

A stopped manager's board kept answering under load and showed it as gone 9 s
after the stop, which is met.

### Cause, 2026-10-15: the launchd job's CPU class

The service's launch agent sets no `ProcessType`. launchd.plist(5) says such a
job gets "light resource limits ... throttling its CPU usage", and every process
the watcher starts inherits them: `ps -o pri` shows 20 for the watcher, the server
and its workers, against 31 for a process started from a terminal. The probe and
the spinners ran at 31, so under load the server lost the CPU to them. That may
also be why lowering the spinners with `nice` did not help; it was not measured
again.

Measured with the same rig (70 spinners, a probe, a loop timing requests on a
second server started from a worktree on its own port), above load average 80.
Only the server's CPU class changed between the runs. `taskpolicy -c utility`
puts the server at priority 20, the value `ps` shows for the service's server:

|                                                                     | median | p90    | max    |
| ------------------------------------------------------------------- | ------ | ------ | ------ |
| priority 31, no page open (load 82–116): `/api/health`              | 2 ms   | 3 ms   | 9 ms   |
| the same: a board's `/health`                                       | 2 ms   | 3 ms   | 7 ms   |
| the same: `/viewer`                                                 | 5 ms   | 6 ms   | 24 ms  |
| the same: a proposal's diff                                         | 209 ms | 219 ms | 254 ms |
| priority 31, six simulated open boards (load 83–116): `/api/health` | 2 ms   | 4 ms   | 100 ms |
| the same: `/viewer`                                                 | 5 ms   | 12 ms  | 76 ms  |
| the same: a proposal's diff                                         | 216 ms | 246 ms | 440 ms |
| priority 20, no page open (load 83–124): `/api/health`              | 132 ms | 475 ms | 816 ms |
| the same: `/viewer`                                                 | 436 ms | 1.1 s  | 2.1 s  |
| the same: a proposal's diff                                         | 11 s   | 27 s   | 27 s   |
| priority 20, six simulated open boards (load 82–163): `/api/health` | 2.7 s  | 9.4 s  | 9.4 s  |
| the same: a board's `/health`                                       | 4.6 s  | 7.5 s  | 7.5 s  |
| the same: `/viewer`                                                 | 7.1 s  | 15 s   | 15 s   |
| the same: a proposal's diff                                         | 50 s   | 52 s   | 52 s   |
| the probe, late from a 5 ms sleep, in every run                     | 1 ms   | 1 ms   | 8 ms   |

At priority 31 the targets are met; at priority 20 the 2026-10-09 result comes
back. The slow runs finished few requests: the last one only 8 `/viewer` reads
and 3 diffs above load 80. Native samples of the workers at priority 31 showed no
thread waiting for the GIL. A child of a process clamped with
`taskpolicy -c utility` stays at 20 even when started with `taskpolicy -a`, so
the server likely cannot leave the class from inside the watcher's tree, though
that was not tried under launchd.

Open: how to lift the server out of the class. Setting `ProcessType` to
`Interactive` in the launch agent lifts the whole tree, managers and agent runs
included. Giving the server a launch agent of its own lifts only the server but
changes who supervises it. Lifting the job and starting managers and agent runs
under a utility clamp keeps their class as it is today. None of these has been
measured under launchd yet.

## Settled at review

- `server_workers` is 4. A worker serves many connections at once on its event
  loop, so open event streams do not use up workers. Each stream still re-reads
  its source in that worker's threads every 0.5 s, sharing the worker's GIL with
  the requests it serves.
- `status_stale_seconds` is 10: three of today's 1 s ticks plus slack. A manager
  stalled in a long tick shows as gone until it writes again.
