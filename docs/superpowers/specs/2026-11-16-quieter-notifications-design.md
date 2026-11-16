# Quieter notifications: design

Issue #412.

## Why

Three weeks of desktop notifications on one live install, two instances, were
matched against what the operator did next on the board, on GitHub and in their
agent sessions. Of 1,793 notifications shown:

- 1,339 were "Watcher not polling". Nearly all were DNS, TLS or EOF errors that
  cleared on the next cycle, yet the text told the operator to check `[[repos]]`
  and `gh_account`. One outage posted one a minute for eleven hours, on both
  instances at once.
- 234 were PR status changes: CI passed, mergeable, unmergeable, updated,
  closed, no longer relevant and review decision. Almost none led to an action.
  "Unmergeable — blocked" only ever meant a review was still required.
- About 42 came from a deployment bot whose login is not in the bot list, so
  its comments were treated as a person's. One agent question about such a
  comment was posted 11 times in four hours.
- 46 were exact same-day copies of an earlier notification. Each post gets a
  fresh key, so nothing stops a repeat. A run that kept failing posted "Run
  failed" 17 times in one day.
- 236 of the 424 PR-level notifications were about PRs the operator did not
  write, where they had reviewed once or twice.
- Titles said "PR #3" or "#368" with no repository and no PR title, so the
  operator could not tell which PR a banner meant without opening it.

The operator ignores most notifications as a result. A notification should
interrupt only when a person or an agent needs the operator. Everything else
stays on the board, which already shows it.

## Rules

### 1. Watcher outages

- A failed cycle whose cause is a network fault never posts. Network faults
  are: no such host or other DNS failure, a TLS or connection error, an EOF or
  reset, an HTTP 5xx, a timeout, and GitHub's secondary rate limit. The hub's
  banner already shows a watcher that is not polling.
- A failed cycle whose cause the operator must fix posts once, when the
  consecutive count reaches 3, and not again until a successful cycle resets
  the count. These causes are: HTTP 401 (bad or expired credentials), a 403 or
  404 that is not rate limiting (a repo the account cannot see), and a full disk
  (`Errno 28`).
- Its text names that cause and what to do about it. The `[[repos]]` and
  `gh_account` advice appears only for a 403 or 404.
- An error that matches neither list is treated as an operator fault, so an
  unknown failure still reaches the operator once.
- The classifier reads the error text the cycle already has. It must not use
  `CycleSaving._fix()` as the signal: that runs `gh repo view`, which fails
  during a DNS outage too.
- "Mentions search failed" follows the same rules.

### 2. Delete the status notifications

`News.changed` and everything that calls it only to notify go. Nothing is
posted for CI passed, became mergeable, became unmergeable, pushed since review,
review decision changed, closed or no longer relevant. Change detection keeps
feeding the board and the agent queue exactly as before.

### 3. Bots and the operator's own comments

- `vercel` and `copilot-pull-request-reviewer` join the bot list in
  `domain.py`.
- "Comment needs your call" is not posted when the comment's classification is
  an acknowledgement, or when its author is the instance's own GitHub account.

### 4. Send each thing once

- An agent question is posted at most once per (PR, thread, question text).
- "Fix failed" and "Run failed" are posted at most once per (PR, kind) per
  local day.
- What was sent is recorded in a small file in the data dir, so a restart does
  not send it again. Entries older than a few days are pruned when the file is
  written.
- The record lives inside `notifications/` and is checked where the post is
  made. The notifier's identifier is not used for this: `notify.swift` exits
  without posting while an older banner with the same identifier is still
  showing, so a stable identifier would swallow a later, different state.

### 5. Other people's PRs

On a PR the instance's account did not write, comment batches are not posted,
except for a person's reply in a thread that the account started. @mentions
keep going through the mentions pipeline and are not affected.

### 6. Say which PR

Every notification about a PR names it as `repo#N` (`pr.short`) in its title,
never `PR #N` or a bare `#N`, and carries the PR's title where the instance
knows it.

## Out of scope

- A per-PR "your turn" notification for a human review round on the
  operator's own PRs, and a once-a-day morning ping listing stalled important
  PRs and reviews owed. These come after a week of living with this change.
- Wiring PR importance into notifications. It belongs with the morning ping.
