# Reply and ticket proposals

Date: 2026-10-08. Issue #231.

## Problem

The comment agent can propose one thing: a commit. Every comment that needs an
answer and no code ends in a skip (`already-done`, `question`, `unclear`,
`out-of-scope`), and the viewer writes the answer by hand. Work that belongs
outside the PR is declined with a reason and then lost: nothing records it.

Today a proposal is a commit throughout. `Proposal`
(`conversation/_domain/conversation.py`) has no kind; it exists whenever the fix
is `proposed`, and the contract, the accept dialog ("Push and post reply") and
the panel all assume a diff.

## Decisions

- **The agent still chooses between fix and not-fix.** Every accepted proposal
  replies; a ticket is a reply that also files a ticket. The agent never has to
  pick between replying and doing something else.
- **Three proposal kinds:** `commit` (today's fix), `reply` and `ticket`.
- **A reply covers any comment that needs an answer and no code.**
  `already-done`, `question` and `unclear` stop being skips. An unclear
  comment gets a reply asking the reviewer a clarifying question.
- **`out-of-scope` is no longer a skip.** The agent searches the tracker first.
  A matching ticket exists → a reply that names and links it. None → a ticket.
- **Only `risky`, `needs-human` and `acknowledgement` still skip.** An
  acknowledgement ("thanks, LGTM") needs neither an answer nor code; it keeps
  landing in Assumed done (comment verdict spec, T3). `already-done` leaves
  `ASSUMED_DONE_WHEN_DECLINED_AS`, since it is now a reply proposal.
- **Config names the tracker and the Jira project.** The agent is given both and
  the branch's ticket key, and chooses the project itself.
- **Every field of a reply or ticket proposal is editable before accepting.**
- **An agent files the ticket on accept**, through `gh` or the Atlassian MCP, so
  the hub holds no Jira credentials. The hub then posts the reply with the link
  added and the rest of the landing runs as today.
- **The resolve box never starts ticked,** on an accept of any kind or on the
  Resolve on GitHub action, unless the comment's author is a bot.

## Config

| Key               | Values             | Meaning                                                     |
| ----------------- | ------------------ | ----------------------------------------------------------- |
| `tracker`         | `github` / `jira`  | Where tickets are searched for and filed.                   |
| `tracker_project` | a Jira project key | The default Jira project. Required when `tracker = "jira"`. |

With `tracker = "github"` tickets are issues on `watch_repo`. An instance with no
`tracker` has no ticket outcome: out-of-scope work becomes a reply that says so,
and the prompt does not offer the ticket command.

## Rules

| ID  | Rule                                                                                                                                                                                                                                                                        |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1  | The thread prompt classifies the comment into: needs code (fix), needs an answer (reply), out-of-scope (search, then reply or ticket), `risky`, `needs-human` or `acknowledgement` (skip).                                                                                  |
| R2  | A reply is reported as `thread reply --body "<reply>" --classification already-done\|question\|unclear\|out-of-scope`. The classification is kept for the panel; zero commits.                                                                                              |
| R3  | A ticket is reported as `thread ticket --project <key> --title "<title>" --body "<body>" --reply "<reply>"`. Zero commits.                                                                                                                                                  |
| R4  | Before R3 the agent searches the tracker (`gh issue list --search` on `watch_repo`, or JQL through the Atlassian MCP in the chosen project). Any match it judges to be the same work makes it report R2 with `out-of-scope` and a reply that names and links the ticket.    |
| R5  | The prompt gives the agent `tracker`, `tracker_project`, `watch_repo` and the branch's ticket key (`pr_manager/_snapshot.py` `_extract_jira_ticket`), when there is one.                                                                                                    |
| R6  | A reply or ticket report puts the fix in `proposed` with a proposal of that kind, exactly as `thread ready` does for a commit. A run that exits without reporting and left a commit is still a commit proposal (`_proposed_by_exit`).                                       |
| R7  | Rework reruns the agent with the viewer's note, from whatever it proposed last; it may come back as any kind. Reject drops the proposal and the worktree and may post a reply, as today.                                                                                    |
| R8  | Accepting a reply posts the edited reply, then resolves only if ticked. No agent runs.                                                                                                                                                                                      |
| R9  | Accepting a ticket starts a run that files the ticket from the edited project, title and body, and reports `thread filed --key <key> --url <url>`. The hub then posts the edited reply with the link appended on its own line, then resolves only if ticked.                |
| R10 | A filing run that fails, or exits without reporting, leaves the thread in a failed-landing state with the proposal kept; Retry starts filing again. Nothing is posted to GitHub until the ticket exists.                                                                    |
| R11 | Every accept dialog, for all three kinds, and the Resolve on GitHub action (`decisions.ts` `resolve`) open with resolve unticked, unless the thread's opener is a bot (`AuthorKind.BOT`: claude, codex, copilot), when they open ticked. The viewer can flip it either way. |
| R12 | The accept dialog for a reply shows the reply pre-filled and editable; for a ticket it also shows project, title and body, each editable. The approve request carries what was submitted, not what the agent wrote.                                                         |
| R13 | The panel titles a proposal by kind: the commit card as today; "Agent proposes a reply" with the reply text; "Agent proposes a ticket" with project, title, body and reply. The diff, files and tests rows appear only for a commit.                                        |

## Shape of the change

- **Domain.** `Proposal` gains a kind and the fields of each kind (reply text;
  project, title, body). `commits`, `tests` and the diff are commit-only. The
  landing steps for a ticket are `FILE` (the run), then `ANSWER` and
  `MARK_RESOLVED`; for a reply `ANSWER` and `MARK_RESOLVED`; for a commit
  unchanged. The `Classification` enum loses its skip role for `already-done`,
  `question`, `unclear` and `out-of-scope`; it stays on the proposal as why.
  Records on disk declined with those four still load and show as declined.
- **Agent runs.** `thread_prompt`, `fix_rebase_prompt` and `rework_prompt` learn
  the new outcomes and R4–R5. A new filing prompt for R9. The report commands
  `reply`, `ticket` and `filed` join `skip`, `ready` and `fail` in
  `ReportCommands`, and the test that every printed command names the CLI's
  required flags covers them.
- **Board API.** The contract `Proposal` carries `kind` and the new fields;
  `readProposalDiff` stays 404 for the non-commit kinds. `approveThread` takes
  the edited fields. A ticket's landing shows its filing step beside `picked`,
  `pushed` and `answered`.
- **Front end.** `decisions.ts` `approve` branches on the proposal's kind for its
  question, note, pre-fill and submit label ("Post reply", "File ticket and post
  reply"), and its resolve default follows R11. `panel.ts` renders R13.

## To verify while building

- That a thread agent can reach the Atlassian MCP. **Not reachable** (checked
  2026-10-08). Claude spawned exactly as a thread run is, with
  `claude --print --output-format stream-json --verbose --permission-mode auto --model opus`
  in a thread worktree and a prompt allowed one read-only JQL search, loaded
  only the `readast` server. It had no
  Atlassian tool, so it ran no search. Under that config directory neither
  the R4 search nor a Jira filing can work until the Atlassian connector is
  added there. The prompts still name the MCP. GitHub issues go through `gh`
  and are not affected.

## Out of scope

- Linking the new ticket to the branch's ticket.
- Labels, issue types beyond the tracker's default, assignees.
- Any change to how the reviewer-side verdict judge reads threads.
