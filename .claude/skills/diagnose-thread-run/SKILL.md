---
name: diagnose-thread-run
description: Use when a thread's fix run did something unexpected — ignored a rework, proposed a stale diff, stopped, failed or never reported — or the board refused an action, an accepted fix's push failed or a thread is stuck landing, to find out what actually happened before reading the orchestrator's code or running any verb on the thread
---

# Diagnose a thread run

What happened lives in places outside this repository: the first three for a run, the
fourth too for a refused action or a landing. Read them in this order; the
orchestrator's code comes last, and only explains how that output reached (or missed)
the board.

1. **The thread's state.** `$XDG_DATA_HOME/github-orchestrator/threads/<owner>/<repo>/<pr>/`
   (`~/.local/share` when the variable is unset) holds one `<thread>.json` per thread,
   a `-<suffix>` copy per run worktree. Read it with `jq`: `fix_state`, `run_kind`,
   `attempts`, `rework_brief`, `plan`, `tests_note`, `fix_summary`, `agent_note`,
   `thread_sha`, `base_sha` and `operations[]` (each request with its brief and state).
   A `fix_summary` or `agent_note` that answers an earlier brief means this run never
   reported. `tests_note` "run exited without reporting; commit found in worktree" is
   the salvage path: the proposed commit is whatever HEAD was, often the last attempt.

2. **The worktree.** `…/github-orchestrator/thread-worktrees/<owner>/<repo>/<pr>/<thread>-<suffix>/`.
   `git log` shows which commits each run made (compare their times with
   `runs.jsonl`); `git status` and `git diff HEAD` show work the run left uncommitted.

3. **The run's own transcript.** Under the `projects/` folder of the agent config dir
   the run used (`CLAUDE_CONFIG_DIR`, else `~/.claude`), in the folder named after the
   worktree's absolute path with every character other than a letter or digit turned
   into `-`; the newest `.jsonl` is the
   last run. Its final assistant text is what the agent said when it stopped:

   ```bash
   jq -r 'select(.type=="assistant") | .message.content[]? | select(.type=="text") | .text' <run>.jsonl | tail -n 40
   ```

4. **The PR checkout**, for a refused action or a landing whose push failed. It is not
   under `thread-worktrees/`: its path ends the last
   `Agent manager started for <owner>/<repo>#<pr> in <path>` line of
   `logs/agent-manager.log`. There, `git reflog show --date=iso origin/<branch>` lists
   every push; an `update by push` the landing did not make means something else
   pushed the branch, often another thread's run on the same PR, so read
   `git -C <tree> reflog` for each tree in `git worktree list --porcelain` to find
   which. The refused request itself is a `POST …/operations:<verb> -> 409` line in
   `logs/server.log`.

The diagnosis is done when you can say what the run changed, what it reported (or that
it reported nothing), what the board therefore showed, and, for a landing, what moved
the PR branch.

## Before you repair through the board's verbs

Stop, rework and reset-to-origin discard what the operator queued. Before sending one,
read the thread's `pending_reply` and the `text` and `brief` of each `operations[]`
entry with `jq`, and quote them back to the operator. A request the board refused left
no text in the record; read it from the board tab in the browser before asking the
operator to type it again.
