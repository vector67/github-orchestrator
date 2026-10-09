# Deepening the hot spots: plan

Carries out [the deepening spec](../specs/2026-09-30-deepening-design.md). The
spec is the decision; this plan says in what order, and how each step is judged.

## How to work

- Every change follows `.claude/skills/normal-workflow`. Load `refactor` for
  reshaping and `tdd` for anything that changes behaviour. The user has approved
  running every step straight through without stopping to confirm.
- Steps run two at a time, one front-end step beside one python step, each in
  its own worktree cut from local `main`. Neither step edits a file the other
  step's spec item names. The coordinator merges both and runs
  `make restart-all` before the next pair starts.
- A step does its spec item and nothing else. Code another item names is left
  for that item's step.
- Run `make lint-python` and `make test-python` before each commit. A front-end
  step also runs the full `make lint` and `make test` before each commit. A
  count that falls fails the check unless the commit message names each deleted
  test and what made it impossible.
- A refactor's protective tests pass on the old code first and stay green. Test
  through the deepened module's interface; the old tests through the old entry
  points stay until the new ones are proven by breaking the new code once, and
  go in a later commit of the same step.
- Front-end tests stay acceptance tests against `FakeBoard` unless the new
  module has behaviour an acceptance test cannot reach cheaply; then a
  `tests/unit/*-test.ts` for that module's interface is allowed.
- The export budget (about 5, 10 for the exceptional modules) and the method
  cap (about 10) bind every touched python module; `make interface-report`
  checks them. A new front-end module keeps its exports to what callers use.
- `tests/test_layering.py` pins imports and exports on purpose. Update its
  pins to the new shape; never loosen a rule to make a step pass.
- mypy strict with no `type: ignore`, no per-module overrides, no new ruff
  exceptions.
- Duplicates collapsed into one: diff them first and list every difference
  (logging, error types, wording) in the commit message as a behaviour change.
- Wire changes (item 6) update the OpenAPI YAML under `docs/superpowers/specs/`
  and the front end's contract JSON together, through the existing contract
  copy check.
- Code carries no comments (the user's rule).
- Nothing a step does may approve, reject, reply, post, push or dismiss on a
  real PR.
- A front-end step checks the look of what it changed in the dev preview
  (`python -m github_orchestrator.preview`, after `make build_frontend`) with
  headless Chrome and console logging on: any `Uncaught` error fails the check.
- When the spec leaves a choice open, make it, record it in the decision log
  with the reason, and name it in the report.
- Bound every long command with `timeout` (a suite with `timeout 300`).
- Mark the item **Done** in the spec, with the hash, in the same commit as the
  last code change.

## Steps

1. **Round 1.** Spec item 1 (front end: polled sources and reachability) beside
   spec item 2 (python: manager commands).
2. **Round 2.** Spec item 3 (front end: decision module) beside spec item 4
   (python: dashboard source).
3. **Round 3.** Spec item 7 (front end: PR controls, on item 1's services)
   beside spec item 6 (python: delete eligibility, with its front-end offer and
   refusal in `panel-actions`, `verbs` and `dialogs` only).
4. **Round 4.** Spec item 8 (front end: key scopes) beside spec item 5 (python:
   wiring), last because it touches every top module's constructor.
5. **Test speed.** With nothing else running, `make measure-test-speed` on
   `main`, compared with the latest row of `docs/test-speed.md`; within about
   20% or the added tests get cheaper; then add the row and commit it.
