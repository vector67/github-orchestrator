---
name: next-issue
description: Use for "work on the next issue", "grab the next issue" or "pick up an issue" — takes the oldest open GitHub issue in this repo through to closed
---

The next issue is the oldest open one: `gh issue list --state open --limit 50`, lowest number. Read its body and every comment with `gh issue view <n> --json title,body,comments`, since the comments often narrow or restate the ask; `--comments` outside a terminal can print nothing at all, body included, which reads as an empty issue. Then check it against `main`, because recent commits often fix an issue without closing it. If the fix is already there, show the evidence and ask before closing. Otherwise do the work through `normal-workflow`, pushing `main` after the merge. Close the issue by putting `Closes #<n>` in the commit message; the push closes it, and the issue gets no comment. `git push` saying "Everything up-to-date" can mean another session already pushed a `main` holding your merge, so prove it with `git fetch -q origin`, then `git merge-base --is-ancestor <branch> origin/main` and `gh issue view <n> --json state`.
