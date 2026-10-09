# Next move for a pull request

Date: 2026-10-01. Visual version:
(private design page)

## Problem

Two PRs showed the wrong next move on the board.

- **#41** (Carol's PR). Jeffrey had approved, but the NEXT banner said
  "Re-review: 2 threads answered" and counted the PR as needing him. The two
  threads were Dave's, answered by Carol.
  `_board_move` (`pr_manager/_snapshot.py`) checks answered threads before the
  viewer's review state, and `counts().answered` counts every thread whose newest
  comment isn't from its opener, whoever opened it.
- **#42** (Dave's PR). It had two approvals, GitHub said APPROVED and CLEAN,
  and it showed "Waiting on carol". `_merge_blocker`
  (`change_detection/_facts.py`) returns AWAITING_REVIEW whenever anyone is on
  the requested-reviewers list, before it looks at mergeability.

The move is decided in five places: `_your_move` and `_board_move`, then
`_wanted_of_author`, `_wanted_of_reviewer` and `_merge_blocker`, and the front
end's `moveOf`. This design replaces them with one decision in the back end. It
returns a move code with its numbers, the wall group, the tags and the counts.
Each interface writes its own text from the code, because the board may not be
the only interface.

## Wall groups

In wall order: Needs you, Draft, Agent working, Waiting on others, On hold,
Mentioned. Draft and Mentioned are new. A PR can also be off the wall entirely.

## Rules

Each list reads top to bottom, and the first question that gets a yes wins.

### 1. Before anything else

| ID  | Question                                       | Yes                             |
| --- | ---------------------------------------------- | ------------------------------- |
| G1  | Is the PR's worktree holding the wrong branch? | Needs you: Release the worktree |
| G2  | Did you put it on hold?                        | On hold: N events held          |
| G3  | Has the PR been polled yet?                    | No: Waiting for the first poll  |
| G4  | Is it merged or closed?                        | Off the wall                    |
| R   | Are you the author?                            | Yes: section 3. No: section 2   |

### 2. Someone else's PR

Your review state comes first. Threads and drafts only matter once it's your
turn to review.

- **V1** Are you a reviewer: requested now, or you've already submitted a
  review? GitHub drops you from the requested list once you submit, so
  "requested now" alone would hide every PR you've approved. Yes: go to V3.
- **V2** Has anyone ever mentioned you by name on the PR? No: off the wall,
  drafts included. Once a mention exists, the PR stays on the wall until it's
  merged or closed.
- **V2b** Is there a mention you haven't answered? Yes: Needs you, "X
  mentioned you". No: Mentioned.
- **V3** Are you on the requested-reviewers list right now? This is GitHub's
  "your turn" signal.
  - **V4** (requested) Have you reviewed it before?
    - No, first review: V6 a review agent running for you → Agent working. V7
      drafts in your pending review → "Send your review · N drafts".
      Otherwise "Review this PR".
    - Yes, re-review: V8 review agent running → Agent working. V9 drafts →
      "Send your review · N drafts". Otherwise "Re-review · M/N of your
      threads answered". The count always shows and counts only threads you
      opened.
  - **V5** (not requested) What was the last review you submitted?
    - Commented, changes requested or dismissed: V12 a mention since your
      review that you haven't answered → Needs you, "X mentioned you".
      Otherwise waiting on the author to ask you again. Threads, drafts and new
      pushes don't count.
    - Approved: V10 a mention since you approved that you haven't answered →
      Needs you. V11 does GitHub's review decision say the PR has all the
      approvals it needs? No → "Waiting on reviewers X, Y". Yes, or no review
      decision at all → "Waiting on the author", plus "· X still requested"
      when the decision is empty and someone is still on the requested list.

### Review agent

Every review request starts a review agent automatically, the first request and
every re-request. Today only the first sighting does (`_requested` in
`change_detection/_rules.py`). "Review this PR" and "Re-review" also show a
**Start a review agent** button, for when the automatic run went wrong.

On a re-request the prompt sets out the situation: your last review and what it
said, every commit since, and the threads that have been replied to. The agent
re-reviews based on the changes.

### Mentions

- The watcher finds them with a `mentions:@me` search, next to `--author=@me`
  and `--review-requested=@me`, run at most once a minute.
- A mention is answered by your reply.
- On a PR you didn't author, a mention's card has one button, **Reply and
  resolve**. It opens a modal, posts your reply to GitHub, and resolves the
  mention on the board only, never on GitHub. **Defer** sits at the bottom right
  as a link, like the other cards. The card has no "Reply to X" link under the
  comment and no line for a proposal.

### 3. Your PR

Other people's comments come first. Fix CI and Rebase only become the next move
once nobody's comments are waiting.

| ID  | Question                                                      | Yes                                                    |
| --- | ------------------------------------------------------------- | ------------------------------------------------------ |
| A1  | Is it a draft?                                                | Draft group, then carry on: the move below shows muted |
| A2  | Changes requested, and that reviewer not asked again?         | Needs you: Address changes requested from X            |
| A3  | Human comments waiting on you?                                | Needs you: Human comments · M/N done · K to decide     |
| A4  | Agent working on human comments?                              | Agent working: Human comments · M/N done · agent on K  |
| A5  | Bot comments waiting on you?                                  | Needs you: Bot comments · M/N done · K to decide       |
| A6  | Agent running on anything else (bot comments, CI, rebase)?    | Agent working                                          |
| A7  | CI failing?                                                   | Needs you: Fix CI                                      |
| A8  | Conflicts with main, or behind it when that blocks the merge? | Needs you: Rebase on main                              |
| A9  | Can you press merge (merge state CLEAN)?                      | Needs you: Ready to merge                              |
| A10 | CI still running?                                             | Waiting on CI                                          |
| A11 | Re-requested someone who asked for changes?                   | Waiting on X to re-review                              |
| —   | Otherwise                                                     | Waiting on reviewers X, Y                              |

A draft's move is whatever the rest of the list gives, shown muted. There is no
"Mark ready for review" step.

A bot is a comment author on a fixed list: `claude`, `codex`, `copilot`.
Everyone else is human. Your own comments and unsent drafts don't count toward
A3 or A5, and drafts are never the next move on your own PR.

"Waiting on you" in A3 and A5 means one of these: a fix was proposed, the
agent declined or failed, a push or reply failed, the reviewer answered back,
or the comment was deleted on GitHub.

A thread counts as done when its fix landed on the branch, you replied and are
waiting on the reviewer, or the reviewer resolved it. A proposed fix you haven't
accepted counts as to decide, not done.

Branch protection that requires conversations to be resolved isn't modelled.

### Shown on every PR

- Flags, beside NEXT in the top bar, on the wall and in the PR switcher whenever
  they're true: **Draft**, **Fix CI**, **Rebase**, **N unresolved threads**.
- On your PR: human comments M/N done, bot comments M/N done.
- On someone else's PR: your threads M/N answered.

### Draft in the top bar

A grey Draft pill before the title, and the NEXT box outlined in grey with no
yellow, so yellow keeps meaning "needs you now".

### Dismissing a PR

Dismissing sits on top of these rules. A dismissed PR leaves the wall until its
next event, then goes through the rules again. A stuck worktree (G1) stays on
the wall even when dismissed.

## Evidence from GitHub, 2026-10-01

- **Review decision vs merge state.** GitHub returns `reviewDecision`
  separately from `mergeable` and `mergeStateStatus`. On acme/widgets: #42
  APPROVED and CLEAN, #56 REVIEW_REQUIRED and CONFLICTING, #16
  REVIEW_REQUIRED and BLOCKED. There are three catches. BLOCKED doesn't say
  which rule blocks. UNKNOWN is common until GitHub computes it. On #86,
  #63 and #64 `reviewDecision` is null, possibly because they don't target
  main (unchecked).
- **Re-request after changes requested.** #37's timeline shows bob's
  CHANGES_REQUESTED review, then a separate re-request event, then their
  approval. It seems like the changes-requested review stands until the
  reviewer submits again. No PR was found in both states at once to confirm.
- **Stale approvals.** Jeffrey's approval on #42 survived a force-push, so
  automatic dismissal seems to be off on acme/widgets.
- **Bots.** Thread authors come back typed `Bot` for `claude`, but the rule
  uses the name list.
- **Mentions** aren't tracked anywhere in `src` today. The watcher only finds
  PRs through `--author=@me` and `--review-requested=@me`
  (`github/_client.py`), and keeps one while `relevance()` says you authored or
  reviewed it.
- **The top bar** shows one line in the NEXT box (`pr-view.gts`), with flags
  such as CI failing beside it in `prflags`.

## Decisions from grilling, 2026-10-01

01. **Where the decision lives.** The back end decides and returns a move code
    with its numbers. Each interface words it, since there may be others besides
    the board.
02. **The comment counts say "done", not "fixed".** Done means the fix landed,
    you replied, or the reviewer resolved the thread.
03. **A mention wakes the author's-turn case.** After you comment, request changes
    or have a review dismissed, an unanswered mention brings the PR back to Needs
    you (V12), the same as after an approval (V10).
04. **A dismissed review waits for a re-request**, the same as commented or
    changes requested.
05. **The group for answered mentions is called Mentioned** and sits at the
    bottom of the wall, below On hold.
06. **A draft shows the rest of the list, muted**, with no "Mark ready" step.
07. **The order of A2–A8 stays as written.** An agent on human comments ranks
    above bot comments, and one on CI or a rebase ranks below both.
08. **The review agent starts automatically**, and "Start a review agent" is a
    fallback for when that goes wrong.
09. **Every request starts the agent, re-requests included**, with a re-review
    prompt built from the last review, the commits since and the replied threads.
10. **Mentioned PRs come from a `mentions:@me` search**, at most once a minute.
11. **A mention is answered by your reply.**
12. **One "Reply and resolve" button on a mention**, resolving on the board only,
    with Defer as a link at the bottom right and no reply link or proposal line.
13. **An empty review decision means waiting on the author**, with "· X still
    requested" added.
14. **"Ready to merge" replaces "Merge the PR"**, and conversation-resolution
    protection isn't modelled.
15. **"N unresolved threads" is a flag beside NEXT**, not a line inside it.
