# Commits on the diff tab: design

Issue #145. The diff tab shows the whole pull request today. This adds a way to
read it one commit at a time, a graph of the branch to pick a commit or a range,
and a setting that shrinks or hides the commit UI. Every situation below was
drawn as a mockup and approved as drawn on 2026-10-22.

## Words

- **The PR's commits**: what `GET /pull-request/commits` returns, oldest first,
  from the fork point to the head (step 1, `f8a8d367`). Only these can be picked.
- **Base commits**: commits on the base branch. Context only, never pickable.
- **Fork point**: where the PR's commits leave the base. After main is merged
  in, it is the merged main commit.
- **Read**: a mark the user puts on one of the PR's commits.
- **Your review**: the user's latest submitted review on the PR, and the commit
  it was made on.

## Decisions

01. **The stepper is the default commit UI.** A bar above the diff:
    `‹ Prev [` · `Commit n of N · <sha> <subject> · <author> · <age>` ·
    a **Read** checkbox · a **Timeline `t`** button · `Next ] ›` (yellow).
    Under it a row of pips, one per PR commit: green when read, yellow with a
    black outline for the current commit, grey otherwise. `[` and `]` move to the
    previous and next commit. The diff and the file tree show only the current
    commit: `/diffs/{parent}..{sha}`.
02. **It opens after your review**: on the first commit you haven't read that
    comes after the commit your review was given on. With no review, a review
    whose commit is not among the PR's commits, or nothing unread after it, it
    opens on the first commit you haven't read, or on the last commit when all
    are read. The note (decision 4) shows only when it opened after your review.
03. **Read state is kept on the server**, per PR, keyed by sha, with each read
    commit's subject kept beside it so decision 16 can match rewritten commits.
    Ticking or unticking the Read box writes it through the board API's operation
    path; the store holds it once.
04. **The "picked up" note** sits under the bar, 8px below it, not inside it:
    black border all round, a yellow inset stripe on the left, an **×** on the
    right. Text: `Picked up at the first new commit: <b>N commits</b> pushed since your review on <day date>.` It shows only when you have reviewed and commits
    came after that review. × hides it until the PR's head changes.
05. **Commit box sizing** is a new item in the gear settings menu, opening in place
    to three radio choices, remembered in this browser (localStorage) like the
    theme:
    - **Full** (default): commit bar with Prev, Next, Read and Timeline.
    - **Minimal**: only the pips, as a progress line. No buttons, no text, no
      note. Hovering a segment names its commit (`n of N · <sha> <subject>`);
      clicking it jumps there. `[`, `]` and `t` still work, the timeline opens
      under the line, and it opens on the first unread commit.
    - **Hidden**: no bar and no stepping. The diff is the whole PR unless a commit
      or range is picked in the timeline. The Timeline button moves next to the
      origin/local switch in the diff tab's left column, and the graph opens
      across the top of the diff.
06. **Timeline** (`t`, or the button) opens a branch graph under the stepper;
    pressing again closes it. The button shows pressed while open.
07. **The graph's lanes.** The top lane is the base branch, grey, with small grey
    dots and a `main` label at its tip. The PR's commits sit on the lane below,
    forking off at the fork point with a curve, black. Read commits are drawn
    hollow (white with a black ring), unread ones filled. The stepper's commit
    has a yellow-and-black ring. The range in the diff is a yellow band with a
    white handle at each end. A `head` label ends the PR lane. Short shas sit
    under the dots. A flag `you reviewed <day>` stands between the last commit
    your review saw and the next.
08. **The graph's header** reads `<b>N commits</b> on <branch> · forked from main at <sha>`, adding `, main's tip` when main has not moved, or a yellow
    `<k> behind main` chip and `main's new commits aren't in this diff` when it
    has. Presets on the right: **All**, **Since my review**, **This commit**; the
    active one is yellow. A key under the graph names each dot style, with
    `click a dot for one commit · shift-click or drag the handles for a range`.
09. **Main moved on.** The base lane keeps going past the fork to main's real tip,
    in grey, with a dashed box labelled `<k> commits on main since the fork`.
    Hovering one shows its subject. The diff still runs from the fork point.
10. **Picking.** Clicking a PR dot shows that commit. Shift-click on a second dot
    or dragging a handle picks a range: the bar switches to range mode, a grey
    `range` pill, `<from sha> → <to sha> · N commits · M files`, a
    **Back to stepping** button and the Timeline button. The pips of the range
    turn yellow. The diff and tree show the range as one change,
    `/diffs/{from's parent}..{to}`. Escape or Back to stepping returns to the
    commit you were on.
11. **Merged main into the branch.** A merge is a diamond on the PR lane, with a
    thinner grey curve coming down from the main commit it pulled in. Stepping
    skips merges by default; its pip is striped. When the stepper does stop on a
    merge (the skip box unticked, or picked in the timeline) the bar adds a grey
    `merge` pill, and the diff shows only what the merge changed on its own
    (its conflict fixes), with a grey info line above the diff:
    `<b>N files came in from main</b> and are hidden. This merge changed M file on its own: … ` and a **Skip merges when stepping** checkbox (localStorage). A
    range across a merge leaves out what came from main. The header says
    `N commits and 1 merge · last synced with main at <sha>`, and the behind
    count runs from the merged main commit.
12. **Stacked on another PR.** When the base is another PR's branch there are three
    lanes: main, the base PR's commits in blue (blue-fill dots, a blue
    `#<n> <branch>` label that opens that PR), and this PR forking off it. The
    header names the base: `base is #<n> <branch>, which is based on main`. The
    stepper counts only this PR's commits.
13. **Far behind.** When main is more than about 20 commits ahead, its run between
    the fork and its last two commits collapses into a pill `⋯ <k> more`;
    clicking it opens the list in a popover, still context only. The fork and
    main's tip stay real dots, with their dates under them. A commit inside that
    run that another lane leaves from (origin's lane when the worktree has
    diverged, the ghost lane's old fork, a stacked base's) stays a real dot with
    its short sha under it, and splits the run into one pill per stretch:
    `⋯ <k>` before it and `⋯ <k> more` for the last. That lane leaves from that
    dot. The server sends each such commit with its place among main's commits
    since the fork (`base_forks`), beside the capped `base_commits` (#146,
    decided 2026-10-23).
14. **A long PR.** Past about 20 commits the dots shrink to small ticks, shas show
    only at the band's ends and the stepper's commit, and a day row under the
    lane marks where each day starts. The pips become a thin bar, one segment per
    commit.
15. **Unpushed local commits.** With the diff on **local**, commits the worktree
    has not pushed extend the PR lane past an `origin` flag as dashed hollow dots
    on a dashed line, ending in a dashed `local` label. The stepper adds a yellow
    `not pushed` pill on them. On origin they are not drawn.
16. **Rebased since your review.** When the commits your review saw no longer
    exist, they stay on the graph as a dashed grey ghost lane hanging off the old
    fork, below the PR lane, with the review flag on them and a line naming their
    old shas. The PR lane forks from the new point; both forks are labelled.
17. **Diverged from origin** (#146, decided 2026-10-23). When the worktree's head
    and origin's are each missing from the other's commits (origin rewritten, the
    worktree holding the older branch), the local view draws two lanes under main.
    Origin's commits that the worktree lacks sit on a lane of their own, forking
    from where they leave main or the shared commits, drawn hollow and grey,
    never pickable, ending in a dashed `origin` box. The worktree's commits keep
    the black PR lane below, forking from their own older fork; it is the lane the
    stepper walks, solid rather than dashed, ending in the dashed `local` box, with
    no origin flag. The header reads `<b>N commits</b> in the worktree · forked from main at <sha> · origin has M other commits from <sha>` and a yellow chip
    `diverged from origin · N here, M on origin`, without the behind chip. The
    stepper's pill on those commits reads `not on origin`. The key adds the hollow
    grey dot only when origin's lane is drawn. Origin's view is unchanged. On the
    wall such a worktree's chip reads `diverged from origin`, with no numbers, in
    place of `N unpushed`, which stays for a worktree only ahead of origin.
18. **Reset to origin** (#146, decided 2026-10-23). A `Reset to origin` button
    sits beside the diverged chip. It asks on the page, never in a browser
    dialog: `Reset the worktree to origin? Its N commits that aren't on origin will be dropped.` with **Reset** and **Cancel**. Reset posts
    `operations:reset-to-origin`, which fetches origin and runs
    `git reset --hard` to origin's head of the branch in the PR's worktree, with
    no backup (`PrCheckout.fetch(…, reset=True)`). It is refused, changing
    nothing, while an agent works in the worktree (`agent-working`) or it holds
    uncommitted changes (`uncommitted-changes`); the refusal shows under the
    header as `Not reset: <why>`. Refused because an agent is working, it offers
    **Reset when the agent finishes**, which asks `Reset the worktree to origin when the agent finishes? Its N commits that aren't on origin will be dropped, and so will any commits the agent makes before then.` and posts
    `operations:queue-reset-to-origin`. The queued reset is kept beside the
    thread records, so it outlives a restart, and the manager runs it the moment
    the agent's run ends, through the same fetch and hard reset, unless the
    worktree then holds uncommitted changes. While it waits the chip area reads
    `Reset queued until the agent finishes` with a **Cancel**
    (`operations:cancel-reset-to-origin`); afterwards the page says
    `Reset to origin when the agent finished.` or `The queued reset didn't run: <why>`, with a × that forgets it. The dashboard carries it as
    `system.reset_to_origin`.
    A new commit whose subject matches a read ghost's counts as read and carries
    `≈ read` above it. Ghosts cannot be picked. **Since my review** picks only
    the commits with no match. The header reads `now forked from <new>, was <old>`, and the note (decision 4) says `<b>Rebased since your review</b> (force-pushed <day date>). K of your read commits were rewritten onto newer main and matched by message; <b>M are new</b>.`

## Spacing

New UI only; the board's existing chrome stays as it is. Spacing uses
4, 8, 12 and 16px, with more space around a group than inside it. Buttons are
about 8×12px padding at a 12px font. Line height 1.2 for titles, 1.5 for body
text. The note sits 8px under the bar.
