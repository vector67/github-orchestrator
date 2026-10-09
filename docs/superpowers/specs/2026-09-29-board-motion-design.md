# Motion on the board

Settled with the user on 2026-09-29, from the Board Motion Review artifact
(private design page; the answers are in its
`responses` collection) and the grilling after it. The board moves when it
changes while you are looking at it, so you can follow what changed. When you
come back from other work you expect a still page and to reorient yourself;
nothing replays or marks what changed while you were away.

Motion covers the user's own actions too. The rule the review proposed, that
only changes made by the system animate, was rejected.

## The wall and the rail share their parts first

1. **The wall's rows lose their squares** and take the rail's coloured left
   edge, the `inset` box-shadow that `.rail-row[data-square=…]` draws today.
   One rule set draws the edge for both lists, so the move animation below is
   written once. The wall keeps its table and its columns. **Done**
   (`ee413074`).

2. **Edge per wall section:**

   - Needs you: yellow, as Ready for you.
   - Working: grey, as In progress.
   - Waiting on others: a lighter grey.
   - On hold: none, a hairline only.
   - An alarm row takes the rail's `failed` red. The grilling didn't cover this
     one; it follows the rail.

   **Done** (`ee413074`).

3. **Group headers share one style.** The count sits right after the name, as on
   the wall (`.wall-group .c`), not right-aligned as the rail's `.group-count`
   was. **Done** (`ee413074`).

4. **"Moved here N ago" becomes "moved here".** It shows for 10 seconds, then
   fades out. It gets no special case for hidden tabs: come back with 6 seconds
   left and it shows for 6. **Done** (the commit that records this).

## Timing

5. **Durations are tokens on `:root`:** `--motion-slide` 220ms,
   `--motion-slide-far` 260ms (across columns), `--motion-flash` 1.2s (today's
   `.diff-slot[data-updated]`), `--motion-in` 150ms, `--motion-out` 120ms,
   `--motion-collapse` 180ms. Easing `cubic-bezier(.2,.7,.2,1)`; fades use
   `ease` or `ease-out`. **Done** (`5c0bc63c`).
6. **A move is a FLIP:** measure each keyed row, let Glimmer re-render, then
   animate `transform` from the old place to the new one. A row that moved also
   gets the colour flash. **Done** (`d957a7e5`).
7. **Reduced motion follows the OS only.** Under `prefers-reduced-motion` a move
   draws instantly and keeps its flash. Fades stay; slides, collapses and the
   live dot's pulse go. There is no in-app toggle. **Done** (`5c0bc63c`).
8. **Tests zero every duration** through one switch the test build turns on. It
   covers the CSS tokens and the durations the FLIP and collapse code passes to
   `element.animate()`, because a CSS variable doesn't reach those. Tests that
   read `scrollTop` or `isVisible()` right after an action keep working because
   nothing is left in flight. **Done** (`5c0bc63c` and the commit that records
   this).

## What moves

09. **Rail regroup:** a card that changes group slides to its new place and
    flashes. When a group empties, its header goes and the rows below slide up.
    **Done** (`d957a7e5`).
10. **Wall section change:** the row slides to its new section and flashes, and
    "moved here" fades in. **Done** (`23c419aa`).
11. **Columns:** a card that changes column travels across (`--motion-slide-far`)
    with a ring flash, instead of vanishing from one column and appearing in the
    other. **Done** (the commit that records this).
12. **Accept, and every decision from the panel:** the button's label changes
    at once ("Accepting…"). When the server answers, the panel draws the
    decided card's new state at once and stays on it; `n` moves on, as today. The decided card flashes green, then slides to its new group.
    The toast waits until that slide has finished, plus 0.5s, so the eye isn't
    pulled two ways at once. **Done** (`48cb0d35`, `fdebf669` and the commit
    that records this).
13. **Toasts:** enter with opacity and `translateY(-4px)` over `--motion-in`,
    and leave with opacity over `--motion-out`. The rest then close the gap with
    a FLIP. **Done** (the commit that records this).
14. **Discarding a local draft in the diff:** the card's height and opacity go
    to 0 over `--motion-collapse`, then it's removed. The lines below follow the
    height. **Done** (the commit that records this).
15. **j and k:** the selection highlight slides to the new row over 180ms, on
    both the rail and the wall. **Done** (the commit that records this).

## What changes behaviour, with little or no motion

16. **The "board server not answering" banner** shows only after two failed
    polls in a row and hides on the first good one. It fades in over
    `--motion-in`, and the wall's dim changes over 200ms. **Done** (the commit
    that records this).
17. **A resolved thread you're reading stays open** when a poll brings in its
    resolution. Its header gains a "Resolved on GitHub" chip with a flash, and
    the chevron (08172de8) folds it, over `--motion-collapse`. A resolved
    thread drawn fresh starts folded, as it does today. **Done** (the commit
    that records this).
18. **The live dot pulses for 5 seconds** when work starts or the state changes,
    then holds steady. WCAG 2.2.2. **Done** (the commit that records this).
19. **Claude's output keeps your place.** Scrolled up, the lines on screen stay
    where they are. New lines are added below, lines are trimmed above, and
    `scrollTop` moves by the height trimmed. A "N new lines ↓" pill jumps to the
    end. At the end it follows the stream, as today. **Done** (the commit that
    records this).
20. **A terminal session whose command exits keeps its screen.** Its text dims
    to 45% over 200ms, and a bar says the exit code with a Close button. The
    session leaves the list only when you close it, and then it fades out over
    `--motion-in`. This reverses the part of 7ae44269 that removes the screen on
    exit. **Done** (the commit that records this).
21. **j and k keep the selection in view** with an instant
    `scrollIntoView({ block: "nearest" })`, with no smooth scrolling. **Done**
    (the commit that records this).

## Out

- Holding `/` for key hints stays as it is (review item 10, skipped).
- Holding a list still under the pointer. f6b1a642 did this on the old
  server-rendered board, and 1ad1fbeb removed it with that board. It stays out.
- Replaying or marking what changed while you were away.
- View Transitions and animation libraries. CSS and `element.animate()` cover
  every item above.

## Order

1. Merge the wall's and the rail's edges and headers (1–4). No motion yet.
2. The tokens, the reduced-motion rules and the test switch (5–8).
3. FLIP moves with their flashes: rail, wall, columns (9–11).
4. Decisions and toasts (12–13).
5. Collapse: draft discard and resolved thread (14, 17).
6. j/k: the sliding highlight and keeping the selection in view (15, 21).
7. The banner, the live dot, output scroll and terminal exit (16, 18–20).
