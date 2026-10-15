# The Summary tab

Date: 2026-10-15. Issue #32. Builds on
[the pr-summary plugin](2026-10-15-pr-summary-design.md).

## Problem

The pr-summary plugin says what a PR was asked to do, what its author claims,
what the code and tests do, why the change was needed, and where those
disagree. It runs only when someone types the command, and takes several
minutes. A reviewer who opens a PR on the board sees none of it.

## What it is

A Summary tab on the PR page, first, before Board. On PRs you review, the
board runs the plugin once per review request, keeps the latest result, and
shows it on that tab. A chip on the wall row and in the PR header counts the
Alignment section's mismatches.

## Decisions

| #   | Decision                                                                                               |
| --- | ------------------------------------------------------------------------------------------------------ |
| 1   | Summaries run on their own only on PRs you review. Your own PRs show the tab with a button to run one. |
| 2   | A run starts when a review is requested from you, so it is ready before you open the PR.               |
| 3   | A push marks the summary stale. A new run starts on the next review request, or when you press Rerun.  |
| 4   | The tab renders the plugin's stdout markdown.                                                          |
| 5   | The board keeps only the latest summary per PR.                                                        |
| 6   | Summaries run one at a time in their own lane.                                                         |
| 7   | Exit status 3 shows its reason and a button that reruns with `--use-github-api`.                       |
| 8   | While running, the tab ticks off each witness as it finishes.                                          |
| 9   | The tab's state sits in a one-line strip above the summary.                                            |
| 10  | Keys follow screen order: Summary 1, Board 2, Dashboard 3, Terminal 4, Diff 5.                         |
| 11  | PRs you review open on Summary; your own open on Board.                                                |
| 12  | A chip counts the Alignment mismatches on the wall row and in the PR header.                           |
| 13  | The plugin gains `--work-dir <path>`, the one change to it.                                            |
| 14  | The mismatch count comes from the judge's `alignment/output.json`.                                     |
| 15  | The newest run's working folder is kept per PR and replaced by the next run.                           |
| 16  | A summary is due once per review request, not once per head SHA.                                       |

## The plugin's one change

`summarise.py` takes `--work-dir <path>`. With it, the plugin writes its
witness folders into `<path>` instead of a fresh `mkdtemp` folder. It creates
`<path>` if missing and refuses one that is not empty, so a leftover
`output.json` can never pass for a finished witness. Without the flag nothing
changes.

The README documents the layout as part of the flag's contract:
`<path>/<witness>/output.json` for `requested`, `claimed`, `implementation`,
`tests`, `why` and `alignment`, each written when that witness finishes. A
plugin test pins the layout.

## When a summary is due

The watcher already emits `ReviewRequested` each time `review_requested`
turns from false to true (`change_detection/_rules.py`). GitHub drops the
request when you review and sets it again when the author re-requests, so
the event fires once per request, and the stored launch queue carries it
across restarts.

The summary record holds two request marks:

- `wanted`: when the latest `ReviewRequested` for this PR was seen.
- `answered`: the `wanted` value the stored summary was run for.

A summary is due when `wanted` is newer than `answered` and no run for that
PR is in flight. Each poll works this out again, as commit checks do. A run
that dies with the process leaves `answered` unchanged, so it is due again
after a restart.

Rerun, the GitHub API button, and the button on your own PRs start a run at
once without touching `wanted`. Each finished run sets `answered` to the
current `wanted`.

## Running

A lane of its own with one slot. Due PRs wait their turn, oldest `wanted`
first. A run is:

1. Delete the PR's working folder.
2. `uv run --script <plugin>/scripts/summarise.py <pr-url> --config <instance config.toml> --work-dir <folder>`,
   plus `--use-github-api` when the button started it, with the repository's
   `local_path` as the working directory.
3. Store the result. Keep the folder.

A run past 25 minutes is killed and stored as failed. The plugin allows six
processes of ten minutes each, and the judge runs only after the five
witnesses finish.

## What is stored

`<data_dir>/summaries/<owner>/<repo>/<n>.json` holds the latest summary:

- `head_sha`: the PR head the run read
- `wanted` and `answered`
- `started` and `finished`
- `exit_status` and `stderr`
- `markdown`: stdout without its final `Working files:` line
- `mismatches`: the length of `mismatches` in `alignment/output.json`, or
  null when that file is missing or malformed

The working folder is `<data_dir>/summaries/<owner>/<repo>/<n>/`.

## What the board serves

The summary joins the board's API as one entity per PR in
`frontend/app/services/store.ts`:

- the stored fields above
- `running` and `since`
- one `done` flag for each witness, read from the working folder on each
  poll while a run is in flight

Two operations go through the existing operation path: `summarise` (Rerun,
or the button on your own PRs) and `summarise-with-github-api`.

Derived values live in `frontend/app/data/summaries.ts`:

- the tab's state
- stale or not, by comparing `head_sha` with the PR's head
- the chip's count

## The tab

The tab bar becomes Summary, Board, Dashboard, Terminal, Diff, with keys 1–5
in that order (`pr-view.gts`, `takes()`). `routes/pr/index.ts` opens Summary
when your role on the PR is reviewer, and Board otherwise.

The tab is a strip above the rendered markdown (`markdownOf`). The strip shows
one state:

| State                | Strip                                                                  | Below the strip              |
| -------------------- | ---------------------------------------------------------------------- | ---------------------------- |
| None yet, reviewer   | A request is waiting (`wanted` set): Waiting for its turn              | nothing                      |
| None yet, author     | No summary, and a Summarise button; a reviewer's with no request too   | nothing                      |
| Running              | Live dot, SHA, elapsed time, and a checklist of the six witnesses      | the previous summary, if any |
| Ready                | SHA and when it finished                                               | the summary                  |
| Stale                | Written for `<sha>`, head is `<sha>`, N commits behind; a Rerun button | the summary                  |
| Needs the GitHub API | The plugin's reason; "Use the GitHub API (about N calls)"              | the previous summary, if any |
| Failed               | Exit status, the end of stderr, and a Rerun button                     | the previous summary, if any |

N commits behind comes from `git rev-list --count <head_sha>..<head>` in the
local clone, run by the board. The strip's tint follows the board's existing
tones: ready ground for stale, red fill for failed.

## The chip

When `mismatches` is above zero, the wall row and the PR header's `.prflags`
show a chip reading "N mismatches". It shows for a stale summary too: the
disagreement is still the latest one known.

## Known limits

- **The board relies on the plugin's folder layout.** The README and a plugin
  test make it a contract.
- **A request the board never sees runs nothing.** If a review is requested
  and answered while the watcher is down, no false-to-true edge is seen.
- **The mismatch count misses a failed judge.** It shows no chip, not zero.

## Testing

Test-first throughout. The plugin's flag gets tests beside its existing ones.
Each of these runs against a fake plugin script that writes the folder layout
and prints markdown:

- the due rule
- the lane
- the store
- the working-folder reader

The front end gets component tests for each strip state and for the key
mapping, and a check in the dev preview in both themes.
