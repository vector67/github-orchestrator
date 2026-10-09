# Reply and ticket proposals: plan

Carries out [the reply and ticket proposals spec](../specs/2026-10-08-reply-and-ticket-proposals-design.md).
The spec is the decision. This plan sets the order of the steps and how each one
is judged. Rule IDs (R1–R13) are the spec's. Issue #231.

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
- **One proposal, three kinds.** The kind lives on the proposal in the
  conversation domain (`conversation/_domain/`), decided in one place: the
  report that made it. Nothing outside the domain infers a kind from whether
  `commits` is empty. The front end branches on the contract's `kind` and never
  on classification to pick what a proposal card or accept dialog shows.
- **Agents report through the CLI.** New outcomes are report commands beside
  `skip`, `ready` and `fail` (`ReportCommands`, `cli/_report_commands.py`,
  `cli/_threads.py`), never parsed output. Every prompt that prints a command is
  pinned in `tests/agent_runs/pinned/`; the test that each printed command names
  the CLI's required flags covers the new ones.
- **Nothing a step does may post, reply, resolve, react, or create an issue or
  ticket on a real PR, repo or Jira project.** Tests use the fakes and the
  recorded subprocesses. A new `gh` call the code makes is recorded with
  `uv run pytest tests/ -k '<tests>' --record`, never by file path, and the
  tmux and dark-mode captures `make record` sweeps up are reverted.
- **The contract carries kinds, not text.** `kind` and the new fields go in
  `board_api/_contract.py`; regenerate `api.ts` and the contract copy through
  `tests/board_api/test_contract_copy.py`.
- **Budgets.** `make interface-report` must show no package with more exports
  than it has on `main` when the step starts, and no class with more methods.
  `conversation` and its `ConversationManager` and `EditableConversation` are
  over budget and may only shrink, so new operations go through the existing
  generic operation path, not new methods. Data fields are not methods.
- **Data on disk.** Thread records written before a step still load. A proposal
  with no kind reads as `commit`. A record declined as `already-done`,
  `question`, `unclear` or `out-of-scope` stays declined and shows as it does
  today; nothing rewrites it. A config with no `tracker` loads, and its prompts
  offer no ticket (spec, Config). Keep each translation in one place inside the
  module that owns the schema (`conversation/_adapters/record_schema.py`,
  `settings/_config.py`).
- Delete what the spec replaces in the step that replaces it: the prompt's
  skip wording for the four classifications that become replies in step 1, and
  `ALREADY_DONE` out of `ASSUMED_DONE_WHEN_DECLINED_AS` in step 1.
- Tests assert behaviour and structure, never colours, borders or widths.
- Code carries no comments (the user's rule).
- Check the look of any step that changes the board, in both themes, in the dev
  preview (`python -m github_orchestrator.preview`, after
  `make build_frontend`). Add preview cards for each new proposal kind. Take
  headless Chrome screenshots, look at them, and load the page with console
  logging on. Any `Uncaught` error fails the check.
- **The front-end store plan runs at the same time**
  (`docs/superpowers/plans/2026-10-08-front-end-store.md`), and its step 4
  reshapes the proposal in the contract (`commits`, `updated_at`, diffs by
  shas). Merge `main` into your branch before you start and again before you
  report, and build `kind` on whatever proposal shape `main` holds then.
- When the spec leaves a choice open, make it, record it in the decision log
  with the reason, and name it in the report.
- Bound every long command with `timeout` (a suite with `timeout 300`), so a
  hang shows up as a failure rather than silence.
- When a step finishes, mark it **Done** below with its last commit hash, in
  the same commit as its last code change.

## Steps

1. **Reply proposals.** R1 without the ticket branch, R2, R6, R7, R8, R12 and
   R13 for the reply kind. The proposal gains `kind` (`commit` or `reply`) and
   the reply text, carried on the fix the report settles. `thread reply`
   joins the report commands. The three thread prompts send `already-done`,
   `question`, `unclear` (as a clarifying question) and `out-of-scope` to a
   reply instead of a skip; `out-of-scope` replies say the work belongs outside
   this PR (step 3 adds the tracker search). The skip command keeps only
   `risky`, `needs-human` and `acknowledgement`. Accepting a reply proposal
   runs `ANSWER` then `MARK_RESOLVED` when asked: no pick, no push. The
   contract `Proposal` carries `kind` and `reply`; the diff read is 404 for a
   reply. The accept dialog pre-fills the reply, asks "This posts this reply
   to the comment. Are you sure?" and submits "Post reply"; the panel titles
   the card "Agent proposes a reply" with the reply text and no diff, files or
   tests rows.
2. **Resolve defaults off.** R11. Every accept dialog, commit or reply, opens
   with resolve unticked unless the thread's opener is a bot, when it opens
   ticked. If the contract does not already say the opener is a bot, the
   server says it (one boolean from `domain.author_kind_of`); the front end
   keeps no bot list of its own. The Resolve on GitHub action follows the
   same rule.
3. **Tracker config and ticket proposals.** Config, R3, R4, R5, R12 and R13 for
   the ticket kind. `OrchestratorConfig` gains `tracker` and `tracker_project`,
   validated as the spec's Config table says. The prompts carry R5's facts and,
   with a tracker, R4's search and `thread ticket`; without one, the ticket
   command is not offered. The proposal gains the `ticket` kind with project,
   title, body and reply. The accept dialog shows all four fields editable and
   the approve request carries them. The panel titles the card "Agent proposes
   a ticket". Accepting a ticket is refused until step 4 lands it, with a
   standing error the board shows, so no step ships a ticket that half-lands.
4. **Filing on accept.** R9 and R10. Approving a ticket proposal starts a
   filing run (a new operation kind on the generic path) with its own pinned
   prompt that files the edited ticket with `gh issue create` on `watch_repo`
   or the Atlassian MCP in the edited project, and reports `thread filed --key --url`. The landing records the key and URL, posts the edited reply with
   the link on its own line, then resolves when asked. A failed or silent run
   leaves the proposal and offers Retry; nothing reaches GitHub before the
   ticket exists. The landing steps in the contract show the filing step. The
   accept dialog submits "File ticket and post reply". Prove the Atlassian MCP
   is reachable from a thread run (spec, To verify) with one real search-only
   call, never a create.

After the last step, `run-plan-steps` step 6: measure the test speed and add a
row to `docs/test-speed.md`.

## Done

- Step 1, reply proposals: **Done** (`ba1e8c7a`, `def69a95`, `56a314be` and the
  commit that records this)
- Step 2, resolve defaults off: **Done** (`e18f1ac4` and the commit that
  records this)
- Step 3, tracker config and ticket proposals: **Done** (`b8e31b57`,
  `5f728be0`, `63e46a77` and the commit that records this)
- Step 4, filing on accept: **Done** (`3cb71e61` and the commit that records
  this)
