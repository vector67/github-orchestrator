# Step brief template

Fill in every `<…>` and hand the result to the step agent as its whole brief.

______________________________________________________________________

You are carrying out step `<n>: <title>` of the plan in
`<plan path>`, in the github-orchestrator repo. Work only in the worktree
`<worktree path>` on branch `<branch>`, freshly cut from local `main`. Use
absolute paths, or `git -C` and `make -C` against that path. The coordinator
merges and restarts, so commit on the branch and stop there. Set the worktree
up first if `make test` needs it (uv sync, front-end packages).

Read first:

- `<plan path>`, whose "How to work" section binds you. The user has approved
  running the steps straight through, so you do not stop to confirm.
- `<spec path>`, the source of truth, and the sections your step names.
- `git log --oneline main -20` and the commit messages of earlier steps, so you
  build on them rather than redo them.

Invoke these skills by name: `normal-workflow` (its steps 2 and 3 only),
`refactor` for reshaping, `tdd` for anything that changes behaviour, and
`show-me-your-work`, keeping its decision log in
`<scratchpad>/<step>/`: every leftover, every budget call and every choice the
spec left open, each with its reason. Write your edit scripts to the same
folder.

## What counts as a reason to leave something

The spec is the decision. How the code stands today is not a reason to keep
it. Change the callers, the prompts and the tests together. Two things can hold
a leftover:

- An external contract the spec fixes. Translate at that one edge, in one
  place.
- Data already on disk on the live machine. Read the old form, write the new
  one, and keep the translation in one place inside the owning module.

Any other leftover names the exact external constraint that holds it, or it is
not a leftover and you do it now.

## Commits

Split the step into commits that each pass `make lint-python` and
`make test-python`. A falling pass count fails the check unless the commit
message names each deleted test and what made it impossible. Mark finished
items **Done** in the spec, with the hash, in the same commit as your last code
change.

## Before you report back

Run the check the coordinator will run, and fix anything that misses. For
every module your step touched:

- `make interface-report`: exports against the budget, and each exported
  class's methods against the cap;
- any word still written in an old form;
- any wording or rule now written in two modules;
- every leftover with the constraint that holds it.

Then run the full `make lint` and `make test` once.

## Report

- the commits, as hash and subject
- the final lint and test pass counts
- the "Before you report back" list, module by module
- the path to your decision log
- the step's items you did not do, and the constraint for each
- any decision the spec did not settle
- any behaviour change a user would notice
