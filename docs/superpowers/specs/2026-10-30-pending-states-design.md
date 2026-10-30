# Pending states: design

Issue #227. The board shows a write it has sent and not yet had answered in one
way everywhere. Today it shows it in thirteen ways, or not at all: an edited
draft keeps its old text until the server answers, and Add to review, every PR
control, reset to origin and the terminal launchers show nothing while they
wait.

## Decisions

01. **Where it lives.** A write the page has sent is a local operation in
    `services/store.ts`, merged into the entity's `operations[key]` at send time
    with state `sent`, beside the server's `pending` and `running`. PR-level
    verbs get the same on the PR's record, which absorbs `pr-controls.sent`.
    `takeOutcome` replaces the local operation by id. A refusal turns it to
    `refused` with the reason. Component flags (`sending`, `saving`, `acting`,
    `summarising`, `checking`, `writing`, `moving`, `going`, …) and
    `board.acting` go.

02. **What derives from it.** `thread.ts` `outstanding()` and `busy()` treat
    `sent` like `pending`, so rows, panels, cards and the composer lock follow.
    The word is `decisions.inFlight(kind)`; verbs without one get one there.

03. **The look.** One attribute, `data-pending`, on the element that stands for
    the entity, and one CSS block: opacity .6, a dashed edge where the element
    has an edge, its controls held, and one word in the element's meta or chip
    slot (or on the pressed button). Success drops the attribute and runs the
    existing `[data-decided]` flash.

04. **The spinner.** On the long waits below, a 12 px ring in `currentcolor`
    sits before the word **from the moment the write is sent**: no delay. It
    turns on `--motion-spin`, which is 0 under `prefers-reduced-motion` (a
    still ring) and under `data-still`. The long waits: fetch the branch, reset
    to origin, the git palette's push, pull and rebase, setup Check, setup Start
    watching and Move aside, send review, close PR, ready for review, opening a
    terminal session or asking the agent, harvest Prepare. Other writes get no
    ring.

05. **Lasting until the fact.** For send review, close PR, ready for review and
    a session the drain opens, `data-pending` lasts until the server fact flips
    (the operation settles, the dashboard shows the PR closed or ready, the
    session is listed), not until the 202.

06. **Shown early.** Only what the user typed or ticked: a draft's body, a
    reply's text, the mark-read checkbox. Columns, chips and phases wait for
    the server.

07. **Refusal.** The element returns to its last confirmed values and carries a
    red line (`data-refused`) with the refusal's detail and a way back in
    ("Edit again" reopens the box with the typed copy, which `drafts.copies`
    and `composer.words` already keep). Toasts stay only where the element has
    left the page (close, dismiss).

08. **Waiting covers writes.** `http.sent()` registers in `asking`, so the
    existing `Waiting` note names a stuck write after ten seconds, as it does a
    read.

09. **The draft edit.** Save closes the box at once; the card shows the new
    text with `data-pending` and "Saving"; confirmed flashes; refused shows the
    old text, the red line and "Edit again".

10. **Kept as they are.** Reads (the "Loading …" lines and `Waiting`), server
    agent states (queued and working banners, row squares, the live dot), the
    setup page's own page states beyond its buttons, `markSeen` and `sawTour`.

11. **Removed.** The unstyled `provisional` flag (`store.ts`, `rail-row.gts`).

Set aside: a grey veil (covers the text just written), a spinner on every
write (they answer in about 0.2 s, so it would flicker), a flag per component
(the status quo), fully optimistic rows (guesses server rules and jumps back),
and a separate pending service (a second index keyed by entity).

The mockup, with file:line for every place today, was published for review as
an artifact; its decisions are the ones above.
