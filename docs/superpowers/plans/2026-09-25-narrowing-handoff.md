# Narrowing the module interfaces: handoff

The decisions are made. What is left is carrying them out.

## Read first

- [The module map](../specs/2026-09-23-module-map-design.md) has the interface
  rules, the shared kernel and every module's entry. Each item there is marked
  done or to do. That spec is the source of truth.
- [The grilling record](../specs/2026-09-25-exports-grilling-record.md) has
  every question, recommendation and answer (Q1–Q59). Read it when an entry in
  the spec leaves you unsure what was meant.

Done already, merged into local `main` and not pushed:

- `9035bba5..4689ad32`: settings path helpers
- `a9f36830`: `PrThreads.now`
- `cab0e466`: `GH_TOKEN`

## How to work

- Every change follows `.claude/skills/normal-workflow`. Load `refactor` for
  reshaping work and `tdd` for anything that changes behaviour.
- Work one step at a time. Each step is its own branch, merged and restarted
  before the next. Stop after each step and confirm with the user before
  starting the next one.
- Run `make lint-python` and `make test-python` before each commit, the full
  `make lint` and `make test` when `frontend/` changed and once before
  reporting, and report the pass counts. A count that falls in a step that only
  moves code fails the check, unless the commit message names each deleted test
  and the API or state that made it impossible.
- Before reporting, check every touched module against the interface rules'
  export budget and method cap, list any old word still written and every
  leftover with its external constraint, and fix what misses. The parent
  session reviews against the same list.
- The rules above, and what counts as a reason to leave something, are settled
  before a step starts. If one changes mid-step, stop that step and restart it
  with the new rule rather than relaying the change into it.
- Tests go through interfaces only. A test that seeds internal state is
  rewritten against the interface. If the interface can't reach that state,
  the test is deleted (Q56).

## Suggested order

This is a proposal. Agree it with the user before starting. It lays the
shared foundations and closes the leaks that later steps build on, leaving the
large review-threads reshaping until the modules around it are narrow.

01. **The shared kernel**: `Repo`, `Pr`, `Side` and `Location`, with its
    admission test. Replace the eight copied owner/name checks.
02. **Export hygiene**: fakes only in `<module>.fake`, a layering check that
    every export has an outside user who writes its name, and deleting the
    exports nobody writes.
03. **Settings**: the config file (one read that reports errors, plus
    writing), the log layout, the child-process environment, dismissals as
    verbs and questions, and `TMUX_SESSION` moved to PR windows.
04. **GitHub**: the four roles provided by wiring, wire words turned into
    answers, and GitHub's own rules moved home.
05. **Change detection and the PR event queue**: typed events and
    `REBASE_REASONS` in change detection. Rename the inbox to `pr_event_queue`,
    with typed queued entries and facts in place of wording.
06. **Notifications**: roles with one method per fact, wording and badges
    moved in, and the still-news protocol implemented by review threads and
    the queue.
07. **Agent runs**: every prompt, its four roles, the run ledger, and the
    CLI's command lines handed in by wiring.
08. **Working copies**: the branch-trouble verdict, derived thread paths with
    `base_sha` as the adopted marker, and the board's git reads.
09. **Thread records**: opaque versioned documents, and the per-thread inbox
    renamed to pending decisions.
10. **Review threads**: the five roles, `of(repo, pr)`, methods in place of
    command classes, questions in place of constants, one refusal type,
    `ThreadActivity` typed, a fake with contract tests, and
    `tests/review_threads/internals.py` deleted, its 283 seeded tests
    rewritten through the roles or dropped where no role reaches the state. This is the largest step, so split it into several merges.
11. **The rest**: PR windows' five items and manager lifecycle, one teardown
    with a reason, watcher health as data, per-module archiving for
    `switch-repo`, and the preview moved to its own entry point.

## Open

- Nothing is left unplaced: the CLI's `gh repo clone` went to GitHub's Access
  in step 11, and the git palette's `claude "/rebase-on-main"` to agent runs'
  PR work in step 7.
- Dropping `Review` from review threads' exports only works if the board's
  projection can be written without naming it. Check that in step 10.
- The token-free `git fetch` from `cab0e466` has only been run by the tests.
  The first PR worktree placed live will be its real check.
