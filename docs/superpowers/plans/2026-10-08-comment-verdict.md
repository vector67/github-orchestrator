# Whose move a comment thread is: plan

Carries out [the comment verdict spec](../specs/2026-10-08-comment-verdict-design.md).
The spec is the decision. This plan sets the order of the steps and how each one
is judged. Rule IDs (T1–T4, T2a–T2e) are the spec's. Issue #222.

## How to work

- Every change follows `.claude/skills/normal-workflow`. Load `tdd` for
  anything that changes behaviour and `refactor` for reshaping. The user has
  approved running the steps straight through without stopping to confirm.
- Each step gets its own branch in its own worktree, cut from local `main`. It
  is merged and restarted before the next step starts.
- Run `make lint-python` and `make test-python` before each commit. When the
  commit touches `frontend/`, run the full `make lint` and `make test` as well,
  and report the pass counts. A falling count fails the check unless the commit
  message names each deleted test and what made it impossible.
- **One placement rule per role.** Where a verdict or a classification lands is
  decided in the conversation domain (`conversation/_domain/`), in one place
  per role. The front end maps states to groups and words them; it never reads
  comments or classifications to choose a group. The only comment-reading the
  front end does is the card line naming who spoke last.
- **The LLM call is a port.** The verdict call goes through `agent_runs` next
  to the existing summaries, with its prompt pinned in
  `tests/agent_runs/pinned/`, a fake in `agent_runs/fake.py`, and the domain
  seeing only the parsed outcome. It answers on one line (`summarize` passes
  only the first line on). Nothing a step does may post, reply, resolve or
  react on a real PR.
- **The contract carries states, not text.** New `ConversationState` values
  (`assumed-done`, `not-mine`) and a boolean `unread`, plus any new operation
  verbs, go in `board_api/_contract.py`; regenerate `api.ts` and the contract
  copy through `tests/board_api/test_contract_copy.py`.
- **Budgets.** `make interface-report` must show no package with more exports
  than it has on `main` when the step starts, and no class with more methods.
  `conversation` and its `ConversationManager` and `EditableConversation` are
  over budget and may only shrink, so new operations go through the existing
  generic operation path, not new methods. Data fields are not methods.
- **Data on disk.** Thread records written before a step still load. A missing
  verdict field reads as "never asked"; `not-a-change` reads as `question`.
  Keep each translation in one place inside the module that owns the record
  schema (`conversation/_adapters/record_schema.py`).
- Delete what the spec replaces in the same step: `_answered_state` and the
  mention lift in `state_of` go in step 1, `NOT_A_CHANGE` goes in step 3.
- Tests assert behaviour and structure, never colours, borders or widths.
- Code carries no comments (the user's rule).
- Check the look of any step that changes the board, in both themes, in the dev
  preview (`python -m github_orchestrator.preview`, after
  `make build_frontend`). Add preview cards for the new groups. Take headless
  Chrome screenshots, look at them, and load the page with console logging on.
  Any `Uncaught` error fails the check.
- **The front-end store plan runs at the same time**
  (`docs/superpowers/plans/2026-10-08-front-end-store.md`). It ports the
  thread counts (`_tally`, `counts()`) and later the next move into
  `frontend/app/…/summaries.ts`. Merge `main` into your branch before you
  start and again before you report. The counting rule (Assumed done and
  confirmed count as done; Not my conversation is left out) goes wherever the
  counts live on `main` at that moment, Python, TypeScript or both, and never
  in a third place.
- When the spec leaves a choice open, make it, record it in the decision log
  with the reason, and name it in the report.
- Bound every long command with `timeout` (a suite with `timeout 300`), so a
  hang shows up as a failure rather than silence.
- When a step finishes, mark it **Done** below with its last commit hash, in
  the same commit as its last code change.

## Steps

1. **The verdict on someone else's PR.** T1, T2, T2a–T2e and the mention lift.
   Reviewer records gain the verdict and the newest comment it was asked and
   answered for; record states gain `assumed_done` and `not_mine`. Create,
   reopen, GitHub unresolve, board Reopen and wake put a reviewer thread in
   open with no verdict and ask for one (an effect beside `WriteGist`); a
   board reply parks it in waiting and asks for one. The verdict call and its
   pinned prompt carry T2's facts. `_answered_state` goes, and so does the
   mention lift in `state_of`. The contract gains `assumed-done`, `not-mine`
   and `unread`. Next-move counts: Assumed done counts as done, Not my
   conversation is left out (`conversation/_threads.py` counts,
   `pr_manager/_next_move.py`). The board: the two new groups in the spec's
   order with labels and hints, the Columns placement, the strip counts, "not
   yet read" on the card line and header, and "You replied" only when the
   newest comment is the viewer's. Write tests from the Problem section: a
   colleague's single comment, the PR description and a bot's summary never
   read "You replied".
2. **Confirm, Not confirm and Move.** A `confirmed` record state (shown as Done,
   card "Confirmed"), a confirm operation that touches nothing on GitHub, and
   a place operation taking the outcome. Assumed done cards offer Confirm and
   Not confirm; Not my conversation cards offer Move…; both open one modal
   listing the role's outcomes from the spec, with Later… opening the existing
   Defer dialog. On your PR, Needs a fix queues a fresh first run, Needs a
   reply from me goes to Needs a look, Their move to Waiting on reviewer. Build
   the modal on the existing decide dialog, not a second dialog.
3. **Your PR.** T3, T4: split `not-a-change` into `acknowledgement` and
   `question` in the classification, the agent prompts (pinned) and the report
   CLI; a decline classed `already-done` or `acknowledgement` lands in Assumed
   done, every other decline where it lands today. A reviewer's new comment on
   an Assumed done or confirmed thread reopens it like a resolved one. Old
   records with `not-a-change` read as `question`.

After the last step, `run-plan-steps` step 6: measure the test speed and add a
row to `docs/test-speed.md`.

## Done

- Step 1, the verdict on someone else's PR: **Done** (`49c69001`, `fb37b114`,
  `df3a6c39`, `2edf3c94`, `935386d5` and the commit that records this)
- Step 2, Confirm, Not confirm and Move: **Done** (`bb501fc8`, `ed2311c9`,
  `f880f016` and the commit that records this)
- Step 3, Your PR: **Done** (`7ed92a95` and the commit that records this)
