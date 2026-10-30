---
name: diagnose-thread-run
description: Use when a thread's fix run did something unexpected — ignored a rework, proposed a stale diff, stopped, failed or never reported — to find out what the agent actually did before reading the orchestrator's code
---

# Diagnose a thread run

What the agent did lives in three places outside this repository. Read them in this
order; the orchestrator's code comes last, and only explains how that output reached
(or missed) the board.

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

The diagnosis is done when you can say, from these three, what the run changed, what
it reported (or that it reported nothing), and what the board therefore showed.
