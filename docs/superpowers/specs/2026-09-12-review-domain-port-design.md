# Porting the review board onto a layered domain

The review board's logic is spread across six lookup tables and a hand-written
transition whitelist, every consumer reads the JSON record's fields directly, and
the functions that decide what happens next also run git and call GitHub. A read
of the code against the redesign in `2026-09-12-review-board-redesign-design.md`
found that each hard part of that redesign was one of those three things seen
from a different angle.

This spec is the first of two. It ports the whole review board subsystem, with
no change in behaviour, onto a new package with a domain that can be tested
without git, GitHub, tmux or the filesystem, an application layer that runs
effects through ports, and adapters for everything that touches the outside
world. The redesign is built on it afterwards and is specified separately.

The decisions behind it were asked and answered on 2026-09-12 and are recorded in
the appendix.

## The package

`github_orchestrator.review`, three layers, and a rule about imports. Nothing
under `domain` imports anything outside the standard library. Nothing under
`application` imports an adapter; it imports the domain and the port interfaces
it defines itself. Adapters import both and are imported by nothing but the
process entry points and each other where one adapter needs another's port.

```
src/github_orchestrator/review/
  domain/        Conversation, Fix, commands, effects, the state machines, the diff
  application/   services that load a conversation, apply a command, run the effects
  adapters/      records, github, git, agents, board, cli, poller
```

## Domain

### Conversation

The aggregate. It is what GitHub calls a conversation when you press "Resolve
conversation": a root comment and every reply under it. The root is anchored to
a file line, to a file, or to the PR itself, and the three kinds share one
shape; the anchor is a value on the conversation, not a subtype. Conversation
comments and review summaries, which have no thread on GitHub, are conversations
of one, as today.

A conversation knows its key, its comments in order, who wrote each, which ones
the board posted itself and so must never reopen it, the one-line gist of the
root, whether GitHub holds it outdated and where its anchor was before, whether
GitHub still has the root and whether the board deleted it, and its own state:

| Conversation state | Today's status                    | Meaning                                           |
| ------------------ | --------------------------------- | ------------------------------------------------- |
| `open`             | everything not listed below       | the board is working on it or waiting for you     |
| `dismissed`        | `dismissed`, with `declined` flag | closed from the board, with or without a reply    |
| `removed`          | `removed`                         | GitHub deleted the root before the board finished |

### Fix

An entity owned by the conversation: the agent's answer to it. A conversation
has at most one current fix and keeps the earlier attempts. A fix knows the
commit it proposes by sha, the test verdict and note, the agent's note, the
reason it declined or failed, how many attempts it has spent, the head it was
cut from, its workspace by an opaque handle, and its state:

| Fix state    | Today's status                        | Meaning                                                            |
| ------------ | ------------------------------------- | ------------------------------------------------------------------ |
| `queued`     | `queued`                              | waiting for an agent; carries the kind of run wanted               |
| `running`    | `working`                             | an agent is at work; carries the kind                              |
| `declined`   | `skipped`                             | the agent classified the conversation not safe and said why        |
| `failed`     | `failed`                              | the attempt budget is spent                                        |
| `proposed`   | `ready`                               | a commit to decide on, or one that could not land, with the reason |
| `in_session` | `rejected`                            | a human is steering an agent in the fix's workspace                |
| `landing`    | `committed`, `approved` with an error | accepted; records which landing steps have succeeded               |
| `landed`     | `approved`, pushed and answered       | on the PR branch, pushed, and answered                             |

A run has a **kind**: `first`, or `rebase` onto a named head, which is today's
`rebase_onto`. A session is not a run kind. It is a fix state, because the
scheduler must never start a run into a workspace a human is typing in, and a
state the scheduler does not schedule is the only way to say that which cannot
drift. Today that safety is an accident of `rejected` being a status the pool
happens to ignore.

A fix names its commit by sha and its workspace by a handle. What a workspace is
on disk, and that it is a git worktree on a branch, is the git adapter's
knowledge alone.

### Commands

Everything that happens to a conversation, from whichever direction, is a
command applied to it. Today's commands, by where they come from:

- From the poller: a new conversation was seen; a reply arrived; the root was
  edited; a refresh that only brings comments and anchors in step.
- From the presence check: the root is gone from GitHub.
- From the agent: reported ready with a sha and verdict; declined with a
  classification and reason; failed with a reason.
- From the pool: a run started; a run exited, with the workspace head; a run
  was killed for exceeding its timeout.
- From the board: approve with an optional reply and the delete tick; reject,
  which today means open a session with an optional steer; dismiss with an
  optional reply and the delete tick; decline with the same; retry; a composer
  reply.
- From effects: a workspace was cut; the range was picked; the push succeeded;
  the reply was posted with its id; the comment was deleted; an effect failed
  with a reason; the gist was written.

Applying a command either changes state and returns the effects to perform, or
refuses with a reason. Every transition today's tests pin, allowed and
disallowed, is a domain test. The whitelist of transitions is the state
machines themselves; there is no separate table to keep in step.

### Effects

The only things the domain ever asks the outside world to do: start a run of a
kind, stop a run, open a session with a steer, cut a workspace from a head, drop
a workspace, pick a range onto the PR branch, push, post a reply with or without
a commit link, delete a comment, write the gist. A landing is a fix in `landing`
whose record says which of pick, push and answer have succeeded; each success is
a command back into the conversation, and approving again resumes at the first
step not yet done, exactly as today's approve does with its error fields.

### The diff

Today's `diff_threads` is domain code and moves in unchanged in behaviour. It
takes the previous snapshot and a fetched conversation and answers: new
comments that want an agent, changes that only want the record brought in step,
and conversations that vanished. The rules it encodes stay: a reply the board
posted never reopens, a resolved conversation is never active, an edit to the
root is active, everything else that changed is stale, and comments younger than
the cutoff wait for the next poll. Fetching is the poller adapter's job.

## Application

Services do three things and nothing else: load a conversation through the
repository port, apply a command, save it and run the effects through the other
ports, feeding each outcome back as a command. One per inbound direction:

- `decide`, for the board's verbs and the composer, draining the intent and
  reply inboxes. Today a reply on its own is never drained because the loop
  only looks for intents; `decide` drains both, and that is the one behaviour
  change this spec makes, since the old behaviour is a bug.
- `report`, for the agent's verdicts.
- `poll`, for the watcher's conversation updates: create, reopen, refresh. It
  also serves the panel's "rebuild a record the board has lost" path, which
  fetches one conversation through the GitHub port and creates it without
  queueing a fix, as `thread_repair` does today.
- `tick`, for the manager loop: pump runs, settle exited ones, requeue a running
  fix with no live run, schedule queued fixes up to the configured limit, and
  apply the presence check for the open panel.

The **read model** for the board is application code: from every conversation on
the PR it computes today's three bands, the ordering, the counts, and the
per-row and per-panel view data, including the git-derived progress line.
Drawing it is an adapter.

**Ports** the application defines and adapters implement: a conversation
repository, a GitHub client, a git client for workspaces and landing, an agent
runner that starts, pumps and stops runs and opens sessions, a summariser for
the gist, and a clock.

## Adapters

### records

The repository. One JSON document per conversation, under today's `threads/`
layout, with a `version` field the adapter owns. Every read-modify-write happens
under a per-conversation `flock` on a sibling lock file and lands as tmp, fsync,
rename, so the manager process and an agent's `cli` process can both write
without either clobbering the other. Reads take no lock; a document is always
whole.

The intent and reply files the board writes stay an inbox this adapter reads for
`decide`, in today's format: first line the decision and the optional delete
modifier, the rest one payload. Garbage is still decided by contents that do not
parse, never by the shape of a name, and intents still drain in mtime order.

The agent's last tool action stays a sibling file because it changes every second
and is display only.

**Migration.** A record without `version` is today's shape. On first touch, from
either process and under the lock, the adapter maps its status onto a
conversation state, a fix state and a run kind by the two tables above, keeps
every other field, and writes it back at version 1. Idempotent, and the tests
cover every status in the tables plus the `approved`-but-not-pushed case that
today's display code synthesises.

### github

`gh` over REST and GraphQL as today, including the raising mutation helper for
replies on real threads and the non-raising query helper for polling. Fetching
conversations, posting replies on a thread or on the PR quoting the comment,
deleting comments, checking a comment still exists.

### git

Workspaces are worktrees on branches cut from a head, under a module lock as
today. Landing is cherry-pick of the range then push, with today's timeout,
abort and conflict-diagnosis behaviour and the rebase-on-conflict requeue. The
progress count and the diff rendering live here too, since they are git reads.

### agents

The Claude subprocess pool, the prompt for each run kind, the report contract
the prompts quote, the timeout, and the tmux split for a session. The contract
is written once here and every prompt reads it; today it is copied into four
prompts and the skill, and two of the copies disagree with the CLI.

### board

The HTTP server and the page, unchanged in HTML, CSS and JavaScript, rendering
the read model. Routes, gzip, the host and origin checks, the stale-card 409.
Nothing in it decides anything.

### cli

`cli thread …` becomes an inbound adapter over `report` and `decide`, with the
same commands and flags as today.

### poller

The watcher's fetch, the snapshot, and the call into the domain diff and the
`poll` service. The watcher process, its cycle and the queue between the
processes are otherwise untouched.

## Two rules for the port

Callers move to the new package as each piece is ported, and the old module is
deleted in the same change. No compatibility shim, no re-export, no function
that makes the new layering look like the old one from the outside. If a caller
cannot be moved yet, the piece is not ready to be ported yet.

Behaviour does not change during the port, with the one exception named above.
The existing tests are the net: each is moved or rewritten against the new
layer that now owns the behaviour it checks, and the suite stays green at every
step. Where a test pinned the old storage layout or the old module boundary
rather than behaviour, it goes.

## Testing

Domain and application tests run with no subprocess, no filesystem and no
network: a conversation, a command, the expected state and effects. They are the
bulk of the new tests and they are fast. Adapter tests keep the recorded
subprocess harness and the re-record discipline; the git and GitHub adapters are
where every `make record` happens. The board adapter's page is verified in a
real browser, following the project's Chrome note, because the node harness
computes no CSS.

## Build order

1. **Domain.** Conversation, Fix, commands, effects and the two state machines,
   modelling today's behaviour exactly by the tables above. The conversation
   diff moves in from the poller. Pure tests for every transition today's tests
   pin, including the disallowed ones.
2. **Records adapter.** The versioned document, the per-conversation lock, the
   inbox, the migration.
3. **Application services** for `decide`, `report`, `poll` and `tick`, with the
   effect runner, against fake ports.
4. **git, github and agents adapters**, moved from `thread_land`, `thread_git`,
   `thread_dispatch`, `thread_progress`, `thread_diff`, `claude_run`,
   `summarize`, `gh` and `tmux`, behind the ports. The recorded subprocess tests
   move with them.
5. **The CLI, the drain and the loop** call the services. `thread_land.py` and
   the pool class are deleted in the same change.
6. **The poller** calls the domain diff and the `poll` service. `review_threads`
   keeps the fetch and loses the diff.
7. **The read model and the board adapter.** Today's bands, ordering, counts,
   rows and panel rendered from the read model; the page unchanged. The
   rendering tests that check behaviour move; the ones that regex-match function
   bodies out of the page string go, since the redesign replaces the page.
8. **Delete what is left** of `review_board.py`, `threads.py`, `thread_repair.py`
   and `presence.py` that has not already moved. CLAUDE.md and README describe
   the new layout.

Each step is a plan of its own with tests first, per CLAUDE.md, and the suite
must stay under replay: anything that spawns git needs `make record`.

## Choices made while writing this

1. **The CLI keeps writing records directly**, under the repository's lock,
   rather than dropping report files for the manager to apply. Both processes
   use one repository adapter and one `report` service.
2. **Directory and command names stay.** Records stay under `threads/`, the CLI
   stays `cli thread …`, the queue event stays `thread-activity`. Renaming them
   is a migration with no behaviour behind it and can be its own change later,
   or never.
3. **The gist is an effect.** Today it is written on a daemon thread that nothing
   waits for, and the write is dropped if the body changed meanwhile. The
   summariser port keeps the daemon thread; the drop rule moves into the domain
   as the command's precondition.
4. **`dismissed` survives the port** with today's meaning and its declined flag,
   because the port changes no behaviour. The redesign folds it into resolve.

## Appendix: the architecture decisions

Asked and answered in conversation on 2026-09-12, after a read of the code
against the redesign's decision record.

| Id  | Question                             | Answer                                                                                                    |
| --- | ------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| Q1  | One aggregate or two?                | The Fix is owned by the Conversation.                                                                     |
| Q2  | Who writes the records?              | Several processes may, and every write is atomic and under a lock; the files must be protected.           |
| Q3  | Persistence shape?                   | One versioned JSON document per conversation; the adapter owns the format and migrations.                 |
| Q4  | Refactor first or build to the spec? | Refactor everything first, behaviour unchanged, then build the redesign.                                  |
| Q5  | Where does the poller's diff sit?    | In the domain; the watcher process structure stays.                                                       |
| Q6  | Package layout?                      | A new package. Port everything over with no facade that makes the new architecture look like the old one. |

## Amendments made while implementing (2026-09-13)

Where the code and the wording above differ, the code is right and this is what
it does.

1. A pre-port document is migrated on the **first write**, not the first touch:
   reads decode it by its `status` and leave the file alone.
2. The panel's rebuild of a card the board has lost **queues a fix**, as the old
   `thread_repair` did; a thread GitHub no longer has comes back removed instead.
3. The presence check runs on the **panel GET**, not as a step of `tick`.
4. `gh`, `tmux`, `claude_run` and `claude_env` stay where they are and are
   wrapped by adapters; only `common/summarize.py` moved.
5. A reopen resets the landing progress — `steps`, `landed_base`, `landed_sha`
   and the four error and note fields (`push_error`, `reply_error`,
   `decision_error`, `reply_note`) go with the fix back to `queued`. It keeps
   `reason`: that is the agent's own account of the last attempt, and the panel
   still shows it beside the new attempt.
6. Deleting the root comment on an approve is **its own step after the push**,
   never the reply's slot.
7. `cli thread open` **ensures** a workspace rather than re-cutting one, so a
   redelivered open keeps the branch the fix already has.
8. The poller's reopen path works: the module it was ported from called
   `reopen_thread` without importing it, so every reopen raised `NameError` and
   was logged and skipped.
