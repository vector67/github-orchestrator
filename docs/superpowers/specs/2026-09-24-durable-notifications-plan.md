# Durable notifications — plan

Design: `2026-09-24-durable-notifications-design.md`. Four phases, each merged
and restarted on its own; stop after each for Jeffrey to confirm.

## Phase 1 — the store, the courier, and every immediate notification

1. `notify.swift` takes `--id`, asks `getDeliveredNotifications` first, and
   exits 0 without posting when that identifier is already in Notification
   Centre. `Desktop.announce(badge, title, body, key)` passes it through.
2. `Badge.INFO` and a `GHO Info` app for notifications that are neither a
   problem nor a fix: CI passed, now mergeable, review decision changed, PR
   updated, PR closed, Claude disabled. Problems — unmergeable, Watcher not
   polling, the worktree and `pr_windows` warnings — use `Badge.FAILED`. A
   failed fix or run keeps `Badge.FAILED` in phase 2. CI failed has no banner
   today; adding one is a separate change.
3. A `notifications` package: `Notifications.post(badge, title, body)` writes
   one JSON file per notification to `<data_dir>/notifications/` (tmp, fsync,
   rename). `Courier.deliver()` announces each pending file oldest first,
   keyed by its file name, then removes it; one delivered more than 30 minutes
   after it was posted gets `(from HH:MM)`.
4. Under `--loop` the watcher rests between polls two seconds at a time and
   runs the courier before each rest, so a post waits at most the rest of a
   poll plus two seconds; a one-shot cycle runs it once at the end.
5. Every `desktop.notify` caller posts instead: the inbox alerts
   (`pr_manager/_carry_out.py`, with a badge on `Alert`), `pr_windows`,
   `working_copies`, and the watcher's "Watcher not polling".
6. `Desktop.notify`, `desktop/_notify.py` and the osascript path go.

The in-memory `Announcements` keeps working untouched until phase 2, passing a
fresh key.

## Phase 2 — batches

Fixed three-minute windows kept on disk; the overdue-after-wake rule (wait for
the first poll that starts after the wake); fixes ready and Claude disabled
become batches, Needs You and Failed become immediate posts, made as soon as
`pump_and_schedule` hands back the settled conversations — right after their
record is saved. `pr_manager/_announcements.py` keeps only that translation.
The courier asks haiku through `AgentRuns.summarize`, adapted in the wiring so
`notifications` imports nothing but the desktop. The watcher passes the
courier when it last woke (a rest step that took over 30 seconds, or the
process starting) and when the last completed poll started; a dry run delivers
nothing.

## Phase 3 — seen on the board

`seen_at` on the conversation record; `POST /api/conversations/{key}:seen`
written straight to the record, outside the etag; the front end sends it from
rail and board-card clicks, Prev / Next ready and `n`/`p`/`j`/`k`. Fix-ready
staleness at send time.

## Phase 4 — comment banners

The watcher's thread diff hands back each new comment (thread key, comment
id, author, body, created_at, kind); the watcher posts a comment item with its
thread action, skipping `gh_account`'s own. Fix state and reply staleness are
read at send time, after the PR's pending `thread-activity` has been drained
(at most 60 seconds). One haiku call per banner for the gists, answered on one
line split by `||` because `AgentRuns.summarize` hands back only the first
line. `Badge.COMMENTS` and a `GHO Comments` app. Nothing is gathered on the
first poll of a PR, when every comment on it looks new.
