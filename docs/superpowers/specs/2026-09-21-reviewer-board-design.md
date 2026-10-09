# Reviewer board

The review board works on PRs you authored. Open it on a PR you are reviewing and
it draws nothing: the watcher polls the threads and enqueues `thread-activity`
for every PR regardless of role, but the manager's reviewer branch in
`github_pr_agent_manager/handlers.py` appends the comments to `agent-changes.md`
and returns without creating a record, so the repository's `list()` is empty and
the rail has no rows. The `v` key is not gated on role and opens an empty board.

This spec makes the board the place you review from. Every thread on the PR is a
card. Yours rank first. The half of the card that used to hold the agent's fix
holds what the author did about the comment instead: the commits that touched
it, and a model's judgment of whether they answer it. Resolving a thread writes
to GitHub. The review run's findings become drafts, and one button sends them as
your review.

It was settled as a design tree in a grilling session on 2026-09-21, one question
a round, and confirmed. The full record is the appendix. The layout options were
drawn on the board's own palette and type and chosen from a mockup page
(private design page). It is written against the
domain of `2026-09-12-review-domain-port-design.md` and the states of
`2026-09-12-review-board-redesign-design.md`, and it reverses one rule of
`2026-09-07-comment-threads-design.md`, named below.

## What the board is for on a PR you are reviewing

A queue of what the author has come back to you on, and a monitor for the rest
of the PR. You open a card the author has answered, read what they said, read
what they changed, and either resolve the thread or send it back. Between those
you write the comments of your next review pass as drafts and send them as one
review. GitHub remains where the PR lives; the board is where the review is
worked.

## One rule above the others

**State is the only axis of priority.** The rail's groups are states, in one
order, and nothing else may create a group or move a card between groups. Who
opened a thread is not a state, not a group and not a badge that pretends to be
one. It is one bit in the sort key inside a group. A colleague's answered thread
therefore sits above your quiet one, because state says there is something to do
there and nothing to do on yours.

Ownership still enters the state computation as a fact: "answered" is defined by
who wrote the newest comment relative to who opened the thread. That is an input
to a state, the same way the newest comment's timestamp is. The rule is about what
the board may sort and group by, and that stays state alone.

## States and groups

The existing states cover a reviewer PR. Nothing new is invented for it except
the two draft states in "Your review".

| group             | states                                       | on a reviewer PR it means                                       |
| ----------------- | -------------------------------------------- | --------------------------------------------------------------- |
| Answered          | `open`                                       | the newest comment is by someone other than the thread's opener |
| Your review       | `draft`, `pending`                           | a comment of yours that is not on GitHub yet                    |
| Waiting on author | `waiting_on_reviewer`, labelled for the role | the newest comment is the opener's own                          |
| Deferred          | `deferred`                                   | parked until the next push                                      |
| Done              | `resolved`, `rejected`                       | resolved on GitHub, or a discarded draft                        |

`waiting_on_reviewer` is parked-on-the-other-side. On your PR the other side is
the reviewer; on theirs it is the author. Same state, one role-dependent label.
Agent working, Queued for agent, Sent back for rework and Landing never fill on a
reviewer PR, because there is no fix to queue, run or land, and the rail heads
only non-empty groups.

### Answered

A thread is answered when its newest comment is by someone other than the person
who opened it. For your thread that is "someone wrote back to you". For a
colleague's it is "the author, or anyone, wrote back to them". The PR author
commenting on their own PR opens a thread whose opener and author are one
person; it falls into Waiting on author and nothing is invented for it.

**Only a reply promotes.** A push, a commit linked from a reply, a commit that
touched the commented lines, a verdict that says the comment is addressed: all of
these land on the card and none of them moves it. The one exception is a card you
deferred until the next push. A row in Waiting on author whose code a push has
touched wears a mark in its meta line, "New push touches this", and stays where
it is.

The initial state differs by role. On your PR every polled thread starts `open`.
On theirs, a freshly polled thread whose newest comment is the opener's own is
already parked on the author and must start in Waiting on author, or every quiet
thread lands in Answered on the first cycle.

### Ordering

Inside a group: threads you opened first, then the reopened mark, then recency.
Your thread answered three days ago outranks a colleague's answered two minutes
ago. `sort_key` gets the opener bit ahead of the mark it already carries; the
groups' order does not change.

The word "yours" is taken. In `read_model/standing.py`, `is_yours` means "the
card is in the top group" and the reply box reads it to decide whether a reply
parks the card. The opener notion needs a different name so the two never meet
in one sentence.

### Your review

Sits below Answered and above Waiting on author. Answered is someone waiting on
you; a draft is something nobody is waiting for yet, and when the author
re-requests review while their replies to your earlier threads are in Answered,
you read what they said before you send more. Inside the group, drafts before
pending, then recency. Every draft is yours, so the opener bit is a no-op here.

## The card

### The top

Unchanged from today: header with kicker and Prev / Next over the answered list,
the thread transcript, the always-visible reply composer, and the code the
comment sits on. The kicker counts the card's place among the answered rows. The
role line names whose thread it is and who replied.

### Below the line

The work row loses everything about a fix: label, banner, gist, plan, confidence,
tests, files touched, notes, the landing failure. In its place the left column
holds two tabs and the right column holds one diff fold. This is V3 of the
mockups.

**Tabs: Verdict and Commits.** One visible at a time; the tab is remembered per
card. The Commits tab shows its count; the Verdict tab shows its word. You asked
for both because you will glance at the verdict, decide it is stupid, and want the
plain facts, and the tab is that switch made explicit.

**Commits, the tool.** Git's answer, with no model in it. Push sections newest
first, each headed with when the push happened and how many commits it brought.
Inside a push the commits are ranked by the signals they carry, in this order of
weight:

1. **Linked from the thread.** A reply in this conversation carries its SHA. Both
   formats in use link the full SHA in the URL, the board's own approve as
   `[sha7](url)` and the push-and-reply skill as `🤖 [sha8](url)`, so the SHA is
   parsed from the link, never from the text.
2. **Named by the verdict.** The model cited it. A tag, never a rank above a
   fact.
3. **Touched your lines.** Its diff intersects the commented range in the
   commented file.
4. **Message names the place.** The commit message mentions the file or the
   function the comment sits in.
5. **Touched your file.** Same file, anywhere.
6. **Force-push status.** Modified, new or dropped in a rewrite; see below.

A commit with no signal folds under "N other commits". The top commit of the
newest section is ticked by default. Ticking several shows them as one diff. Each
row carries its short SHA, subject, tags and numstat. Tags are recomputed on the
current branch every push.

**Verdict, the intelligence.** One Claude run fires on every push and judges every
thread on the PR against the comparison of the head before and the head after.
Per thread it says addressed, partly or not addressed, one sentence of reasoning,
and the commits it rests on. Partly exists because "they fixed the rename but not
the test" is the common case and a two-value verdict forces it into a lie either
way. The row shows the word, the sentence, the cited commits as chips, and which
push it judged. Clicking a chip ticks that commit in the Commits tab.

The run never skips: a push that changes no file any thread points at still gets
a run, and the verdict says "unrelated" per thread. Runs that overlap are separate
runs and each verdict is its own row. Every verdict is kept, keyed by the head it
judged, and the card shows the newest by default. A run that fails or times out
leaves the card saying so and is not retried; the next push brings the next run.
The verdict never resolves, never replies, never moves the card.

The run is handed the comparison, modified, new and dropped commits with their
patches, not the raw old-to-new diff, or after a rebase it would be judging
main. Its input is one prompt per push over every open thread; its output is one
record per thread through a `cli thread verdict` verb whose contract joins the
table in `adapters/prompts.py`.

**The fold.** Today's `diff-fold`, full screen and Esc as they are. The range is
whatever is ticked, and the title names the ticked commits. The fold is the one
place a diff is drawn on the card.

## Force pushes

A commit's identity is its content, matched across rewrites the way
`git range-diff` matches them. The comparison is the PR's own range before and
after, each measured from its merge-base with the base branch, so a rebase onto
main brings none of main's commits into the list.

- **Unchanged** commits produce no row anywhere. They keep the row they had in the
  push section that first brought their content, wearing the new hash and a small
  "was `<old>`" tag.
- **Modified** and **new** commits are the force-push section's rows, ranked and
  folded like any push's.
- **Dropped** commits appear only when they carried a relevance tag, as a
  struck-through row, "dropped in this push", diffable while the old object
  survives locally. A fix you were about to judge disappearing is the one event in
  a rewrite you would otherwise never see.
- **A squash reads literally**: five dropped and one new, or four dropped and one
  modified. The surviving commit is re-tagged for relevance like any other and
  so inherits what the five had. No containment logic.
- **The fold on a modified commit** carries a toggle in its title: this commit,
  or what the amend changed relative to the earlier version.
- **Holes in the record.** The watcher down across one or more pushes compares
  against the last head it fetched and labels the section "N pushes while the
  watcher was down, shown as one". Commits that landed after the comment but
  before the board watched the PR, an adopted PR or a comment older than the
  first fetch, sit in one section at the bottom, "before the board watched this
  PR", tagged like any other.

Hashes in the list move with every rewrite. The fold's title always names the
live one, and a tick follows content, not hash.

## Verbs

The same on every thread on the PR, yours and others'.

**Resolve.** Calls `resolveReviewThread` on the thread. The dialog offers an
optional reply; left empty, the board puts a `+1` reaction on the newest comment
that is not the opener's, or on nothing if there is none. The card moves to Done.
This reverses the rule in `2026-09-07-comment-threads-design.md` that nothing
ever resolves a thread. That rule was written for the author's board, where
resolving someone else's comment is presumptuous; resolving as the reviewer is
what GitHub expects, and it is the signal the author's own tooling watches.

**Not fixed.** A reply with your opener pre-filled, keeps the thread open, parks
the card on the author. Reply with a template, and nothing else.

**Reply.** As today: posts to the thread, parks the card.

**Defer until the next push.** The one place a push moves a card, and only
because you asked it to on that card. A new wake condition beside CI and another
PR closing.

**Reopen** from Done. Calls `unresolveReviewThread` and brings the card back. The
cost of making Resolve a real write.

There are no agent verbs on a reviewer card. The verdict runs on the push, never
on request.

## Drafts and the review

### Draft cards

The run that fires on `review-requested` writes prose into `agent-changes.md`
today. It hands back structured findings instead, file, line and body, and each
becomes a card in Your review, state `draft`, with the finding as its body and the
line as its anchor. Nothing exists on GitHub for it.

The card's talk column is a composer: the body in a textarea, the anchor as a
typed path and line, and the code beside it redraws as the anchor changes. New
draft opens the same composer empty. The run anchors comments on the wrong line
often enough that a fixed anchor would send you back to GitHub to write the
comment again.

Verbs on a draft: **Add to review** moves it to `pending`. **Post now** posts it
on its own as a standalone review comment for the one that should not wait.
**Discard** moves it to Done, not to nowhere, so a wrong discard is one click
back.

### Send review

Pending drafts accumulate into one review held locally. Nothing about it shows on
the board until you click. One **Send review** button sits at the right end of the
head, beside the theme toggle, with a keystroke twin; the head is the only strip
on the page about the PR rather than one conversation.

It opens a modal: the decision as Comment, Request changes or Approve, a summary,
the pending drafts going out with it, each with edit and leave-out, and a note on
what you are leaving open, threads of yours the author has not answered and drafts
you have not added. Send posts one review through `POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews` with `event` and the drafts as
`comments[]`, each carrying `path`, `line`, `side` and `body`. The author gets one
notification, with the comments that justify the decision. Because the review is
held locally until then, the poller never has to see a pending review of yours.

## Discovery, views, gist

The watcher's search stays as it is: PRs you authored and PRs where your review
was requested. A CLI verb adopts one PR by number into the watched set, for the
teammate's PR you decided to read; no third search, no surprise windows.

The Board view's columns are the reviewer groups, Answered, Your review, Waiting
on author, Deferred, Done, drawn with the same card component.

Every thread keeps its model-written gist, as today. A colleague's twelve-line
comment needs the one-line version more than yours does.

## What changes in the system

**Watcher.** The reviewer PR's worktree is fetched every cycle, not once at
creation as `common/worktree.py` does now, so the previous head's objects survive
a force push. The state snapshot already carries `head_sha` before and after,
and `pushed-since-review` already fires on head change with force pushes counted;
the manager's handler for it grows the push run and the commit-list refresh.

**Poller and diff.** `domain/diff.py` drops any thread GitHub reports resolved
before it reaches `active` or `stale`. On a reviewer PR resolved threads keep
being polled, so a reply on one reopens it, and a resolved thread lands in Done
rather than vanishing. The GraphQL query asks for the thread's current `commit { oid }` beside `originalCommit`, which it does not today.

**Manager handlers.** The reviewer branch of `thread-activity` materialises and
refreshes through `poll` exactly as the author branch does, and stops appending
prose. `pushed-since-review` computes the range comparison, refreshes every
card's commit list and starts the push run. `review-requested` collects the run's
findings into draft records.

**Domain.** The initial state on materialise depends on role and on who spoke
last. New commands: `Resolve` grows a GitHub write and a reaction; `Unresolve`;
`DeferUntilPush` and its wake; `VerdictWritten` per head; `DraftOpened`,
`DraftEdited`, `DraftAdded`, `DraftPosted`, `DraftDiscarded`; `ReviewSent`. The
conversation carries its opener. A `Draft` is a conversation with no GitHub key
yet; it is keyed by a local id and re-keyed by the node id the review hands back.

**Application.** `standing.group_of` learns the role, the two draft states and
the role-dependent label. `sort_key` gets the opener bit. The read model's panel
view grows the tabs, the commit list and the verdicts, and drops every fix field
on a reviewer card. `is_yours` keeps its meaning; the opener gets its own name.

**Adapters.** `git/` gains the range comparison: merge-base on both sides,
`range-diff` matching, per-commit tags against the commented range, numstat, and
the interdiff for a modified commit. `github.py` gains `resolveReviewThread`,
`unresolveReviewThread`, the `+1` reaction on a review comment, and the review
POST. `agents.py` and `prompts.py` gain the push run and the findings contract.
`pull_requests.py` gains the next-push wake condition. `cli.py` gains `adopt` and
`thread verdict`.

**Board API and front end.** The panel document grows `tabs`, `commits` (push
sections with tagged rows) and `verdicts`; the conversation collection's `meta`
carries the reviewer group labels. New components: the tab strip, the commit list,
the verdict row, the draft composer, the review modal, the head's Send review
button. The fold learns a multi-commit range and the amend toggle.

## What stays exactly as it is

The author board, in every respect. The layering rule and its test. The palette
and the no-hex rule. The record format's version and rewrite rules. `records.update`
and the lock. The gist path. Prev / Next and the keys service. The rework dialog,
the decide dialog and the accept flow, none of which appear on a reviewer card.

## Verified against the vendored docs, and what still wants the live schema

From `docs/github/rest/`: `POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews`
takes `event` in `APPROVE`, `REQUEST_CHANGES`, `COMMENT` and a `comments[]` array of
`path`, `body`, `line`, `side`, `start_line`, `start_side`; `body` is required for
`REQUEST_CHANGES` and `COMMENT`. `POST /repos/{owner}/{repo}/pulls/comments/{comment_id}/reactions` takes `content` with
`+1` among its values.

`resolveReviewThread` and `unresolveReviewThread` are GraphQL mutations the thread
spec already confirmed against the live schema. Their arguments and the
`commit { oid }` field on `PullRequestReviewComment` are to be re-checked with
`gh api graphql` before the adapter is written, per the rule in CLAUDE.md that
thread shapes are never answered from memory.

## Choices made while writing this

- The `+1` reaction goes on the newest comment that is not the opener's, which
  on your own thread is the author's last word and on a colleague's is whoever
  answered them.
- "Message names the place" matches the commented file's basename and the
  enclosing function's name as the code context already finds it; nothing fuzzier.
- The Not fixed opener text lives in `config.toml` and the example file, so it
  appears where every other knob does.
- A verdict on a thread that has since been resolved is still written and never
  shown unless the card is reopened.
- The push run's prompt lists every open thread with its transcript inline, as the
  autonomous skill's prompts do, so it never has to fetch a parent comment.
- The commit list's "before the board watched" section is computed once, at the
  first fetch, from the comment's own commit to the head then, and never again.

## Build order

1. Records on reviewer PRs: the reviewer branch materialises through `poll`, the
   role-dependent initial state, the opener bit in `sort_key`, the labels. The
   board draws every thread with an empty work row. Tests on standing and
   ordering first.
2. Resolve, Reopen, Not fixed, Defer until push: the GitHub writes, the reaction,
   the wake condition, the poller keeping resolved threads.
3. The fetch-every-cycle in the watcher and the range comparison in `git/`:
   merge-base, `range-diff` matching, tags, numstat. The Commits tab and the
   fold's multi-commit range.
4. Force-push presentation: the four classes, the struck-through drop, the amend
   toggle, the merged and "before" sections.
5. The push run: prompt, `thread verdict` contract, per-head storage, the Verdict
   tab, the chip-to-tick link.
6. Drafts: the findings contract on the review run, draft records, the composer,
   Post now and Discard.
7. Send review: the head button, the keystroke, the modal, the review POST, the
   re-keying of posted drafts.
8. Adopt, and the Board view's reviewer columns.

Each step leaves the author board untouched and the suite green, and each is
usable on its own: after step 1 you can read a reviewer PR on the board, after 2
you can work it, after 3 you can see what the author did.

## Appendix: the decision record

Asked one a round on 2026-09-21. The recommended answer is marked where the
answer differed from it.

| #   | question                               | answer                                                                                                                                           |
| --- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Q1  | what earns the top of the rail         | my threads the author has answered since I spoke; changes not mine are the next concern                                                          |
| Q2  | what counts as the author coming back  | a reply, or the commented code changed; plus an agent run per push judging relevance to my comments (later narrowed by Q7)                       |
| Q3  | what the push agent says               | both: a mechanical relevance tool and a model assessment, displayed separately, so I can fall back from a stupid verdict to plain relevance      |
| Q4  | how relevance is computed              | mechanical, from git alone, in rings                                                                                                             |
| Q5  | what the diff is measured against      | the previous head, this push; with an intelligent way of seeing the commits relevant to the comment (recommended: since the comment)             |
| Q6  | what makes the commit list intelligent | signals 1, 2, 3, 5, 6 (message text out; later re-admitted)                                                                                      |
| Q7  | which signals promote                  | only a reply; the other signals are not trustworthy enough. Ranking weight 3, 6, 1, 4, 2, 5 (recommended: reply, lines, link or verdict promote) |
| Q8  | what ends a card                       | resolve on GitHub, optional reply in the same dialog, default a thumbs-up on the author's comment                                                |
| Q9  | the verb set                           | Resolve, Reply, Defer until next push, Reopen from Done, Not fixed                                                                               |
| Q10 | how verdict, list and fold sit         | deferred to mockups; V3, tabs in the left column with one fold on the right (recommended: V1)                                                    |
| Q11 | the not-mine group                     | the same machinery as mine, verdict and resolve included, ranked lower (recommended: reply only, no verdict, no resolve)                         |
| Q12 | how mine-first and state compose       | state first; ownership is not a parallel concept and only orders within a group; opener outranks recency                                         |
| Q13 | when the push run runs                 | overlapping pushes run separately; never skip; keep every verdict; no retry (recommended: coalesce)                                              |
| Q14 | which PRs get a board                  | requested-review PRs as today, plus a CLI adopt-by-number verb                                                                                   |
| Q15 | PR-level verbs                         | Approve, Request changes and Comment on the board (recommended: none in this feature)                                                            |
| Q16 | the review-requested run's findings    | become draft cards (recommended: leave as is)                                                                                                    |
| Q17 | how a draft is posted                  | drafts accumulate into one pending review                                                                                                        |
| Q18 | where drafts live                      | one group below Answered, above Waiting on author; draft before pending; discard to Done                                                         |
| Q19 | authoring drafts                       | body and anchor editable, New draft button, no diff browser                                                                                      |
| Q20 | the gist                               | as today, every thread                                                                                                                           |
| Q21 | the Board view                         | the reviewer groups as columns                                                                                                                   |
| R   | where the review control goes          | none of the three bars; one button in the head opening a modal that holds all review state; nothing shows on the board until clicked             |
| F1  | a commit's identity across rewrites    | content                                                                                                                                          |
| F2  | which rewrite effects earn a row       | modified and new as any push; dropped struck through when tagged                                                                                 |
| F3  | how a squash reads                     | literal; the surviving commit is re-tagged and inherits the relevance (recommended: content-first containment)                                   |
| F4  | which diff for a modified commit       | both, as a toggle on the fold's title (recommended: the commit's own only)                                                                       |
| F5  | holes in the push record               | compare against the last head seen and say so; a "before the board watched" section for adopted history                                          |
