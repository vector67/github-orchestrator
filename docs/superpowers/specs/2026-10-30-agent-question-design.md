# Agent question: design

Issue #253. A fix run that cannot finish as asked has no way to say so. In the
run that prompted this, a rework brief asked for one `clock_timestamp()` helper
for both bounds of a test; the agent made the change, saw every test in the
file fail because production stamps `now()` inside the test's outer
transaction, left the edit uncommitted, and ended with a question offering two
ways out. Nothing reads a run's last message, so `_run_exited` found the
previous attempt's commit in the worktree, proposed it with "run exited without
reporting; commit found in worktree", and the board showed last attempt's diff,
summary and note under the new plan. It looked as if the agent had ignored the
rework.

The salvage rule in `_run_exited` stays: a run that never reported has not
changed what the board should propose. What changes is that a run can ask, and
that a silent run's last words are kept.

## Decisions

01. **How a run asks.** A new report verb,
    `thread ask --question <one line> --context <markdown> [--option <text>]…`.
    The run stops after it. `--context` says why it stopped (what it tried,
    what broke); `--option` repeats, and is given only when the agent has
    narrowed the fork to concrete alternatives.

02. **When a run asks.** The fix prompt tells the agent to ask when the brief
    cannot be met as stated, or when the way forward goes beyond what the
    comment and brief asked for (a production change for a test comment,
    another module, a public signature). Anything else it decides and says so
    in the confidence note.

03. **The fallback.** A run that exits without any report keeps its final
    assistant message. The salvage rule is unchanged: a commit newer than
    `base_sha` is still proposed, `kind=commit`, `tests="unverified"`, and the
    proposal carries that message. The board shows it as "Stopped without
    reporting", never as a question. With no commit, retry and fail are as
    today, with the message as the reason's detail.

04. **The `asking` state.** `thread ask` puts the fix in a new state, `asking`,
    beside `proposed`. It is not a proposal kind: nothing in it can be
    approved or landed. It shows under Ready for you.

05. **What the card shows.** It takes the proposal section's place, under the
    comment thread: the heading "Agent question · stopped after N of M steps",
    the question, the options when there are any, a "Why it stopped" callout
    styled as the confidence note (3 px yellow left border), and the plan steps
    as they stand. The queue row reads "Agent question". The NEXT banner reads
    "Your move: an agent is asking you a question". No solid yellow anywhere:
    the row uses the ready edge stripe and the head its ready square, as today.

06. **The diff.** Two sections in the right-hand panel: "Last proposal" (the
    commit last proposed, collapsed) and "Since the last proposal" (everything
    in the worktree past it, committed or not, open). A first run that asks has
    no last proposal; its one section reads "Changes so far".

07. **Actions.** Two: **Answer in a session** and **Drop…**. Send back for
    rework, approve and the rest are not offered on a question.

08. **Answering.** Every fix run stores the id of the agent session it ran in
    on the thread. Claude takes the id the orchestrator chooses
    (`--session-id <uuid>`); Codex reports its own in the first `--json` event
    (`thread.started`, `thread_id`).
    Answer opens a live session in the thread's worktree that resumes that id
    (`claude --resume <id>`, Codex `resume <id>`), never "the newest
    conversation in the directory", which a reply re-run or another session in
    the same worktree would change. A session that runs inside the answer
    (item 09) stores its own id the same way. The session and the fix run must
    use the same agent config directory, or there is nothing to resume.
    The question goes in as the resume's opening prompt argument
    (`codex resume <id> "<prompt>"`, `claude --resume <id> "<prompt>"`), never
    typed into the TUI, which may be showing a start-up menu (Codex's update
    offer takes the first keystrokes). Proven on 2026-11-02: a finished
    `claude --print --session-id` run and a finished `codex exec --json` run
    each resumed interactively by id, answered from the headless turn's
    context, and wrote the new turns under the same id. While it is open the
    bar shows "Go to the session".

09. **When the session ends.** Reported `ready`, `reply`, `ticket` or `ask`:
    that report applies (a new `ask` replaces the question). Ended with no
    report: back to `asking`, the same question, the worktree untouched.

10. **Drop.** Opens a modal of three choices, each with a small diagram of
    the state change and what happens to the worktree:

    - **Back to the last proposal**: uncommitted edits discarded, the worktree
      reset to that commit, the thread `proposed` again. A first run that asked
      goes to `failed`, "question dropped".
    - **Defer**: the existing defer and its wake conditions, edits kept; the
      question returns when it wakes.
    - **Reject the thread**: the existing reject with its reply step, edits
      discarded.

11. **A reviewer reply while asking.** With no session open it re-runs the
    agent: a headless resume of the stored session id with the reply. The
    run reports, asks again, or ends silent, which goes back to `asking`.

12. **A reviewer reply during the answer session.** Nothing is typed into the
    terminal. A persistent toast, top right on the board: "<author> replied to
    the thread you're answering", with **See their comment**. It opens a modal
    with the whole thread from the start, the newest comment marked with the
    ready edge stripe, and **Copy <author>'s reply**, which copies that
    comment's text. The toast stays until opened or dismissed.

13. **The PR head moves while asking.** Nothing runs. The section heading gains
    a marker, "PR moved since the question · N new commits". The
    rebase-under-proposal rule applies once the thread is `proposed` again.

14. **Notification.** A new `agent_asked` notification, batched like the rest:
    "Agent question on #<n>", the question as the body, opening the thread. The
    fallback of 03 uses `fix_ready` with the last message as the gist.

15. **Attempts.** An ask does not count against `MAX_ATTEMPTS`. Answering resets
    the count, as a send-back does.
