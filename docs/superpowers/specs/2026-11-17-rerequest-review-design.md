# Re-request review prompt: design

Issue #428.

## Why

On your own pull request, a reviewer who requested changes or left comments
waits for you to ask them again. The board closes their comments one by one,
but nothing tells you that the last one just closed, and nothing asks them
back. Today the next move only notices a reviewer who requested changes
(`ofAuthor` in `frontend/app/data/summaries.ts`, "Address changes from X"),
and it keeps saying so after every comment is closed. A reviewer who only
commented is never mentioned.

This change asks, at the moment the last of a reviewer's comments closes,
whether to re-request their review, shows what happened to each comment
before they see it, and sends the request once the fixes are pushed and CI
is green.

## Requirements

These were settled on the mockup page. They are fixed.

### 1. When the prompt opens

On a pull request you wrote (or took over), the prompt opens when a closing
decision would leave a reviewer with no open board thread. The reviewer
qualifies when all of these hold:

- their review that stands is `changes-requested` or `commented` (the
  snapshot's `reviewer_status`: a later comment does not overwrite an
  approval or a change request);
- they are a person, not a bot (the thread's `author_kind` is `human`);
- GitHub does not list them in `pending_reviewers`. A pending team does not
  count: the person is asked even when the original request went to a team.

Any action on the thread that would leave it closed opens the prompt:

- Accept (whatever it lands: a commit, a reply or a ticket), Reply and mark
  done, Resolve, Mark done, Reject and Defer, always;
- Confirm (either form) on a thread an agent placed as assumed done, always;
- Move, when it moves the thread to Their move (`waiting`) or Not my
  conversation (`not-mine`); a move to Needs a fix or My move leaves it open;
- a plain Reply from the reply box, when it parks the thread: the domain
  moves a replied thread to `waiting` only when the thread awaits you
  (`Conversation.awaits_you`: its state is `ready`, or it was reopened and is
  `queued` or `working`), and the front end reads the same condition from
  the thread's `state` and `reopened`.

A deferred or rejected comment counts as addressed.

A reviewer's comments are their **round**: every board thread they opened
since they were last asked to review (section "Data"), the review body
included as one comment. Threads in the record states `draft`, `enrolled`,
`discarded`, `not_mine` and `removed` are not part of a round.

A thread is **open** unless its state is `done`, `waiting`, `assumed-done`,
`not-mine` or `deferred`.

### 2. The dialog

The hold warning's shape (`frontend/app/components/hold-warning.gts`): a
`decide-dialog` with a `role="alertdialog"` form, a header with a kicker and a
× button, a question, notes and two buttons.

- Kicker: "Last comment from <reviewer>".
- Question: "Re-request <reviewer>'s review of #<n>?"
- A badge for the review that stands: "Changes requested" in the alarm tone
  (the existing `state-chip tone-alarm`), "Commented" plain.
- A summary line counting outcomes across the round, the comment being
  closed included: "This is the last one open: 2 pushed, 1 replied, 1 marked
  done, 2 rejected". Each comment counts once, under the first that applies:
  rejected, deferred, pushed, replied, resolved, marked done. Zero counts are
  left out.
- A bold flag line, only when comments were rejected or closed with no reply
  and no push: "You rejected 2 comments, and 2 have no reply and no push. Open
  the list to see them before <reviewer> does." Either clause stands alone
  when the other count is zero.
- One closed accordion row, "N comments from <reviewer>", in the ready
  dialog's `outstanding-kind` treatment
  (`frontend/app/components/ready-confirm.gts`). Open, it lists each comment:
  - where: `file:line`, "review body" for the review summary, "PR comment"
    for a comment on the pull request at large;
  - what it said: the thread's gist, or the first line of the reviewer's
    comment where there is no gist;
  - outcome chips: pushed, replied, ticket filed, resolved, marked done,
    rejected, deferred (as many as apply);
  - a closed "History" row that opens to the full timeline, oldest first,
    each entry with its time: reviewer commented, agent proposed a fix, sent
    back for rework (with the note), accepted and pushed (with the short
    sha), replied, resolved, marked done, rejected, deferred (with what wakes
    it).
- Buttons: primary "<decision> and re-request", secondary "<decision> only".
  The label follows the thread's own decision: "Mark done and re-request",
  "Resolve and re-request", "Accept and re-request", "Confirm and
  re-request", "Move and re-request", "Reply and re-request". Keys `r` and
  `o`.

### 3. The dialog interrupts the decision

The closing decision is not posted until a button is picked.

- Primary: post the decision; once the board accepts it, queue the
  re-request.
- Secondary: post the decision only. The re-request stays owed (section 5).
- × or Escape: cancel the whole click. Nothing is posted and the thread
  stays open.

A decision that opens its own dialog first (Accept, Resolve, Reject, Defer,
Reply and mark done, Confirm with its resolve choices) shows that dialog,
then this one, with what was gathered kept until a button is picked. A plain
Reply keeps the typed words in the reply box until a button is picked, and
× leaves them there unsent.

### 4. When the re-request goes out

Queued, the re-request waits until the accepted fixes have pushed and CI is
green, then asks the reviewer through GitHub's `requested_reviewers` API for
that person's login. It reuses `PullRequests.assign_reviewers`
(`src/github_orchestrator/github/interface.py`) with `detailed=None`, which the
ready-for-review "when ready" path already calls through
`ManagerCommands._assign_reviewers`.

While it waits, the PR's next move reads "Re-request queued for <reviewer>".

"Green" depends on whether the pull request has ever had checks:

- If it has, only `ci_status` `passing` on the head polled after the pushes
  is green. `none` is never green there: a fresh head has no checks until CI
  starts.
- If it never has (a repository with no CI), the re-request goes out once
  the pushes have landed and been polled.

The Dashboard on that move offers two controls per queued reviewer
(labelled with the login when more than one is queued):

- **Cancel** takes the reviewer off the queue. Nothing is sent and the next
  move goes back to "Re-request review from <reviewer>".
- **Send now** asks the reviewer at once, without waiting for pushes or CI,
  and takes them off the queue.

### 5. Skipping, and the next move

"<decision> only" leaves the PR in your column with the next move
"Re-request review from <reviewer>", for a commented review as well as a
change request. It is not a dismiss: nothing is hidden.

That next move's Dashboard control opens the same dialog without a closing
decision: same kicker, question, badge, lines and list (no comment being
closed), with the buttons "Re-request review" (`r`), which queues it as in
section 4, and "Not yet" (`n`), which closes the dialog and changes nothing.

### 6. The hold warning

The hold warning and this prompt cannot meet today: mentions are only held
on pull requests the viewer did not write, and this prompt only opens on the
viewer's own. If mentions on your own pull requests ever arrive, the hold
warning goes first.

## Data

What the board knows today, and what it lacks.

### What exists

- **Review states.** `change_detection/_rules.py` folds every review into
  `reviewer_status` per login in the snapshot. `Facts` and the contract's
  `PrFacts` expose only `approved_by` and `changes_requested_by`.
- **Pending reviewers.** `PullRequestState.pending_reviewers`, people by login
  and teams as `@slug`, in `PrFacts.pending_reviewers`.
- **CI.** `PrFacts.ci_status` (`passing`, `failing`, `pending`, `none`) and the
  checks on the head as of `polled_at`, with `head_sha` in `Facts`.
- **Threads.** Each `Conversation` holds its opener (`author` in the domain,
  `author_kind` in the contract), `kind` (`review`, `issue`,
  `review-summary`), `anchor.path` and `anchor.line`, `gist`, `state`,
  `record_state`, `github_resolved`, comment summaries (author, time, review
  state) and operation summaries (kind, state, `lands`, `requested_at`,
  `settled_at`).
- **Full operations.** `/conversations/{key}/operations`, which
  `store.readThread` already reads, carries the rework `brief.note`, the
  approve's `landed_sha`, the defer's `until` and a fix run's `proposal`.
- **Sending a request.** `PullRequests.assign_reviewers`, and the manager's
  `assign_once_ready`, which runs every tick and fires a saved pick once the
  PR is not a draft (`ReviewerPicks`, on disk under `assign_when_ready/`).

### What is missing

1. **Commented reviewers.** `reviewer_status` knows them; nothing past
   change detection does. Add `commented_by` to `Facts`, the manager's
   `Dashboard` and `PrFacts`, beside `changes_requested_by`. **Done**
   (`7b06a50b` for `Facts`, the commit that records this for `Dashboard`
   and `PrFacts`).
2. **When a reviewer was last asked.** Nothing records it, so a round cannot
   be told from the reviewer's earlier rounds. The snapshot gains
   `review_requested_at`, a map from login to the poll time at which the
   login was first seen in `pending_reviewers` after not being there, carried
   forward from the old snapshot otherwise. `Facts` and `PrFacts` expose it.
   A login with no entry (every PR polled before this change, and reviewers
   never asked) has every thread they opened in its round. **Done**
   (`8435d797` for the snapshot and `Facts`, the commit that records this
   for `PrFacts`).
3. **Who opened a thread, on the wall.** `ThreadRow` carries `author_kind`
   but not the login or when the thread was opened, so the next move of a PR
   whose conversations are not loaded cannot group threads by reviewer.
   `ThreadRow`, and `Conversation` with it (a row is a subset of a
   conversation), gain `opened_by` (the opener's login) and `opened_at` (the
   first comment's time). **Done** (the commit that records this).
4. **Resolved or marked done.** Both close as a `resolve` operation; the
   request's `resolve` flag is not kept on it. The outcome is read from the
   conversation's `github_resolved` instead: true reads "resolved", anything
   else "marked done". No new field.
5. **A queue that waits on push and CI.** `ReviewerPicks` holds one pick per
   PR and fires on "no longer a draft". A new per-PR store, `Rerequests`,
   holds the logins queued for a re-request, on disk under
   `rerequest_review/<owner>/<repo>/<n>.json`, with the same disk and fake
   implementations and contract tests as `ReviewerPicks`. **Done**
   (`b331a05a`).
6. **Whether the pull request has ever had checks.** The snapshot holds only
   the checks on the current head, and the board fetches nothing about a
   repository's CI configuration or the checks of earlier heads. The
   snapshot gains `had_checks`, a sticky flag in the change-detection
   snapshot (`change_detection/_rules.py`): true once any poll of the pull
   request saw a check on its head, carried forward from the old snapshot
   and never cleared. `Facts` exposes it to the manager; the front end does
   not need it. It is per pull request, not per repository: by the time a
   reviewer is re-requested CI has almost always run on an earlier head of
   the same pull request. A snapshot written before this change has no
   field, which reads as whether the current head has checks; a pull request
   on a CI repository whose head has none at that first poll counts as never
   having had checks until a later poll sees one. Knowing it per repository,
   or from the repository's workflow files, would need a new GitHub read.
   **Done** (the commit that records this).

Replies need no new data: a comment on the thread by the PR's author after
the reviewer's first comment is a reply, whichever operation posted it.
Pushed is an Accept whose `lands` is `commit` and that was not refused.

## Server

- **Change detection.** `snapshot_of` writes `review_requested_at` and
  `had_checks`; `facts_of` reads them and `commented_by`. **Done**
  (`7b06a50b`, `8435d797` and the commit that records this).

- **Conversation.** `counts()` fills `opened_by` and `opened_at` on each row.
  **Done** (the commit that records this).

- **Settings.** `Rerequests` with `queued(pr)`, `queue(pr, login)`,
  `drop(pr, login)` and `forget(pr)`. The watcher's teardown forgets a PR's
  queue with its reviewer pick. **Done** (`b331a05a` and the commit that
  records this).

- **Manager command.** `Command.REREQUEST_REVIEW` with a `reviewer` field,
  `ManagerPanel.rerequest_review(reviewer)` and the board route
  `POST /manager:rerequest-review` with `{"reviewer": "<login>"}`, beside
  `manager:assign-reviewers`. It is refused, as assigning is, on a PR that is
  not yours (`not-yours-to-assign`). **Done** (`71d07303` and the commit that
  records this). A body without a reviewer, or with an empty one, is the
  board's `malformed-request` 400, as every other malformed body is.

- **Cancel and send now.** `Command.CANCEL_REREQUEST` and
  `Command.SEND_REREQUEST_NOW`, each with a `reviewer` field, the panel
  methods `cancel_rerequest(reviewer)` and `send_rerequest_now(reviewer)`,
  and the routes `POST /manager:cancel-rerequest` and
  `POST /manager:send-rerequest` with the same body. Cancel drops the login
  from `Rerequests`; send now asks through `_assign_reviewers` at once and
  drops it, with the same refusal handling as the send below. Both are
  refused on a PR that is not yours, and cancelling a login that is not
  queued does nothing. **Done** (`71d07303` and the commit that records
  this).

- **The send.** Each tick, beside `assign_once_ready`, the manager asks one
  pure function which queued logins are due, given the facts and the PR's
  conversations. A login is due when:

  - it is not in `pending_reviewers` (if it is, it is dropped from the queue:
    someone asked them already);
  - no thread it opened is open;
  - no Accept on any of the PR's threads is pending, running or requeued;
  - the facts were polled after the last Accept settled; and
  - `ci_status` is `passing`, or, when `had_checks` is false, anything but
    `failing` or `pending`.

  Each due login is asked through `_assign_reviewers` and dropped from the
  queue. A refusal from GitHub drops it too and shows the existing
  `assign-reviewers-refused` notice, so the next move goes back to
  "Re-request review from <reviewer>" rather than retrying every tick.

  The function is `due` in `pr_manager/_rerequest.py`, and the manager calls
  it only on a PR that is yours: on one that is not, the queue waits
  untouched. A thread is in the login's round as section 1 says. **Done**
  (`0a216a19`).

- **Dashboard.** `DashboardSystem.rerequest_queued: list[str]`, beside
  `assign_when_ready`. **Done** (`71d07303` and the commit that records
  this).

## Front end

The store rule holds: the store keeps `commented_by`, `review_requested_at`,
`rerequest_queued` and the new row fields once; everything below is derived
in `frontend/app/data/summaries.ts`.

- **Rounds.** For each qualifying reviewer: their threads in the round, which
  are open, and each thread's outcomes. A reviewer is **owed** a re-request
  when no thread in their round is open, they are not queued, and either
  their review requested changes or their round has at least one thread.
  **Done** for the round and who is owed (the commit that records this);
  each thread's outcomes come with the prompt.

- **The prompt's question.** One function answers, for a thread and an
  action with what it gathered, whether the action closes the thread
  (section 1's list, replacing a fixed set like `CLOSES_A_MENTION`) and
  leaves a qualifying reviewer with nothing open. It returns the reviewer,
  the badge, the counts, the flag and the list, the closing thread's outcome
  taken from the action (Accept of a commit is pushed, of a reply or ticket
  replied; a written reply, a plain Reply included, is replied; Resolve
  resolved; Mark done, Confirm and Move marked done; Reject rejected; Defer
  deferred).

- **Next move.** `ofAuthor` gains two moves and narrows one:

  - `address-feedback` ("Address changes from X") only while a reviewer who
    requested changes has an open thread in their round;
  - `rerequest-review` ("Re-request review from X"), Needs you, for an owed
    reviewer, changes requested or commented;
  - `rerequest-queued` ("Re-request queued for X"), Waiting on others, while
    `rerequest_queued` is not empty.

  The order is `address-feedback`, `rerequest-review`, `fix-ci`, `rebase`,
  `rerequest-queued`, then the rest as today. `onYourPr` lets waiting
  comments and agents come before `rerequest-review`, as for every move but
  `address-feedback`. **Done** (the commit that records this).

- **Dialog.** A new component, `rerequest-prompt.gts`, opened from
  `panel-actions.gts` beside the hold warning, from `reply-box.gts` for a
  plain Reply, and from `dashboard-tab.gts` for the `rerequest-review` move. The History row reads each thread's full
  operations through `store.readThread` when it is opened, and shows what the
  summaries give until they arrive.

- **The write.** `rerequest-review` joins `PR_WRITES` in the `reviewers` slot,
  settled once the login is in `rerequest_queued` or `pending_reviewers`;
  `cancel-rerequest` and `send-rerequest` join it in the same slot, settled
  once the login has left `rerequest_queued`. `pr-controls` gains
  `rerequestReview`, `cancelRerequest` and `sendRerequestNow`, each taking
  the PR and the reviewer.

## Edge cases

- A reviewer GitHub already lists as pending never prompts and is never owed.
- A reviewer whose standing review is an approval never prompts, even with
  open comments closed afterwards.
- A bot's threads never prompt, whatever their review.
- A team request: the team stays pending, the person is not, so the person
  prompts and is asked by login.
- A comment from the PR's author on their own PR is not a reviewer's.
- An Accept whose push later fails reopens its thread, so the reviewer has an
  open thread again and the queued re-request waits.
- CI failing: the queue waits and the next move is Fix CI.
- CI on a repository with checks has not started on the pushed head
  (`none`): the queue waits.
- Send now while an Accept is still landing: sent anyway, as asked.
- A reviewer asked on GitHub while queued is dropped from the queue on the
  next tick.
- The PR closes or merges: teardown forgets the queue.
- A decision the board refuses (409, 412) queues nothing: the re-request is
  queued only after the decision's post is accepted.
- A changes-requested review with no comments at all: owed at once, so the
  next move reads "Re-request review from X" rather than "Address changes".

## Out of scope

- **Several reviewers on one click.** A closing decision acts on one thread,
  which one reviewer opened, so the first version asks about that reviewer
  alone. One dialog per reviewer, in turn, comes later.
- Accepting a split's parts from the part rows does not prompt. A thread it
  leaves closed still counts as closed, so the reviewer can become owed
  without a prompt and the next move says so.
- Dismissing a review.
- A notification when the queued re-request goes out.
