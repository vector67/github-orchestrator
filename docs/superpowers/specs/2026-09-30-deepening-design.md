# Deepening the hot spots

Eight deepenings found by an architecture review of the modules that changed
most in the 300 commits before 2026-09-30. Each item names the friction, the
module that absorbs it, and what must not move. The module map spec
(`2026-09-23-module-map-design.md`) and the board API decisions
(`2026-09-22-board-api-decisions.md`) still bind every item: one wiring module
under Dishka, a fake per module with shared contract tests, the export budget of
about 5 and the method cap of about 10, one refusal type per module, the HTTP
thread reading only the published snapshot while commands cross into the loop,
and "the back end refuses; it does not enumerate".

## 1. Each polled endpoint owns its reachability (front end)

Files: `frontend/app/services/toasts.ts`, `services/hub.ts`,
`services/dashboard.ts`, `services/threads.ts`, `routes/conversations.ts`.

Today `ToastsService` counts misses per `Source`, asks `/api/health` and owns
the banner and outage wording, and every poller hand-writes the etag read, the
change check, the flip, `reportError` and `toasts.lost/restored(source)` (7
copies). `hub.ts` and `dashboard.ts` both report into `'server'`, so a good read
of one endpoint clears the other's misses. `hub.refresh` counts an unanswered
read as a miss of the shared `'server'` source, and `startBar`'s timer has no stop.

The deepening: one polled-source module that owns an endpoint's tag, change
check, flip, error reporting and its own miss count, and one reachability module
that folds those counts into the banner and outage wording. Toasts only shows
toasts. Keep the motion spec's rule (banner after two failed polls, hidden on
the first good one) and the heavy-load wording from `252f38e8`.

Behaviour changes a user can notice, all intended: two endpoints no longer
clear each other's misses; a hub poll that comes due while its endpoint's last
read is still unanswered counts one miss for that endpoint, not for a shared
source; the bar's timer stops when its route leaves. **Done** (the commit that
records this).

## 2. One command surface for the PR manager (python)

Files: `pr_manager/_manager.py`, `pr_manager/_panel.py`,
`pr_manager/interface.py`, `pr_manager/_terminal_front.py`,
`board_api/interface.py` (`ManagerPanel`), `board_api/fake.py`.

The same manager actions have two vocabularies: `Controls` for the terminal
front, and `ManagerPanel` → `LoopPanel` → `Command` enum → `_obey` match for the
board. The frozen-worktree refusal is written four times (`_manager.py` around
98, 114, 217 and `_terminal_front.py` around 280). The board starts through the
loop but the terminal front stops it and sets `want_board` itself. Mark-ready
touched four places in pr_manager alone.

The deepening: one manager-commands module owns every action, the freeze rule
once, and the board's start and stop. It satisfies `ManagerPanel`, the terminal
front calls it, and the cross-thread queue carries "run this on the loop"
rather than one enum value per verb. `ManagerPanel` stays board_api's port;
commands still cross into the loop thread. The terminal front keeps presenting
and stops reaching `pr_work`, `pr_windows` or `history` for actions the
commands module owns.

**Done** (`3089e4c0`, `b930df66`, `71b14624`, `eb5630ff` and the commit that
records this): `pr_manager/_commands.py`'s `ManagerCommands` answers
`ManagerPanel` and every action both fronts take, wiring builds it once for the
loop and the front, and `Controls`, `LoopPanel` and the `Command` enum went. A
call from the board's thread is queued as a closure the loop runs at its next
drain; one made on the loop's own thread, a key or the loop's own carry on,
runs at once. The freeze rule is one function reading the published
dashboard's `frozen_on`, with one wording. The commands start and stop the
board and record whether it is wanted. `ManagerPanel` has one `set_on_hold` in
place of `hold` and `resume`, ten methods.

## 3. One decision module (front end)

Files: `frontend/app/data/verbs.ts`, `data/dialogs.ts`,
`components/panel-actions.gts`, `services/board.ts`.

A thread decision's name keys `KEYS`, `LABELS`, `WEIGHTS`, `TITLES`, the
per-phase label and weight tables, `QUEUED_LABELS`, `QUEUED_SQUARES`, the
`requestOf` switch and `dialogFor`, while `PanelActions.decide` special-cases
`rework`, `reply` and the `not-fixed` prefill, `SENT_AS_SAVED` holds `enrol` and
`post-now` behind unsaved drafts, and `board.decide` special-cases
`start-session`.

The deepening: one decision module holding one entry per decision (key, label,
weight, dialog or composer, gating, request shape, queued toast, what follows),
behind two operations: which decisions are offered for this conversation and
role, and carry out this decision with what was gathered. The panel, the keys
and the dialog read the same entry. No behaviour change.

**Done** (`f573f8af` and the commit that records this): `data/decisions.ts`
holds one entry per decision with its key, label, weight, title, dialog or
composer, whether it waits for a saved draft, when it is offered, its request,
its in-flight wording, its Queued toast and whether it opens the terminal, and
keeps the per-phase and reviewer wording inside the entry. `offered` hands the
panel, its keys and its dialog one offer per button, and `board.decide` carries
out every decision through `carriedOut`, rework and reply included. `verbs.ts`
and `dialogs.ts` went, and the key help reads its letters from the entries. The
button order per phase stays one table per role, because it is not a fact about
any single decision. `edit-draft` is carried out the same way and has no
button.

## 4. One place builds a PR's dashboard (python)

Files: `pr_manager/_snapshot.py` (`dashboard_of`), `pr_manager/_manager.py`,
`pr_manager/_unmanaged.py`, `board_api/_projection.py`, `preview/__init__.py`.

The managed and unmanaged paths each gather the inputs from change detection,
working copies, worklist, holds, dismissals and conversations, with small
differences: the manager passes `unpushed_commits=None` then patches it with
`replace()`, `Frozen` is copied field by field from `WrongBranch` twice, and the
projection re-nests groups and drops a group when any one field is `None`
(verify this; fix it only if it drops something a user should see). The
preview hand-writes all 50 fields, including wording `_snapshot` owns.

The deepening: a per-PR dashboard source inside pr_manager answers the whole
`Dashboard` from the modules. The loop adds only what only it knows (the active
run and the notice); the unmanaged path is the same source with those empty.
The preview builds its dashboards through it, or through its inputs, rather than
restating owned wording. `Dashboard` stays flat (export budget) and its wording
stays as web-interface step 2 set it.

**Done** (`1598d31e` and the commit that records this):
`pr_manager/_dashboard_source.py`'s `DashboardSource` builds every PR's
dashboard. The hub asks it through `Dashboards`; the loop asks it for a
`Drawn` and adds its active run, its notice, its own conversation manager
(whose live thread runs only it knows) and the verdict of its own
`report_branch` (the watcher can take the flag on disk away mid-tick).
`Drawn` counts unpushed commits only when read, `Frozen` went for the
`WrongBranch` working copies export, and both paths read the last run from
the runs ledger. The projection's None-drop stays: the source fills each
group from one value, and a stopped run or a frozen worktree out of grace
keeps its group. The preview builds its panel through the source in its own
container and adds only a live run.

## 5. Wiring stops re-spelling constructors (python)

Files: `wiring.py`, `watcher/_cycle.py`, `conversation/_threads.py`,
`pr_manager/_config.py`, `settings/`.

`ManagerLoop` (18 collaborators), `PollingWatcher` (17) and `OperatorCli` (14)
are each written in their `__init__`, their provider signature and their
constructor call, so any new edge is a wiring edit. `PollingWatcher` takes 17
modules only to hand subsets to `Placement` (8), `Teardown` (9) and
`WatchedHoldings`. Clocks are positional `Callable[[], datetime]` that types
cannot tell apart. `claude_enabled` is copied into five config types and
`gh_account` into four; conversation copies `ThreadsConfig` into a second
internal `Settings`.

The deepening: providers let Dishka build implementations from their own
`__init__` hints; clock, monotonic and sleep get distinct types; `Placement`,
`Teardown` and `WatchedHoldings` are provided as parts and injected into the
watcher; each module takes one config value it owns, built once, and
conversation drops its second copy. Provider classes stay in `wiring.py`. Keep
the one-graph-per-provider-shape caching from `37a64edc`/`814aba9a` and the
guard that providers hold no values (`7ec1f8cc`).

**Done** (`c81e34b8`, `af131d82`, `a0cd7de8` and the commit that records
this): the kernel admits `UtcClock`, `LocalClock`, `Monotonic` and `Sleep`,
and one `ClocksWiring` part provides one of each per container, so no
module's wiring carries a clock and a test world's modules share its clocks.
`Placement`, `Teardown` and `WatchedHoldings` are provided parts and the
watcher takes them in place of the five modules it only passed on.
`PollingWatcher`, `HealthFiles`, `ManagerLoop`, `ManagerCommands`, both
fronts, `DashboardSource`, `OperatorCli` and `GitHubConversationManagerFactory`
are built from their own `__init__` hints, their configs and callables reaching
the container by type. The manager's config is built once, its terminal front's
copy went with that front's wiring, and conversation's ports carry the
`ThreadsConfig` wiring built in place of a second `Settings` copied from it.
`ManagerConfig.gh_account` and conversation's `not_fixed_opener` went, read by
nobody. The providers of the leaf modules still build from their wiring's
values: their constructors take paths and numbers dishka can key only by type,
and callables whose aliases are the same key (GitHub's, git's and the preview's
`Callable[..., CompletedProcess[str]]`; tmux's, the CLI's and the desktop's
`Callable[..., CompletedProcess[Any]]`), and the board and hub providers import
their servers lazily.

## 6. Conversation owns delete eligibility (python)

Files: `board_api/_app.py` (`can_delete`, `_deletes`, their callers),
`conversation/_domain/machine.py`, the conversation interface.

`can_delete` is a domain rule (you wrote it, it is a review or issue comment,
it has an id, it is not deleted, every comment in the thread is yours) living
in the HTTP layer and comparing raw `comment_type` strings. `_deletes` turns
`delete_comment=true` into `false` without saying so.

The deepening: conversation decides. The board passes `delete_comment` as asked;
a delete the rule forbids comes back from the machine table as a `Denied` with
its own code and reason, and the board answers 409. The user decided on
2026-09-30 that it refuses rather than downgrading. The front end offers the
delete only where the conversation says it applies, from a question the
snapshot already answers or one it gains, and shows the refusal's reason.
The OpenAPI YAML and the front end's contract JSON change with it.

**Done** (the commit that records this): `_yours_to_delete` in the machine
table refuses an approve, resolve or reject asking to delete a comment that is
someone else's, of a kind GitHub deletes none of, without an id, or replied to
by anybody else, as `not-deletable` with a reason naming which. The account
reaches it on the command, filled by the ask and the drain from the settings,
so `ConversationManager` gained no method. The board passes `delete_comment`
as asked and answers the refusal 409; `can_delete` and `_deletes` went. A
comment already gone is not refused: the domain already takes a delete of a
lost root as a plain close, and two tests pin it. The front end keeps drawing
the delete tick from what the snapshot already carries (the root's author,
kind, id and deletion, every comment's author, the viewer), because the back
end refuses and does not enumerate, and shows the refusal's reason in its
toast as it does any code it has no words of its own for.

## 7. PR controls as one module (front end)

Files: `frontend/app/services/dashboard.ts`, `services/hub.ts`,
`components/dashboard-tab.gts`, `components/wall.gts`, `data/dashboard.ts`,
`components/git-palette.gts`.

Hold, resume, release and dismiss exist in both `HubService` and
`DashboardService`; `flipHold` picks the route by `isLive`. Why a control is
held back is split between `carryOnHeldBack` in `data/dashboard.ts` and four
`BOARD_DOWN_*` getters in the component. The x-then-u/f dismiss confirmation is
written in `wall.gts` and `dashboard-tab.gts`, and release gating in both.
`dashboard-tab.gts` also carries the git palette's state machine.

The deepening: a PR-controls module that, given a PR and whether its board is
live, says what each control offers or why it is held back, and carries it out
through the right route. The wall and the tab both read it. The git palette's
state becomes its own module next to its template. Builds on item 1's services.
No behaviour change beyond the wall and the tab agreeing where they differ
today; name every such difference.

**Done** (`f789bc81` and the commit that records this):
`services/pr-controls.ts` says, for a pull request and whether its board is
live, what each control offers or why it is held back, and carries it out; the
wall asks it per row and the tab for its page, and the control methods left
`HubService` and `DashboardService`. Hold goes to whoever produced the
dashboard on screen, the manager for the tab reading its board and the hub
otherwise, as the tests pinned both. The dismiss question is one
`DismissConfirm`. The wall took the tab's rules: dismiss waits for an answering
board, a frozen row takes only `w`, a dismissal says the manager has exited,
and the question stays open on a key that answers nothing on both. The git
palette's state is `components/git-palette-state.ts`.

## 8. Keyboard as a stack of scopes (front end)

Files: `frontend/app/services/keys.ts`, `components/rail.gts`,
`components/wall.gts`, `components/pr-view.gts`,
`components/dashboard-tab.gts`, `modifiers/modal.ts`, `services/threads.ts`.

`KeysService` has nine registration methods with one caller each, and the
precedence is one hard-coded expression in `handle()`. The board's keys live in
the service while the wall's and the PR view's live in their components, and
the git palette reaches the tab through the dialog branch. The ready-keys rule,
the conversation-id regex, open-and-mark-seen and the clamped j/k step are each
written twice.

The deepening: each surface pushes a keymap tagged with its layer (dialog,
screen, tab, board) and the keys module owns the ordering; the board's own keys
move to the board. Each duplicated rule is written once. Keep `42cf42c9` (a
modal owns the keyboard) and `1b578115` (held Enter is ignored). No behaviour
change.

**Done** (`e630413b`, `4fda568c` and the commit that records this): a surface
pushes a keymap on its layer and drops it when it goes; with a dialog on the
stack only the dialog layer hears a key, otherwise the screen, the tab and the
board do, newest first in a layer, and then any keymap's `otherwise`. The pull
request view's own keys are its `otherwise`, so the tab and the board still
shadow its o, y and Esc while its open switcher still comes first. A modal
answers its own keys (the dismiss and close questions), and so does the open
git palette. The board's own keys are `services/board-keys.ts`, pushed by the
conversations and board routes; the panel's decision keys and the diff fold
push board keymaps of their own. The open conversation's id and
open-and-mark-seen live in board-keys, the ready keys in `threads.readyKeys`,
the clamped step in `stepped`, and the control keys the wall and the tab share
in one table in `pr-controls`, which the key help and the buttons read.
Collapsing the copies changed three things: the panel's "k of m ready" counts
an unreadable card as the heading does, k from no open row lands on the first
row as j does, and the columns view walks the rail's threads on every visit.
