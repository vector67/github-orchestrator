# Review board: rows on the left, one comment open on the right

Date: 2026-09-06. Branch: `feat/board-split-panel`. Status: agreed in
conversation, being built.

## What this is for

The board exists so one person can read what reviewers said about a PR and
react to it without leaving the page. This change is about making that easier
to do: see what needs a decision at a glance, read one comment at a time without
the page moving underneath, take every action from the same place, and always
be able to tell why a card is where it is and why it changed.

Two of those pull against each other. "What needs me is at the top" means cards
move when their state changes. "Don't disturb me while I read" means nothing
moves while I am reading. The current board can do neither: cards are appended
in comment order and never reorder, and every card carries its whole body, so
any reflow is a big one.

The resolution is to split reading from scanning. The left side becomes a list
of short rows that is allowed to reorder, with rules about when. The right side
becomes a panel that shows one comment in full and does not change unless you
change it.

## The shape

- A fixed-height shell, two panes, no page scroll. Closed, the left pane is a
  centred column that looks like today's board with shorter cards. Open, the
  column slides left and the panel fills the rest of the window.
- Each row is two lines: status, author, anchor and age, then a one-line gist
  of the comment written by a small model. A third line appears only when the
  card has something to report about what happened after a decision.
- Rows sort into three bands the user never sees named: cards wanting a
  decision, cards an agent is working on, cards that are done. Inside a band,
  comment order.
- The client owns the order. The server sends rows with a band and a sort key
  every two seconds; the client merges them into the list it already shows.
- Reordering waits while the pointer is over the list, and cards that want to
  move pulse until it is allowed. Content on a row always updates at once.
- Clicking a row or pressing `j`/`k` opens it in the panel. A decision closes
  the panel and the row reports what happened next.

## Shell and layout

The `<body>` is `100dvh` with `overflow: hidden`. Inside it, `#shell` holds two
children, `#left` and `#panel`, side by side. Neither the page nor `#shell`
scrolls; `#rows` and `#panel` scroll on their own.

`#left` is a flex column. `#left-header` (the PR heading, the disabled notice,
the status counters, the error banner) is fixed at the top and does not scroll.
`#rows` fills the rest and scrolls. Closed, `#left` is the same width the board
has today, centred, and `#panel` is not displayed. Open (`body.open`), `#left`
shrinks to 28rem over 200ms, `#shell` stops being centred, and
`#panel` appears beside it and fills the remaining width, full height. The
slide is the open animation. It exists because the list starts centred.

The panel's left border is the selected row's right border continued. The
selected row drops its own right border, and a small element `#panel-notch`
sits on the panel's left edge at the selected row's vertical position, painted
in the page background with the row's border colour on its top and bottom
edges, so the row reads as opening into the panel. The notch tracks the row: it
moves when the row moves or `#rows` scrolls, and clamps to the panel's top or
bottom edge when the row scrolls out of view. Position is recomputed on
`#rows` scroll, on every reorder, and on resize, throttled through
`requestAnimationFrame`.

The status counters stay per-status, worded as today. Bands are never named
anywhere in the chrome. That is deliberate. Naming them would be one more
thing to read, and the ordering is meant to be inferred, not taught.

## Rows

`#rows` is `<ul role="listbox">`. Each row is `<li role="option" id="c-<id>" aria-selected data-band data-sort>`. The client creates and owns the `<li>`;
the server renders only its inner HTML and the client sets the attributes from
the JSON beside it. This is what lets a row keep its client-side classes
(`selected`, `pending-move`) across a content update without any attribute
merging.

`render_row(record, repo, pr, intent)` in `review_board.py` renders the inner
HTML; `render_card` goes. Row content, in order:

1. `div.row-head`: the status pill, the author, the comment-type label, the
   `path:line` anchor linking to the comment on GitHub, and the age. Same
   scanning order as today's card header.
2. `p.gist`: the summary line (see "The gist").
3. `p.aftermath`, only when there is something to say:

| status                        | pill            | third line                                                                        |
| ----------------------------- | --------------- | --------------------------------------------------------------------------------- |
| `queued`                      | queued          | `waiting for an agent` (+ ` (attempt 2 of 3)` after a retry)                      |
| `working`                     | working         | `agent running 2m 14s`                                                            |
| `ready`                       | ready           | none                                                                              |
| `ready` with `reason`         | failed to land  | `could not land: <reason>`                                                        |
| `committed`                   | committed       | `committed, not pushed`                                                           |
| `approved`                    | landed          | `a1b2c3d · pushed · replied` (the settled line)                                   |
| `approved` with `reply_error` | needs you       | `reply failed: <reason>`                                                          |
| `skipped`                     | skipped         | `skipped: <reason>`                                                               |
| `failed`                      | failed          | `failed: <reason>`                                                                |
| `rejected`                    | reworking       | `rework session running`                                                          |
| `dismissed`                   | dismissed       | none, or `declined · replied on GitHub` / `replied on GitHub` when a reply posted |
| `removed`                     | comment deleted | `comment removed from GitHub`                                                     |
| `unreadable`                  | unreadable      | `this card's record could not be read`                                            |
| any, with an intent on disk   | unchanged       | `approving…`, `dismissing…`, etc.                                                 |

A settled card carrying the `comment_deleted` flag appends ` · comment removed from GitHub` to its third line. Long `reason` strings are truncated to one line
with `text-overflow: ellipsis`; the panel has the whole text.

A record that is only `{comment_id, status}` (`unreadable`, or `removed` written
by the repair path) renders `comment #<id>` in the anchor's place, no gist, and
a third line saying what happened: `this card's record could not be read` or
`removed from GitHub before this board could read it`.

Rows carry no folds, no buttons, and no text long enough to want selecting.
That is what makes reordering them safe.

## Ordering

Three bands, as integers the client sorts on:

| band               | statuses                                                                                                                                        |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| 0, wants you       | `ready`, `ready` with `reason`, `committed` with no intent on disk, `skipped`, `failed`, `approved` with `reply_error`, `removed`, `unreadable` |
| 1, an agent has it | `queued`, `working`, `rejected`, and any card with a decision intent on disk                                                                    |
| 2, settled         | `approved` that pushed and replied, `dismissed`                                                                                                 |

The intent rule is the one entry that is not a status lookup, and it does two
jobs. A `ready` card you just approved drops to band 1 the moment the intent is
written, because something else is now acting on it. A `committed` card whose
push failed and whose intent has been cleared rises to band 0 on its own,
because nothing is acting on it and it wants you. The intent is the single fact
that says "someone else has this".

`band_of(record, intent)` lives in `review_board.py` beside `_display_status`
and reads the displayed status, so an `approved` record that never pushed bands
as `committed` exactly as it displays.

Inside a band, `(created_at, comment_id)`, as `list_candidates` sorts today.
The server sends it as one string the client compares lexicographically:
`f"{created_at or '~'}|{comment_id:020d}"`. `created_at` is
`%Y-%m-%dT%H:%M:%S.%fZ`, so string order is time order, and `~` sorts after
every digit, so a record with no `created_at` lands last in its band.

There are no band headings, gaps or rules. The list is uniform and the sort is
the whole mechanism.

## The list endpoint and the reconciler

`GET /rows` returns JSON:

```json
{
  "summary": "<counters html>",
  "rows": [
    {"id": 123, "band": 0, "sort": "2026-09-06T10:00:00.000000Z|00000000000000000123", "html": "<div class=\"row-head\">…"}
  ]
}
```

Rows arrive in `(created_at, comment_id)` order. The client sorts by
`(band, sort)`. `summary` replaces the counters in `#left-header` on every
poll. Everything GitHub wrote is escaped on the server before it reaches
`html`; the client inserts it with `innerHTML` and never builds markup from
reviewer-authored text itself.

The client polls `/rows` with `fetch()` every two seconds and reconciles by id:

- A row on screen whose `html` differs gets its `innerHTML` replaced and its
  `data-band` and `data-sort` updated. Its `class` and `aria-selected` are the
  client's and are left alone. Content updates are never deferred.
- A row not on screen is created. If the list is held, it is appended at the
  bottom with `pending-move`; otherwise it is inserted at its sorted position.
- A row on screen that is absent from the response is removed. If it was
  selected, the panel closes and the error banner says the card is gone.
- If the list is not held and any row's current index differs from its sorted
  index, the DOM is reordered with a FLIP animation. If it is held, every such
  row gets `pending-move` and nothing moves.

htmx is not used for `/rows`. htmx swaps an element wholesale; this endpoint
needs a merge into a list that must not be disturbed. htmx stays for the
panel, the diff folds, the elided-row expander and every POST.

After any reorder, if the selected row is outside `#rows`' visible area, `#rows`
scrolls so the row sits one row-height in from the nearest edge. Only the
selected row is chased.

## The hold

While the pointer is over `#rows`, rows do not change position. Their content
still updates. The hold is released when:

- the pointer leaves `#rows`;
- the pointer has not moved for 10 seconds;
- the hold has lasted 20 seconds, whatever the pointer is doing;
- the user presses `j` or `k`.

Releasing applies every pending move at once, animated, then clears
`pending-move`. A tick every 500ms checks the idle and ceiling clocks. The
pointer resting on the panel never holds the list.

A row with `pending-move` wears an amber border that pulses on a 1.6s loop.
Amber is neutral here: a card becoming ready and a card dropping to settled
both pulse the same colour, and the pulse means only "this is in the wrong
place and will move". Red was rejected because it is the failure colour on this
board. Under `prefers-reduced-motion` the border is amber and still.

A brand-new comment arriving while held is appended at the bottom, where it
pushes nothing, and pulses like any other pending move. When the hold releases
it moves to its place.

## Selection and keys

Two pieces of client state: `selected`, the id of the open row or `null`, and
`cursor`, the id the keys last stood on. The panel is open exactly when
`selected` is not `null`. Closing the panel sets `selected` to `null` and
leaves `cursor` where it was.

- `j` from closed opens the row after `cursor` in the displayed order, or the
  first row if there is no cursor or the cursor's row is gone. `k` from closed
  opens the row before it, or the last row. `j`/`k` from open move to the next
  or previous row and switch the panel to it. Both release the hold first, so
  the row the key lands on is where the list says it is.
- Clicking a row opens it, or switches the panel to it. Clicking the selected
  row again, pressing Escape, clicking empty space in `#rows`, or the panel's
  `×` closes the panel.
- `a`, `r`, `d` act on the open comment only. With the panel closed they do
  nothing.
- `?` opens the shortcut legend from anywhere; it floats centred over the
  whole shell. Any key closes it.

Panel fetches from `j`/`k` are debounced at 150ms: holding `j` walks the
cursor without fetching a panel for every row it passes, and only the row it
settles on is fetched.

The legend and the empty-board text are rewritten: `j`/`k` open and walk the
comments, `a`/`r`/`d` act on the open one, Escape closes it.

## The panel

`GET /panel/<id>?theme=` returns the panel as server-rendered HTML,
`<section id="panel-body" data-status data-intent data-updated>`:

1. A sticky header: the status pill, author, comment-type label, anchor, age,
   and a `×` button.
2. When the status is `queued`, `working` or `rejected`, a banner: "an agent is
   working on this, so what you see here can change".
3. When the record carries `comment_deleted`, a notice: "GitHub no longer has
   this comment". For a `removed` card the notice is a bold heading, "GitHub
   removed this comment", and the content below it is dimmed.
4. The comment in its PR diff context, exactly as `_comment_in_context` renders
   it today, or the plain body for a comment not on a line of the diff.
5. The fix diff as a lazy `details.diff` fold with the copy-hash button, when
   there is a `candidate_sha`.
6. Reason, rebase conflict, decision error, tests, agent note, land notes, as
   the card renders them today.
7. The action footer, or the queued-intent line in its place.

The panel does not render the gist. It shows the comment.

While a panel is open the client polls. For an in-progress card (`queued`,
`working`, `rejected`) it fetches `/panel/<id>` whole every two seconds, and
restores the panel's `scrollTop` after each swap; the banner is what warns
that this happens. For every other card it fetches `GET /panel/<id>/state`
every two seconds, which returns

```json
{"status": "ready", "intent": null, "updated": "…", "comment_deleted": false}
```

and re-fetches the whole panel only when any of those differ from the
`data-*` attributes the panel carries. The comment and the diff are fixed for a
given candidate, so there is nothing honest to gain from redrawing them.

Both panel routes run the existence check before they render, so an
in-progress card polling the whole panel is checked exactly as a settled card
polling `/state` is. For any record that has a `comment_type`, is not `removed`
or `unreadable`, and does not carry `comment_deleted`, the server asks GitHub
whether the comment still exists, memoised for 60 seconds per
`(repo, pr, comment_id)`, so it costs one `gh` subprocess per open comment per
minute. The check lives in `github_pr_agent_manager/presence.py` and is one
`gh api` GET on the path for the record's type: `/repos/{repo}/pulls/comments/{id}` for `review`,
`/repos/{repo}/issues/comments/{id}` for `issue`,
`/repos/{repo}/pulls/{pr}/reviews/{id}` for `review-summary`. A `GhError`
whose message carries `HTTP 404` means gone. Any other failure means unknown,
and unknown changes nothing: a network blip must never mark a comment removed.

When the comment is gone: an unfinished record (`queued`, `working`, `ready`,
`skipped`, `failed`, `rejected`, `committed`) transitions to `removed` with
`comment_deleted: true`; an `approved` or `dismissed` record only gains
`comment_deleted: true` and keeps its status. The next state poll reports the
change and the panel re-renders.

## Decisions

The four verbs keep the single `<dialog>` and the `htmx:confirm` interception.
The dialog is modal over the whole shell. When the user confirms, the panel
closes at once, before the request is answered: `selected` becomes `null`,
`cursor` stays on the row.

`POST /candidate/<id>/decide` returns the row's JSON (`{id, band, sort, html}`)
instead of a card, so the row shows `approving…` in the frame the response
lands. The buttons use `hx-swap="none"`, and an `htmx:afterRequest` listener
reads the JSON and merges the row. A 409 returns the same shape and the client
shows today's "that card had moved on" banner. Everything that happens after
the decision (the landed SHA, a push failure, a reply that could not post)
reaches the user through the row's third line, and a failed step leaves the
card in band 0.

Approve on a `removed` card skips the reply on purpose and records
`reply_note: "no reply: the comment was deleted"`. Attempting the reply would
fail, drop the card back into band 0 wearing `reply failed`, and say something
went wrong when nothing did. `_approve` reads `comment_deleted` for this,
because by the time it replies the status is `committed`, not `removed`.

## Deleted comments

Two facts about a deleted comment, kept apart because they mean different
things.

`removed` is a status. It means the comment was deleted while the card still
wanted work: the fix is unlanded or undecided. It is reachable from the seven
unfinished statuses and has edges to `committed` and `dismissed`. It sorts
into band 0 because it wants a decision, and it offers `dismiss`, plus
`approve` when there is a `candidate_sha`: the worktree holds real work that a
deleted comment should not silently bin, and `dismiss` is the verb that
reclaims the branch and worktree. The pill reads `comment deleted`.

`comment_deleted` is a boolean flag on the record, like `declined`. On an
`approved` or `dismissed` card it means someone tidied the comment away after
the work was done, and nothing is wrong. The card keeps its status, its landed
line and its place in the counters. `declined` is the precedent: a fact that
qualifies a settled card does not rewrite what the card is. The `removed`
transition also sets the flag, so a `removed` card that is later approved
still knows its comment is gone.

`ALLOWED_TRANSITIONS` gains `REMOVED` as a key and as a member of the seven
unfinished statuses' sets. Every status-keyed table in `review_board.py`
gains an entry, `render_summary`'s `counted` tuple gains `(REMOVED, False)`,
and the stylesheet gains `.status.removed`. `_STRIP_CLASSES` is indexed with
`[status]`, so leaving it out raises.

### The stale-client repair

`list_candidates` skips files that do not exist, so a record deleted from disk
simply vanishes from the board. The only way a client asks for a record that
is gone is that it was already showing the row when the file went. That is the
one case `GET /panel/<id>` has to handle, and it handles it by rebuilding:

1. Take `_repair_lock`, a single module-level lock. Repairs are rare, so one
   lock for all of them is simpler than one per comment and costs nothing
   visible.
2. Re-check for the record; another thread may have just rebuilt it.
3. Ask GitHub for the comment by id, trying the three endpoints above in
   order, since the type is not known without the record.
4. If one answers, build the comment fields from it and call
   `open_candidate`, which cuts the worktree and writes a fresh `queued`
   record with its gist. Author is `user.login`; body is `body`; a review
   comment gives `path` and `line` (falling back to `original_line`) and type
   `review`; an issue comment has no path and type `issue`; a review has no
   path, `submitted_at` for its time and type `review-summary`. Return that
   record's panel. This is slow and that is acceptable.
5. If all three answer 404, write `{comment_id, status: "removed", comment_deleted: true}` and return its panel. The comment's text existed
   only in the record that was deleted, and GitHub no longer has it either;
   the row and panel say so.
6. Any other `GhError` returns 503 with a message; the client shows it in the
   banner and closes the panel.

`dismiss` must tolerate a record with no `worktree` or `branch`, because the
minimal record has neither and `dismiss` is its only way off the board.

A dismiss on a card carrying `comment_deleted` has no thread to reply on. The
panel carries `data-comment-deleted`, and the dialog hides its reply box for
such a card so nothing can be typed that cannot be posted; `_closing_reply`
refuses a reply aimed at a deleted comment the way it refuses one aimed at a
type with no thread, in case one arrives anyway. `decline` is not offered on a
`removed` card at all: its whole point is the reply.

## The gist

`common/summarize.py`:

- `fallback_summary(body) -> str`: the first non-empty line of the body that
  is not a code fence, truncated to `SUMMARY_MAX_CHARS` (60) with an ellipsis.
- `summarize_comment(body, path, line, model) -> str | None`: runs
  `claude --print --model <model>` with the prompt on stdin, `stdin` only, no
  shell, `env=claude_env()`, `timeout=SUMMARY_TIMEOUT` (20s). Returns the
  first non-empty line of stdout, stripped and truncated to 60, or `None` on
  a non-zero exit, a timeout, or empty output.
- `SUMMARY_WORKERS = 4`. A module constant, not a config key. Nothing wants to
  tune it yet.

The prompt asks for one line of at most 60 characters, lowercase, no trailing
period, saying what the reviewer wants changed, and gives it `path:line` and
the body. The result is a description of what the reviewer wants, not of the
code: "db connection is never closed", "wants the close in a finally".

`common/claude_env.py` holds `claude_env()`, the one place that strips
`ANTHROPIC_API_KEY` from the environment so a run bills the OAuth
subscription. `build_claude_run` and `summarize_comment` both call it. It is
the one thing about spawning `claude` that must not drift between the two.

`summary_model` is a new config key, default `"haiku"`, beside `claude_model`.
`config.py` exposes it as `SUMMARY_MODEL`. `claude_enabled = false` means no
gist spawn from either path; every row shows its fallback line and the board
works with worse labels.

The gist runs inside `open_candidate`, which takes `summary_model: str | None`.
With a model, it writes the record with `summary = fallback_summary(body)`,
spawns the gist, and updates the field through `candidates.set_fields`. With
`None` it writes the fallback and stops. Both callers pass the model:
`materialize_candidates` from the config it is handed, `cli candidate open`
from `SUMMARY_MODEL`, and the CLI prints one line to stderr saying it is
waiting for the model before it calls. Hooking the gist into `open_candidate`
rather than beside each caller is what keeps a candidate opened from a skill
from showing its fallback forever.

`materialize_candidates` runs its `open_candidate` calls in a
`ThreadPoolExecutor(max_workers=SUMMARY_WORKERS)`, and
`create_candidate_worktree` takes a module lock so the `git worktree add`
calls stay serial while the gists overlap. Concurrent ref updates in one
repository can collide on `packed-refs.lock`; the gists are the slow part and
the only part worth overlapping.

`candidates.set_fields(candidates_dir, repo, pr, comment_id, **fields)` is
load, update, save. It is a plain field write and that is fine here: every
writer holds the loaded dict for microseconds except `candidate_land`, which
runs long after creation and never touches `summary` or `comment_deleted`.
The worst case is one lost gist, which shows as a row wearing its fallback
line. It is used for `summary` and for `comment_deleted`.

Gist runs are not appended to `runs.jsonl`. `cli runs` answers "what has this
cost me" about fix work, and forty 300-token gists would drown that number.
A gist is never regenerated: the stored `body` is already a snapshot that an
edited comment never updates, and a gist fresher than the body it labels
would be a lie in the other direction.

## Server died

Two consecutive failed `/rows` polls trip the takeover, as `LOST_AFTER` does
today. `#rows` and `#panel` are hidden, the `#server-died` notice stands under
the frozen header, every decision is disabled, and the keydown handler answers
nothing. The header stays so the window still says which PR's board this is.
The notice reads exactly as it does today. The next `/rows` poll that answers
puts everything back, including the panel that was open.

## Motion

FLIP moves at 220ms ease-out through the Web Animations API, measured with
`getBoundingClientRect` before and after the DOM reorder. The open slide and
panel entrance at 200ms. The pulse a 1.6s ease-in-out loop on `border-color`.
Under `prefers-reduced-motion: reduce`, moves apply instantly, the slide is
instant, and the pulse is a still amber border, because the border is
information and the motion is not.

These numbers are starting points. They get tuned in front of the real board
once it exists.

## What this retires

- `heldStill`, the `paused-note`, and the `beforeRequest`/`beforeSwap` guards
  that paused a card's poll while a fold was open or text was selected. Rows
  have no folds, and the panel never redraws what you are reading.
- `refetchMovedCards` and the `span.card-state` fingerprints on `/summary`.
  The `/rows` poll is the fingerprint.
- `/board`, `/board/new?seen=`, `_sentinel` and append-only ordering.
- `/summary` as a route; the counters ride on `/rows`.
- `GET /candidate/<id>` as a card fetch, and per-card `hx-get` polling.
- `render_card`, `_slotted`, `.card-slot`, the `collapsed` set and the fold
  round-trip, `details.card-fold` and `details.folded-card`.
- The tests that pin each of those.

`render_diff_fragment`, `render_context_fragment`, the elided-row expander and
`handle_post`'s decision handling stay.

## CLAUDE.md

The review board section is rewritten for the new mechanisms, and one rule
changes. "The POST handlers do no git work" stays true. It gains a sibling:
`GET /panel/<id>` may rebuild a missing record, cutting a worktree and writing
a record, because nothing but the client that was showing the row knows the
record is gone, so no other actor could do it. That amendment is written into
CLAUDE.md with that reason rather than left as an exception someone finds
later. The pre-existing lost-update window in `candidate_land` (a record
loaded before a push and saved after it) is documented as out of scope; it
does not touch the fields this change adds.

README's review-board section is updated for the panel, the keys, and the
deleted-comment states.

## Testing

Python, through the existing suite:

- `band_of` for every status, with and without an intent; the sort string,
  including the missing-`created_at` case.
- Row rendering per status against the table above, the minimal-record row,
  the `comment_deleted` suffix, escaping of reviewer-authored text.
- `/rows` JSON shape and ordering; `/panel/<id>` contents per status; the
  `/panel/<id>/state` fingerprint; the presence check's memo, its 404 and its
  non-404 paths with `gh_api` stubbed; the repair path, alive and dead, with
  `gh_api` stubbed and the worktree cut recorded.
- `REMOVED` in `ALLOWED_TRANSITIONS`; `_approve` skipping the reply on
  `comment_deleted`; `dismiss` on a record with no worktree; `set_fields`.
- `fallback_summary`; `summarize_comment` with `subprocess.run` stubbed (the
  suite never spawns `claude`); the `summary_model` config key; `open_candidate`
  writing the fallback then the gist; the CLI's waiting line.
- The POST returning row JSON, and 409's shape.

Node, through the two required tests: `node --check` on the script, and the
stub-DOM test extended to drive the reconciler (insert, update, remove,
reorder), the hold (enter, leave, idle, ceiling, key release), `pending-move`
marking, `selected`/`cursor` rules including `j`/`k` from closed, panel open
and close paths, the debounce, and the takeover. `element.animate` and
`getBoundingClientRect` are stubbed; motion itself is not tested. Both tests
keep `@pytest.mark.no_replay`.

New tests that spawn git run live first, then `make record`, and the recording
is committed with the change.

## Delivery

One branch. Commits are small enough that each passes the suite on its own,
and the sequence proves itself to a reader: the gist and its plumbing, the
`removed` status and flag, the server's row and panel endpoints, the shell and
the script, the retirements, then the docs.

## Not in scope

- A periodic sweep for deleted comments. The `since`-windowed poll cannot see
  deletions and a full-list fetch per cycle is the cost that window exists to
  avoid.
- A "new comments" chip while held. A new row appends at the bottom and
  pulses.
- Regenerating gists, or a config key for gist concurrency.
- Band headings, gaps or any other marker of the grouping.
- Per-comment repair locks.
- The `candidate_land` lost-update window.
