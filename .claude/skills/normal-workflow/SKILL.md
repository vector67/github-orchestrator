---
name: normal-workflow
description: Use for any change to this repository — the branch, worktree, test and merge steps every task here follows, from the first edit to the cleanup after the merge
---

# Normal workflow

The change lands on a target branch: `main`, unless the caller names another,
such as a release's `release-X.Y.Z`. A change that lands on another target is
merged into `main` straight after, so `main` never lacks a fix the release has.

1. Open a GitHub issue for the task with `gh issue create`, unless the task already
   came from one (as through `next-issue`): a title naming the change, and a body
   that starts with 🤖 and restates the ask. Note its number for the last step.

2. Cut an isolated workspace through the `using-git-worktrees` skill — never edit
   or commit on `main` or the target. It prefers the harness's own worktree tool, which puts the
   tree under `.claude/worktrees/<branch>`; drop to `git worktree add` only where
   that skill says to. A worktree under `.claude/` is gitignored, so it cannot
   show up as untracked clutter in `git status` the way a sibling `../gho-<slug>`
   does. The harness branches the tree from `origin/main`, which lags the local
   `main` that sessions merge into without pushing, so run
   `git merge --ff-only main` in the new tree before the first edit. For another
   target, cut the tree from the target instead:
   `git worktree add <main checkout>/.claude/worktrees/<name> -b <name> <target>`,
   then `EnterWorktree` with its `path`. Give the absolute path: Bash keeps its
   working directory between calls, so a relative path run from inside another
   worktree nests the new tree in that one.

3. Do the work you have been instructed to do. If the work is a refactor, load the
   `refactor` skill first. Run `make lint-python` and `make test-python` before
   each commit, and the full `make lint` and `make test` when anything under
   `frontend/` changed since the last full run: the layering tests run in
   `make lint-python`, not `make test-python`, and only the full targets run the front end's import rules,
   which are what refuse a new import, export or test file. A commit that only
   marks items done in a spec belongs in the same commit as the code it records.
   A change to an agent prompt (an agent, skill or brief) is not verified until
   you have run it as the system runs it, or in a subagent given the same prompt
   and inputs, and seen the requested behaviour change in its output: lint and
   tests never run a prompt.

4. Commit with a lowercase imperative subject and no prefix, no co-author trailer.
   Write `Closes #<n>` only when the commit fixes the whole issue, and `Refs #<n>`
   for part of it: a pushed `Closes` closes the issue either way. File what is left
   as its own issue before the push, with the same release pick as the original.

5. Check the branch for private information before it reaches the target: the
   repo is public, and whatever merges is pushed. Read `git diff <target>...<branch>`
   and `git log <target>..<branch>` for anything CLAUDE.md's public rule forbids — the
   employer, clients, colleagues, ticket keys, home or temp paths, real emails,
   secrets, private claude.ai links, real node ids, PRs or comments copied from
   work — and fix each finding in the worktree. `git rev-list --max-parents=0 <branch>`
   must print only `d9021cb5977b00acf1e6aa9a3b2f8387b8e7c510`: a branch cut before the public commit
   carries the old history, and merging it publishes that history.

6. Merge into the target only a tree that has already passed. In the worktree, first
   read `git diff --stat <target>...<branch>` and the pass count each check printed:
   a deletion you did not intend, or a count that fell in a commit that only adds
   tests, is a failed check even though every run was green. A count that fell
   because tests went with the API they covered passes only when the commit
   message names each deleted test and what made it impossible. Then catch up with
   the target, which other sessions commit to too:
   `git merge <target> -m "merge <target> into the <thing>"`, rerun
   `make lint` and `make test`, and commit any fix in the worktree. A worktree
   session cannot reach the main checkout: the isolation guard refuses
   `git -C <main checkout>`. Leave with `ExitWorktree` and `action: "keep"`, then
   `git merge --ff-only <branch>` — `EnterWorktree` names the branch
   `worktree-<name>`. When `--ff-only` refuses, `main` moved again: re-enter the
   worktree with `EnterWorktree` and its `path`, and catch up again.

   For another target, nothing checks it out, so land the branch from the main
   checkout with `git fetch . <branch>:<target>`, which like `--ff-only` refuses
   anything but a fast-forward. Then merge it into `main` the same way: re-enter
   the worktree, `git merge main -m "merge main into the <thing>"`, rerun
   `make lint` and `make test`, leave, and `git merge --ff-only <branch>`. That
   merge stays off the target, so the release never picks up what `main` gained.

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
   `git branch --merged main` lists it). A tree the Agent tool cut for a subagent
   stays locked as `claude agent <id> (pid N …)` after the agent ends. When
   `ps -p N` shows that pid is this session, the tree is clean and its branch is
   merged, run `git worktree unlock <path>` and remove it without asking.

9. Close the issue with `gh issue close <n>` once the merge has passed step 7,
   unless a pushed `Closes #<n>` already closed it. Prove it with
   `gh issue view <n> --json state`. A merge that delivers only a spec or a plan
   leaves the issue open as the tracker for the build: comment on it with the
   spec's path instead.
