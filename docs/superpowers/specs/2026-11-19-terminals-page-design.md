# Terminals page

Issue: #447. A hub page that lists every terminal session on the instance,
across all pull requests, and says whether each is working, waiting for you, or
idle, plus a chip on the Wall rows of pull requests with a session waiting.

## Decisions

1. **A Terminals page in the hub bar**, between Runs and Setup: Wall · Runs ·
   Terminals · Setup. It lists every session of every pull request the watcher
   holds.
2. **The Terminal tab's layout**: the list on the left; clicking a row opens
   that session's screen beside it, whichever pull request it belongs to. The
   screen connects to the session's own pull request's websocket, as its
   Terminal tab does.
3. **Order**: waiting first, the longest wait at the top, then working, then
   idle. Each row names its pull request, its program and the branch its
   worktree had checked out when it started, says how long the session has
   been open, and has a ▾ arrow that opens its actions menu, the mentions
   list's menu placed in the top layer at the arrow:
   - **Open pull request**, **Open diff**: the session's pull request board, and
     its Diff tab.
   - **Open in Terminal tab**: the pull request's Terminal tab, with this
     session chosen (`?session=<id>`).
   - **Fullscreen**: this session's screen over the whole page, until its ×.
   - **New shell here**: a login shell in the same worktree: the pull
     request's own (`POST /api/terminal/sessions`, keys `new`), or, for a
     session a thread opened, the thread's (`:open-shell` on that thread).
   - **Copy worktree path**, **Copy branch name**: to the clipboard; the second
     is greyed out for a session on no branch.
   - **Open conversation**: the thread that opened the session; greyed out for
     a session no thread opened.
   - **Close**: asks once, then ends that live session.
4. **Working or waiting**:
   - Claude sessions the board starts get hooks through `--settings`:
     `UserPromptSubmit` writes `working` and `Stop` writes `waiting` into the
     session's turn file, `<session>.turn` beside the holder's files. The holder
     names the file to its command in `GITHUB_ORCHESTRATOR_TURN_FILE`. A
     session with a turn file is what the file says, waiting since the file
     last changed.
   - Every other session (codex, git, a shell, a Claude session no hook has
     written for yet) goes by output silence: working while output arrived in
     the last 30 seconds, waiting after that, since the last output (or since it
     started, when it never printed). The holder touches `<session>.output` when
     output arrives, at most once a second, so its modification time is when
     output last arrived.
5. **Idle**: a quiet session is idle unless it is a git session (its command is
   `git`) or the instance's agent program runs in it (any process under the
   holder whose program, or its first argument's, is named as the agent
   command's program). Agent and git sessions that go quiet are waiting.
6. **Wall chip**: a Wall row whose pull request has a waiting session shows a
   `tone-strong` state chip, `1 terminal waiting` or `N terminals waiting`.
   Working and idle sessions get no chip.
7. **Nothing else**: no hub-bar count, no desktop notification, no chip on the
   pull request's own board or the switcher.

## Shape

- `terminal_sessions`: the holder records the branch the worktree's `HEAD`
  names when the session starts (none on a detached head or outside git), read
  from the files, without running git. `TerminalSessions.watched(now, agent)`
  answers each session with that branch, when it started, its activity and, when waiting, since when.
  A thread's fix, answer and shell sessions also record the thread's key, passed
  down from `agent_runs` through `PrProcesses.split`.
  `TerminalSessions.close(session)` ends one live session as hanging up ends
  them all.
- The hub serves `GET /api/terminal-sessions`, every held pull request's
  sessions in the page's order. Each pull request's board serves
  `POST /api/terminal/sessions/{session}:close`.
- The Wall's `HeldPullRequest` carries `terminals_waiting`.
- Codex sessions get no hooks; they and everything else go by silence, so the
  page works the same with either agent.
