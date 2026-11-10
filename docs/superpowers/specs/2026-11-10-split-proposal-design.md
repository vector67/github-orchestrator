# Split proposal: design

Issue #339. A reviewer writes "this isn't part of PROJ-12, can it go in a
separate PR?" or "this alert isn't in the acceptance criteria". The code is
already in the pull request. None of today's three proposal kinds fits: a
`commit` changes this PR, a `reply` only answers, and a `ticket` files work
that does not exist yet. Every one of them leaves the code where it is.

`split` is a fourth kind. It takes the code out of this PR and carries it
into a new PR on the same repository, under this PR's ticket or a new one,
and tells the reviewer where it went. Cross-repository splits are out of
scope.

## Decisions

01. **When the agent splits.** The thread prompt describes split as a fourth
    way to finish a run, beside the commit, reply and ticket paths. It covers
    every "not in the acceptance criteria", "move it to another PR" and "put it
    under another ticket" comment, and the agent judges whether the code
    deserves its own PR or should simply go. A wrong pick costs a Rework. The
    out-of-scope instruction "change no code" gains an exception: when the
    out-of-scope code is already in this PR's diff, split it out instead of
    proposing a ticket. Split carries no `Classification`; like `commit`, it
    is a run that ends with commits.

02. **What the run produces.** The agent commits the removal against this
    PR's latest head, and builds the new PR's branch with the code and any
    extra asks the comment made (a rename, say). It picks the new branch's
    base per case: `main` when the code stands alone, stacked on this PR's
    branch when it depends on it, with a one-line reason. It reports through
    a new report command carrying the branch, the base and its reason, either
    "same ticket" or a ticket draft (project, title, body, as `ticket` does
    today), and the reply.

03. **One proposal, up to four parts.**

    | Part               | Present                                  | Buttons              |
    | ------------------ | ---------------------------------------- | -------------------- |
    | Ticket             | only when the agent drafted a new ticket | Accept, Edit, Rework |
    | Changes to this PR | always                                   | Accept, Rework       |
    | New PR             | always                                   | Accept, Rework       |
    | Reply              | always                                   | Accept, Edit, Rework |

    When the new PR reuses this PR's ticket there is no ticket part, and the
    new PR waits on nothing. Rework on a part reworks only that part.

04. **Accepting.** Each part's Accept runs its work straight away: file the
    ticket, push the removal here, open the new PR, post the reply. A part
    whose prerequisite has not run is queued, not refused, and says what it
    waits for: the new PR shows "waiting for ticket" until the ticket is
    filed, and the reply shows "waiting for new PR" so it can name the PR.
    **Accept all** accepts every part not yet accepted and stays available
    until every part has run. The proposal counts as accepted when every part
    has run.

05. **After a part runs, it locks.** It shows only its result (ticket key and
    link, the commit, the new PR's link, the posted reply) and loses its
    buttons. Further changes go through the new PR's own review or a new
    thread.

06. **Reject.** Reject on the whole proposal is offered only while no part
    has run. Once any part has run, Reject is gone; Accept all stays.

07. **Ending.** When the last part has run, the thread ends as the other
    kinds do: it resolves on GitHub when `resolve_on_land` is set, then
    lands. The new PR reaches the board the way any PR the viewer authors in
    a watched repository does; nothing links the two PRs beyond the reply and
    the new PR's body.

08. **Edit uses today's modal.** Edit on the ticket and on the reply opens
    the same dialog the ticket proposal uses today, and saves without
    accepting. Today the dialog only opens from Accept, so an Edit that saves
    without filing is new.

09. **The look: cards.** Each part is its own card in the panel's work area,
    with a kicker naming the part, its content (the ticket box, the file
    rows, the reply quote) and its own buttons. A queued or running part
    shows the board's existing queued / working banner. A part that has run
    collapses to a one-line result. Accept all sits in the footer with the
    thread-level actions.

10. **The diffs.** The right-hand pane holds two accordions, "Changes to this
    PR" and "New PR", both collapsed by default. Each diff looks exactly as
    the diff pane does today, full-screen button in its top-right corner
    included.

11. **Creating the PR is a skill.** The orchestrator ships a generic
    `create-pr` skill beside `rebase-on-main`, installed the same way. It
    writes a detailed body with a reviewer guide, follows the repository's
    `.github/pull_request_template.md` when there is one, links the original
    PR and thread, and names the ticket. It holds nothing
    specific to one organisation.

12. **Per-repository settings.** Two optional keys in a `[[repos]]` entry,
    documented in the README beside `has_tests`:

    - the skill that creates the new PR, defaulting to `create-pr`, so a repo
      can name its own team's PR skill;
    - `draft`. When unset, the orchestrator says nothing and the skill
      decides (`create-pr` opens a draft). When set, it wins: after the skill
      returns, the orchestrator flips the PR to draft or ready to match.

## Out of scope

- Splitting into another repository.
- Undoing a part that has run.
- Linking the two PRs on the board beyond the reply and the PR body.
