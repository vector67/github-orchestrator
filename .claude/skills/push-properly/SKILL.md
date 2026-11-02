---
name: push-properly
description: Use for "push", "push main" or "push properly" in this repository — checks the unpushed commits for private information, pushes main or the branch the caller names, watches CI, and fixes a red run through normal-workflow until it is green
---

# Push properly

The target is `main`, unless the caller names another branch, such as a
release's `release-X.Y.Z`. `<pushed>` below is `origin/<target>`, or
`origin/main` while the target is not on `origin` yet.

1. Push only the target, from the main checkout. Run `git fetch -q origin`, then
   `git log --oneline <pushed>..<target>`. If it prints nothing and the target is
   already on `origin`, there is nothing to push: say so and stop. A target not
   on `origin` yet is pushed even with no commits of its own.

2. Run `uv run python .claude/skills/push-properly/leak_check.py <pushed>..<target>`.
   It prints one line per hit: kind, where (a file or `commit <sha>`), and the
   line. It covers home and temp paths, emails, real-shaped tokens, claude.ai
   links, and every term in `~/.config/push-properly/denylist.txt`, one per line.
   That file holds the employer, clients, colleagues, ticket prefixes and private
   repo names, and it never enters the repo. Judge each hit: a fixture's
   `/Users/octocat` is fine; a real person's path is not. Then read
   `git log --stat <pushed>..<target>` and skim the diff for what no pattern can
   name: a real person or company not on the denylist, or text copied from a work
   PR or ticket. CLAUDE.md's public rule is the test.

3. If anything private turns up, stop and show the user each finding. A
   follow-up commit still publishes the leak in history, and rewriting the target
   moves it under every worktree cut from it, so the fix is the user's call.

4. `git rev-list --max-parents=0 <target>` must print only
   `d9021cb5977b00acf1e6aa9a3b2f8387b8e7c510`.

5. `git push origin <target>`. "Everything up-to-date" can mean another session
   pushed first, so prove the push with
   `git merge-base --is-ancestor <target> origin/<target>`.

6. Watch CI for the pushed commit:
   `gh run list --workflow CI --commit $(git rev-parse <target>)` gives its run id
   once it appears, and `gh run watch <id> --exit-status`, run in the background,
   waits for the run to finish. A newer push from another session can supersede
   the run; then watch the run for the new `origin/<target>`.

7. When the run fails, read `gh run view <id> --log-failed`, then fix the cause
   through `normal-workflow` with its own issue and the same target: red test
   first. A failure that only CI shows usually comes from CI's environment. CI
   and every install run Python 3.12, so reproduce it there first with
   `uv run --python 3.12 pytest …`. Then start this skill again from step 1.

8. Done when the CI run for the pushed target is green. Report its URL and the
   commits it carried.
