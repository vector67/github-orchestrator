# Split proposal: plan

Carries out [the split proposal spec](../specs/2026-11-10-split-proposal-design.md).
The spec is the decision. This plan sets the order of the steps, how each one
is judged, and the choices the spec left to the build. Decision numbers
(01–12) are the spec's. Issue #339.

## How to work

- Every change follows `.claude/skills/normal-workflow`. Load `tdd` for
  anything that changes behaviour, `refactor` for reshaping,
  `frontend-work` for anything under `frontend/`, and `writing-for-agents`
  for a prompt or a skill.
- Each step gets its own branch in its own worktree, cut from local `main`. It
  is merged and restarted before the next step starts. The user approved
  running the steps straight through, without stopping to report between them.
- Each step is a vertical slice that is safe to merge alone. No agent can
  propose a split until step 7 changes the prompt, so the earlier steps build
  the machinery behind it and prove it with fakes. What a later step will add
  is refused with a standing error, never half shown, and a split record must
  never break a projection, a load or a page.
- Run `make lint-python` and `make test-python` before each commit. When the
  commit touches `frontend/`, run the full `make lint` and `make test` as well,
  and report the pass counts. Run every test command under `timeout`.
- **Proof is tests and fakes.** Each step proves itself with domain,
  application, adapter, CLI, board API and ember acceptance tests against the
  existing fakes (`agent_runs/fake.py` and the like). No step starts a real
  agent run, pushes a branch, opens a PR or touches a real PR. Step 8 is the
  one live check.
- **Prompt and skill changes are replayed in subagents.** A step that changes a
  run prompt or ships a skill renders the real text and gives it, with the
  case's files in a scratch git repository, to a subagent in a scratch folder.
  The subagent works for real in that scratch repository but is told it has no
  network: it writes the `gh` or report commands it would run to a file
  instead of running them. Record each subagent's last report and the file in
  the decision log. The cases are named in the step.
- **The board holds each server fact once**, in `frontend/app/services/store.ts`;
  derived values live only in `frontend/app/data/summaries.ts`.
- **Follow the board's look.** Reuse the treatments it has: the queued and
  working banners, the ticket box, the reply quote, `DiffFold`, the dialog in
  `decide-dialog.gts`. Check the look of every front-end step in a real
  browser in both themes, with console logging on; any `Uncaught` error fails
  the check.
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
- **Nothing internal.** Examples use `acme/*`, `octocat` and `PROJ-12`. No
  employer, client, team skill name or real PR in code, tests, prompts, the
  shipped skill or commit messages.
- Code carries no comments.
- When the spec leaves a choice open and this plan does not settle it, make it,
  and name it in the report.

## Choices this plan settles

- **The parts are one value on the fix.** A split proposal is `Fix.kind == SPLIT` with a `Split` value holding the new branch, its base and the reason
  for it, the ticket draft or none for "same ticket", the new PR's link once
  opened, and which parts are accepted. Whether a part has run is read from
  `Fix.steps`, as today: `FILE` for the ticket, `PICK` and `PUSH` for the
  changes, a new `OPEN` step for the new PR, `ANSWER` for the reply. A part is
  *accepted* when it is in the accepted set, *queued* when accepted and its
  prerequisite has not run, *running* while its effect or run is in flight,
  and *run* once its step is recorded. The rules live in one domain module.
- **One thing runs at a time.** The fix runs accepted parts in the order
  ticket, changes, new PR, reply, skipping any not accepted. A part waits for
  its prerequisite (decision 04): the new PR for a drafted ticket, the reply
  for the new PR. Between parts, when nothing accepted is runnable, the fix
  returns to `proposed` with its run parts locked, so the thread is back under
  Ready for you.
- **Opening the new PR is an agent run.** A new run kind, `open`, runs in the
  thread's worktree, like the filing run. Its prompt has it push the branch and
  invoke the repository's PR skill (decision 12) to open a PR from that branch
  into the base, naming the original PR, the thread and the ticket, and report
  `thread opened --url`. When the repository sets `draft`, the board then flips
  the PR to match with `gh pr ready` or `gh pr ready --undo`.
- **The reply names the new PR.** Like a ticket's reply today, the posted
  reply ends with the new PR's link and, when a ticket was filed, the
  ticket's link.
- **Rework on a part** starts a rework run whose brief names the part, and
  names the parts that have run as fixed. The run reports a split again; the
  domain takes the reworked part's content from it and keeps every other
  part's.

## Steps

### 1. The split report

Decisions 02 and 03 (storing only). `ProposalKind.SPLIT`, the `Split` value on
`Fix`, `ReportSplit` from a new `thread split` verb in `cli/_threads.py`
through `ReportCommands.split` and `conversation/_threads.py` down to
`_report_split`, leaving the fix `proposed`. The verb takes the branch, the
base and its reason, either `--same-ticket` or a ticket's project, title and
body, and the reply; it refuses a branch the worktree does not have. Saved
and loaded through the thread record, old records reading as no split.
The board shows a split thread as a proposal under Ready for you whose
approve is refused with a standing "accepting a split arrives in a later
step"; Reject and Rework work as for any proposal.

Done when: a fake run that reports a split leaves the fix proposed with every
field, the record survives a save and load, and an old record loads.

### 2. Per-repository settings and the `create-pr` skill

Decisions 11 and 12. Two optional `[[repos]]` keys, the PR skill (default
`create-pr`) and `draft` (unset, true or false), read in
`settings/_config.py`, carried to where the thread's agents are built, written
into `config.toml.example` and documented in the README beside `has_tests`.
A generic `create-pr` skill ships under `cli/skills/` beside
`rebase-on-main`; `cli/_skill.py` installs, checks and reports every shipped
skill rather than the one `SKILL`, and `doctor` names each.

Replay the skill per "How to work" for three cases: a repository with a
`.github/pull_request_template.md`, one without, and a stacked base. Each
writes a body with a reviewer guide, the original PR and thread link and the
ticket, following the template when there is one, and opens a draft.

Done when: the settings round-trip with and without the keys, `skill --status`
reports both skills, and the three replays write what decision 11 says.

### 3. Accepting the changes, the ticket and the reply

Decisions 03 to 07, except the new PR. An approve names a part, or all of
them. Accepting the ticket starts the filing run; the changes pick and push
as a commit proposal does; the reply is queued "waiting for new PR". Accept
all accepts every part not yet accepted. A run part locks. Reject is refused
once any part has run. Accepting the new PR is refused with a standing
"opening the new PR arrives in a later step". The CLI's `thread approve` takes
`--part`. The board API's approve operation takes the part, and the
projection carries each part's state (decision 03's table, plus accepted,
queued, running, run and its result); the board itself still shows the
standing refusal from step 1.

Done when: through the fakes, every order of accepting the three parts lands
where decisions 04 to 06 say, a failed filing or push leaves its part
re-acceptable, and the projection reports each part's state.

### 4. Opening the new PR

Decisions 04, 07 and 12. The `open` run kind, its prompt in
`agent_runs/_thread_prompts.py`, the `thread opened` report command and verb,
the draft flip when the repository sets `draft`, and the reply posting with
the new PR's link once the PR is open. The last part to run ends the thread as
decision 07 says. A run that exits without reporting, times out or is lost
fails the part, as a filing run does, and the part can be accepted again.

Replay the `open` prompt per "How to work" for a base of `main` with a drafted
ticket, and a stacked base under the same ticket.

Done when: through the fakes, accepting all four parts files, pushes, opens,
flips draft per the setting, posts the reply naming both links and lands the
thread, resolving it when `resolve_on_land` is set; and both replays run the
right push and skill.

### 5. Edit and Rework per part

Decisions 03 and 08. Edit on the ticket and on the reply saves the new text
without accepting: a domain command, a CLI verb and a board API operation.
Rework names a part, as "Choices this plan settles" says; a run part cannot
be edited or reworked. The rework prompt names the part and the fixed parts.

Replay the rework prompt for a rework of the new PR that asks for a rename,
with the changes already pushed.

Done when: an edit changes only its part and accepts nothing, a rework report
changes only the reworked part, and both are refused on a run part.

### 6. The cards and the diffs on the board

Decisions 03, 05, 06, 08, 09 and 10, under `frontend-work`. Each part is a
card in the panel's work area with its kicker, content and buttons; queued and
running parts show the existing banners; a run part collapses to its one-line
result. Edit opens today's dialog in a save-only mode. Accept all sits in the
footer with the thread actions, and Reject goes once a part has run. The diff
pane holds two accordions, "Changes to this PR" and "New PR", collapsed by
default, each a `DiffFold` with its full-screen button; the new PR's diff
comes from a board API read of the new branch against its base. The standing
refusals of steps 1 and 3 go.

Done when: acceptance tests walk a split through every card state, Edit,
Accept all and the Reject rule, and the look passes in both themes with no
console error.

### 7. The prompt

Decisions 01 and 02. The thread prompt describes split as a fourth way to
finish, the out-of-scope section gains the exception for code already in this
PR's diff, and split is a run that ends with commits, carrying no
`Classification`. Replay per "How to work" for four cases: out-of-scope code
in the diff that stands alone (split onto `main`), out-of-scope code that
depends on the PR (stacked), "not in the acceptance criteria" for a few lines
that should simply go (a commit that removes them), and out-of-scope work not
yet in the diff (a ticket, as today).

Done when: the four replays end as their cases say.

### 8. The live check

The one end-to-end proof on the real system, coordinated with the user before
it starts: a real thread on a PR of the user's choosing is split, every part
is accepted on the board, and the new PR, the reply and the landing match the
spec. Then, in the user's local `config.toml` (not committed), set the PR
skill for the repository the user names.
