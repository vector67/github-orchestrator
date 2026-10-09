# One-command install: plan

Carries out [the one-command install spec](../specs/2026-10-08-one-command-install-design.md).
The spec is the decision. This plan sets the order of the steps and how each one
is judged. The steps are the spec's "Order" section, run in the order below so
that nothing collides with the front-end store plan and the comment-verdict plan
while they are still running.

## How to work

- Every change follows `.claude/skills/normal-workflow`. Load `tdd` for
  anything that changes behaviour and `refactor` for reshaping. The user has
  approved running the steps straight through without stopping to confirm.
- Each step gets its own branch in its own worktree, cut from local `main`. It
  is merged and restarted before the next step starts.
- Run `make lint-python` and `make test-python` before each commit. When the
  commit touches `frontend/`, run the full `make lint` and `make test` as well,
  and report the pass counts. A falling count fails the check unless the commit
  message names each deleted test and what made it impossible.
- **Stay out of the other plans' way.** Until the front-end store plan and the
  comment-verdict plan are marked done, a step touches nothing under
  `frontend/`, and nothing in `pr_manager/_terminal_front.py`, the terminal
  dashboard, `board_api/_contract.py` or `conversation/`. A step that needs one
  of those waits; the coordinator holds it back rather than splitting it.
- **The live machine keeps running.** The owner's three instances run from this
  checkout under launchd. After every merge, `make restart-all` (or, once
  step 2 lands, `github-orchestrator restart-all`) must bring every instance
  back, and `/api/health` must answer on 8720, 8721 and 8722. A step that
  changes how the service starts proves it on those instances, not only in
  tests.
- **Never break the owner's existing install.** Until migration ships in step
  12, a config in the checkout, the old plist and the `~/.local/bin` symlink
  keep working. Where a step moves a default, it reads the old place too, in
  one place inside the module that owns it.
- **No real upgrades or installs on the owner's machine.** Don't run
  `brew upgrade`, `uv self update`, or the installer against the live install.
  Prove a service-layout change by reading the rendered plist or unit, or in a
  scratch HOME, or in an OrbStack Linux machine.
- **Linux checks run in OrbStack.** `orb create ubuntu <name>` gives a machine
  with systemd and a user manager. Delete it when the step is done.
- **Budgets.** `make interface-report` must show no package with more exports
  than it has on `main` when the step starts, and no class with more methods.
  A package at its budget swaps an export rather than adding one. Data fields
  on a dataclass or model are not methods.
- **Data on disk.** Configs, snapshots, thread records and queue files written
  before a step still load. Read a missing key as its old meaning, write the new
  form, and keep the translation in one place inside the module that owns the
  file.
- **No GitHub writes.** Nothing a step does may approve, reject, reply, post,
  push, resolve or dismiss on a real PR, or create a release or tag on the real
  repo. Release workflows are proven on a fork or with `act`, or left to the
  first real tag.
- Tests assert behaviour and structure, never colours, borders or widths.
- Code carries no comments (the user's rule).
- Check the look of any step that changes the board, in both themes, against
  the running hub after the restart. Take headless Chrome screenshots, look at
  them, and load the page with console logging on. Any `Uncaught` error fails
  the check.
- When the spec leaves a choice open, make it, record it in the decision log
  with the reason, and name it in the report.
- Bound every long command with `timeout` (a suite with `timeout 300`), so a
  hang shows up as a failure rather than silence.
- When a step finishes, mark it **Done** below with its last commit hash, in
  the same commit as its last code change.

## Steps

The numbers are the spec's. They run in this order: 1, 2, 3, 10, 11, then 5,
8 and 4 once the other plans no longer touch their files, then 6, 7, 9, 12, 13
and 14.

01. **Run without a checkout.** As the spec's step 1. **Done** (`4dafb994`,
    `cf0e299e`, `d2feeb21` and the commit that records this).
02. **The LaunchAgent runs the tool's Python.** As the spec's step 2. **Done**
    (`7b304def`, `341928a8` and the commit that records this).
03. **Linux as a systemd user unit.** As the spec's step 3. **Done** (`b9dbb265`,
    `77c6057a`, `9510bca0`, `b06a0f53` and the commit that records this).
04. **Remove tmux mode.** As the spec's step 4. **Done** (`718b0712`, `3a688b9f`,
    `bfda0a42`, `300a93b8`, `9d30e78c`, `57e961c9` and the commit that records this).
05. **Many repos.** As the spec's step 5. **Done** (`e8f676fc`, `4966b246`, `d98db55e`,
    `94b5449a`, `a89673ee` and the commit that records this).
06. **PR URLs by repo.** As the spec's step 6. **Done** (`b1494e53` and the
    commit that records this).
07. **The repo filter.** As the spec's step 7. **Done** (`e90e39a9`, `119049a3`
    and the commit that records this).
08. **The hub in setup mode.** As the spec's step 8. **Done** (`b1b39ad6`,
    `cf64c95f`, `0d59657a`, `431972c5` and the commit that records this).
09. **The setup screen.** As the spec's step 9. **Done** (`8bed67f2`, `e1cb82a7`, `19ca44a6`,
    `35445fb8`, `f089b5ba`, `0aa44cc2` and the commit that records this).
10. **The CLI's help.** As the spec's step 10. **Done** (the commit that
    records this).
11. **doctor.** As the spec's step 11. **Done** (`69c23d07`, `ec158a7b`, `edd6af33`,
    `16ecac06`, `d3b6bb19`, `3da2af11`, `e057b628`, `40cbd1c8`, `2c99b3c8`, `8e805053`
    and the commit that records this).
12. **Releases.** As the spec's step 12. **Done** (`045e797d`, `f17ab625`, `fef78f35`,
    `f8dfee78`, `b6020f58`, `2709673b`, `6ba76da0`, `fe286d19`, `54c9ffc1`, `9ea3c4f3`,
    `efe2a164`, `dcff6c72`, `3dc70162`, `2b65fc21`, `175bc0ec`, `e79d755b`, `bf50ab31` and the commit
    that records this).
13. **The tour.** As the spec's step 13. **Done** (`e2f47f15`, `2a52e884` and the commit
    that records this).
14. **Docs.** As the spec's step 14. **Done** (`2904dbde` and the commit that
    records this).
