---
name: run-plan-steps
description: Use when running a multi-step plan in this repository as a sequence of subagents, one step per worktree, from settling the rules before the first dispatch to reviewing and merging each step
---

# Run plan steps

A **step agent** carries out one step of a committed plan in its own worktree
and reports back. This session is the **coordinator**: it settles the rules,
briefs each step, reviews what comes back, merges and restarts. The costliest
failure in the 2026-09-25 narrowing was the **second round**: a step handed
back, the coordinator rejected its leftovers against rules the brief never
stated, and the step redid its commits (about 118 minutes over 6 of 9 steps).
Everything below exists to make the first round the last.

1. **Settle the rules before the first dispatch.** Grill the user on every
   policy each step will be judged by: what counts as a reason to leave
   something, the export budget and method cap, what data on disk justifies
   (reading old forms, never writing them), which checks run before a commit.
   Write them into the plan's "How to work" section and commit it. Done when
   every rejection reason you can foresee is a sentence in the committed plan.

2. **Brief the step from [`step-brief.md`](step-brief.md).** Fill in the plan,
   the spec, the step's section and a scratch subfolder of its own. Keep the
   brief to what CLAUDE.md does not already say: the step agent loads
   CLAUDE.md itself.

3. **Dispatch one step at a time** as a background subagent pinned to a fresh
   worktree cut from local `main`. If a rule changes while the step runs, stop
   it and relaunch it with the new brief: a relayed rule arrives after
   commits made under the old one, and unpicking them cost Step 2 about 28
   minutes.

4. **Review against the brief's own "Before you report back" list**, the same
   list the step agent ran: `make interface-report` for the budgets, then every
   leftover against the external constraint it names, then the decision log.
   Send back only what misses a written rule, quoting the rule. Done when every
   touched module is within budget and every leftover names a constraint that
   holds in the code.

5. **Merge and restart through `normal-workflow`** steps 4 to 6, then return to
   step 2 for the next plan step.

6. **Check test speed once the last step is merged.** With no other test runs
   or agents going, run `make measure-test-speed` on `main` and compare its
   medians with the latest row of [`docs/test-speed.md`](../../../docs/test-speed.md),
   taken at a similar load. If either median is more than about 20% slower,
   find the tests the plan added or slowed and make them cheaper before calling
   the plan done. Then add a row for this run to that table and commit it. Done
   when the new row is committed and within about 20% of the one above it.
