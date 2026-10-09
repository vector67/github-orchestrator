# Thread verdicts on Jev, with needs-verification

Date: 2026-10-09. Issue #12. Builds on
[the comment-verdict design](2026-10-08-comment-verdict-design.md), whose rules
T1–T4 still hold except where this spec changes them.

## Problem

On someone else's PR the verdict call (`claude --print --model haiku`) put a
colleague's review comment, addressed to the PR author, in Answered about one
time in three. Near-identical comments landed on both sides, and the same
prompt gave different verdicts from one batch to the next.

Rewording the prompt did not fix it. Four variants ran 20 times on each of 16
threads from one real PR (colleague threads and threads the viewer opened):

| Haiku prompt                                         | Colleague threads called not-mine |
| ---------------------------------------------------- | --------------------------------- |
| production, plus "addressed to the PR author"        | about 65%                         |
| replies labelled "replying to" the opener            | about 73%                         |
| people named once, question at the end               | about 45%                         |
| as above, plus the file and lines the author changed | about 40%                         |
| a minimal first-person prompt                        | about 80%, on few runs            |

The same 16 threads, with usernames swapped for stand-ins and URLs removed,
went to Jev (TypeSafe AI's decision model, `jev-1.13.0`) 20 times each:

| Jev form                              | Colleague threads right | Viewer's own threads right |
| ------------------------------------- | ----------------------- | -------------------------- |
| one `choice` over the four verdicts   | 240/240                 | 57/80                      |
| two yes/no questions combined in code | 240/240                 | 80/80                      |

Jev gave the same answer on every run of nearly every thread. Its misses were
on the viewer's own threads answered with a bare "Tackled in <sha>", where its
probabilities were close and its confidence low. A call cost about 500 input
tokens, roughly $0.00002.

## Decisions

- **The verdict on someone else's PR moves from haiku to Jev.** Which form, and
  what instructions and criteria it gets, is settled by experiment against the
  test cases below; see [The form](#the-form).
- **The decomposed form as tried breaks T2.** T2 says the model chooses freely
  and the code does not narrow or overrule it. The two-question tree made
  outcomes unreachable: once the viewer commented it could never say not-mine
  (O10), when the viewer spoke last it could only say their-move (O9b), a
  colleague's "+1" came out my-move (O8), and checking "done" before "asks the
  viewer" lost the question in O7. A decomposed form is acceptable only if it
  passes every test case; the single choice keeps T2 by construction.
- **A fifth outcome, needs-verification, on someone else's PR.** See below.
- **Two changes on your own PR**, from the scenarios: reviewers talking among
  themselves about something other than the PR is Not my conversation (Y10),
  and a someday suggestion wants a ticket proposed, not only a reply (Y9).

## Outcomes

| Outcome            | Someone else's PR        | Your PR                      |
| ------------------ | ------------------------ | ---------------------------- |
| my-move            | Answered                 | Ready for you / Needs a look |
| their-move         | Waiting on author        | Waiting on reviewer          |
| needs-verification | Needs verification (new) | (not on your PR)             |
| assumed-done       | Assumed done             | Assumed done                 |
| not-mine           | Not my conversation      | Not my conversation (new)    |

## Needs verification

On someone else's PR, a thread the viewer commented on goes to
needs-verification when a later comment claims a fix to what the viewer asked
for, or answers the viewer with something the code can confirm ("Yes, see the
test on line 40"). Opus then reads the PR's commits against the viewer's
comment.

| ID  | Rule                                                                                                                                                                                         |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| NV1 | A claimed fix names a commit: Opus checks the named commits (up to five, as the commit check takes today).                                                                                   |
| NV2 | A claimed fix names no commit, or the reply is a bare acknowledgement such as 👍: Opus looks for commits pushed since the viewer's comment that could be the fix.                            |
| NV3 | Whoever claims the fix, the author or a colleague, the check is the same.                                                                                                                    |
| NV4 | Addressed → assumed-done.                                                                                                                                                                    |
| NV5 | Not addressed, or only partly → my-move. The card shows what Opus found missing, so the viewer can say what is still wrong without opening the diff first.                                   |
| NV6 | No commit found that could be the fix → their-move.                                                                                                                                          |
| NV7 | When the viewer has spoken since the claimed fix ("LGTM, thanks"), there is nothing to verify: the verdict stands. The commit check already only reads comments after the viewer's last one. |

Today's commit check (`conversation/_domain/commit_check.py`) covers NV1 and
half of NV5: "not addressed" sends the card back to Answered, and "addressed"
leaves it where the verdict put it. NV2, NV6, the partial result in NV5 and the
visible state are new.

## Test cases

Every row is a case the verdict, and needs-verification where it applies, must
get right. On someone else's PR the viewer reviews Mei's PR, and Sam and Ana
are other reviewers. On your PR the viewer wrote it, and Sam and Ana review it.
"You" is the viewer. Comments are listed oldest first.

### Someone else's PR

| ID   | Thread                                                                                                                                                                                                           | Facts                                      | Expected           |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ | ------------------ |
| O1   | Sam: "I'd drop this"                                                                                                                                                                                             | line thread; you have not commented        | not-mine           |
| O2   | Sam: "Could we register it automatically instead, like the base class does?" · Mei: "Thank you @sam. Done in abc1234"                                                                                            | line thread; you have not commented        | not-mine           |
| O3   | Sam: "@you what do you think, keep the check or drop it?"                                                                                                                                                        | line thread; @-mentions you                | my-move            |
| O4   | You: "This should be a constant."                                                                                                                                                                                | line thread; you spoke last                | their-move         |
| O5b  | You: "This should be a constant." · Mei: "Good call, fixed in abc1234 — moved it to settings.py."                                                                                                                | line thread; names a commit                | needs-verification |
| O6   | You: "Drop the retry loop, the client already retries." · Mei: "I'm not sure it does on 502s — the client only retries on timeouts. Do you still want it gone?"                                                  | line thread                                | my-move            |
| O7   | You: "This breaks on empty input." · Mei: "Fixed in abc1234. Could you check the new test covers what you meant?"                                                                                                | line thread; names a commit                | my-move            |
| O8   | You: "This should use the shared validator." · Sam: "+1, agree"                                                                                                                                                  | line thread; colleague spoke last          | their-move         |
| O9b  | You: "Rename this to amount_kg." · Mei: "Done in abc1234" · You: "LGTM, thanks!"                                                                                                                                 | line thread; you spoke last                | assumed-done       |
| O10  | Sam: "Asking the other reviewers — @you @ana — shout if you disagree" · You: "I'd remove the checks so drafts stay unvalidated." · Ana: "Agree with you on this." · Mei: "OK, removing them. Sam, fine for you?" | line thread; @-mentions you; you commented | not-mine           |
| O11  | claude\[bot\]: "Summary: this PR adds input validation. 3 suggestions below."                                                                                                                                    | conversation comment                       | not-mine           |
| O12  | Mei, in the PR description: "Adds the migration. @you could you look at the down-migration in particular?"                                                                                                       | PR description; @-mentions you             | my-move            |
| O13  | Sam, review summary: "Leaving some comments. Mainly: move the check into the service, and keep the basic input checks."                                                                                          | review summary                             | not-mine           |
| O14  | Sam: "Just to be sure, could you ask Claude whether every handler is covered? Not 100% sure about the exports."                                                                                                  | line thread; no mention of you             | not-mine           |
| O15b | You: "These comments describe how the code used to be; describe what it does now." · Mei: "Tackled in abc1234"                                                                                                   | line thread; names a commit                | needs-verification |
| O16  | You: "Drop the legacy flag, it's unused." · Sam: "I don't think that's right, the import path still uses it."                                                                                                    | line thread; colleague spoke last          | my-move            |
| O17  | You: "We should do this for every entity, not just this one." · Mei: "Agreed but out of scope here — filed a ticket for it."                                                                                     | line thread                                | my-move            |
| V1   | You: "Drop the retry loop, the client already retries." · Mei: "Hmm, not sure about this one."                                                                                                                   | line thread                                | my-move            |
| V2   | You: "This query runs once per row, can it be batched?" · Mei: "I'll look into it."                                                                                                                              | line thread                                | their-move         |
| V3   | You: "Should this live in the domain layer instead?" · Mei: "Good point, will think about it."                                                                                                                   | line thread                                | their-move         |
| V4   | You: "Why not reuse the existing validator here?" · Mei: "Sam and I already discussed this offline."                                                                                                             | line thread                                | my-move            |
| V5   | You: "This will break when the list is empty." · Mei: "Should be fine as is."                                                                                                                                    | line thread                                | my-move            |
| V6   | You: "Add a test for the negative amount case." · Mei: "👍"                                                                                                                                                      | line thread; no commit named               | needs-verification |
| V7   | You: "This should go through the repository, not the session directly." · Mei: "Fair, but can we keep it for now and revisit in the refactor?"                                                                   | line thread                                | my-move            |
| N1   | You: "This should be a constant." · Mei: "Done, moved it to settings.py."                                                                                                                                        | line thread; no commit named               | needs-verification |
| N2   | You: "Both endpoints need the same validation." · Mei: "Fixed in abc1234 and def5678."                                                                                                                           | line thread; names two commits             | needs-verification |
| N3   | You: "Validate the name and the email here." · Mei: "Name done in abc1234, email in a follow-up PR."                                                                                                             | line thread; names a commit                | needs-verification |
| N4   | You: "This breaks on empty input." · Sam: "Mei fixed this in abc1234, I checked."                                                                                                                                | line thread; names a commit                | needs-verification |

Where the verification lands:

| ID   | Then                                                                                                           |
| ---- | -------------------------------------------------------------------------------------------------------------- |
| O5b  | assumed-done if the commit makes it a constant in settings.py (NV4), else my-move (NV5)                        |
| O15b | as O5b                                                                                                         |
| V6   | Opus looks for a commit adding the test (NV2): addressed → assumed-done, none found → their-move (NV6)         |
| N1   | as V6, for the move to settings.py                                                                             |
| N2   | both commits read together                                                                                     |
| N3   | partly addressed → my-move, with "name validated, email not" on the card for the viewer to accept or not (NV5) |
| N4   | as O5b: a colleague's claim is checked the same way (NV3)                                                      |

### Your PR

| ID  | Thread                                                                                                 | Facts                            | Expected                                      |
| --- | ------------------------------------------------------------------------------------------------------ | -------------------------------- | --------------------------------------------- |
| Y1  | Sam: "Rename this to amount_kg."                                                                       | line thread                      | needs a fix                                   |
| Y2  | Sam: "Why a dict here rather than a dataclass?"                                                        | line thread                      | needs a reply from me                         |
| Y3  | Sam: "Nice, LGTM 👍"                                                                                   | review summary                   | assumed done                                  |
| Y4  | Sam: "Why a dict here?" · You: "It's serialised straight to JSON, a dataclass would need a converter." | line thread; you spoke last      | their move                                    |
| Y5  | Sam: "This should be a constant." · Ana: "@sam I'd keep it inline, it's used once."                    | line thread; reviewer spoke last | needs a reply from me                         |
| Y6  | claude\[bot\]: "3 nits: unused import in models.py, a missing type hint, a typo in the docstring."     | review summary                   | needs a fix                                   |
| Y7  | Sam: "Rename this to amount_kg." · You: "Done in abc1234" · Sam: "Thanks!"                             | line thread                      | assumed done                                  |
| Y8  | Sam: "This breaks on empty input." · You: "Fixed in abc1234" · Sam: "Still fails for an empty list."   | line thread                      | needs a fix                                   |
| Y9  | Sam: "We should do this across the whole codebase at some point."                                      | line thread                      | needs a reply from me, with a ticket proposed |
| Y10 | Ana: "Are we still releasing Thursday?" · Sam: "@ana yes, after standup."                              | conversation comment             | not my conversation                           |
| Y11 | Sam: "@ana can you double-check this SQL? You know the index better."                                  | line thread; @-mentions Ana      | their move                                    |

On your PR these come from the agent run and its decline classification (T3,
T4), not from the verdict call: needs a fix is a proposed fix (Ready for you),
needs a reply from me is Needs a look, and Y9 is the reply-and-ticket proposal
of [that design](2026-10-08-reply-and-ticket-proposals-design.md). Y10 needs a
classification for chatter that is not about the PR, which T4 does not have.

## The form

Settled by experiment on 2026-10-09: one `choice` over the five outcomes, asked
of `jev-1.13`, with the instruction "What does this thread ask of viewer now?".
The criteria are `MEANINGS` in `conversation/_domain/verdict.py`, in the order
my-move, needs-verification, their-move, assumed-done, not-mine; the order is
part of the form, since reordering the options lost O17. The state is the
thread as plain text, with usernames swapped for `viewer`, `pr-author` and
`colleague-N`, links reduced to their text and bare URLs removed, a marker line
after the viewer's last comment, an emoji-only reply tagged with its emoji's
name, and the closing facts sentence (thread kind, whether the viewer commented,
whether the thread @-mentions the viewer).

Scored on the 28 test cases above, the 16 real threads, and two held-out sets of
30 synthetic cases no variant was tuned on, 20 runs each: every case right on
every run. A JSON state, role words such as "you", and a decomposed form of
seven yes/no questions all scored lower on the held-out sets.

Until the Needs verification group exists, needs-verification places the thread
in Answered.

## Open questions

- Where a Needs verification card sits on the board and in the Columns view,
  and how it counts in the PR's next move while the check runs.

## Out of scope here

- Building needs-verification and the Y9/Y10 changes.
