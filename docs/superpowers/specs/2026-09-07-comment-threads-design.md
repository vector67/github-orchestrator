# Comment threads as the primary unit

The review board is keyed on the individual review comment. This makes a thread
of one comment and a thread of five look like five unrelated pieces of work: a
reviewer replying to their own point gets a second row, a second candidate, a
second worktree and a second branch, all racing to fix one thing. GitHub's own
resolve state never reaches the board, so a thread settled on github.com goes on
demanding a decision here. And the agent fixing a comment sees only that comment,
never the reply above it that says what the reviewer actually wants.

This replaces the comment with the **thread** as the primary record. One thread
is one row, one branch, one worktree, for the life of the pull request.

## What a thread is

A thread is GitHub's `PullRequestReviewThread`: a root review comment and every
reply under it, anchored to a path and a line, carrying its own resolved and
outdated state.

Issue comments and review-summary bodies have no thread object and never will.
They become threads of one, keyed by their own `node_id`, so every consumer sees
one record shape. `comment_type` keeps labelling them and the reply paths keep
refusing them, because there is no thread to reply into.

## Identity

The key is the GitHub node id: `PullRequestReviewThread.id` for a real thread,
the object's own `node_id` for a synthetic one. The rule is one sentence — *the
key is always a GitHub node id* — and it holds for all three comment types.

Reversed by `2026-09-22-board-api-contract-revisions.md`: the key is the
board's own and `github_node_id` is a field beside it, null until GitHub has
the thread, because a draft has a key before GitHub has anything and nothing
may ever be re-keyed.

Node ids are opaque strings, so every path built from one is percent-encoded with
an empty safe set. Modern ids (`PRRT_kwDOABCDEF0123`) contain nothing that
needs escaping and survive verbatim; legacy base64 ids carrying `=`, `+` or `/`
are encoded rather than silently growing a path component inside a branch name.
The encoding is reversible, so two distinct ids can never collide.

Three places currently parse the key back out of a filename as an integer, and
one of them **deletes what it cannot parse**: `_drain_intents` unlinks any
`.intent` whose stem is not a number. Shipping opaque keys against that code
would silently destroy every decision made on the board. The garbage rule becomes
*contents that do not parse*, never *a name that is not a number*, and intents
drain in file-mtime order — which is the decision order the numeric sort was
approximating anyway.

## Naming

The record is renamed throughout. A thread is what the board is about now, and
leaving six modules and a data directory named after the old unit would leave the
vocabulary lying about the model.

| Was                                             | Becomes                                      |
| ----------------------------------------------- | -------------------------------------------- |
| `common/candidates.py`                          | `common/threads.py`                          |
| `common/candidate_git.py`                       | `common/thread_git.py`                       |
| `github_pr_agent_manager/candidate_dispatch.py` | `github_pr_agent_manager/thread_dispatch.py` |
| `github_pr_agent_manager/candidate_land.py`     | `github_pr_agent_manager/thread_land.py`     |
| `github_pr_agent_manager/candidate_diff.py`     | `github_pr_agent_manager/thread_diff.py`     |
| `github_pr_agent_manager/candidate_repair.py`   | `github_pr_agent_manager/thread_repair.py`   |
| `CANDIDATES_DIR` / `CANDIDATE_WORKTREES_DIR`    | `THREADS_DIR` / `THREAD_WORKTREES_DIR`       |
| `candidates/` / `candidate-worktrees/`          | `threads/` / `thread-worktrees/`             |
| `orchestrator/candidate/<pr>/<id>`              | `orchestrator/thread/<pr>/<key>`             |
| `cli candidate <verb> --comment-id`             | `cli thread <verb> --thread-id`              |
| `/candidate/<id>/{diff,expand,decide}`          | `/thread/<key>/{diff,expand,decide}`         |
| `new-comments` event                            | `thread-activity` event                      |

## The poll

One GraphQL query supplies threads and their comments together. REST stops
being the source of review-comment content, and the three id watermarks
(`last_review_comment_id`, `last_issue_comment_id`, `last_review_id`) are
deleted with it.

Both connections paginate. `reviewThreads(first: 100)` today has no `pageInfo`
and no pagination, so a pull request with more than a hundred threads already
undercounts `unresolved_thread_count`; under this design it would lose thread
identity outright.

What is new is computed by diffing a stored snapshot, not by a rising id. State
holds each thread key with the ids of its comments; one comparison per poll
yields new threads, new replies and vanished threads together. The vanished case
is only visible this way, and it is what `removed` now means.

A GraphQL failure skips comment processing for that cycle and leaves everything
else flowing — CI, mergeable and closed-PR events do not depend on thread
identity and should not be held hostage to it.

## Lifecycle

A reply reopens its thread: back to `queued`, attempts reset to zero, work
restarting on the thread's existing branch rebased onto the PR head. A new reply
is new information, so the old attempt count does not count against it.
`approved` and `dismissed` stop being terminal in `ALLOWED_TRANSITIONS`.

Two things do not reopen a thread:

- **Replies the board posted itself.** `posted_reply_ids` already collects the
  ids of replies sent on approve and decline; it extends to cover the panel's
  reply box. This is the whole of the loop protection — approve posts a reply,
  and without this the row it just closed returns on the next poll, forever.
- **Threads GitHub reports resolved.** Read-only: resolving on github.com settles
  the row here, and nothing the board does ever writes that flag back.

`removed` now means the whole thread is gone from GitHub. Deleting one comment
from a live thread changes the transcript and nothing else, which retires most of
the current `removed`-versus-`comment_deleted` apparatus.

## The board

Rows sort on thread creation. Sorting on last activity would make a row jump
every time somebody typed a reply, and the band move already carries that signal
— the hold-and-`pending-move` machinery exists precisely because rows moving
under a reader is a cost worth not paying twice for one event.

A row gains a reply count and an `Outdated` badge. Its gist is regenerated over
the whole thread when the thread reopens. This changes a documented rule — *"A
gist is never regenerated"* — and the reason it changes is that the rule's own
justification was body-and-gist skew: the stored body is a snapshot, so a fresher
gist would describe something the record does not hold. Re-summarising the thread
we have just stored keeps the two in step, which is what the rule was protecting.
`CLAUDE.md` is updated in the same change.

The panel is the thread's diff context once, then every comment in order beneath
it, then a plain reply box. The code appears once because the whole thread is
about the same lines.

Anchoring that diff context has two cases, and the second is not an edge case —
it was 13 of 24 threads on the pull request this was designed against:

- A current thread (`isOutdated: false`) anchors on `line` in the PR's diff, as
  the board does today.
- An outdated thread has **`line: null`** and anchors on `originalLine` against
  `originalCommit.oid`, the commit the comment was written against. This is what
  GitHub itself renders, and it reuses `_file_rows`, which already reads plain
  file rows out of `git show <ref>:<path>` — it needs the original commit rather
  than the head.

Without the second case the panel would show no code at all for most threads on
a mature pull request.

## Writing to GitHub

The reply goes through the `addPullRequestReviewThreadReply` mutation, whose
input is `pullRequestReviewThreadId: ID!` and `body: String!`.

That makes this repository's first GraphQL mutation, and `gh_graphql` returns a
200 carrying an `errors` array without raising — a refused reply would look
exactly like a posted one. A new `gh_graphql_mutate` raises `GhError` on any
`errors` array. `gh_graphql` keeps today's forgiving behaviour, because the
poller deliberately uses partial data alongside logged errors, and one helper
cannot hold both policies without lying to one of its callers.

Nothing ever resolves a thread. `resolveReviewThread` and `unresolveReviewThread`
exist and are deliberately unused.

A reply typed into the panel posts verbatim with no `🤖`, the same as a decline
reply, because those are the user's own words. The marker stays on
agent-authored text such as the commit link posted on approve. A plain reply
moves no status: a `ready` thread stays `ready`.

## Migration

One-shot and tolerant. Records and directories are renamed; anything that cannot
be mapped is left where it is and settles under its old key.

Branches are not renamed. The branch name is already stored on the record and
read back rather than recomputed, so a migrated thread keeps
`orchestrator/candidate/<pr>/<id>` for life while new threads get the new prefix.
Renaming would mean `git branch -m` on branches that are currently checked out in
worktrees, plus moving those worktrees — risking exactly the unpushed candidate
work that a tolerant migration exists to protect.

Queued `new-comments` events are dropped rather than translated. The event's
meaning changed — it now fires on replies to old threads, not only on new
comments — and a compatibility shim for a queue that drains in seconds is not
worth its own failure modes.

## Verified against the live API

These were checked by introspection and against a real pull request rather than
assumed:

- `PullRequestReviewThread` carries `id`, `isResolved`, `isOutdated`, `path`,
  `line`, `startLine`, `originalLine`, `originalStartLine`, `diffSide`,
  `subjectType`, `comments`, `resolvedBy`, `viewerCanReply`, `viewerCanResolve`.
- `addPullRequestReviewThreadReply`, `resolveReviewThread` and
  `unresolveReviewThread` all exist; the reply mutation's input is
  `pullRequestReviewThreadId: ID!` plus `body: String!`.
- `reviewThreads` returns resolved and outdated threads, not only live ones.
- Ids on a real pull request are all modern `PRRT_…` form, so percent-encoding is
  a no-op in practice and a safety net in principle.
- Outdated threads carry `line: null` with `originalLine` and
  `originalCommit.oid` populated.

The vendored REST reference cannot answer any of this: a grep across all 2,334
files for `reviewThread`, `isResolved` or `PullRequestReviewThread` returns
nothing, because `docs/github/scripts/README.md` shows the generator's input is
the REST OpenAPI document. There is no GraphQL in that pipeline to vendor.

One thing remains unverified: whether a thread's node id is stable across a
force-push or across the thread going outdated. Nothing available here proves it.
The design rests on it, and the read path is the thing that would show it — a
thread whose id changed would appear as a vanished thread and a new one on the
same line.

## Tasks

Delivered as one change, in this order, each leaving the suite green.

01. `gh_graphql_mutate` in `common/gh.py`, raising on any `errors` array.
02. The thread query in the poller: threads and comments, both connections
    paginated, replacing the REST review-comment fetch.
03. Thread snapshots in state, and the diff that yields new threads, new replies
    and vanished threads.
04. `thread-activity` replacing `new-comments` through the queue, the handlers and
    `--dry-run`'s consequence table.
05. Rename the modules, constants, directories and the branch prefix; suite green
    with no behaviour change.
06. Re-key the store to node ids: percent-encoded paths, mtime intent ordering,
    content-based garbage.
07. The migration.
08. Lifecycle: reopen edges out of `approved` and `dismissed`, attempts reset,
    `removed` as vanished-thread only, resolved and self-posted replies excluded.
09. Reply through the mutation; extend `posted_reply_ids` to thread and panel
    replies.
10. Board rows: reply count, `Outdated` badge, creation-order sort, gist
    regenerated on reopen.
11. Board panel: transcript beneath the diff, outdated anchoring via
    `originalLine` and `originalCommit`, reply box.
12. CLI `thread` subcommand and `--thread-id`; the three generated prompts, with
    the whole thread inlined and the `in_reply_to_id` research instruction
    deleted.
13. `SKILL.md`, `CLAUDE.md` and `README.md`.
14. `make record`, then the full suite.
