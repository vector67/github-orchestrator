# CLAUDE.md

README.md is how this repository works. What follows is the rules.

A rule earns a line or two — what to do and the one thing that goes wrong
otherwise. The reasoning belongs in the commit message or a spec under
`docs/superpowers/specs/`, not here.

## Checks

```bash
make lint      # ruff and mypy, then the front end's linters, then mdformat
make test      # the python suite, then the ember suite, then one line with both results
make lint-fix  # whatever those linters fix themselves
make watch     # rerun the python suite on every save
make interface-report  # each package's exports and each class's methods against the spec's budgets
```

Either aggregate stops at the first stage that fails. `lint-python`,
`lint-frontend`, `fmt-check`, `test-python` and `test-frontend` run one stage.

`make test` replays recorded git and sh output from
`tests/recorded_subprocesses.json`. `uv run pytest tests/ --no-replay` spawns
every subprocess for real, and `make record` rewrites the recording after a
change to what the code runs. To record only some tests, select them with
`uv run pytest tests/ -k '<tests>' --record`, never by file path: a path-limited
run wipes every other test's entry.

Before a commit, `make lint-python` and `make test-python` are enough when
nothing under `frontend/` changed since the last full run. Run the full `make lint` and `make test` before
merging.

Run a long suite as `timeout 120 uv run pytest … -x -q`, not through `| tail`:
tail prints nothing until the run ends, so a hung test looks like silence.

`make dev-install` installs the `github-orchestrator` command from this checkout
(an editable uv tool) and builds the front end, so the service runs your code in
a user's layout; `make install_hooks` turns on the pre-commit hook.

## Rules

- **Every change follows `.claude/skills/normal-workflow`.**

- **This repo is public: commit nothing internal.** No employer, client, colleague,
  ticket, private repo name or home path from the live machine; examples use
  `acme/*` and `octocat`. A real name in a fixture or spec ships to everyone.

- **The board holds each server fact once, in `frontend/app/services/store.ts`.**
  Fetch and read through the store and derive values only in `data/summaries.ts`;
  a copy kept anywhere else drifts, and the page contradicts itself.

- **Search with `rg`, never `grep -r`.** `make build_frontend` leaves a 613 KB
  minified bundle under `src/github_orchestrator/board_api/static/app/`.
  It is gitignored, so `rg` skips it and `grep -r` reads the whole thing into the
  transcript — twice over, and then every later search wants a defensive
  `| grep -v static`.

- **In a worktree, call ReadAST on the exact path the denial names.** Which copy
  `readast check-bash` resolves to depends on how the worktree was entered, and
  ReadAST on the other copy never clears the read.

- **Read source with Read, never `cat`, even inside `bash -c`.** The harness
  counts only a Read, so a later Write or Edit on a file seen through `cat` is
  refused. ReadAST is deferred: load it with ToolSearch before the first read.

- **In a worktree session, keep each Bash call plain.** The isolation guard refuses
  a heredoc, a `for` loop or git chained with other commands as too complex to
  verify, and nothing runs. Write an edit script to the scratchpad with Write, run
  it as one `uv run python <script>` call, and run git commands on their own.
  The script checks that every anchor appears once in every file before it
  writes any of them; one that stops halfway leaves a half-applied edit.

- **Never put a write and a source read in one Bash call.** A compound command is
  refused whole, so the write never runs and nothing says so — it reads as an edit
  that silently failed to take.

- **Ruff and mypy also gate the pre-commit hook.** mypy is `strict = true` over
  `src` and the shared test helpers (`conftest.py`, every `support.py` and
  `scripted_*.py`), so a double that drifts from the signature it stands in for
  fails lint, with no per-module overrides and no `type: ignore`; ruff has E501 off,
  because the codebase has never held a line width. Adding either back as an
  exception is how the 457 findings come back.

- **Never `pytest -n auto`.** `make test` forks `PYTEST_WORKERS` (8) processes
  beside the ember suite; every core on top of that locks up the machine.
