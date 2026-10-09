# One server process: plan

Carries out [the server process spec](../specs/2026-10-09-server-process-design.md).
The spec is the decision. This plan sets the order of the steps and how each one
is judged.

The order cuts the board loose from the manager's memory first, while the board
still runs inside the manager, so each step can be checked on the running system.
The server process comes next and is tested on its own. Then one step switches
serving over and deletes what it replaces.

## How to work

- Every change follows `.claude/skills/normal-workflow`, including its private
  information and public-root checks before each merge. Load `tdd` for anything
  that changes behaviour and `refactor` for reshaping. The user has approved
  running the steps straight through without stopping to confirm.
- Each step gets its own branch in its own worktree, cut from local `main`. It
  is merged and restarted before the next step starts.
- **Who proves what.** A step agent proves its step with tests, and where the
  step says so, with a scratch instance (its own data directory and port) or a
  server on a spare port. Against the live data directory it sends only GET
  requests. It never runs `make restart-all`, never stops or signals the live
  watcher, managers or server, and never writes under the live data directory.
  The coordinator merges, restarts and does each step's "prove on the running
  system" check.
- **Every decision goes in the plan.** A choice the spec left open, a leftover
  and the constraint that holds it, a budget call: each gets a line under its
  step in "Decisions" at the end of this plan, with its reason, in the step's
  last commit.
- Run `make lint-python` and `make test-python` before each commit. When the
  commit touches `frontend/`, run the full `make lint` and `make test` as well,
  and report the pass counts. A falling count fails the check unless the commit
  message names each deleted test and what made it impossible.
- **Files are written whole.** Every new file (status, command, held list, hub
  state, setup) is written to a temp file and moved into place, as thread records
  are. A reader that finds no file reads it as the spec's "nothing yet", never as
  an error.
- **One owner per file.** Each new file has one module that writes it and reads
  it, with its path in one place. Nothing else opens it.
- **No second copy of a rule.** The refusal rules for manager commands live in
  one place, used by both the server's check and the manager's check on drain.
  The starting/answering/gone rule lives in one place, used by the board and the
  wall.
- **Budgets.** `make interface-report` must show no package with more exports
  than it has on `main` when the step starts, and no class with more methods,
  unless the step creates the package. Data fields on a dataclass or model are not
  methods.
- **Data on disk.** Thread records, queues and snapshots written before a step
  still load. The new files are optional: their absence must not break a board
  or a manager.
- **No GitHub writes.** Nothing a step does may approve, reject, reply, post,
  push, resolve or dismiss on a real PR.
- Tests assert behaviour and structure, never colours, borders or widths.
- Code carries no comments (the user's rule).
- Test parallelism stays at 4 workers or fewer. Never `-n auto`.
- A new test that runs git under replay needs recording:
  `uv run pytest tests/ -k '<tests>' --record`, never by file path. Revert any
  machine state `--record` sweeps in.
- When the spec leaves a choice open, make it, record it in the step's commit
  message with the reason, and name it in the report.
- Bound every long command with `timeout` (a suite with `timeout 300`), so a
  hang shows up as a failure rather than silence.
- When a step finishes, mark it **Done** below with its last commit hash, in
  the same commit as its last code change.

## Steps

1. **The manager writes its status file.** **Done** (`ed567d91` and the commit
   that records this)

   - Each tick, after it publishes `_drawn`, the manager writes the status file:
     `written_at`, `active_run` (event, started at, last output at), `notice`,
     `threads_live`, `frozen_on` and the fields that go with it, and
     `flags_changed_at`.
   - One function reads it back and answers starting, answering or gone, with
     `status_stale_seconds` = 10 and "starting" meaning no file yet for this
     manager's run.
   - Nothing reads it yet in production. Prove it on the running system after
     the restart: the file appears for each manager and moves every tick.

2. **Commands go through the command file.**

   - Hold, resume, carry-on, start-review, dismiss and close write a command file
     and answer 202 as today. The manager drains the directory each tick in id
     order, carries out each command, deletes its file and reports in `notice`.
     `_crossing` goes.
   - The refusal rules move to one place that reads the status file. The handler
     refuses with them, and the manager checks again on drain.
   - `run_git` takes a file lock on the worktree's palette lock instead of
     `_git_lock`. Its frozen check, and `open_terminal`'s, read the status file.
   - Prove each command on a real manager (hold then resume a PR; carry-on on an
     idle one) and that a command survives a manager restart in between write and
     drain.

3. **The dashboard comes from disk.**

   - The board's `dashboard()` is `DashboardSource.dashboard(pr)` with the status
     file's fields laid over it. Nothing on the board reads `_drawn` any more.
   - The hub's wall reads every row the same way: no HTTP asks to boards, no
     last-answer cache, no thread pool.
   - The board's standing and each wall row's liveness come from the
     starting/answering/gone rule.
   - Prove on the running system that the wall and an open board agree, and that a
     stopped manager's row shows as gone within 10 s.

4. **The watcher's memory goes to disk.**

   - The watcher writes the held list and its told flag each cycle, and the hub
     state when it changes. The hub's routes read them.
   - Setup's progress and listing move to files. Setup's write ends by writing
     the leave file instead of setting `Leaving`. The watcher checks for that file
     on each wait, deletes it and exits.
   - After this step nothing the hub serves needs the watcher's memory.
   - Prove the setup flow end to end in a scratch instance with its own data
     directory and port, never the user's live instances.

5. **The server process.**

   - `python -m github_orchestrator.server` binds the instance's hub port and
     runs uvicorn's `Multiprocess` supervisor with `server_workers` = 4 spawned
     workers.
   - Each worker serves the hub's routes without the proxy, the board routes for
     every held PR at `/pr/{owner}/{name}/{n}/api` built lazily on first request,
     and the page. Board routes write their `Location` headers with the prefix.
     A PR the watcher does not hold is 404.
   - It holds a flock on `server.lock`, writes `server.pid`, logs to `server.log`
     through a new `SERVER` process, and exits with a log line when its port is
     taken.
   - Nothing launches it yet. Test it by starting it on a spare port against the
     live data directory, driving it with the same requests the board makes
     (including a terminal websocket and an event stream), and comparing answers
     with the hub's.

6. **The watcher runs the server; managers and the hub stop serving.**

   - On every loop iteration, in every state, the watcher starts the server
     detached if `server.lock` is free. The watcher no longer serves the hub, and
     stops nothing when it exits.
   - Managers stop starting a board. Delete `ServedBoardApi`'s use in the manager,
     `BrowserFront.serve_board`, board ports and their files, `PORT_RANGE`, the
     `want_board` flags, `_proxy.py`, the websocket relay and `open_streams`.
   - `make restart-all` stops the server with the managers before it restarts the
     watcher, then waits for `/api/health` to answer from a new server pid before
     it waits for the managers. `doctor` checks that pid against `server.pid` and
     drops its board-port report.
   - The front end always uses the `/pr/<repo>/<n>` prefix, and its handling of
     the `manager-starting` refusal goes.
   - Prove after `make restart-all`: every board answers through the hub port, a
     terminal attaches, a stream streams, the wall is right, and killing the
     server brings it back within one watcher cycle.

7. **The older specs point here, and the load test passes.**

   - Add a line to the browser-mode, web-interface and one-command-install specs
     where they say what this one replaces, pointing to this spec.
   - Run the acceptance load test from the spec: 70 CPU spinners for 7 minutes, a
     probe outside the server, and a loop timing diff, `/viewer` and `/health`
     through the hub port. Record the numbers in the spec. The step passes when,
     with the load average above 80, the diff's p90 and `/health`'s max are both
     under 1 s, and a stopped manager's board still answers and shows it as gone.

## Decisions

Each step adds its decisions here, under its number, with the reason for each.

1. - **A run is the life of the file.** The manager deletes its status file when
     it starts, before its first tick, so no file means this run has not drawn
     yet. A reader needs no pid or run id to tell runs apart, and nothing else
     has to publish one.
   - **`StatusFiles` lives in `pr_manager/_status.py`; readers reach it through
     `ManagerStatuses` in `board_api/interface.py`.** That is how the board and
     the wall already reach `DashboardSource` through `Dashboards`, and it adds
     no export to either package.
   - **Staleness is read from `written_at`, against the reader's UTC clock.**
     The file's own stamp keeps the rule testable with a manual clock, and both
     sides run on the same machine.
   - **`status_stale_seconds` is a constant, `STATUS_STALE_SECONDS = 10.0`, not a
     config key.** The spec settled the value at review and nothing asks to
     change it per instance.
   - **`Dashboard.threads_live` and `Counts.live` hold the live keys instead of
     their count.** `pr_manager` cannot name `Counts`, and carrying the keys on
     the dashboard counts the threads once a tick. The contract and the flags
     stamp take the length, so what the board shows is unchanged.
   - **`active_run`'s `started_at` and `last_output_at` are `written_at` minus the
     run's elapsed and silent seconds**, stamped like `flags_changed_at`
     (`%Y-%m-%dT%H:%M:%S.%fZ`, UTC).
   - **The frozen fields are the dashboard's own:** `frozen_on`,
     `expected_branch`, `seconds_left`, `run_working` and `release_requested`.
     They are what the board shows of a freeze today.
