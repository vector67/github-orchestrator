# The conversation aggregate

Today every caller of the threads workflow reaches one PR's threads through a
handle with five roles and names the thread by key on nearly every call:
`of(pr).decisions.approve(key)`. So callers hold lists of keys, not lists of
threads. This spec replaces that with a `conversation` module whose
`Conversation` is an aggregate root, and a `ConversationManager` for whatever
arrives without a conversation in hand.

The design was settled with the user on 2026-09-28; the reading note is the
artifact "The Conversation Aggregate".

## Decisions

- **The module is `conversation`**, singular: it represents one conversation.
  `threads_workflow` becomes it; nothing called the threads workflow survives.
- **Two exports carry it.** `Conversation`, the aggregate root, and
  `ConversationManager`, the shell around it. A `ConversationManagerFactory`
  answers one manager per PR, as the old factory answered one handle.
- **A read-only conversation and an editable one.** `get(key)` and `all()`
  answer read-only conversations. `editing(key)` is the only way to change one:
  it hands out an editable conversation whose command methods work only while
  its block is open, and refuses them once it has closed.
- **Anything holding a conversation calls its methods.** The manager exists
  only for what arrives without one: a key from an HTTP route or the CLI, an
  effect's outcome, the poll.
- **Commands and events.** A command is an intention, imperative, and can be
  refused. An event is a fact, past tense, and is applied or ignored as stale,
  never refused. Commands go to the conversation; events go through the
  manager. `Command` and `Event` are private to the module.
- **One state machine.** A command method builds its command and asks the
  machine to try the transition; it knows its parameters, not which
  transitions are valid. The rules live in one place.
- **The conversation decides effects; the manager carries them out.** Effects
  stay values, as `_domain/effects.py` has them.
- **The outbox stays.** A board command is refused at once when the rules
  forbid it, and otherwise written as a pending decision the drain carries out
  in the PR manager's process, with the live facts it needs then (run alive,
  worktree clean, Claude enabled, the head). Running a command's effects on
  the request was rejected on 2026-09-22 (board API build decisions: GitHub
  and git inside a request, a race for the record's lock) and stays rejected.
- **Agent reports apply on the spot.** `plan`, `step`, `ready`, `skip` and
  `fail` carry no effects, so the agent's CLI process applies them inside
  `editing` and reads back the answer or the refusal at once.
- **Creation is the manager's.** A conversation cannot create itself: the poll,
  the draft composer and `thread open` go through the manager. `thread open`
  cuts its worktree on the spot, because its caller waits on the path.
- **`Land` and `First` are the manager's internal steps; `Rebase` is an event.**
  `Land` carries an approve already taken through its pick, push and answer;
  `First` starts a new conversation's first fix; `Rebase` reports a rebase.
- **Thread records keep their purview.** The manager uses them for the files,
  the atomic writes, the locks and the pending decisions.
- **Size is no reason to split a module.** Doing a second job is.
- **Reviews are PR-level.** Sending one moves to the PR manager after this
  redesign (step 2, option A): the PR manager owns the review, and the
  conversation module hands over the enrolled drafts, locked.

## Order

An interface change and an internals change never share a step: a suite that
changed with the internals could pass for the wrong reason.

1. **Rename.** `threads_workflow` becomes `conversation`, the factory
   `ConversationManagerFactory` and the handle `ConversationManager`. Nothing
   else changes.
2. **Interface.** The five roles go. The manager answers `editing(key)`,
   `get(key)`, `all()`, the PR-level reads and upkeep, and creation; the
   editable conversation answers every command as a method. Callers and tests
   move onto the new calls, and the tests are green over today's internals.
3. **Internals, green to green.** The tests stay as step 2 left them. The
   rules move into one state machine, commands and events are split and made
   private, `Land` and `First` become the manager's steps and `Rebase` an
   event, and `editing` holds the record's lock for its block.
