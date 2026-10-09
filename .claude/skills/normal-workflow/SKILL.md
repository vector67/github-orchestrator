---
name: normal-workflow
description: Use for any change to this repository — the branch, worktree, test and merge steps every task here follows, from the first edit to the cleanup after the merge
---

# Normal workflow

1. Open a GitHub issue for the task with `gh issue create`, unless the task already
   came from one (as through `next-issue`): a title naming the change, and a body
   that starts with 🤖 and restates the ask. Note its number for the last step.
2. Cut an isolated workspace through the `using-git-worktrees` skill — never edit
   or commit on `main`. It prefers the harness's own worktree tool, which puts the
   tree under `.claude/worktrees/<branch>`; drop to `git worktree add` only where
   that skill says to. A worktree under `.claude/` is gitignored, so it cannot
   show up as untracked clutter in `git status` the way a sibling `../gho-<slug>`
   does. The harness branches the tree from `origin/main`, which lags the local
   `main` that sessions merge into without pushing, so run
   `git merge --ff-only main` in the new tree before the first edit.
3. Do the work you have been instructed to do. If the work is a refactor, load the
   `refactor` skill first. Run `make lint-python` and `make test-python` before
   each commit, and the full `make lint` and `make test` when anything under
   `frontend/` changed since the last full run: the layering tests run in
   `make lint-python`, not `make test-python`, and only the full targets run the front end's import rules,
   which are what refuse a new import, export or test file. A commit that only
   marks items done in a spec belongs in the same commit as the code it records.
4. Commit with a lowercase imperative subject and no prefix, no co-author trailer.
5. Check the branch for private information before it reaches `main`: the repo is
   public, and whatever merges is pushed. Read `git diff main...<branch>` and
   `git log main..<branch>` for anything CLAUDE.md's public rule forbids — the
   employer, clients, colleagues, ticket keys, home or temp paths, real emails,
   secrets, private claude.ai links, real node ids, PRs or comments copied from
   work — and fix each finding in the worktree. `git rev-list --max-parents=0 <branch>`
   must print only `d9021cb5977b00acf1e6aa9a3b2f8387b8e7c510`: a branch cut before the public commit
   carries the old history, and merging it publishes that history.
6. Merge into `main` only a tree that has already passed. In the worktree, first
   read `git diff --stat main...<branch>` and the pass count each check printed:
   a deletion you did not intend, or a count that fell in a commit that only adds
   tests, is a failed check even though every run was green. A count that fell
   because tests went with the API they covered passes only when the commit
   message names each deleted test and what made it impossible. Then catch up with
   `main`, which other sessions commit to too:
   `git merge main -m "merge main into the <thing>"`, rerun
   `make lint` and `make test`, and commit any fix in the worktree. A worktree
   session cannot reach the main checkout: the isolation guard refuses
   `git -C <main checkout>`. Leave with `ExitWorktree` and `action: "keep"`, then
   `git merge --ff-only <branch>` — `EnterWorktree` names the branch
   `worktree-<name>`. When `--ff-only` refuses, `main` moved again: re-enter the
   worktree with `EnterWorktree` and its `path`, and catch up again.
7. `make restart-all` — always, even for a one-line change. It syncs, rebuilds the
   front end and restarts the watcher and the agent managers, so what you merged is
   what is running. Skip it and the board keeps serving the old build. "Managers
   back up" is not proof the change works: run any CLI command the diff touched
   against the real state, and after a change to how the watcher reads or saves,
   check its log for a clean poll. Evidence counts only when it is newer than the
   restart: compare each log line's timestamp and each file's mtime with when
   `make restart-all` ran. When the request names who will use the result (a
   person, another agent, a runbook), put that consumer through its task on the
   real system: cause the failure the change should explain, say, and have a
   fresh agent diagnose it from what the change produced.
8. Remove the workspace the way the `using-git-worktrees` skill made it, then
   `git branch -d <branch>` (`-D` when nothing is pushed, once
   `git branch --merged main` lists it).
9. Close the issue with `gh issue close <n>` once the merge has passed step 7,
   unless a pushed `Closes #<n>` already closed it. Prove it with
   `gh issue view <n> --json state`.
