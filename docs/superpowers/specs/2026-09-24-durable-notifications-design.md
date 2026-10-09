# Durable notifications

Agreed with Jeffrey on 2026-09-24 in a grilling session, after a fixes-ready
banner for widgets#16 was lost: the fix settled seconds before the managers
restarted, and the in-memory batch in
`pr_manager/_announcements.py` died with the process.

## The promise

A notification is never lost unless it has gone stale. It is never repeated,
except when a restart lands in the moment between sending it and recording
that it was sent — and even then the badge app checks Notification Centre for
the same identifier before posting.

## Shape

- Every process that has something to say **posts** it to a store on disk,
  `<data_dir>/notifications/`. Posting never touches the desktop.
- Only the **watcher** delivers. Between polls it rests two seconds at a time
  and runs a courier before each rest; the courier reads the store, sends what
  is due through a badge app, and removes it once sent. If
  the watcher is dead nothing is delivered; that is accepted.
- Each notification or batch has a stable identifier. `notify.swift` posts
  with it and skips the post when `getDeliveredNotifications` already holds it.
- Anything delivered more than 30 minutes after its oldest item was posted
  gets `(from HH:MM)` in its title.

## Immediate and batched

Immediate — delivered on the courier's next tick:

- Needs You, Failed (fix failed, claude run exited non-zero)
- CI passed, CI failed
- unmergeable, now mergeable, review decision changed, PR updated, PR closed
- Watcher not polling
- worktree init timed out / failed, and every `pr_windows` warning (fetch
  failed, worktree still shared, shares a worktree, left on the wrong branch,
  blocked)

Batched — fixed window, not a debounce:

- fixes ready, per PR
- new comments, per PR
- Claude disabled, across every PR

A batch opens with its first item and is due exactly three minutes later.
Anything posted after it is sent opens a new batch. A batch found overdue —
the watcher has just started, or the gap since its last tick shows the machine
slept — waits for the first poll that starts after the wake to finish, takes
in whatever that poll found, and goes out straight after.

## Staleness

Checked against the thread records at send time. An item that is stale is
dropped; a batch whose items are all stale is not sent.

- **Fix ready** is stale once the conversation has any board verb requested
  after the fix became decidable (`operations[*].requested_at > decidable_at`), its fix is no longer proposed, or the user clicked it on the
  board after it became decidable (`seen_at > decidable_at`).
- **Comment** is stale only when the user (`gh_account`) replied on that
  thread after the comment was created — on the board or on GitHub. Clicks do
  not count.
- Immediate notifications never go stale.

`seen_at` is new. The board posts it from explicit selections only — a click
on a rail row or a board card, Prev / Next ready, and the `n`/`p`/`j`/`k`
keys — never from page load, the redirect to the first thread, or refocus. It
is written straight to the record, not through the intent inbox, and stays out
of the contract `Conversation` so a click does not change the etag.

## Formats

Fixes ready — title plus one haiku sentence for every fix together, no
authors line:

```
3 fixes ready on widgets#56
rename the collapse helper, pass submission objects instead of ids…
```

Comments — one line per comment, action first:

```
3 comments on widgets#16 · 2 fixes started
New thread | Fix started | Ada (review comment): "<gist>"
Reopened | Fix queued | Reviewer B: "<gist>"
Reply | No fix | Reviewer B: "<gist>"
```

- Thread action: New thread, Reopened, Reply — decided when the watcher sees
  the comment, from the record it finds (none, a closed state, open).
- Fix state: Fix started, Fix queued, No fix — read from the record at send
  time. Never a reason.
- `(review comment)` flags a review's top-level message. The review's verdict
  only goes out as the immediate "Review decision changed".
- The gist summarises the new comment itself: one haiku call per banner, the
  comment's first words after 60 seconds without an answer.
- The user's own comments never get a line.

Claude disabled — `Claude disabled — skipped events on #56, #16`.

Everything else keeps today's text.
