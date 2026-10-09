# Whose move a comment thread is

Date: 2026-10-08. Issue #222. Visual version, with today's behaviour below the
target: (private design page) (rule IDs C, S, A,
D, W describe today; T1–T4 the target).

## Problem

On someone else's PR the board said "Waiting on author · You replied" on
threads the viewer never touched: a colleague's unanswered review comment
(#41), the PR description and claude[bot]'s summary comment (#85).

`_answered_state` (`conversation/_domain/apply.py`) puts a reviewer thread in
`waiting_on_reviewer` when its newest comment is by the thread's **opener**,
never asking who the viewer is. A thread with one comment always qualifies, so
every conversation comment and review summary from anyone lands there. It runs
on create, on every reopen, on GitHub unresolve and on the board's Reopen. The
front end prints "You replied" for state `waiting` without looking at the
comments.

Who spoke last is not enough on its own either. After the viewer replies and
the author answers, the answer may be "fixed in abc123", a question back, a
refusal or a 👍, and each needs something different. So the decision is split:
the code supplies the facts, and an LLM reads the thread to decide what it asks
of the viewer.

## Principles

- **Only the viewer can move a thread to Done.** The LLM can at most put it in
  **Assumed done**, which the viewer confirms.
- **The LLM chooses freely given the facts.** The code labels the comments and
  states the facts; it does not narrow or overrule the verdict.
- **Every new comment gets a fresh verdict**, even on a thread the viewer placed
  by hand.
- **Until a verdict arrives, assume it needs you.** A thread with no verdict, or
  whose verdict call failed, sits in My move marked "not yet read".
- **Not confirm offers exactly the LLM's outcomes**, minus Done.

## Outcomes

| Outcome             | Someone else's PR                        | Your PR                      |
| ------------------- | ---------------------------------------- | ---------------------------- |
| My move             | Answered                                 | Ready for you / Needs a look |
| Their move          | Waiting on author                        | Waiting on reviewer          |
| Assumed done        | Assumed done                             | Assumed done                 |
| Not my conversation | Not my conversation                      | (not on your PR)             |
| Later               | Deferred (via the existing Defer dialog) | Deferred                     |

## Someone else's PR

| ID  | Rule                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| T1  | A new comment, a new thread, an unresolve on GitHub, a Reopen on the board, or a wake from Deferred puts the thread in **My move**, marked **not yet read**, and asks for a verdict.                                                                                                                                                                                                                                                                                                                                                                                                                    |
| T2  | The verdict call gets the whole thread, each comment labelled `you`, `PR author`, `colleague` or `bot` (the fixed bot list: claude, codex, copilot, with any `[bot]` suffix), plus: who the viewer is, who the PR author is, who spoke last, whether the viewer has ever commented in the thread, whether the thread @-mentions the viewer, and the thread kind (review thread on a line, conversation comment, review summary, PR description). It answers one of `my-move`, `their-move`, `assumed-done`, `not-mine`.                                                                                 |
| T2a | `my-move` → Answered. `their-move` → Waiting on author. `assumed-done` → Assumed done. `not-mine` → Not my conversation. Anything else, or a failed call → stays My move, not yet read.                                                                                                                                                                                                                                                                                                                                                                                                                 |
| T2b | A verdict for an older comment than the thread's newest is discarded: only the verdict for the newest comment places the thread.                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| T2c | A reply posted through the board moves the thread to Their move at once (the viewer just spoke), then asks for a verdict, which may move it again (an "LGTM, thanks" can become Assumed done).                                                                                                                                                                                                                                                                                                                                                                                                          |
| T2d | Resolved on GitHub still goes to Done, as today.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| T2e | A verdict is asked for when a thread gets a new newest comment. A call that times out, comes back empty or answers anything but a verdict word is asked again on a later tick, 10 minutes after the last ask, up to 3 asks per newest comment; after that the thread stays where it is (My move, not yet read, or Their move after a board reply) until the next new comment. A record on disk from before this change, open or waiting with no verdict for its newest comment, reads as My move, not yet read, and is asked on the next tick, so today's wrong "You replied" cards correct themselves. |

The mention lift (`state_of` turning `mention and waiting` into ready) goes.
Being @-mentioned is one of T2's facts. A mentioned thread keeps its **Reply
and resolve** button.

The card line in Waiting says "You replied" only when the newest comment is the
viewer's; otherwise it names who spoke last, as Answered does.

## Your PR

| ID  | Rule                                                                                                                  |
| --- | --------------------------------------------------------------------------------------------------------------------- |
| T3  | The agent runs on every new comment from someone else, as today. There is no separate verdict call on your own PR.    |
| T4  | A proposed fix → Ready for you, no verdict. A declined run is placed by the classification the agent already reports. |

| Decline classification                                      | Goes to                |
| ----------------------------------------------------------- | ---------------------- |
| `already-done`                                              | Assumed done           |
| `acknowledgement` (new: thanks, 👍, "LGTM", no request)     | Assumed done           |
| `question` (new: asks the author something, no code change) | Needs a look           |
| `unclear`, `needs-human`, `risky`, `out-of-scope`           | Needs a look           |
| run failed or stopped                                       | Needs a look, as today |

`not-a-change` is split into `acknowledgement` and `question`. A record on disk
holding `not-a-change` reads as `question` (the safe side). There is no Not my
conversation on your own PR. Their move comes only from the viewer's own reply,
as today.

A reviewer's new comment on an Assumed done, confirmed or Not my conversation
thread reopens it the way a new comment on a resolved thread does today.

## Assumed done

- Only a verdict (T2a) or a decline classification (T4) puts a thread here.
- **Confirm** moves it to Done on the board only. GitHub is never touched: no
  resolve, no reply, no reaction. The Done card reads "Confirmed".
- **Not confirm** opens a modal listing the outcomes the thread could be in,
  apart from Done:
  - someone else's PR: My move · Their move · Not my conversation · Later…
  - your PR: Needs a fix (queues a fresh agent run) · Needs a reply from me
    (Needs a look, no run) · Their move · Later…
  - Later… opens the existing Defer dialog.
- It counts as done in the PR's next move and in every done count.

## Not my conversation

- Someone else's PR only: a colleague's thread, the PR description, a bot's
  summary, or a thread the viewer commented on but no longer cares about.
- Its card offers **Move…**, the same modal as Not confirm (with My move, Their
  move, Later…), and Resolve where Resolve is offered today.
- It is left out of the PR's next-move counts entirely: neither done, nor
  waiting, nor answered.
- A new comment gets a fresh verdict, so a muted thread can come back.

## Board order

Someone else's PR: Answered → Needs a look → Your review → Local drafts →
Waiting on author → **Assumed done** → **Not my conversation** → Deferred →
Done.

Your PR: the groups of today, with **Assumed done** between Waiting on
reviewer and Deferred.

In the Columns view, Assumed done and Not my conversation go in the Done
column. The top strip counts them as "N assumed done" and "N not mine".

## Out of scope

- The other oddities found while mapping (S2b, S4b, S4c, S6b, A5b, A5c, A7b,
  A8b, C3b on the flowchart). S2b and S4b disappear with `_answered_state`; the
  rest stay as they are.
- Changing which comments get a card (C1–C4).
