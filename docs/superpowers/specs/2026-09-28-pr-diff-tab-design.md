# The PR's diff tab and anchoring by selection

Settled with the user in a grilling on 2026-09-28. The draft composer's anchor
form (file, from line, line, side) goes. A draft is anchored by selecting lines
in the pull request's diff, drawn the way GitHub's "Files changed" draws it, in
two places: a new **Diff** tab in the PR view, and the right of the board's
draft panel.

## What the diff is

1. **Merge base to head**, what GitHub shows (`git diff <merge-base> <head>`).
   The merge base comes from `resolve_pr_base`, the one the enrol check already
   uses, so the diff drawn and the anchor check cannot disagree. No commit
   picker.
2. **The base is fetched** where the head already is, so `origin/<base>` is
   always there to resolve against.
3. **`GET /api/pull-request/diff`** answers the same `Diff` shape the proposal
   diff answers (`files` of `FileChange`, their `hunks`, each line's kind and
   old and new numbers), `base` the merge base and `head` the head. The OpenAPI
   record and the contract tests follow.

## Anchors mirror GitHub

4. **Only lines inside a hunk can be anchored.** Lines revealed by expanding
   context are drawn but cannot be selected.
5. **A range may cross sides.** A draft carries `start_side` beside `side`
   (`LEFT`/`RIGHT`; `before`/`after` on the CLI, `--start-side`). A draft with
   no `start_line` has no `start_side`; a record on disk without one reads its
   `side`. It is carried by the domain, the draft store, `DraftBody`, the
   conversation's `anchor` (a posted thread's from GitHub's `startDiffSide`),
   `thread draft`, the agent prompt's usage line, and the comment GitHub is
   sent by send-review and post-now.
6. **Both ends in one hunk.** GitHub refuses a range whose start is in another
   hunk than its line. The in-diff check checks the start on `start_side`, the
   line on `side`, and that both are in one hunk; the selection cannot be
   dragged out of the hunk it began in.

## Drafts in the review can be edited

7. **`edit-draft` accepts an enrolled draft** and it stays in the review. When
   the anchor changed, the enrol check runs on the new one; an anchor off the
   diff refuses the edit with the check's code and message, and the draft keeps
   its old text and anchor. The typed copy survives in the drafts service. The
   note under an enrolled draft reads "In your review. Changes go out when you
   send the review." The send-review dialog's Edit opens the draft without
   withdrawing it. A draft on its way to GitHub stays locked.

## The Diff tab

08. **A fourth tab, Diff**, after Board, Dashboard and Terminal; key `4`; route
    `pr.diff`; the URL's `file` query names the file scrolled to.
09. **Laid out like GitHub.** A file tree on the left with a filter box, folders
    with one child folded into one row, each file with its status (added,
    modified, removed, renamed) and a count of the conversations on it; clicking
    a file scrolls to it. Every file stacked on the right: a header with a
    collapse chevron, the path, a copy-path button, `+added −removed`, and "N
    outdated" linking to the board when outdated threads sit on the file.
10. **Big files start collapsed**: binary, or more than 400 lines added and
    removed. Clicking the header opens them.
11. **Expanding context** is the proposal diff's: up, down, all, read from
    head.
12. **Selecting.** Hovering a hunk line shows a `+` in its gutter. Clicking a
    line number or the `+` selects the line; dragging or shift-clicking extends
    the selection within the hunk, across − and + lines. The comment box opens
    under the selection's last line: "Commenting on lines −19 to +20", the
    textarea, Cancel and Save draft. Esc or Cancel closes it; typed text stays
    in the drafts service's new-draft copy. Saving creates the draft and the
    tab stays where it is.
13. **Conversations show inline, read-mostly**, under their anchor's last line:
    posted threads with their comments (resolved ones folded behind "Show
    resolved"), fix proposals as their thread, drafts as cards. Each card links
    to its conversation on the board. The one action in the tab is **Edit** on
    a draft, open or in the review: the card becomes the comment box, the
    draft's lines selected and re-selectable. Outdated threads are not drawn;
    they are the file header's count.
14. **The diff is read again** when the PR's `head_sha` changes on the poll.
15. **No Viewed checkbox**: nothing would keep it.

## The board's draft panel

16. **The left keeps the comment**: the textarea, one line naming the anchor
    ("changes.py −19 to +20"), Save or Create draft, and the note.
17. **The right is the draft's file's whole diff**, the same component as the
    tab, scrolled to the selection, re-selectable the same way. Other
    conversations on the file are gutter markers, not cards. A file button over
    it switches to another changed file. A new draft opens on the file list
    until a file is chosen. A draft whose lines are no longer in the diff shows
    its file with "These lines are no longer in the diff. Select new ones." A
    locked draft's selection cannot change.
