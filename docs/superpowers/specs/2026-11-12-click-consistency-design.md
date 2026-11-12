# Click consistency: design

Issue #366. Every clickable control on the board should be predictable: **the
same words and the same look mean the same action, and one action has one
name.** Today a button's label does not say whether it acts at once, opens a
dialog, reaches GitHub or starts an agent run; the same word ("Resolve",
"Confirm", "Close", "Bring back") does different things in different places;
and one action carries up to six names.

The rules below were settled in two rounds: 26 questions answered one at a
time, then a clickable walkthrough of 21 scenarios on captured board pages,
reviewed over four versions until every scenario was approved. Where the
walkthrough overturned an earlier answer, the walkthrough wins, and the rule
says so.

## Rules

01. **Same words, same action.** Two controls that show the same words do the
    same thing, and one action carries one name everywhere. The one stated
    exception: a dialog's submit button may repeat the label of the button that
    opened it ("Send review" opens a dialog whose submit is "Send review").

02. **Two glyphs, each with one meaning.** A small window icon after the label
    means the click opens a dialog. A four-point AI star means the click starts
    an agent run. A button that does both shows both, star first. Every dialog
    opener gets the window icon, a plain yes/no confirmation included, except
    the red are-you-sure of rule 03. A button carries the star whether the run
    starts at once or after its dialog.

03. **Red means destructive, and asks first.** A red button opens a plain
    are-you-sure (title, one sentence of consequence, the red action's own
    label as submit, Cancel) and carries no window icon. The red buttons:
    Stop (an agent run), Drop (an agent's question), Close PR #N, Take over.
    Reject is not red: it keeps its dialog with the optional reply, and the
    window icon.

04. **Nothing problematic without a way back or a question.** An action that
    can be reversed acts at once and its toast offers the reverse by name
    (Bring back, Unresolve on GitHub, Reopen PR #N, Convert to draft, Hand
    back, Leave out of review). An action with no way back asks first. A reply
    you typed yourself is not problematic: posting it is the check.

05. **A button behaves the same every time.** No button opens a dialog only
    sometimes. Three stated exceptions, each kept from today:

    - Confirm on the last open mention of a held PR opens the hold warning
      ("Back on hold" / "Resume this PR"), because you have to see that the PR
      goes back on hold. That Confirm carries the window icon.
    - Request change, and the mention's Ask the agent, ask "Run the change in a
      visible session?" until you tick "Remember my choice", then act without
      asking (`request-session-ask.gts`). Answering an agent's question works
      the same way. All three share the one Agent sessions setting
      (`services/request-session.ts`), so remembering a choice in one
      remembers it for the others.
    - The Ready for review dialog's Assign reviewers opens the Assign reviewers
      dialog on top of it (`ready-confirm.gts`). This is the only dialog that
      opens another.

06. **Underline only goes somewhere.** Underlined text is a link that navigates
    (Open the Board, New draft, On the board, See in Diff, Prev / Next). Every
    action is a button. Today's underlined ghost actions (Defer, Steer, Resolve,
    Full screen, a dialog's Cancel) become quiet filled buttons.

07. **Ticked boxes show a tick.** A checkbox that is on shows a tick mark, not
    only a filled square.

08. **Bring back undoes the last move.** It returns the card to the state it
    was in before the move: after Mark as done from Waiting, Bring back returns
    to Waiting, not Ready. The toast's Bring back and the card's own Bring back
    do the same thing. Bring back after Reject, or after a landed fix, re-runs
    the agent from scratch, because the worktree went with it, so there it
    carries the star.

09. **Stop waiting.** A card waiting on someone else's reply offers Stop
    waiting, which brings it back to Ready. It is not called Bring back,
    because it is not undoing a move of yours.

10. **Confirm means "do what the agent proposed".** The card says what that is,
    in the agent's own line above the footer: its reasoning first, then
    `Agent proposal: <what Confirm does>`. For example, "This comment is simply
    Anna thanking you and not asking for anything." then "Agent proposal:
    skip". Or "Every line item now goes through in_units(), which is the
    conversion the comment asked for." then "Agent proposal: resolve the thread
    on GitHub and put 👍 on Mei's reply". The separate "Claude suggests" line
    and the "Addressed" heading go. The author's Confirm acts at once with
    Bring back in the toast. The reviewer's opens a dialog with the GitHub
    steps ticked, any of which you can untick.

11. **Resolve always reaches GitHub.** Every "Resolve" resolves the thread on
    GitHub, through a dialog with an optional reply and no resolve tick box.
    Finishing a card on the board only, with nothing sent to GitHub, is its own
    button, **Mark as done**, which acts at once. The undo of Resolve is
    **Unresolve on GitHub**. The reviewer's Reopen, which already unresolves on
    GitHub (`apply.py` `_unresolves_on_github`), takes that name too.

12. **GitHub posts act at once and show that they are going.** Post now, a
    reply and a reaction post on click. While the post is in flight the card
    shows "Posting to GitHub…" in place of its buttons, until GitHub has it
    (the pending-states design's `data-pending`, lasting until the fact). Then
    the card shows the next state's buttons.

13. **One Reply per thread.** "Reply to <name>" sits by the comment it answers,
    never in the footer's button row.

14. **Use the agent's words.** Where the agent wrote a reason (a declined
    fix), the reply dialog offers "Use the agent's words" above the reply box,
    as `decide-dialog.gts` does today.

15. **Names.** One name per action, sentence case:

    - Hold / Resume (both views).
    - Mark as done (board only).
    - Bring back (all six of today's names: Bring back to Ready, Undefer,
      Reconsider, Un-resolve, Reopen when it does not touch GitHub, Bring back).
    - Move (Not confirm, Move…).
    - Defer (Defer until …).
    - Send back for rework (Disagree — try a fix anyway).
    - Release (Release now).
    - Leave out of review (Leave out).
    - Save draft (Save as local draft, Create draft).
    - Reply to <name> (Reply).
    - Back to the wall (Back to the board, where it goes to the wall).
    - Summarise (Rerun).
    - Check all threads for fixes (the dashboard's Check for fixes).
    - Open draft (the review dialog's Edit).
    - Start a steered session (Send back for rework's submit when its
      visible-session box is ticked).
    - Plain "Close" stays for panels and full screen. Only the PR close names
      its object: Close PR #N.

    Each dialog's submit repeats its opener's words in sentence case ("Defer",
    "Reject", "Not fixed", "Assign reviewers"). The exceptions keep today's
    words: Ready for review's "Mark ready anyway" / "Mark it ready", and the
    hold warning's "Back on hold" / "Resume this PR". Cancel and × may write to
    the server when they cancel something queued (the commit timeline's queued
    reset).

## Controls, place by place

In the tables, ⧉ stands for the window icon and ✦ for the AI star (rule 02).

### Thread footer, author

| State                 | Buttons, left to right                                                                                                | Notes                                                                                                                                                                                                                                                                      |
| --------------------- | --------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Fix proposed          | Accept ⧉ (primary), Send back for rework ✦⧉, then on the right Resolve ⧉, Mark as done, Defer ⧉, Reject ⧉             | Accept's dialog shows the reply that will be sent above the commit message. Reject drops the fix and its worktree; Bring back after it carries the star.                                                                                                                   |
| Agent working         | Stop (red), Defer ⧉                                                                                                   | Stop asks "Stop the agent on this comment?"; afterwards Try again ✦.                                                                                                                                                                                                       |
| Waiting               | Stop waiting, Mark as done, Resolve ⧉, Defer ⧉                                                                        |                                                                                                                                                                                                                                                                            |
| Assumed done          | Confirm (primary), Move ⧉, Resolve ⧉                                                                                  | Agent line per rule 10.                                                                                                                                                                                                                                                    |
| Declined              | Send back for rework ✦⧉, Resolve ⧉, Defer ⧉                                                                           | Resolve's dialog offers Use the agent's words.                                                                                                                                                                                                                             |
| Agent asks a question | The agent's options as answer buttons and Other (`question-answers.gts`), then on the right Defer ⧉, Drop (red, last) | Drop asks "Drop the agent's question?". It drops the question and deletes the agent's worktree. The thread goes back to the state where no agent has run on it, with Write a fix ✦, Resolve ⧉, Mark as done, Defer ⧉. Defer is its own button, never a choice inside Drop. |
| Done                  | Bring back                                                                                                            |                                                                                                                                                                                                                                                                            |

### Thread footer, reviewer

| State              | Buttons                                                                     | Notes                                                                                                                                                             |
| ------------------ | --------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Author answered    | Resolve ⧉ (primary), Not fixed ⧉, Move ⧉, Defer ⧉                           | Resolve's dialog: optional reply, a ticked "Put 👍 on the newest reply".                                                                                          |
| Assumed done       | Confirm ⧉ (primary), Move ⧉                                                 | Dialog ticks: resolve on GitHub, 👍 on the reply.                                                                                                                 |
| Mention            | Reply and mark as done ⧉ (primary), Ask the agent ✦⧉, Mark as done, Defer ⧉ | Ask the agent runs the session chooser (rule 05), then comes back as a proposal with Accept and the rest.                                                         |
| Local draft        | Add to review, Post now, Discard                                            | Add to review ↔ Leave out of review. Post now per rule 12, then the waiting state's Resolve ⧉, Move ⧉, Defer ⧉. Discard's undo is Bring back, to the local draft. |
| Resolved on GitHub | Unresolve on GitHub                                                         | Rule 11.                                                                                                                                                          |

### Dashboard and wall

| Control                       | Behaviour                                                                                                            |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Open the Board                | Underlined link.                                                                                                     |
| Hold / Resume                 | Toggles at once.                                                                                                     |
| Carry on ✦                    | Starts the agent again on its last conversation.                                                                     |
| Ready for review ⧉            | Today's dialog, listing what is outstanding, with Assign reviewers ⧉ inside (rule 05). Toast undo: Convert to draft. |
| Assign reviewers ⧉            | Submit "Assign reviewers".                                                                                           |
| Dismiss ⧉                     | The until-choices dialog, on the dashboard and on the wall row.                                                      |
| Close PR #N (red)             | Asks "Close #N on GitHub?". Toast undo: Reopen PR #N.                                                                |
| Take over (red)               | On someone else's PR. Asks "Take over #N?". Toast undo: Hand back.                                                   |
| Check all threads for fixes ✦ |                                                                                                                      |
| Release ⧉                     | A frozen worktree. Asks first: there is no way back.                                                                 |
| Wall row                      | Hold and Dismiss ⧉ on hover or keyboard selection, as today.                                                         |

### Elsewhere

| Place                         | Controls                                                                                                                     |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Board strip                   | New draft (link); Send review · N ⧉, submit "Send review".                                                                   |
| Diff, a local draft on a line | Edit (opens the box in place), Ask the agent ✦ (opens a session straight away), Add to review, Discard, On the board (link). |
| Diff, the new-comment box     | Cancel (quiet), Ask the agent ✦, Request change ✦⧉ (rule 05), Save draft, Add to review (primary).                           |
| Commit timeline               | Reset to origin ⧉ asks in a dialog naming the commits it drops; the in-place Reset / Cancel goes.                            |
| Git palette                   | Push acts at once. Force push is its own row ⧉ that asks first.                                                              |
| Settings                      | The Harvest timer always toggles; a "Set up Harvest" link shows when the extension is missing.                               |

## To build

- The two glyphs, and the window icon and star on each control above.
- Unresolve on GitHub for the author's Resolve (the reviewer's exists).
- Reopen PR, Convert to draft and Hand back, each as a toast undo.
- The agent's line under an assumed-done thread: the agent's reason, then the
  proposal derived from what Confirm will do.
- "Posting to GitHub…" for Post now, replies and reactions until GitHub has
  them.
- The red are-you-sure for Stop, Drop, Close PR and Take over.
- Drop's new behaviour: no wake-condition form, the thread back to its
  no-agent state.
- Stop waiting, and Bring back returning to the state before the last move.
- The renames under rule 15, Reply moved out of the footer, and the underline
  rule.

## Open

- Reset to origin's place in the commit timeline is a guess: the preview could
  not show a diverged branch.

## Out of scope

The agent's question card's answer buttons (#363) and the split proposal's
cards (2026-11-10) are already built in their own designs. This spec only
names and marks their buttons by the rules above.
