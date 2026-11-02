# Agent question: plan

Carries out [the agent question spec](../specs/2026-10-30-agent-question-design.md).
The spec is the decision. This plan sets the order of the steps and how each one
is judged. Decision numbers (01–15) are the spec's. Issue #253.

## How to work

- Every change follows `.claude/skills/normal-workflow`. Load `tdd` for
  anything that changes behaviour, `refactor` for reshaping, and
  `frontend-work` for anything under `frontend/`.
- Each step gets its own branch in its own worktree, cut from local `main`. It
  is merged and restarted before the next step starts. The user approved
  running the steps straight through, without stopping to report between them.
- Each step is a vertical slice that is safe to merge alone: what a later step
  will add is refused with a standing error, never half shown.
- Run `make lint-python` and `make test-python` before each commit. When the
  commit touches `frontend/`, run the full `make lint` and `make test` as well,
  and report the pass counts.
- **Proof is tests and fakes.** Each step proves itself with domain,
  application, adapter, CLI, board API and ember acceptance tests against the
  existing fakes (`agent_runs/fake.py` and the like). No step starts real agent
  runs or touches a real PR. Step 8 is the one live check.
- **Prompt changes are replayed in subagents.** A step that changes a fix-run
  prompt renders the real prompt and gives it, with the case's files, to a
  subagent in a scratch folder, for three cases: a brief that cannot be met as
  stated (the `clock_timestamp()` helper whose tests then fail because
  production stamps `now()`), a fix that goes beyond the brief (it needs a
  production change for a test comment), and a brief that is fine as asked.
  The first two end in `thread ask`; the third commits without asking. Record
  each subagent's last report in the decision log.
- **The board holds each server fact once**, in `frontend/app/services/store.ts`;
  derived values live only in `frontend/app/data/summaries.ts`.
- **Follow the board's look.** Reuse the treatments it has: the ready edge
  stripe and ready square, the confidence callout's 3 px yellow left border,
  `--grey-fill` grounds. Nothing is filled solid yellow. Check the look of every
  front-end step in a real browser in both themes, with console logging on;
  any `Uncaught` error fails the check.
- **Tests** assert behaviour and structure: states, fields, which actions are
  offered, which text and attributes are present. Never colours, borders or
  widths.
- **Data on disk.** Thread records written before a step lack its new fields.
  Read them with the empty default in one place inside the owning adapter
  (`conversation/_adapters/conversation_document.py`); always write the new
  form.
- **Budgets.** `make interface-report` must show no package with more exports
  than it has on `main` when the step starts, and no class with more methods,
  unless the step names the new export and the spec decision that needs it.
- Code carries no comments.
- When the spec leaves a choice open, make it, and name it in the report.

## Steps

### 1. Session ids and the last message

Decisions 03 and 08 (storing only). Claude fix runs start with a chosen
`--session-id <uuid>`; Codex runs read `thread_id` from their first
`thread.started` event. A run's final assistant text is kept. Both travel from
`AgentRun` through `Run`, `RunProgress` and `RunExited` onto `Fix` and the
thread record. The salvage rule in `_run_exited` is unchanged; a salvaged
proposal carries the last message, and the run that retries or fails keeps it as
the reason's detail.

Done when: a fake Claude run and a fake Codex run each leave their session id
and last message on the fix, both survive a save and load, and an old record
without them loads.

### 2. `thread ask` and the `asking` state

Decisions 01, 02, 04 and 15. `ReportAsk(question, context, options)` and a
`thread ask` verb from `cli/_threads.py` down to `_report_ask`; the `asking`
fix state with its `RULES` entries (`StartSession`, `Reject`, `Defer` allowed;
approve and rework refused); an ask gives back the attempt its run was charged;
the fix-run and rework prompts drop "do not ask questions" and say when to ask
(decision 02), replayed per "How to work". `asking` is not yet projected: the
board API refuses nothing new and shows such a thread as it shows a running
one until step 3.

Done when: a fake run that calls `thread ask` leaves the fix `asking` with the
question, context and options, its attempt count unchanged; the three prompt
cases behave as "How to work" says.

### 3. The question on the board and the notification

Decisions 05, 07 (actions offered: Answer and Drop, both refused with a
standing "not yet" until steps 5 and 6) and 14. Contract and projection carry
the question, context and options; the panel shows the question section, the
queue row reads "Agent question", the PR's next move reads "Your move: an agent
is asking you a question"; the fallback of 03 shows as "Stopped without
reporting" with the last message. `agent_asked` notification, batched, opening
the thread.

Done when: an asking thread is listed under Ready for you with the section the
mockups show, and a stopped-without-reporting proposal shows its last message.

### 4. The two-section diff

Decision 06. A board API read for the worktree's diff past a commit, uncommitted
changes included; `thread_sha` survives an ask. The panel shows "Last
proposal" (collapsed) and "Since the last proposal"; a first run that asked
shows only "Changes so far".

Done when: an asking thread with a commit and an uncommitted edit shows each in
its own section.

### 5. Answering

Decisions 07, 08, 09 and 15 (reset). `resume_session(id, prompt)` on both
command lines; Answer opens a live session resuming the stored id with the
question's answer prompt as its argument, and resets the attempt count; the
session's own id is stored; a session that ends without a report returns to
`asking`; a report from inside it applies. The bar shows "Go to the session"
while it is open.

Done when: with a fake session, Answer opens the resume argv for each agent,
and every way the session can end lands where decision 09 says.

### 6. Drop

Decision 10. The Drop modal with its three choices and their diagrams. Back to
the last proposal resets the worktree to `thread_sha` through a new
`ThreadWorkspace` operation and returns the thread to `proposed`, or to `failed`
"question dropped" for a first run; Defer and Reject reuse the existing flows.

Done when: each choice lands the thread and the worktree where decision 10 says.

### 7. Replies and head moves while asking

Decisions 11, 12 and 13. A reviewer reply on an asking thread with no session
open starts a headless resume of the stored id with the reply; during an
answer session it raises the persistent toast and the thread modal with Copy;
the question records the PR head it was asked on and the section shows the
"PR moved" marker when the head has moved.

Done when: each of the three cases behaves as its decision says.

### 8. The live check

The one end-to-end proof on the real system: a real fix run on a real thread
asks, the board shows it, Answer resumes the run's session, and a report from
that session lands. Coordinated with the user before it starts.
