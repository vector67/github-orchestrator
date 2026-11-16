# Quieter notifications: plan

Carries out [the quieter notifications spec](../specs/2026-11-16-quieter-notifications-design.md).
The spec is the decision. This plan sets the order of the steps, how each one
is judged, and the choices the spec left to the build. Rule numbers (1–6) are
the spec's. Issue #412.

## How to work

- Every change follows `.claude/skills/normal-workflow`. Load `tdd` for
  anything that changes behaviour and `refactor` for reshaping.
- Each step gets its own branch in its own worktree, cut from local `main`. It
  is merged and restarted before the next step starts. The user approved
  running the steps straight through, without stopping between them.
- Run `make lint-python` and `make test-python` before each commit, under
  `timeout`, and report the pass counts. No step touches `frontend/`.
- **Removing a notification needs no new test.** Delete the code and the tests
  that covered it, and stay green. Never add a test that asserts something is
  absent. A commit whose pass count falls names each deleted test.
- **Proof is tests and fakes.** Tests drive `News`, the outbox, the watcher's
  saving and the thread announcements through the existing fakes
  (`notifications/fake.py`, `desktop/fake.py`). Assert what was posted or
  gathered: its badge, title and body. No step writes to a real PR or posts a
  real notification.
- **Wording lives in `notifications/_news.py`** and the batch renderer beside
  it. A notification title or body written in two modules is a miss.
- **Data on disk.** The failure record (`watcher/_failures.py`) already exists;
  read its old form with the empty default in one place. The sent record for
  rule 4 is new and owned by `notifications/`.
- **Codex parity.** Nothing here may depend on which agent ran.
- **Budgets are advisory.** Report `make interface-report` for touched
  packages. Do not split modules to meet a budget.
- **Nothing internal.** Examples use `acme/*`, `octocat` and `PROJ-12`.
- Code carries no comments.
- When the spec leaves a choice open and this plan does not settle it, make it,
  and name it in the report.

## Choices this plan settles

- **Rule 1's classifier is one pure function** from the error text to
  network, operator or unknown, with a table test of real error strings: `gh`'s
  "no such host", "TLS handshake timeout", "unexpected EOF", "HTTP 502", "was
  submitted too quickly" / "secondary rate limit", "HTTP 401", "HTTP 403",
  "HTTP 404", "No space left on device". Unknown counts as operator.
- **"Once per streak"** is decided from the consecutive count already in the
  failure record: post when it reaches exactly 3 and the cause is not network.
  A streak that changes cause mid-way does not post twice.
- **The PR's author** for rule 5 and **the account** for rule 3 come from what
  the snapshot and the instance settings already hold. If the snapshot does not
  carry the PR's author, the step adds it to the snapshot from the data the
  watcher already fetches. No new GitHub call.
- **The sent record** for rule 4 is one JSON file, `notifications/sent.json` in
  the data dir, keyed by a string the post site builds. It keeps entries from
  the last 3 days.

## Steps

### 1. Delete the status notifications (rule 2)

Remove `News.changed`, `_closed`, their callers' notification calls in
`pr_manager/_carry_out.py`, `StatusChange` if nothing else uses it, and their
tests. Change detection, the board and the agent queue are untouched.

### 2. Watcher outages (rule 1)

The classifier, the once-at-three rule and the new wording, for "Watcher not
polling" and "Mentions search failed".

### 3. Bots and the operator's own comments (rule 3)

The two logins in `domain._BOTS`, and the acknowledgement and own-account
filter in `conversation/_threads.py`'s `_announce_settled` or wherever
"needs your call" is decided.

### 4. Other people's PRs (rule 5)

Comment batches on a PR the account did not write are dropped, except a
person's reply in a thread the account started.

### 5. Send each thing once (rule 4)

The sent record and the checks at the agent question, fix failed and run
failed post sites.

### 6. Say which PR (rule 6)

`pr.short` in every PR notification title, and the PR's title in the body or
title where the instance knows it.

### 7. Live check

The coordinator restarts every instance and confirms a clean poll in each
watcher log newer than the restart, and that no notification of a removed kind
is logged as posted after it.
