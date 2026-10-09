# Board state machine

Phase 0 of `2026-09-22-board-api-contract-plan.md`. The states are
`ConversationState` from the contract the board serves at
`/api/openapi.json`, the
triggers are every `OperationKind`, a comment arriving from the poller, and the
four ways an operation's own state changes, and the table below carries a row
for every pair of them. It is the contract's acceptance test rather than a
sketch of one: phase 1 generates its tests by parsing this file, so the columns
are fixed, every value is one enum member, and every value is in backticks.

Where this and `2026-09-22-board-api-decisions.md` disagree,
`2026-09-22-board-api-contract-revisions.md` wins and so does this. Where this
and the domain in `src/github_orchestrator/review/domain/` disagree, the
differences are named in the last section rather than left for whoever writes
phase 1 to find. The first pass of this document found two facts the contract
did not carry; both changed the contract, and
`2026-09-22-board-api-build-decisions.md` records why.

## The states

A thread is born `ready`, or `draft` when the board minted it. `ThreadKind`
decides which states it can reach at all: a draft has no agent and no GitHub
thread, and everything else has both.

| state          | a thread in it                                                                                        | kinds                               |
| -------------- | ----------------------------------------------------------------------------------------------------- | ----------------------------------- |
| `draft`        | a comment you are composing, with nothing on GitHub for it                                            | `draft`                             |
| `enrolled`     | a draft you have put into the review you are about to send                                            | `draft`                             |
| `queued`       | an agent run has been asked for and the board has not picked it up                                    | `review`, `issue`, `review-summary` |
| `working`      | an agent is running on the thread's own worktree                                                      | `review`, `issue`, `review-summary` |
| `in-session`   | a Claude session is open on that worktree and you are steering it                                     | `review`, `issue`, `review-summary` |
| `rework`       | a run is going with a brief you wrote                                                                 | `review`, `issue`, `review-summary` |
| `landing`      | an approve is picking, pushing and answering, or a rebase run is catching a proposal up with the head | `review`, `issue`, `review-summary` |
| `ready`        | nothing is in flight and the thread is yours to decide                                                | `review`, `issue`, `review-summary` |
| `waiting`      | parked on the other party: you spoke last, or a verdict says it is their move                         | `review`, `issue`, `review-summary` |
| `assumed-done` | an agent read the thread as settled, for you to confirm                                               | `review`, `issue`, `review-summary` |
| `not-mine`     | someone else's PR: an agent read the thread as asking nothing of you                                  | `review`, `issue`, `review-summary` |
| `deferred`     | parked until a wake condition                                                                         | `review`, `issue`, `review-summary` |
| `done`         | landed, rejected, resolved, confirmed, or a discarded draft                                           | all four                            |

A posted draft is in `waiting` under kind `review`, because `post-now` and
`send-review` change the kind and leave the key alone. A discarded draft is in
`done` under kind `draft`.

On someone else's PR a verdict moves a thread among `ready`, `waiting`,
`assumed-done` and `not-mine` (the comment verdict spec, 2026-10-08). It is an
answer the board asked for, not a request, so no row below names it. On your own
PR a run the agent declines as `already-done` or `acknowledgement` moves an open
thread to `assumed-done`, for the same reason with no row of its own.

`reopened` is not one of them. It is a boolean on `Conversation`, set when a
comment arrives on a thread whose history holds an applied `reply`, `approve`,
`resolve` or `reject`, and cleared by the next applied one of those four. It is
true or false whatever the state says, and no row below writes it.

## What the table is not about

**Request validation happens before the machine sees the request.** A body that
does not say what it needs to is refused whatever the state, so
`empty-body`, `empty-brief`, `body-too-long`, `bad-wake-condition`,
`anchor-not-in-diff`, `range-inverted`, `range-too-wide`, `not-text`,
`no-such-commit` and `no-such-path` appear nowhere below. So do
`precondition-failed`, which is `If-Match` against a thread that moved,
`unreadable-record`, which is a record that will not parse, and `git-failed`
and `github-rejected`, which are how an operation settles rather than how a
request is refused.

**Two of the triggers never address a thread.** `create-draft` and
`send-review` are custom methods on the pull request's own operations
collection, so asking for either at `/api/conversations/{key}/operations:` is a
path that does not exist. Every row for them is `not-found`, and they are in
the table only because the trigger set is every `OperationKind`.

**`posted` is written, not asked for.** `send-review` appends it to each draft
it posted. Its rows say which thread the domain may write it onto.

**One operation at a time is a precondition, not a row.** A verb asked for
while another is still outstanding is refused `operation-outstanding`, which
the `Outstanding` response already names. The domain checks that against
`operations[]` before it reaches the machine, so no row below encodes it, and
every row that accepts a verb is read as accepting it when nothing else is in
flight.

## Reading the trigger column

**Four triggers are not requests.** `pick-up`, `settle-applied`,
`settle-refused` and `requeue` are an operation's own state moving: `pending`
to `running` as the drain takes it, to `applied` or `refused` as it ends, and
to `requeued` when the board puts it back for the next pass. Nobody asks for
them, so nothing can refuse them and no row for one carries a code. Without
them `queued` to `working`, `working` to `ready`, `rework` to `ready`,
`in-session` to `ready` and `landing` to `done` are transitions the machine has
to make and the table cannot name.

**They act on whatever operation is outstanding.** In the five working states
that is the run the state is named for: `queued` and `working` split one run's
`pending` from its `running`, and `rework`, `in-session` and `landing` each
cover both for their own kind, which is why `pick-up` moves a thread out of
`queued` and is a self-loop on the other three. In `draft`, `ready`, `waiting`
and `deferred` it is a verb that touches GitHub — `post-now`, `reply`,
`resolve` or `reject` — which the board accepts without moving the thread and
which moves it when it applies, so `settle-applied` there is qualified by the
kind that settled. `enrolled` and `done` are the only two states that can have
nothing outstanding at all.

**A row with `—` in both columns is not an edge.** The event cannot arise from
that state: there is nothing pending for `pick-up` to take in `working`,
nothing that has run for `settle-applied` to report in `queued`, and nothing in
flight at all in `enrolled` and `done`. A row whose `to` repeats its `from` is
the other case — the event arises and leaves the thread where it was.

**`requeue` arises only where the board has something to put back.** A run it
lost or that failed with attempts to spare goes back from `working` to `queued`
and from `rework` to itself; an approve waiting on a live agent or a dirty
worktree is put off in `ready`; an approve whose pick conflicted waits in
`landing` behind the rebase it queued. Nothing puts back a run that has not
been picked up, a session, or a verb posting to GitHub, so `queued`,
`in-session`, `waiting` and `deferred` carry `—` in both columns. Phase 0 had
them as self-loops; driving the table in phase 5 found no event that reaches
them, and phase 6 found the same of `draft`, whose only outstanding work is a
`post-now` that settles one way or the other in the pass that takes it.

Four facts decide an edge that the state alone cannot, and each is appended to
the trigger in parentheses. All four are readable from `Conversation` as the
contract already ships it, on `operations[]`, whose members are
`OperationSummary` and carry `kind`, `state` and `reason_code`.

**(a proposal is waiting) and (no proposal).** A proposal is waiting when
nothing is in flight and the newest `first`, `rebase`, `rework`, `retry` or
`start-session` operation settled `applied`. One that settled `refused` left
none, whatever its `reason_code`, so a declined run, a run that spent its
attempts and a run that committed nothing are one case here.

**(closed by `approve`), (closed by `reject`), (closed by `resolve`),
(closed by `confirm`) and (closed by `discard`).** Which of the five applied
operations put the thread in `done`. `unpark` takes every one of them back, and
needs it to know where to put it.

**`place` is read with `to: waiting`.** It moves a thread an agent placed in
`assumed-done` or `not-mine` to the state it names, which only someone else's
PR takes `not-mine` for and only your own takes `queued` for; the other
targets are in `tests/conversation/test_placing.py`, and `waiting` is the one
both roles take.

**(the kind is `approve`) and (the kind is `rebase`).** `landing` holds either,
and applied they end differently: an approve that applies has picked, pushed
and answered, so the thread is `done`; a rebase that applies has only caught
the proposal up with the head, so the thread is `ready` with that proposal
still waiting. Refused, both leave the thread `ready`, so `settle-refused`
needs no qualifier.

**(the kind is `reply`), (the kind is `resolve`), (the kind is `reject`) and
(the kind is `post-now`).** Which of the four verbs that touch GitHub was
outstanding when it applied. An applied `reply` parks the thread on the other
party and an applied `post-now` puts the draft it posted there too; an applied
`resolve` or `reject` closes the thread. Refused, all four leave the thread
where they found it, so `settle-refused` needs no qualifier here either.

## The transition table

| from           | trigger                                   | to             | code                    |
| -------------- | ----------------------------------------- | -------------- | ----------------------- |
| `draft`        | `first`                                   | —              | `still-a-draft`         |
| `draft`        | `rebase`                                  | —              | `still-a-draft`         |
| `draft`        | `rework`                                  | —              | `no-proposal`           |
| `draft`        | `retry`                                   | —              | `still-a-draft`         |
| `draft`        | `start-session`                           | —              | `still-a-draft`         |
| `draft`        | `approve`                                 | —              | `no-proposal`           |
| `draft`        | `stop`                                    | —              | `nothing-in-flight`     |
| `draft`        | `resolve`                                 | —              | `still-a-draft`         |
| `draft`        | `reject`                                  | —              | `no-proposal`           |
| `draft`        | `defer`                                   | —              | `still-a-draft`         |
| `draft`        | `unpark`                                  | —              | `not-parked`            |
| `draft`        | `confirm`                                 | —              | `not-parked`            |
| `draft`        | `place`                                   | —              | `not-parked`            |
| `draft`        | `reply`                                   | —              | `still-a-draft`         |
| `draft`        | `create-draft`                            | —              | `not-found`             |
| `draft`        | `edit-draft`                              | `draft`        | —                       |
| `draft`        | `enrol`                                   | `enrolled`     | —                       |
| `draft`        | `withdraw-from-review`                    | —              | `nothing-enrolled`      |
| `draft`        | `discard`                                 | `done`         | —                       |
| `draft`        | `post-now`                                | `draft`        | —                       |
| `draft`        | `send-review`                             | —              | `not-found`             |
| `draft`        | `posted`                                  | —              | `nothing-enrolled`      |
| `draft`        | `comment`                                 | —              | `not-found`             |
| `draft`        | `pick-up`                                 | `draft`        | —                       |
| `draft`        | `settle-applied` (the kind is `post-now`) | `waiting`      | —                       |
| `draft`        | `settle-refused`                          | `draft`        | —                       |
| `draft`        | `requeue`                                 | —              | —                       |
| `enrolled`     | `first`                                   | —              | `still-a-draft`         |
| `enrolled`     | `rebase`                                  | —              | `still-a-draft`         |
| `enrolled`     | `rework`                                  | —              | `no-proposal`           |
| `enrolled`     | `retry`                                   | —              | `still-a-draft`         |
| `enrolled`     | `start-session`                           | —              | `still-a-draft`         |
| `enrolled`     | `approve`                                 | —              | `no-proposal`           |
| `enrolled`     | `stop`                                    | —              | `nothing-in-flight`     |
| `enrolled`     | `resolve`                                 | —              | `still-a-draft`         |
| `enrolled`     | `reject`                                  | —              | `no-proposal`           |
| `enrolled`     | `defer`                                   | —              | `still-a-draft`         |
| `enrolled`     | `unpark`                                  | —              | `not-parked`            |
| `enrolled`     | `confirm`                                 | —              | `not-parked`            |
| `enrolled`     | `place`                                   | —              | `not-parked`            |
| `enrolled`     | `reply`                                   | —              | `still-a-draft`         |
| `enrolled`     | `create-draft`                            | —              | `not-found`             |
| `enrolled`     | `edit-draft`                              | `enrolled`     | —                       |
| `enrolled`     | `enrol`                                   | —              | `already-enrolled`      |
| `enrolled`     | `withdraw-from-review`                    | `draft`        | —                       |
| `enrolled`     | `discard`                                 | —              | `already-enrolled`      |
| `enrolled`     | `post-now`                                | —              | `already-enrolled`      |
| `enrolled`     | `send-review`                             | —              | `not-found`             |
| `enrolled`     | `posted`                                  | `waiting`      | —                       |
| `enrolled`     | `comment`                                 | —              | `not-found`             |
| `enrolled`     | `pick-up`                                 | —              | —                       |
| `enrolled`     | `settle-applied`                          | —              | —                       |
| `enrolled`     | `settle-refused`                          | —              | —                       |
| `enrolled`     | `requeue`                                 | —              | —                       |
| `queued`       | `first`                                   | —              | `operation-outstanding` |
| `queued`       | `rebase`                                  | —              | `operation-outstanding` |
| `queued`       | `rework`                                  | —              | `operation-outstanding` |
| `queued`       | `retry`                                   | —              | `operation-outstanding` |
| `queued`       | `start-session`                           | —              | `operation-outstanding` |
| `queued`       | `approve`                                 | —              | `operation-outstanding` |
| `queued`       | `stop`                                    | `ready`        | —                       |
| `queued`       | `resolve`                                 | —              | `operation-outstanding` |
| `queued`       | `reject`                                  | —              | `work-in-flight`        |
| `queued`       | `defer`                                   | `deferred`     | —                       |
| `queued`       | `unpark`                                  | —              | `not-parked`            |
| `queued`       | `confirm`                                 | —              | `not-parked`            |
| `queued`       | `place`                                   | —              | `not-parked`            |
| `queued`       | `reply`                                   | `queued`       | —                       |
| `queued`       | `create-draft`                            | —              | `not-found`             |
| `queued`       | `edit-draft`                              | —              | `not-a-draft`           |
| `queued`       | `enrol`                                   | —              | `not-a-draft`           |
| `queued`       | `withdraw-from-review`                    | —              | `not-a-draft`           |
| `queued`       | `discard`                                 | —              | `not-a-draft`           |
| `queued`       | `post-now`                                | —              | `not-a-draft`           |
| `queued`       | `send-review`                             | —              | `not-found`             |
| `queued`       | `posted`                                  | —              | `not-a-draft`           |
| `queued`       | `comment`                                 | `queued`       | —                       |
| `queued`       | `pick-up`                                 | `working`      | —                       |
| `queued`       | `settle-applied`                          | —              | —                       |
| `queued`       | `settle-refused`                          | `ready`        | —                       |
| `queued`       | `requeue`                                 | —              | —                       |
| `working`      | `first`                                   | —              | `operation-outstanding` |
| `working`      | `rebase`                                  | —              | `operation-outstanding` |
| `working`      | `rework`                                  | —              | `operation-outstanding` |
| `working`      | `retry`                                   | —              | `operation-outstanding` |
| `working`      | `start-session`                           | —              | `operation-outstanding` |
| `working`      | `approve`                                 | —              | `operation-outstanding` |
| `working`      | `stop`                                    | `ready`        | —                       |
| `working`      | `resolve`                                 | —              | `operation-outstanding` |
| `working`      | `reject`                                  | —              | `work-in-flight`        |
| `working`      | `defer`                                   | `deferred`     | —                       |
| `working`      | `unpark`                                  | —              | `not-parked`            |
| `working`      | `confirm`                                 | —              | `not-parked`            |
| `working`      | `place`                                   | —              | `not-parked`            |
| `working`      | `reply`                                   | `working`      | —                       |
| `working`      | `create-draft`                            | —              | `not-found`             |
| `working`      | `edit-draft`                              | —              | `not-a-draft`           |
| `working`      | `enrol`                                   | —              | `not-a-draft`           |
| `working`      | `withdraw-from-review`                    | —              | `not-a-draft`           |
| `working`      | `discard`                                 | —              | `not-a-draft`           |
| `working`      | `post-now`                                | —              | `not-a-draft`           |
| `working`      | `send-review`                             | —              | `not-found`             |
| `working`      | `posted`                                  | —              | `not-a-draft`           |
| `working`      | `comment`                                 | `working`      | —                       |
| `working`      | `pick-up`                                 | —              | —                       |
| `working`      | `settle-applied`                          | `ready`        | —                       |
| `working`      | `settle-refused`                          | `ready`        | —                       |
| `working`      | `requeue`                                 | `queued`       | —                       |
| `in-session`   | `first`                                   | —              | `operation-outstanding` |
| `in-session`   | `rebase`                                  | —              | `operation-outstanding` |
| `in-session`   | `rework`                                  | —              | `operation-outstanding` |
| `in-session`   | `retry`                                   | —              | `operation-outstanding` |
| `in-session`   | `start-session`                           | —              | `operation-outstanding` |
| `in-session`   | `approve`                                 | —              | `operation-outstanding` |
| `in-session`   | `stop`                                    | `ready`        | —                       |
| `in-session`   | `resolve`                                 | —              | `operation-outstanding` |
| `in-session`   | `reject`                                  | —              | `work-in-flight`        |
| `in-session`   | `defer`                                   | `deferred`     | —                       |
| `in-session`   | `unpark`                                  | —              | `not-parked`            |
| `in-session`   | `confirm`                                 | —              | `not-parked`            |
| `in-session`   | `place`                                   | —              | `not-parked`            |
| `in-session`   | `reply`                                   | `in-session`   | —                       |
| `in-session`   | `create-draft`                            | —              | `not-found`             |
| `in-session`   | `edit-draft`                              | —              | `not-a-draft`           |
| `in-session`   | `enrol`                                   | —              | `not-a-draft`           |
| `in-session`   | `withdraw-from-review`                    | —              | `not-a-draft`           |
| `in-session`   | `discard`                                 | —              | `not-a-draft`           |
| `in-session`   | `post-now`                                | —              | `not-a-draft`           |
| `in-session`   | `send-review`                             | —              | `not-found`             |
| `in-session`   | `posted`                                  | —              | `not-a-draft`           |
| `in-session`   | `comment`                                 | `in-session`   | —                       |
| `in-session`   | `pick-up`                                 | `in-session`   | —                       |
| `in-session`   | `settle-applied`                          | `ready`        | —                       |
| `in-session`   | `settle-refused`                          | `ready`        | —                       |
| `in-session`   | `requeue`                                 | —              | —                       |
| `rework`       | `first`                                   | —              | `operation-outstanding` |
| `rework`       | `rebase`                                  | —              | `operation-outstanding` |
| `rework`       | `rework`                                  | —              | `operation-outstanding` |
| `rework`       | `retry`                                   | —              | `operation-outstanding` |
| `rework`       | `start-session`                           | —              | `operation-outstanding` |
| `rework`       | `approve`                                 | —              | `operation-outstanding` |
| `rework`       | `stop`                                    | `ready`        | —                       |
| `rework`       | `resolve`                                 | —              | `operation-outstanding` |
| `rework`       | `reject`                                  | —              | `work-in-flight`        |
| `rework`       | `defer`                                   | `deferred`     | —                       |
| `rework`       | `unpark`                                  | —              | `not-parked`            |
| `rework`       | `confirm`                                 | —              | `not-parked`            |
| `rework`       | `place`                                   | —              | `not-parked`            |
| `rework`       | `reply`                                   | `rework`       | —                       |
| `rework`       | `create-draft`                            | —              | `not-found`             |
| `rework`       | `edit-draft`                              | —              | `not-a-draft`           |
| `rework`       | `enrol`                                   | —              | `not-a-draft`           |
| `rework`       | `withdraw-from-review`                    | —              | `not-a-draft`           |
| `rework`       | `discard`                                 | —              | `not-a-draft`           |
| `rework`       | `post-now`                                | —              | `not-a-draft`           |
| `rework`       | `send-review`                             | —              | `not-found`             |
| `rework`       | `posted`                                  | —              | `not-a-draft`           |
| `rework`       | `comment`                                 | `rework`       | —                       |
| `rework`       | `pick-up`                                 | `rework`       | —                       |
| `rework`       | `settle-applied`                          | `ready`        | —                       |
| `rework`       | `settle-refused`                          | `ready`        | —                       |
| `rework`       | `requeue`                                 | `rework`       | —                       |
| `landing`      | `first`                                   | —              | `operation-outstanding` |
| `landing`      | `rebase`                                  | `landing`      | —                       |
| `landing`      | `rework`                                  | —              | `operation-outstanding` |
| `landing`      | `retry`                                   | —              | `operation-outstanding` |
| `landing`      | `start-session`                           | —              | `operation-outstanding` |
| `landing`      | `approve`                                 | —              | `operation-outstanding` |
| `landing`      | `stop`                                    | `ready`        | —                       |
| `landing`      | `resolve`                                 | —              | `operation-outstanding` |
| `landing`      | `reject`                                  | —              | `work-in-flight`        |
| `landing`      | `defer`                                   | —              | `operation-outstanding` |
| `landing`      | `unpark`                                  | —              | `not-parked`            |
| `landing`      | `confirm`                                 | —              | `not-parked`            |
| `landing`      | `place`                                   | —              | `not-parked`            |
| `landing`      | `reply`                                   | `landing`      | —                       |
| `landing`      | `create-draft`                            | —              | `not-found`             |
| `landing`      | `edit-draft`                              | —              | `not-a-draft`           |
| `landing`      | `enrol`                                   | —              | `not-a-draft`           |
| `landing`      | `withdraw-from-review`                    | —              | `not-a-draft`           |
| `landing`      | `discard`                                 | —              | `not-a-draft`           |
| `landing`      | `post-now`                                | —              | `not-a-draft`           |
| `landing`      | `send-review`                             | —              | `not-found`             |
| `landing`      | `posted`                                  | —              | `not-a-draft`           |
| `landing`      | `comment`                                 | `landing`      | —                       |
| `landing`      | `pick-up`                                 | `landing`      | —                       |
| `landing`      | `settle-applied` (the kind is `approve`)  | `done`         | —                       |
| `landing`      | `settle-applied` (the kind is `rebase`)   | `ready`        | —                       |
| `landing`      | `settle-refused`                          | `ready`        | —                       |
| `landing`      | `requeue`                                 | `landing`      | —                       |
| `ready`        | `first`                                   | `queued`       | —                       |
| `ready`        | `rebase` (a proposal is waiting)          | `landing`      | —                       |
| `ready`        | `rebase` (no proposal)                    | —              | `no-proposal`           |
| `ready`        | `rework`                                  | `rework`       | —                       |
| `ready`        | `retry` (no proposal)                     | `queued`       | —                       |
| `ready`        | `retry` (a proposal is waiting)           | —              | `proposal-exists`       |
| `ready`        | `start-session`                           | `in-session`   | —                       |
| `ready`        | `approve` (a proposal is waiting)         | `landing`      | —                       |
| `ready`        | `approve` (no proposal)                   | —              | `no-proposal`           |
| `ready`        | `stop` (a proposal is waiting)            | —              | `proposal-exists`       |
| `ready`        | `stop` (no proposal)                      | —              | `nothing-in-flight`     |
| `ready`        | `resolve`                                 | `ready`        | —                       |
| `ready`        | `reject` (a proposal is waiting)          | `ready`        | —                       |
| `ready`        | `reject` (no proposal)                    | `ready`        | —                       |
| `ready`        | `defer`                                   | `deferred`     | —                       |
| `ready`        | `unpark`                                  | —              | `not-parked`            |
| `ready`        | `confirm`                                 | —              | `not-parked`            |
| `ready`        | `place`                                   | —              | `not-parked`            |
| `ready`        | `reply`                                   | `ready`        | —                       |
| `ready`        | `create-draft`                            | —              | `not-found`             |
| `ready`        | `edit-draft`                              | —              | `not-a-draft`           |
| `ready`        | `enrol`                                   | —              | `not-a-draft`           |
| `ready`        | `withdraw-from-review`                    | —              | `not-a-draft`           |
| `ready`        | `discard`                                 | —              | `not-a-draft`           |
| `ready`        | `post-now`                                | —              | `not-a-draft`           |
| `ready`        | `send-review`                             | —              | `not-found`             |
| `ready`        | `posted`                                  | —              | `not-a-draft`           |
| `ready`        | `comment`                                 | `ready`        | —                       |
| `ready`        | `pick-up`                                 | `ready`        | —                       |
| `ready`        | `settle-applied` (the kind is `reply`)    | `waiting`      | —                       |
| `ready`        | `settle-applied` (the kind is `resolve`)  | `done`         | —                       |
| `ready`        | `settle-applied` (the kind is `reject`)   | `done`         | —                       |
| `ready`        | `settle-refused`                          | `ready`        | —                       |
| `ready`        | `requeue`                                 | `ready`        | —                       |
| `waiting`      | `first`                                   | —              | `parked`                |
| `waiting`      | `rebase`                                  | —              | `parked`                |
| `waiting`      | `rework`                                  | —              | `parked`                |
| `waiting`      | `retry`                                   | —              | `parked`                |
| `waiting`      | `start-session`                           | —              | `parked`                |
| `waiting`      | `approve`                                 | —              | `parked`                |
| `waiting`      | `stop` (a proposal is waiting)            | —              | `proposal-exists`       |
| `waiting`      | `stop` (no proposal)                      | —              | `nothing-in-flight`     |
| `waiting`      | `resolve`                                 | `waiting`      | —                       |
| `waiting`      | `reject`                                  | —              | `parked`                |
| `waiting`      | `defer`                                   | `deferred`     | —                       |
| `waiting`      | `unpark`                                  | `ready`        | —                       |
| `waiting`      | `confirm`                                 | —              | `not-parked`            |
| `waiting`      | `place`                                   | —              | `not-parked`            |
| `waiting`      | `reply`                                   | `waiting`      | —                       |
| `waiting`      | `create-draft`                            | —              | `not-found`             |
| `waiting`      | `edit-draft`                              | —              | `not-a-draft`           |
| `waiting`      | `enrol`                                   | —              | `not-a-draft`           |
| `waiting`      | `withdraw-from-review`                    | —              | `not-a-draft`           |
| `waiting`      | `discard`                                 | —              | `not-a-draft`           |
| `waiting`      | `post-now`                                | —              | `not-a-draft`           |
| `waiting`      | `send-review`                             | —              | `not-found`             |
| `waiting`      | `posted`                                  | —              | `not-a-draft`           |
| `waiting`      | `comment`                                 | `ready`        | —                       |
| `waiting`      | `pick-up`                                 | `waiting`      | —                       |
| `waiting`      | `settle-applied` (the kind is `reply`)    | `waiting`      | —                       |
| `waiting`      | `settle-applied` (the kind is `resolve`)  | `done`         | —                       |
| `waiting`      | `settle-refused`                          | `waiting`      | —                       |
| `waiting`      | `requeue`                                 | —              | —                       |
| `deferred`     | `first`                                   | —              | `parked`                |
| `deferred`     | `rebase`                                  | —              | `parked`                |
| `deferred`     | `rework`                                  | —              | `parked`                |
| `deferred`     | `retry`                                   | —              | `parked`                |
| `deferred`     | `start-session`                           | —              | `parked`                |
| `deferred`     | `approve`                                 | —              | `parked`                |
| `deferred`     | `stop` (a proposal is waiting)            | —              | `proposal-exists`       |
| `deferred`     | `stop` (no proposal)                      | —              | `nothing-in-flight`     |
| `deferred`     | `resolve`                                 | `deferred`     | —                       |
| `deferred`     | `reject`                                  | —              | `parked`                |
| `deferred`     | `defer`                                   | `deferred`     | —                       |
| `deferred`     | `unpark`                                  | `ready`        | —                       |
| `deferred`     | `confirm`                                 | —              | `not-parked`            |
| `deferred`     | `place`                                   | —              | `not-parked`            |
| `deferred`     | `reply`                                   | `deferred`     | —                       |
| `deferred`     | `create-draft`                            | —              | `not-found`             |
| `deferred`     | `edit-draft`                              | —              | `not-a-draft`           |
| `deferred`     | `enrol`                                   | —              | `not-a-draft`           |
| `deferred`     | `withdraw-from-review`                    | —              | `not-a-draft`           |
| `deferred`     | `discard`                                 | —              | `not-a-draft`           |
| `deferred`     | `post-now`                                | —              | `not-a-draft`           |
| `deferred`     | `send-review`                             | —              | `not-found`             |
| `deferred`     | `posted`                                  | —              | `not-a-draft`           |
| `deferred`     | `comment`                                 | `ready`        | —                       |
| `deferred`     | `pick-up`                                 | `deferred`     | —                       |
| `deferred`     | `settle-applied` (the kind is `reply`)    | `waiting`      | —                       |
| `deferred`     | `settle-applied` (the kind is `resolve`)  | `done`         | —                       |
| `deferred`     | `settle-refused`                          | `deferred`     | —                       |
| `deferred`     | `requeue`                                 | —              | —                       |
| `assumed-done` | `first`                                   | —              | `parked`                |
| `assumed-done` | `rebase`                                  | —              | `parked`                |
| `assumed-done` | `rework`                                  | —              | `parked`                |
| `assumed-done` | `retry`                                   | —              | `parked`                |
| `assumed-done` | `start-session`                           | —              | `parked`                |
| `assumed-done` | `approve`                                 | —              | `no-proposal`           |
| `assumed-done` | `stop` (a proposal is waiting)            | —              | `proposal-exists`       |
| `assumed-done` | `stop` (no proposal)                      | —              | `nothing-in-flight`     |
| `assumed-done` | `resolve`                                 | `assumed-done` | —                       |
| `assumed-done` | `reject`                                  | —              | `parked`                |
| `assumed-done` | `defer`                                   | `deferred`     | —                       |
| `assumed-done` | `unpark`                                  | —              | `not-parked`            |
| `assumed-done` | `confirm`                                 | `done`         | —                       |
| `assumed-done` | `place`                                   | `waiting`      | —                       |
| `assumed-done` | `reply`                                   | `assumed-done` | —                       |
| `assumed-done` | `create-draft`                            | —              | `not-found`             |
| `assumed-done` | `edit-draft`                              | —              | `not-a-draft`           |
| `assumed-done` | `enrol`                                   | —              | `not-a-draft`           |
| `assumed-done` | `withdraw-from-review`                    | —              | `not-a-draft`           |
| `assumed-done` | `discard`                                 | —              | `not-a-draft`           |
| `assumed-done` | `post-now`                                | —              | `not-a-draft`           |
| `assumed-done` | `send-review`                             | —              | `not-found`             |
| `assumed-done` | `posted`                                  | —              | `not-a-draft`           |
| `assumed-done` | `comment`                                 | `ready`        | —                       |
| `assumed-done` | `pick-up`                                 | `assumed-done` | —                       |
| `assumed-done` | `settle-applied` (the kind is `reply`)    | `waiting`      | —                       |
| `assumed-done` | `settle-applied` (the kind is `resolve`)  | `done`         | —                       |
| `assumed-done` | `settle-refused`                          | `assumed-done` | —                       |
| `assumed-done` | `requeue`                                 | —              | —                       |
| `not-mine`     | `first`                                   | —              | `parked`                |
| `not-mine`     | `rebase`                                  | —              | `parked`                |
| `not-mine`     | `rework`                                  | —              | `parked`                |
| `not-mine`     | `retry`                                   | —              | `parked`                |
| `not-mine`     | `start-session`                           | —              | `parked`                |
| `not-mine`     | `approve`                                 | —              | `no-proposal`           |
| `not-mine`     | `stop` (a proposal is waiting)            | —              | `proposal-exists`       |
| `not-mine`     | `stop` (no proposal)                      | —              | `nothing-in-flight`     |
| `not-mine`     | `resolve`                                 | `not-mine`     | —                       |
| `not-mine`     | `reject`                                  | —              | `parked`                |
| `not-mine`     | `defer`                                   | `deferred`     | —                       |
| `not-mine`     | `unpark`                                  | —              | `not-parked`            |
| `not-mine`     | `confirm`                                 | —              | `not-parked`            |
| `not-mine`     | `place`                                   | `waiting`      | —                       |
| `not-mine`     | `reply`                                   | `not-mine`     | —                       |
| `not-mine`     | `create-draft`                            | —              | `not-found`             |
| `not-mine`     | `edit-draft`                              | —              | `not-a-draft`           |
| `not-mine`     | `enrol`                                   | —              | `not-a-draft`           |
| `not-mine`     | `withdraw-from-review`                    | —              | `not-a-draft`           |
| `not-mine`     | `discard`                                 | —              | `not-a-draft`           |
| `not-mine`     | `post-now`                                | —              | `not-a-draft`           |
| `not-mine`     | `send-review`                             | —              | `not-found`             |
| `not-mine`     | `posted`                                  | —              | `not-a-draft`           |
| `not-mine`     | `comment`                                 | `ready`        | —                       |
| `not-mine`     | `pick-up`                                 | `not-mine`     | —                       |
| `not-mine`     | `settle-applied` (the kind is `reply`)    | `waiting`      | —                       |
| `not-mine`     | `settle-applied` (the kind is `resolve`)  | `done`         | —                       |
| `not-mine`     | `settle-refused`                          | `not-mine`     | —                       |
| `not-mine`     | `requeue`                                 | —              | —                       |
| `done`         | `first` (closed by `approve`)             | `queued`       | —                       |
| `done`         | `first` (closed by `resolve`)             | —              | `already-closed`        |
| `done`         | `first` (closed by `reject`)              | —              | `already-closed`        |
| `done`         | `first` (closed by `discard`)             | —              | `already-closed`        |
| `done`         | `first` (closed by `confirm`)             | —              | `already-closed`        |
| `done`         | `rebase`                                  | —              | `already-closed`        |
| `done`         | `rework`                                  | —              | `already-closed`        |
| `done`         | `retry`                                   | —              | `already-closed`        |
| `done`         | `start-session`                           | —              | `already-closed`        |
| `done`         | `approve`                                 | —              | `already-closed`        |
| `done`         | `stop`                                    | —              | `nothing-in-flight`     |
| `done`         | `resolve`                                 | —              | `already-closed`        |
| `done`         | `reject`                                  | —              | `already-closed`        |
| `done`         | `defer`                                   | —              | `already-closed`        |
| `done`         | `unpark` (closed by `resolve`)            | `ready`        | —                       |
| `done`         | `unpark` (closed by `reject`)             | `queued`       | —                       |
| `done`         | `unpark` (closed by `discard`)            | `draft`        | —                       |
| `done`         | `unpark` (closed by `approve`)            | `queued`       | —                       |
| `done`         | `unpark` (closed by `confirm`)            | `ready`        | —                       |
| `done`         | `confirm`                                 | —              | `not-parked`            |
| `done`         | `place`                                   | —              | `not-parked`            |
| `done`         | `reply`                                   | —              | `already-closed`        |
| `done`         | `create-draft`                            | —              | `not-found`             |
| `done`         | `edit-draft`                              | —              | `already-closed`        |
| `done`         | `enrol`                                   | —              | `already-closed`        |
| `done`         | `withdraw-from-review`                    | —              | `already-closed`        |
| `done`         | `discard`                                 | —              | `already-closed`        |
| `done`         | `post-now`                                | —              | `already-closed`        |
| `done`         | `send-review`                             | —              | `not-found`             |
| `done`         | `posted`                                  | —              | `already-closed`        |
| `done`         | `comment` (closed by `resolve`)           | `ready`        | —                       |
| `done`         | `comment` (closed by `reject`)            | `ready`        | —                       |
| `done`         | `comment` (closed by `approve`)           | `done`         | —                       |
| `done`         | `comment` (closed by `discard`)           | `done`         | —                       |
| `done`         | `comment` (closed by `confirm`)           | `ready`        | —                       |
| `done`         | `pick-up`                                 | —              | —                       |
| `done`         | `settle-applied`                          | —              | —                       |
| `done`         | `settle-refused`                          | —              | —                       |
| `done`         | `requeue`                                 | —              | —                       |

## The group rewrite

Both boards group cards by vocabulary the contract removed. Every row is
rewritten here in terms of what it ships. A row that rewrites proves the
contract carries enough for that heading; a row that does not names what the
contract would have to add.

`2026-09-12-review-board-redesign-design.md:84-93`, the author's board:

| old group            | old contents                                                                                                                       | new predicate                             | verdict      |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- | ------------ |
| Ready for you        | "`open` with a fix `proposed`, `declined` or `failed`, or no fix; `removed`; a reopened `open` whose fix is `queued` or `running`" | `reopened` is true, or `state` is `ready` | **rewrites** |
| Agent working        | "`open`, fix `running` on a `first` run, not reopened"                                                                             | `state` is `working`                      | **rewrites** |
| Queued for agent     | "`open`, fix `queued` for a `first` run, not reopened"                                                                             | `state` is `queued`                       | **rewrites** |
| Sent back for rework | "`open`, fix `queued` or `running` on a `rework` run, or `in_session`"                                                             | `state` is `rework` or `in-session`       | **rewrites** |
| Landing              | "`open`, fix `landing`, or `queued` or `running` on a `rebase` run"                                                                | `state` is `landing`                      | **rewrites** |
| Waiting on reviewer  | "`waiting_on_reviewer`"                                                                                                            | `state` is `waiting`                      | **rewrites** |
| Deferred             | "`deferred`"                                                                                                                       | `state` is `deferred`                     | **rewrites** |
| Done                 | "`open` with fix `landed`; `rejected`; `resolved`"                                                                                 | `state` is `done`                         | **rewrites** |

`2026-09-21-reviewer-board-design.md:55-59`, the reviewer's:

| old group         | old contents                                   | new predicate                                               | verdict      |
| ----------------- | ---------------------------------------------- | ----------------------------------------------------------- | ------------ |
| Answered          | "`open`"                                       | `reopened` is true, or `state` is `ready`                   | **rewrites** |
| Your review       | "`draft`, `pending`"                           | `state` is `draft` or `enrolled`                            | **rewrites** |
| Waiting on author | "`waiting_on_reviewer`, labelled for the role" | `state` is `waiting`, with the word chosen by `viewer_role` | **rewrites** |
| Deferred          | "`deferred`"                                   | `state` is `deferred`                                       | **rewrites** |
| Done              | "`resolved`, `rejected`"                       | `state` is `done`                                           | **rewrites** |

Every row rewrites. Four of them fold two states under one heading or one state
under two headings, which is allowed: labels and grouping are the front end's,
and the contract ships only `state` and the flag. Sent back for rework takes
`rework` and `in-session`; Landing takes `landing`, which is both a pick in
progress and a rebase run in flight, and the card tells them apart by the
newest operation's `kind`; Done takes `done` however the thread got there;
Answered and Ready for you are the same predicate under two words. Ready for
you reads the flag first and the state second, so a reopened thread appears
there whatever else is happening to it, which is the clause the enum could not
carry.

Three old distinctions survive on the operation rather than on the state.
Whether a run proposed, declined or spent its attempts is the newest fix
operation's `state` and `reason_code`. Whether a landing failed at the push or
at the reply is the approve operation settling `refused` with `push-failed` or
`reply-failed`, at which point the thread is `ready` again, which is where
`group_of` puts it today. Whether GitHub still has the thread is
`github_removed`, a field, so `removed` stops being a state without taking the
Ready for you heading's third clause with it.

### What was missing

Two rows above rewrite only because the contract changed first. What was
missing, and what answered it:

**A thread cannot be `reopened` and have work in flight.** Ready for you's last
clause is "a reopened `open` whose fix is `queued` or `running`": the reviewer
replied after you had spoken, the agent is running on the new reply, and the
card sits under Ready for you until you deal with it. As two members of one
enum, `reopened` and `queued` were mutually exclusive, and `apply.py:295-303`
writes both facts in the same tick, so the enum member was overwritten before
it could ever be drawn. `reopened` left `ConversationState`, which now has
eleven members, and became a boolean on `Conversation` set and cleared by a
rule rather than by an edge, and the `(you had already spoken)` qualifier is
gone with it. `comment` is a self-loop on every state that accepts it but
`waiting`, where the other party speaking is the thing the park was waiting
for.

**A record that will not parse has no state.** `group_of` puts the synthesised
`unreadable` conversation state under Ready for you, and the card draws "this
card's record could not be read". The contract deleted it deliberately, on the
grounds that the repository should say so rather than hand back a conversation
every downstream table has to carry a row for, and gave the single-thread read
the `unreadable-record` refusal. It did not say what `/api/conversations` does,
and that path declared only `200`, `304` and a `500`. It now answers `200` with
a top-level `unreadable` array of the keys it could not read beside the threads
it could, and the `500` is gone. Not a `ConversationState` member, because a
record that will not parse has no kind, no comments and no operations to put
under one.

## Risks and open questions

**`done` maps four histories onto one state, and `unpark` has four answers.**
A landed thread and a rejected thread go back to `queued`, because both
dropped the worktree and the comment that brings either back is asking for
another fix; a resolved
thread goes back to `ready`; a discarded draft goes back to `draft`. The state
decides none of this and the operation history decides all of it. This is the
clearest evidence against the plan's bet that every history maps to exactly one
state that answers for it: four histories map to one state that answers for
none of them.

**A verb that touches GitHub shows nothing until it lands.** `reply`,
`resolve`, `reject` and `post-now` are self-loops on acceptance, so the
operator clicks Resolve and the thread is still `ready` until GitHub has the
reply. Nothing on `state` says a verb is in the air; the card has to draw the
outstanding operation off `operations[]` to show that the click did anything,
and every other verb is refused `operation-outstanding` until it settles. That
is the price of never drawing a state the server has not reached, and it is
paid on the four commonest verbs there are.

**`comment` cannot be driven as a single trigger in six states.** The table
takes a `waiting` thread to `ready`, because the park was on the other party
and they have now spoken, and makes `comment` a self-loop on `in-session`,
`landing`, `ready`, `deferred` and `done`: a deferral is parked until its
`WakeCondition` rather than until the other party speaks, and the two clocks in
the revisions document exist for "the case where someone replies again to a
thread already in its final state". `apply` matches none of the six.
`_reopen_into` re-queues the fix whenever it is not already `queued` or
`running`, so one comment fires two of the table's triggers in the same tick —
the comment arriving, and the board asking for a `first` run — and the thread
lands in `queued` wherever it started from. That one cause is behind all six.
`deferred` and `done` show it most plainly, because `_reopen` also sets the
thread `open` from any state while the table leaves both parked: both set
`reopened`, which brings the card to the front, but every work verb on a
`deferred` card is still refused `parked` and on a `done` one `already-closed`
until `unpark` moves it. Phase 5 resolved it by splitting the two: `Reopen` is
the comment and nothing else, and the poller asks for the run as a `First` of
its own, which the table refuses wherever a run is in flight or the thread is
parked or closed.

**A landed thread that gets a new comment had no way back. Resolved in phase
6.** The price of following that split into `done`. A comment on it sets
`reopened` and leaves it `done`; `first` is refused `already-closed`, and so is
every other work verb; and `unpark` refused a thread closed by `approve` with
`not-parked`. Before phase 5 the comment re-queued a run on it. `unpark` now
takes any `done` thread however it closed, and a landed one goes to `queued`
as a rejected one does, so the run the comment used to queue by itself is one
press away and `stop` turns it into `ready` if the comment wanted only a word.

**Every reply on an author's thread asks for a run. Changed 2026-09-23.** A
reply is new information, so what was decided before it is history: `comment`
takes a `deferred`, rejected or resolved thread back to `ready`, and the
poller's `first` is taken on a landed one. A comment during a run, a session
or a landing leaves the thread where it is and queues a rework on top of what
that work leaves once it settles.

**A thread's state depends on who is looking.** `Role` is "a property of the
board, not of a thread", and the machine reads it: on a reviewer's board a
thread is `ready` when the newest comment is not the opener's, and on the
author's board when a run has settled. The same record computes two states on
two boards. Nothing on this board reads two roles at once, so it is not a bug
today; it is a reason `state` cannot be cached anywhere the role is not known.

**`stop` on a `landing` takes back an approve, not a fix. Changed 2026-10-01.**
The pick lands on the PR branch itself, not in the thread's worktree, so
dropping the worktree would leave the picked commit there unpushed for the next
approve to push. Stop instead resets the PR branch to where it was before the
pick, keeps the thread's worktree, and settles the approve `refused` with
`withdrawn`: the thread is `ready` with its proposal waiting again, to approve,
rework or reject. The stop replaces the approve still waiting in the drain, so
a landing whose push keeps failing is not pushed once the network is back. When
the PR branch has moved past the pick or its worktree has changes of its own,
the branch is left alone and the approve's reason says the commit is still
there. A landing that has already pushed has nothing left to take back, so
stop refuses it `nothing-in-flight`; that thread is `ready` with
`reply-failed`, and approve again posts the reply. A rebasing `landing`, whose
approve waits behind a rebase run, still refuses stop `operation-outstanding`.

**Four of the table's edges contradict `apply` today.** `resolve` and `defer`
from `waiting` and `deferred` are allowed here, which deletes the strict
`xfail` in `tests/review/domain/test_standing.py:404`: a reviewer's parked card
is offered both and `apply` refuses both, because `_closing` and `_defer` read
those two states as the author's and refuse anything that is not `open`. The
table settles it in the direction the offer implies, so `_closing` and `_defer`
change rather than `REVIEWER_ACTIONS`.

**`defer` withdraws what is in flight.** `_defer` already issues `StopRun` on a
running fix, and the table extends that to `queued`, `in-session` and `rework`.
It contradicts the redesign's "Parking a conversation in waiting or deferred
leaves its fix exactly as it was, so the way back is one transition to `open`
and the row lands in the group its fix state puts it in". With one state field
there is nowhere for the fix state to wait, so keeping it would make `unpark`'s
destination unknowable. `defer` from `landing` is refused instead of stopping
one, which is the only place the rule is not uniform.

**`rework` and `retry` are widened and `start-session` with them.** Today
`_rework` takes `proposed` and `declined`, `_retry` takes `failed` only, and
`_start_session` takes those three. Here all three are allowed from `ready`,
with `retry` refused by `proposal-exists` when a proposal is waiting, because
it carries no brief and would otherwise throw one away in silence. Narrowing
them again means telling `ready` apart three ways, which is three qualifiers
where the contract forces one.
