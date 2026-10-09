# Module map

The repository is split by process and by history. `common/` is shared by
whichever process needed a helper first. `github_pr_watcher/`,
`github_pr_agent_manager/` and `review/` each reach into the others where it
was convenient. A test audit on 2026-09-23 read all 2,982 tests and found that
695 of them get into the code past its interface. They call private helpers,
patch collaborators inside the same module, or read module globals. The reason
is almost never the test. The code has no way in that a test could use: no gh
seam, no tmux seam, data-dir paths fixed at import, no injected clock or key
reader.

This spec regroups the code into 15 modules, gives each one a single way in, and
wires them with Dishka. The move is done: the 15 packages exist and main runs
them (`fa6ed0b5`). The second half is narrowing each module's interface, and
the rules and per-module decisions for that are below. The board's HTTP API
does not change.

The map was settled in a grilling session on 2026-09-23 and edited on a shared
page (private design page). The interface rules
and the per-module decisions were settled in a second grilling session on
2026-09-25. Each module entry marks what is **done** and what is **to do**.

The second session's questions and answers are in
[2026-09-25-exports-grilling-record.md](2026-09-25-exports-grilling-record.md).

## What a module is

A module handles one concrete piece of what the orchestrator does. It hides
one design decision that could change, sits behind a thin interface, and can
be tested on its own through that interface. Where the lines go follows Parnas
(1972): each module "is characterized by its knowledge of a design decision
which it hides from all others", and the split is never along the steps of a
flowchart. Things that change for the same reason sit together (Martin); a
module can be replaced without touching its callers (Fowler).

## The rules

**One interface, one instance, injected.** Every module has one interface that
every other module sees. A single instance per process provides it, and Dishka
injects it wherever it is needed. Calling methods on that object is the only
way to use the module. No module builds its own collaborators or reaches for a
module-level global, and nothing but the wiring module constructs an
implementation.

**Handles are part of the interface.** A module that manages many things (runs,
worktrees) may return small objects with their own methods. A handle's type is
published with the interface, only its module creates one, and it is tested and
kept thin like the rest of the interface.

**Tests go through the interface only.** No test reaches a module's insides:
no private helpers, no patching of the module's own collaborators, no
assertions on its internal calls, no seeding of internal state. Inside a
module's own tests the only thing faked is the outside system (`gh`, `git`,
`tmux`, `claude`, launchd, the clock), and where that system is cheap to run
for real, as git in a temporary directory is, the test runs it. A test that
sets up a state no public call can produce was testing something impossible;
rewrite it through the interface or delete it.

**Outcomes, not commands.** GitHub's contract is the outcome: "this PR's
checks", "reply posted to thread T". Its fake holds that state rather than
recording the commands that would produce it.

**Each module ships its fake.** Every module keeps an in-memory fake in
`<module>.fake`, and one set of contract tests runs against both it and the
real implementation, so the fake cannot drift. Callers' tests use the fake.

**One wiring module, Dishka.** One module holds a `Provider` per module and a
function that builds the container from settings. Settings reach each provider through its constructor, so a
module receives its own values and never the whole settings object. Tests build
their container in `tests/conftest.py` from the real providers plus the fake
ones. No object is ever handed the container: that turns it into a service
locator.

**Enforced by the layering test.** `tests/test_layering.py` covers the whole
repository. Its `PACKAGES` table gives each package one entry: the exports it
pins, the packages it may import, the packages that may import it, and the
submodules outside code may reach. Four rules run once per entry, and
bespoke tests remain only where a rule fits one package. From outside a
module, import only its package, whose `__init__` exports the interface, or its
`<module>.fake`. Only the wiring module imports an implementation. Nothing
outside a package imports a `_`-prefixed name from it.

## Interface rules

Settled 2026-09-25. The goal is fewer dependencies through narrower
interfaces. Many imports in a top module are fine: a hub-and-spoke graph is the
intended shape. What is not fine is an interface that reveals what its module
hides.

**The export budget.** A package exports about 5 names. An exceptional module
goes up to 10: conversation, agent runs, and GitHub if it needs it. A name
counts only if some module outside the package has to write it, in an
annotation, a constructor call, an `isinstance` or a `match`. A return type
that callers only read fields from stays out of `__all__`. Fakes in
`<module>.fake` do not count. The layering test pins each package's export
list and fails on a name no outside module writes. **Done** (`e8192613`,
`d627d666`, `2b8687cd`): no package exports a fake; tests and another
module's fake are not outside users; a local annotation mypy could infer
does not count, and a type looked up by value (`container.get(Settings)`)
does. A second check fails on an outside module that imports a name only to
read fields off it. No exported constant is left for callers to compare
against.

**The method cap.** An exported object has about 10 methods. Methods do not
count toward the 5 names.

**Roles, split by domain role.** A module too wide for one object splits into
roles named for what they are in the module's own terms (Decisions, Drafts,
Reading), never for the caller that happens to use them. Any caller uses
whichever roles it needs, and a role gains a method only when the method is
part of that role. Roles may compose the module's application logic freely;
the logic itself lives once, inside the module.

**Methods, not command objects.** A caller asks with a method and plain
parameters (`decisions.defer(key, until, note)`). Command classes stay private
data inside the module.

**Questions where callers decide, enums where the word is the product.** A
caller that branches on a module's state asks the module a question
(`fix.is_settled`, `review.approves`, `facts.ci_passed`) and never compares a
state word. A word that is displayed or sent on, such as a state the board
shows, is an enum owned by the module. Module-level string constants that
callers compare against are a leak.

**The module's own terms.** An interface describes the module in its own
domain terms, never shaped to one caller's needs. When a caller finds
something missing, adding it is a separate decision. Where a domain object
would expose internals, a DTO at the boundary trims or extends it.

**One refusal type.** A module says no by returning one refusal value (review
threads' `Denied(code, reason)`), with codes the module itself gives. Another
module's exception never crosses it: conversation turns a git failure into
`Denied(GIT_FAILED, …)`.

**No module knows another's layout.** Each module owns its folders, creates
them when it first needs them, archives them when the repo switches
(`archive_other_repos(keep, into)`, with the archive folder passed in by the
caller) and never hands out a file name, path or storage format. Callers get
typed values and format their own output. Paths, file names and nanosecond
stamps in return values, and CLI output that is a file format, are leaks.

**Callers pass facts; the owner decides and words.** A caller states what
happened. The module that owns the concern decides what follows and writes the
text: notifications picks batching, timing, badge and wording; agent runs
writes every prompt; working copies returns the verdict on branch trouble;
settings owns the rule for when a dismissal ends.

**A rule lives once.** Knowledge or behaviour written in two modules moves to
the one that owns it, whether or not the spec named it. File-system mechanics
with no domain meaning, such as the tmp-then-rename atomic write, may stay
copied in each module that stores files.

**Values come from their owner.** A caller never tells a module something
another module owns. `conversation.of(repo, pr)` takes nothing else; the
worktree, the role, whether a run is live and whether Claude is enabled each
come from the module that knows them.

## The shared kernel

`github_orchestrator.domain` holds the values that several modules use with
the same meaning and no module owns, as an integer is. Its admission rule:

- immutable value types only, with no behaviour beyond parsing or validating
  themselves
- it imports nothing
- each entry is used by at least two modules with the same meaning
- its entry list is pinned by the layering test, so each addition is a
  visible decision

It holds five entries. **Done** (`2e3a4eba`, `0f23b764`, `e7bcbf30`,
`a7d01486`, `03a0cea1`; `Sha` in `0cadd4dd`). `Pr` spells a PR in all three forms
(`owner/name#n`, `short` for `name#n`, `in_repo` for `#n`) and nothing else
in `src` writes one by hand. Change detection's `Stored` is a `Pr`, its facts
and a problem, and lists only PR paths. `LEFT`/`RIGHT` are spelled only in
GitHub's package, in the board's contract with its one mapping to `Side`
(`board_api/_contract.py`), and in conversation's `side_words.py`, which
reads the old words on disk and writes the kernel's. The CLI's `--side`
takes `after|before`.

- `Side`: whether a line number is from before or after the change. GitHub
  translates it to and from `LEFT`/`RIGHT` at its own edge; no other module
  spells those words.
- `Location`: path, line, side and an optional start line, the place a comment
  hangs.
- `Repo`: owner/name, parsed once where a repo string enters the system
  (`watch_repo`, a CLI argument, a search result) with `Repo.parse`. It
  replaces the owner/name check that eight modules each carry a copy of today.
- `Pr`: a `Repo` and a number, and the one place that spells `owner/name#n`.
  It replaces the loose `(repo, pr)` pair in every interface.
- `Sha`: a commit hash of 7 to 40 hex digits; `Sha.parse` answers `None` for
  anything else. Working copies guards every rev it hands git with it and
  takes it on the PR checkout's commit reads; conversation refuses a
  reported sha that does not parse and answers `Fix.commits` as a pair of
  them. It replaced working copies' `is_sha` and conversation's copy of the
  same pattern. The records still store the strings; conversation's record
  schema refuses one that is no commit hash and reads the rest into `Sha` at
  load, and a thread workspace's `pick`, `descends`, `head_sha` and
  `workspace(key, base_sha)` take and answer `Sha` (`a33f3d08`).

## Processes

"One instance" means one per process. There are four kinds: the watcher,
started by launchd each cycle; one PR manager per PR, started with `--pr` in
that PR's tmux window, each running its own board on a per-PR port; each call
of the CLI; and the Claude runs. Each process's `__main__` builds the
container, asks it for its top module, and calls it.

Several modules keep state on disk that more than one process reads and writes.
The watcher adds to a PR's event queue and that PR's manager takes from it.
Thread records, change-detection snapshots, working copies' mismatch flags and
the per-PR switches are shared the same way. A singleton does not make that
safe; the locking and crash recovery stay inside each module, hidden behind its
interface.

## The modules

Each entry says what the module handles, the decision it hides, the files that
make it up, and its interface decisions.

### GitHub

Handles everything asked of GitHub or told to it: which PRs are mine and which
I have been asked to review; each PR's checks, reviews, review threads and
mergeability; posting replies and reviews, resolving threads, reacting. Hides
how GitHub is reached: the gh CLI, REST versus GraphQL, pagination, auth, the
wire vocabulary, and GitHub's own rules.

`src/github_orchestrator/github/`.

- **Done** (`cab0e466`): `GitHub.token()` is gone. Neither `git fetch` nor
  the manager windows get `GH_TOKEN`; git reaches the watched clone over SSH
  and never read it.
- **Done** (`43aa9600`): four roles that wiring provides directly, with no
  `GitHub` entry object, because none of them is per PR: **PullRequests**
  (mine, review requests, state, head branch, closed, relevance, and the
  github.com pages), **Threads** (fetch, reply, comment on the PR, resolve and
  unresolve, react, delete, exists, a comment's page, a body too long),
  **Reviews** (post a review comment, post a review) and **Access** (can this
  account reach this repo, answered as a refusal value). Each caller takes only the roles it uses; one
  fake implements all four, and the contract tests reach the real one
  through each role as wiring provides it.
- **Done** (`ba0f2278`): wire words became answers at GitHub's edge:
  `review.approves`, `review.requests_changes`, `check.passed`,
  `relevance.is_open`, `pr.conflicts` and the rest of the mergeability and
  review-decision questions, `thread.is_review_summary`. The `KIND_*`
  constants went; the words shown or sent on are GitHub's enums
  (`ReviewState`, `CommentKind`, `Verdict`), and conversation and change
  detection map them to their own words in one table each. Change detection
  stores its own words and reads the GitHub words already on disk in
  `_stored.py`; conversation does the same for its records and queued
  payloads in `_adapters/review_words.py` (`25c45d13`), with its own
  `ReviewState` and `Verdict`. The CLI's status prints change detection's
  words (`ci=passing`, `review=review-required`).
- **Done** (`7bad85d7`): no GitHub exception crosses the edge. `head_branch`
  answers `None` when GitHub will not say, where it raised until step 10a. `GhError`
  left the exports; `Access.check_access` answers a refusal, and the
  watcher's search catches any failure at its own boundary.
- **Done** (`b4d8fb20`): GitHub's rules moved home: `Verdict.takes(body)`
  (from `conversation/_domain/review.py`), `Threads.too_long` for the size
  of a body, and the github.com pages of a PR, a commit and each kind of
  comment (from the board and conversation). The board reaches them through
  conversation (`PrFacts.url`, `ConversationManager.comment_url`,
  `ConversationManager.too_long`).
- **Done** (`2e3a4eba`, `e8192613`): the fakes and the names no outside
  module writes left `__all__`: `FakeGitHub`, `FakePullRequest`, `FAKE_NOW`,
  `KIND_ISSUE`, `KIND_REVIEW`, `KIND_REVIEW_SUMMARY`, `Check`,
  `PostedComment`, `Relevance`, `ReviewComment`. `Repo` moved out to the
  kernel. Tests take `Check`, `PushEvent`, `Review` and `ThreadAnchor` from
  `github.fake` to seed it.
- Exports (`ac82bda2`, `7bad85d7`): the four roles, `PullRequestState`,
  `Thread`, `ThreadComment`, `ReviewState`, `CommentKind` and `Verdict`, ten
  for the exceptional module. `FoundPr` went with the search
  (`mine` and `review_requests` answer PRs, and the watcher takes a new
  review request's title and url from the poll), `DraftComment` became plain
  parameters, and `PushEvent`, `Review` and `ThreadAnchor` are only read.

### PR change detection

Handles remembering what each PR looked like at the last poll and working out
what changed: a newly failing check, a merge conflict, a review request, pushes
since my review, the PR closing. Hides the snapshot format and the rules for
what counts as a change. New-comment detection belongs to conversation.

`src/github_orchestrator/change_detection/`.

- **Done** (`a6347480`): change detection owns the typed events, one frozen
  value per kind under the union `PrEvent`: `CiSucceeded`, `CiFailed(check, summary)`, `BecameUnmergeable`, `BecameMergeable`, `ReviewDecisionChanged`,
  `PushedSinceReview`, `HeadChanged`, `ReviewRequested` and `PrClosed`, each
  carrying its word as `kind`. `advance` raises the review request the first
  time it sees a PR the poll says was requested, and `ended(still_open, merged)` says how a PR that left the search ended. `Change` is gone. Thread
  activity is conversation's own value and no longer passes through change
  detection.
- **Done** (`1341f573`): change detection reads its own words off a snapshot
  once, as typed values (`_stored.words_of`, and a private `Mergeability`),
  where it compared raw strings.
- **Done** (`eaecefff`, `0da03701`): `NewComment` went; conversation's poll
  says when I last commented and how many others did, and the `Poll` carries
  those two facts. The watcher names no event class: it asks an event
  `moves_head`, and on a dry run the queue's would-intake writes the whole
  would-enqueue line.
- Exports: 19, against a budget of about 5. Each of the nine event classes is
  written by the PR manager's `EventCarryOut`, which carries each event out
  and words its agent-changes note, three by the queue, which says which
  events start a run, and seven by notifications' `PrStatus.changed`, which
  words each; `PrEvent` by the queue's and the watcher's
  signatures. `ChangeDetection` is written by wiring and every caller, `Poll`
  by the watcher and the preview, `Facts` by the dashboard and conversation,
  and `Blocker`, `CiStatus`, `ReviewDecision`, `ReviewerStatus`,
  `SinceReview` and `Want` by the dashboard alone, which keys its labels and
  colours by them. Candidates to go: those six, if change detection kept the
  dashboard's labels.
- **Done** (`d42219da`): `PushedSinceReview.pushes` is the one
  pushed-since-review sentence; notifications shows it and the PR manager's
  agent-changes note adds a full stop.
- **Done** (`d627d666`, `63e217b9`, `a6347480`): which unmergeable states
  fire again is change detection's rule. `REBASE_REASONS` moved here from the
  event queue, and the edge from change detection to the queue went.
  `BecameUnmergeable.rebase` says whether a rebase fixes it, and the queue
  reads only that.
- **Done** (`df015c5e`): `Facts.is_author` is what the poll saved (the PR's author against the account),
  or `None` when the snapshot does not say; nothing reads a missing role as
  the author's.
- **Done** (`ba0f2278`): `Facts` stays a read model the dashboard displays.
  Decisions ask questions (`facts.ci_passed`, `facts.is_author`); the words
  the dashboard and the CLI show are enums owned here (`CiStatus`,
  `ReviewDecision`, `ReviewerStatus`). Snapshots store these words, not
  GitHub's. `Stored` carries no file name (`a7d01486`).
- **Done** (the commit that records this): `advance` always saves; its
  `save` flag went. A dry run gets `_would.WouldSaveChangeDetection` from
  wiring instead, which reads and advances as the disk one does and says
  `would save state for <pr>` where that one writes a snapshot, on `advance`
  and on `close`. `forget` and `archive_other_repos` are not overridden: no
  dry run reaches them.

### PR event queue

Renamed from the Inbox (`pr_event_queue`). Handles each PR's events from the
watcher to the response. It keeps them safe across crashes, and when the PR's
manager asks for the next thing to do it answers one value: the event, the
Claude run it starts for this PR's role (if any), whether Claude being off
skips that run, and whether more failing checks wait behind it. On a dry run
wiring hands the watcher its would-intake instead, which says each event it
would hold and whether that event starts a run for the PR's role, and nothing
of what other modules do with it. Hides how pending events are stored and
recovered, and which events start a run for which role.

`src/github_orchestrator/pr_event_queue/`.

- **Done** (`907ba2c7`): the package is renamed `pr_event_queue`, its
  interface `PrEventQueue`. The files on disk stay under `queues/`.
- **Done** (`a6347480`): `add(pr, event)` takes change detection's typed
  event, and `add_thread_activity(pr, activity)` conversation's typed
  `ThreadActivity`. The queue stores each as it is, walking the dataclass, in
  `_stored.py`, which also reads the files queued before the typed values
  (GitHub's review-decision words, check dicts, pr-closed's reason, old
  thread payloads with `LEFT`/`RIGHT`). `dry_run_effect` takes a typed event.
- **Done** (`9215f67c`): `queues()` and `failed_since(when: datetime)` return
  typed entries: the PR, the event (or the problem when its file will not
  read), when it was queued, and `pending`, `in_flight` or `failed`. File
  names and nanosecond stamps stay inside; the CLI formats the entries.
- **Done** (`8a20eea7`, `1db19511`): responses carry facts and the table
  words nothing but its dry-run lines. A `Notice` carries the event, a
  `TearDown` the `PrClosed`, a launch what it needs (`FixCheck`, `Rebase`,
  `Review`), and `Skipped` says Claude is disabled and what it would have
  launched. `Alert` and every `changes` text are gone. Until PR windows owns
  `agent-changes.md`, its lines live once in the PR manager's
  `_carry_out.py`, beside what each event does (`_announcements.py` went). The
  notification wording moved into notifications (`d42219da`).
- **Done** (`a1af4fda`): three roles that wiring provides from one queue:
  **Intake** (add, add thread activity), **Worklist** (next,
  waiting, recover, drop in flight, torn down, forget) and **Queues** (queues,
  failed since, archive other repos). The watcher takes all three, the PR
  manager the worklist, the CLI the queues. **Done** (`91f8c35d`): the
  worklist answers notifications' `Settling` question, `settling(pr)`, and
  wiring provides the queue as it; `Waiting.thread_activity` went.
- **Done** (the commit that records this): thread activity always goes to the
  conversation. Whether an authored PR's threads drain while Claude is off is
  conversation's rule alone: `absorb` answers `drained` and makes no records,
  and the PR manager words the skip. The dry run says how many threads and
  stale records the activity holds, and no longer what the conversation does
  with them.
- **Done** (the commit that records this): the queue's answer is one
  `Response`: `event`, `launch` (the `CiFailed`, `BecameUnmergeable` or
  `ReviewRequested` itself when it starts a run for this role, else nothing),
  `skipped` (Claude is off, so that run will not start), `more_failures_wait`
  and `closes`. `FixCheck`, `Rebase`, `Review`, `Notice`, `Threads`,
  `Skipped`, `TearDown`, `Nothing`, `Launch` and `Taken.event_type` went; what
  each event leads to is the PR manager's `EventCarryOut`.
- **Done** (the commit that records this): `Intake.dry_run` went. Wiring's
  dry-run parts provide `Intake` as `_would.WouldIntake`, which says
  `would enqueue <kind> (<detail>) for <pr>` and, only where the queue's own
  rule says the event starts a run for the PR's role, whether it would launch
  one or skip it while Claude is off. The detail is the event's own: the
  reason, the moved range, the count of threads and stale records. It no
  longer says what the PR manager or the conversation would do (compare,
  refresh, start a verdict run, tear down, notify, note in the changes pane).
  It counts what it would have held per PR, for the watcher's would-placement.
  It is not exported: wiring builds it, as it builds the disk queue.
- Exports: 5, within the budget: the three roles, `Response` and
  `Launching`, the union of the three events that can start a run, which
  the PR manager's carry-out types its launches by.

### Git working copies

Handles giving each PR a worktree on the right branch, noticing a worktree on
the wrong branch or shared with another PR and deciding what to do about it,
cutting a worktree per thread for each fix, reading commits, files and diffs,
and landing an approved fix as one commit. Hides the git commands, where
worktrees live, how branch trouble is detected, and how long it may last.

`src/github_orchestrator/working_copies/`.

- **Done** (`dfeddd37`): the verdict on a PR's worktree is nothing wrong
  (`None`), **hold** (seconds left, and `run_working` for a run still
  talking) or **hand off**. The manager reports what it sees with
  `report_branch` (its run's output time is the one fact only it has) and
  draws the verdict's own countdown; the watcher asks one `verdict` call,
  whose `window_open` says whether it judges a wrong branch in a window that
  exists or a shared worktree for one about to open (`0cadd4dd`), detaches on
  hand off and tells `handed_off` the name the window was kept as. The
  verdict carries its own `trouble` line for the log. The grace settings reach working copies through wiring; the grace
  rule, the run-idle rule, the shared-worktree comparison, the 20-minute
  retry and the notify timing live in `_trouble.py`, which the fake shares,
  and working copies posts wrong branch, shared and still shared itself.
  `Mismatch` and `WorktreeConflict` are private, and the flag files keep
  their format (`_flags.py`).
- **Done** (`fe35b902`): a thread's worktree path and branch are derived from
  the `Pr` and the thread key; `workspace(key, base_sha)` takes nothing else.
  A recorded `base_sha` is the adopted marker: the derived folder is reused
  only when it is recorded and the folder exists, otherwise it is cut
  afresh. On 2026-09-25 all 111 stored paths on the live machine (of 126
  records) matched the derivation. Records stop storing `worktree` and
  `branch`; thread records' migration drops them and reads a record that
  stored an empty worktree as not adopted.
- **Done** (`52117a74`): the board reads commits, files, diffs, diff stats and
  commit messages from a PR checkout of working copies, and conversation
  says which commits a fix consists of (`Fix.commits`). `ThreadGitError` and
  `is_sha` left the exports; conversation refuses a reported sha that is
  no commit hash.
- **Done** (`0cadd4dd`): one refusal type holds here too. A thread handle's
  `ensure()` answers a `Cut` (the adopted handle, or the failure git gave),
  `drop()` answers the failure or nothing, and `push`, `is_clean` and `pick`
  turn a git that will not run into their answer; `ThreadGitError` stays
  private. Conversation turns a failed cut or drop into its own
  `WorkspaceRefused`, which `open_thread` answers as `Denied(GIT_FAILED, …)`.
  `pick` answers one `Picked` value (landed, conflicting, not commits, a
  missing branch, changed since review, or refused) that conversation reads
  and words.
- **Done** (`37f83076`, and the step 10a follow-up): `checkout(pr)` takes no path. Working
  copies finds the PR's worktree itself, the one of the watched clone holding
  the PR's head branch, which it asks GitHub for as it does when it places a
  worktree (one source; change detection's stored branch is not read here).
  When GitHub names no branch or no worktree holds it, the checkout says so:
  `no_worktree()` answers why, and every read on it answers its failure value
  (no commit, no diff, not clean, the reason from `push`, `pick`, `drop` and a
  cut). Conversation refuses an enrol or post-now with that reason, and the
  board's diff and file reads carry it. `PrCheckout` has 10 methods.
- Exports (`0cadd4dd`): 4. `WorkingCopies` is written by wiring, the watcher,
  the PR manager, conversation and the board's server; `PrCheckout` by
  conversation's ports and the board's app and projection; `ThreadWorkspace`
  by conversation's `thread_workspace`; `FileDiff` by conversation's
  drafts and asking and the board's projection. `Picked`, `Cut`, `Verdict`,
  `WrongBranch`, `FileStat`, `DiffHunk` and `DiffLine` are only read; tests
  take the diff values from `working_copies.fake`. `WorkingCopies` has 9
  methods, `PrCheckout` 9 and `ThreadWorkspace` 9. **Done** (the commit that
  records this): `remove_worktree` left the interface and the fake once no
  outside module called it; the fake's tests remove a worktree from outside
  with `lose_worktree` and make a removal fail with `fail_removals`.
- **Done** (browser mode, step 5): `wrong_branch(pr, now=…)` answers the
  wrong branch a PR's manager is frozen on, judged as `report_branch` would,
  or `None`, and starts no grace of its own, so the hub can say a PR is
  frozen and offer its release. `WorkingCopies` has 10 methods.

### PR windows

Handles each PR's tmux window and the PR manager process's whole life:
starting, stopping and finding managers, the dashboard, a free shell, the live
agent-changes pane, renaming, reviving and closing windows as PRs come and go.
Hides tmux (the session, window and pane layout, window ids, tmux's errors),
the manager's command line, and the `agent-changes.md` file.

`src/github_orchestrator/pr_windows/`.

- **Done** (`6fcd7312`, `eafcf7ef`): the window id stays inside, and PR
  windows imports no other module but the desktop it asks for the appearance.
  **Done** (`cab0e466`): no `GH_TOKEN` in window environments.
- **Done** (`39831dc7`): it stops managers as well as starting them.
  `stop_managers()` walks the PRs whose window ids it keeps and signals the
  children of each running manager pane's shell, answering the PRs it
  stopped. The CLI's `restart`, `confirm-restart` and `switch-repo` call it
  and `manager(pr)`; `pkill -f`, the `ps` parsing and `MANAGER_MODULE` went.
- **Done** (`40c6fe77`): `split` answers `None` or a failure reason (no
  window, tmux's first stderr line, the exit code, or why tmux would not
  start) and never lets tmux's `CalledProcessError` out; agent runs'
  `rebase_in_session` answers the same. `window_target` went, and the dry-run
  lines speak of the PR's window and a note in the changes pane.
  `close_other_repos` answers the PRs whose windows it closed (`c73c7512`),
  which `switch-repo` prints as `owner/name#n`.
- **Done** (`2d3d96be`, `b5a3c868`): it owns the `agent-changes.md` file, its
  name and its header rule, in a second role, **AgentChanges**: `file_name()`
  (for the prompts, through wiring, and the manager's help text),
  `note(worktree, text, at)` (the manager's notes under a `## [minute]`
  header) and `read(worktree)` (what the markdown preview renders, piped to
  pandoc). `_changes.py` writes the rule once for the disk and the fake.
  `PrWindows.changes_file()` went. The note wording stays in the PR manager's
  `_carry_out.py`.
- **Done** (`b0bbff3a`): it asks Mac desktop for the appearance instead of
  running `defaults read`. `TMUX_SESSION` moves here from settings (done in
  `d627d666`). **Done** (`a2ea102f`): it merges settings' child environment
  into each manager window without knowing the variable names.
- **Done** (browser mode, step 2): a second `PrWindows`,
  `BackgroundPrWindows`, runs each manager as a detached process
  recorded under `data_dir/pr_managers/`, and wiring builds it when
  `pr_windows = "browser"`. The interface-level contract tests run over the
  fake, tmux and it; the pane, glow and split tests stay on tmux.
- **Done** (web interface, step 1): the manager's command line is the same in
  both modes; `--headless` went. A recorded pid counts as the PR's manager when
  its command line holds the manager's arguments, so managers started with the
  old flag are still found and stopped.
- **Done** (web interface, step 8, `f5ce0302`): a third role,
  **TerminalSessions**: `start(worktree, argv)`, `listed()` and
  `attach(session)`, whose connection reads, writes, resizes and closes. Each
  session is a pty in its worktree running its command as an xterm with the
  program's environment, keeping its last megabyte of output for every
  connection; it ends when its command does, or 30 seconds after it started
  when no connection came — closing the last connection leaves it running. Browser mode's `split` starts one instead of
  refusing, so `g r`, the palette's split commands and the board's steered
  session land in the Terminal tab with no caller knowing the mode. Wiring
  builds one per process in both modes, for the board to serve.
- **Done**: `TerminalSessions` moved out to its own module, Terminal sessions.
  `BackgroundPrWindows` is handed its `Terminals`, starts each split in that
  PR's sessions, and hangs them up when it closes or detaches the PR.
- Exports: `PrWindows`, `AgentChanges` and `ManagerPane`. `PrWindows` has 10
  methods, `AgentChanges` 3.

### Terminal sessions

Runs a command on a pty in a worktree for the page to watch and type into.
Hides how the pty is held, how much output a late connection is shown, and when
a session nobody connected to ends. Knows nothing of the modules that start or
serve its sessions.

- **TerminalSessions**: `start(worktree, argv)`, `listed()` and
  `attach(session)`, whose connection reads, writes, resizes and closes. Wiring
  builds one per process from the program's child environment; PR windows
  start splits on it and the board serves it.
- **Done**: each session is held by its own detached process, forked loose of
  whoever started it and in a session of its own, which owns the pty and the
  output kept for late connections and serves them on a unix socket. Its
  record and socket sit in a directory wiring names per PR under `/tmp`, short
  enough for a socket path, so a restarted PR manager lists and attaches the
  sessions its predecessor started.
- **Done**: **Terminals**, `of(pr)`, hands out each PR's `TerminalSessions`,
  which gained `hang_up()`: it ends every session the PR holds, since a holder
  would otherwise outlive the PR it was started for. Wiring hands a PR manager
  its own PR's sessions for the board.
- Exports: `TerminalSessions`, with 4 methods, and `Terminals`, with 1.

### Agent runs

Handles every Claude Code run: turning what another module wants done into a
prompt, starting the run in a working copy, streaming what it writes,
recording its time and cost, showing its transcript, and the short summary
runs. Hides how Claude is invoked: every prompt, the command line, model,
environment, output parsing, the run ledger, and where transcripts go. A run is
a handle. No other module writes or sees prompt text.

`src/github_orchestrator/agent_runs/`.

- **Done** (`e8ee4005`, `898c1dc4`, `d7fdbd89`, `9035226c`): an exceptional
  module, split into roles that wiring provides from one `ClaudeAgentRuns`:
  - **Summaries** (`e8ee4005`): `summarize_comment` (a thread's opening
    comment), `summarize_thread`, `summarize_comments` and `summarize_fixes`,
    each taking the length the caller will show. They hand back typed
    results: a line, or one gist per comment (`||` is split inside), so no
    caller parses an answer.
  - **PR work** (`898c1dc4`): `review`, `fix_check` (push now or hold),
    `rebase`, `carry_on` (the `r` key's `--continue`) and
    `rebase_in_session`.
  - **Thread work** (`d7fdbd89`): `fix`, `rebase_fix`, `rework` and
    `open_session`.
  - One refusal type (`7d791746`, `5ab42631`, `d30ff6af`): no exception
    crosses agent runs. Every run starter answers the run or why claude
    would not start, `open_session` answers `None` or PR windows' reason, and
    a transcript that cannot be written no longer stops `pump`. Review
    threads turns a refused session into its own `SessionRefused` (the fix
    goes back to its state, the operation settles refused) and a refused
    launch into a failed attempt; the PR manager fails the event and shows
    the reason.
  - **History** (`9035226c`): `last_run`, `transcript_tail`,
    `finished_since(when)`, `live(pr)` (a PR run started in this process
    that has not ended; thread runs do not count) and `archive_other_repos`.
    The `AgentRuns` interface went.
- **Done** (`d7fdbd89`): agent runs owns the request types for large inputs:
  `ThreadFix`, with its `FixComment`s and `PointedAt` lines, which review
  threads fills in (who wrote each comment, how the thread had ended up, the
  conflict, the operator's brief, why a fix was skipped, the confidence
  words). Small inputs are plain parameters. Agent runs imports no caller.
- **Done** (`e8ee4005`, `898c1dc4`, `d7fdbd89`): every prompt moved here word
  for word, pinned by `tests/agent_runs/pinned/` (checked through the old
  entry points first, `32c7c2cf`, then through the roles): conversation's
  `_adapters/prompts.py` and `_adapters/gists.py`, the PR manager's
  `_carry_out.py`, notifications' `_batches.py` and the git palette's
  `claude "/rebase-on-main"`. The test-parallelism cap is agent runs' own
  rule (`_rules.py`), fed `pytest_workers` by wiring. The CLI owns the syntax
  of the report-back commands (`cli/_report_commands.py`, with its flag
  choices); wiring provides it as agent runs' `ReportCommands`, the one copy
  of the agent-facing `uv run … github_orchestrator.cli` line. The prompts
  name the changes file PR windows gives (`2d3d96be`).
- **Done** (`9035226c`): the CLI's `runs` asks History for finished runs and
  formats them; `runs.jsonl`, its field names and the tail scan stay in
  `_ledger.py`, which reads the ledger on disk unchanged.
- Exports: `Summaries`, `PrWork`, `ThreadWork`, `History`, `ReportCommands`,
  `Run`, `LastRun`, `ThreadFix`, `FixComment` and `PointedAt`, ten for the
  exceptional module. `FinishedRun` is only read. It carries the run's exit
  code and `failed`, agent runs' own rule (`37974fd2`). `History` also
  answers `finished_today(now)`, a `RunDay` of the runs since local midnight
  with their summed cost and how many reported none, the one definition of
  "today" the CLI's `runs` and the hub's health line both read; `RunDay` is
  only read too.

### Notifications

Handles every desktop notification: the durable outbox, deciding whether an
item goes out at once or waits for a batch, the batching window, the wait
while a PR's thread activity settles, dropping items that are no longer news,
the summaries of a batch, the wording, and the badge. Hides the outbox layout
and every rule about when and how you are told.

`src/github_orchestrator/notifications/`.

- **Done** (`d42219da`): callers state what happened through methods split
  by domain role, which wiring provides from one `News` over the outbox:
  **ThreadNews** (fix ready, comment arrived, needs your call, fix failed),
  **Runs** (run failed, Claude skipped), **Worktrees** (blocked, fetch
  failed, init timed out, init failed, wrong branch, shared, still shared),
  **PrStatus** (CI passed, CI failed, unmergeable, mergeable, review decision
  changed, pushed since review, closed) and **Polling** (the watcher not
  polling). The fact classes are private in `_facts.py`, and `post` and
  `gather` went: no caller chooses between sending now and batching, or
  names a badge. Every title, body and badge is written in `_news.py` and
  `_batches.py`, word for word what the callers wrote (`7b794c2f` pinned
  them). PrStatus takes change detection's typed events; `ci_failed` tells
  you nothing, as before. **Done** (the commit that records this): PrStatus
  is one `changed(pr, change)`, and notifications matches the change itself;
  its seven one-caller methods went. Conversation' poll announces each arrived comment
  to ThreadNews with whether it opens or reopens a thread, and `Polled`
  carries no notifications item. The outbox stores the same documents as
  before, so what is queued on disk still reads.
- **Done** (`91f8c35d`, `d42219da`): a caller may pass a gist it already has
  (`fix_ready` and `fix_failed` take the thread's gist). When there is none,
  the courier asks agent runs' Summaries itself for a batch's summary or its
  comments' gists; the prompt text moved to agent runs (`e8ee4005`).
- **Done** (`91f8c35d`): notifications defines the questions it asks before
  delivering a batch. **Standing** (`fix_still_news`, `comment_still_news`,
  `fix_progress`) is answered by conversation, and `fix_progress` answers
  `FixProgress` (none, queued, started), which notifications words and
  counts. **Settling** (`settling(pr)`) is answered by the PR event queue's
  worklist. Wiring provides `GitHubConversationManagerFactory` as Standing and the queue as
  Settling; `_Standing` left `wiring.py`, and conversation's `fix_progress`,
  `handled_since_ready` and `replied_since` left its exports.
- **Done**: the watcher's loop calls delivery every 2 seconds
  (`DELIVERY_INTERVAL`); the courier decides what is due.
- Exports (`d42219da`): `ThreadNews`, `Runs`, `Worktrees`, `PrStatus`,
  `Polling`, `Courier`, `Standing`, `Settling` and `FixProgress`, nine against
  a budget of about 5. The five fact roles and the courier are what callers
  take; `Standing`, `Settling` and `FixProgress` are what wiring and review
  threads write to answer notifications' questions. `Badge`, `ClaudeSkipped`,
  `CommentArrived`, `FixReady`, `Gathered` and `Notifications` left.
  Notifications imports change detection, for PrStatus's events, and agent
  runs, for the summaries.
- **Done** (`c0d7168d` and the commit that records this): notifications
  asks **BoardPages** (`board_of(pr)`) where a PR opens, and the courier
  hands the answer to the desktop as the banner's link. Board API's
  `HubPages` answers with the hub's `/pr/<number>` in browser mode;
  notifications' own `NoBoardPages` answers nothing in tmux mode; wiring's
  `mode_providers` picks. A posted item names its PR on disk as a batched
  one does; a document without one opens nothing. Exports: ten, with
  `BoardPages`, because wiring writes it to provide the answer.

### PR manager

Handles the process in each PR's window: taking that PR's next thing to do from
the event queue, carrying it out, drawing the dashboard, and answering keys
(pause, dismiss, close, board, git palette, markdown preview). Hides the
terminal UI and when the next event may start. It owns every write to the PR
itself, as opposed to one of its threads: close, send a review, merge, reopen
and mark ready. It reaches GitHub for them through the GitHub module's
`PullRequests`.

`src/github_orchestrator/pr_manager/`.

- **Done** (2026-09-28): its panel answers `close()`: the manager closes the PR
  through `PullRequests.close`, or shows GitHub's refusal as its notice, and
  the watcher's next poll sees it closed and tears it down. The dashboard's
  Close button and `c y` send it.

- **To do.** Send review moves here from conversation's `Drafts`, and merge,
  reopen and mark ready come in beside close.

- **Done** (`898c1dc4`): it writes no prompts; it asks agent runs' PR work
  to review, fix a check, rebase or carry on. **Done** (`d42219da`):
  it writes no notification text; it tells notifications' ThreadNews, Runs
  and PrStatus what happened, and `Announcements` went.

- **Done** (the commit that records this): `_carry_out.py`'s `EventCarryOut`
  is the one part that says what a queued event leads to. Wiring builds it
  with its collaborators (PrStatus, Runs, PR work, change detection, agent
  changes), and the loop hands it the queue's `Response`, whose PR it is,
  the live run and the PR's conversation manager, in place of the twelve
  arguments `carry_out` took. It starts or skips the run the response names,
  tears down on a close, hands thread activity to `absorb`, logs a moved
  head, and tells PrStatus of a status change, and it words every
  agent-changes note. The loop exits once a response `closes`, and tells it
  when its run ended: it reports a failed run to Runs and, when that run was
  fixing a failed check, queues the check again with the next `attempt`
  (up to `CI_FIX_RETRIES`, three) and notes each failure or the giving up.

- **Done** (`dfeddd37`): on a wrong branch it freezes and shows working
  copies' verdict, and does no grace arithmetic of its own.

- **Done** (`0583c3b0`): dismiss records the dismissal, stops its run, drops
  the event that run was for, and exits before it takes anything else. The
  watcher does the rest: it closes the window of a PR dismissed until its next
  event once the manager has exited, and tears down a PR dismissed forever.

- **Done** (browser mode, step 3): it answers board API's `ManagerPanel`. The
  loop publishes a frozen `ManagerStatus` each unfrozen tick and drains the
  board's commands where a key lands, through the same code `p`, `r` and
  `x u` / `x f` run; the HTTP thread reads only that snapshot, the agent's
  notes and the transcript tail.

- **Done** (web interface, step 1): the loop is the same in both modes and
  hands drawing and keys to a **Front**, one interface it owns: the terminal
  front draws the dashboard and reads keys; the browser front draws nothing,
  reads nothing and keeps the board up. Wiring reads `pr_windows` once and
  builds a matching pair, tmux windows with the terminal front or background
  managers with the browser front. `--headless`, `ManagedPr.headless` and
  `keep_board_up` went.

- **Done** (web interface, step 6): its panel answers `run_git(keys)` through
  the palette's own `run_captured`, in the worktree, for the captured
  commands and for log and diff, which the page shows read-only; the keys of
  a command that needs a terminal are refused. It runs on the board's HTTP
  thread, as the terminal's palette runs on the loop's, bounded by the same
  timeout.

- **Done** (web interface, step 8, `8dc09865`): its panel answers
  `open_terminal(keys)` for those commands, `new` (a login shell), `a`, `c`,
  `i<N>` and `r`, through the same `open_in_terminal` the terminal front's
  palette uses: `split` for git, `rebase_in_session` for `r`. A frozen
  worktree refuses it as it refuses git.

- **Done** (web interface, step 2): every field the dashboard shows is
  computed once, in `_snapshot.py`, as board API's `Dashboard`: the PR,
  its status, the action and its detail, what happened since you last
  acted, the system block, the freeze screen's branches and the dismiss
  wording. The loop builds one each tick, frozen or not, publishes it to
  the board and hands it to the front; the terminal front draws the
  dashboard and the freeze screen from it alone. Preview and board on/off
  stay the terminal front's own state beside it. The design's "your move"
  is worded there too, from the snapshot's own values: frozen, then
  paused, then the board's threads that need you (proposed fixes on your
  PR; drafts, then answered threads on one you review), then the agent's
  run or thread fixes, then what change detection says the PR wants.

- **Done** (web interface, step 4): each branch of the verb also names the
  wall group it puts the PR in (needs you, agent working, waiting on
  others, paused), and a PR dismissed until its next event is hidden
  unless it is frozen, so the verb and its group cannot disagree. `UnmanagedDashboards` answers the
  board API's `Dashboards` port for the hub: the same `dashboard_of` over
  what is on disk, with no run, no notice and the watcher's frozen verdict,
  for a PR whose board does not answer. Wiring builds it; nothing imports
  it, so the watcher still knows nothing of the PR manager.

- **Done** (architecture review of 2026-10-01, candidate 3): "your move" is
  no longer worded here. `_your_move` names the branch that holds
  (`release-worktree`, `on-hold`, `decide-fixes`, `send-review`,
  `re-review-answered`, `agent-running`, `agent-on-threads`, `first-poll` or
  `wants`) with its group, and the `Dashboard` carries the facts the browser
  words it and the action's detail from: the author, the failed checks and
  check counts, who approved, asked for changes or is pending, unresolved
  threads, the blocker, the since-review counts and the undismiss command.
  `_snapshot.py` words nothing: the `Dashboard` holds only facts and codes,
  and the terminal front words the action's label and detail, whose PR it is,
  the since lines and the dismiss choices from them in `_dashboard.py`, as the
  browser does in `data/dashboard.ts`. Each audience has one wording.

- **Done** (deepening, item 2): one `ManagerCommands` answers the panel and
  every action the fronts take, with the freeze refusal written once; the
  fronts take it from wiring, and the board's thread queues each call as a
  closure the loop runs.

- Exports: `PrManager`, `ManagedPr`, `Front` and `Terminal`.

### Master controller

The watcher. Handles the cycle: finding my PRs, polling each, handing events to
the event queue, opening and closing PR windows, tearing down PRs, pacing
notification delivery, and recording its own health. Hides the order of a
cycle and how one PR failing is kept from stopping the rest.

`src/github_orchestrator/watcher/`.

- **Done** (`0583c3b0`): one teardown, `Teardown.reap(pr, reason)`, with a
  reason: closed or dismissed (`is_dismissed_forever`). Both forget the PR's
  worktree, thread workspaces and branches, thread records, queue, pause,
  board and, through working copies' `forget_pr`, its branch trouble. Closed
  also forgets the dismissal and closes the window, and forgets change
  detection's snapshot last; dismissed keeps the dismissal and the snapshot
  and closes the window last. That last step is the one left standing when an
  earlier one fails, so the next poll retries. A PR dismissed forever is torn
  down once, on the first poll after its manager exits, while it is in the
  search and has a window.
- **Done** (`dfeddd37`): it acts on working copies' verdict and applies no
  grace rule.
- **Done** (`f7b4fea9`): health is data. `WatcherHealth.health()` answers a
  `Health`: `alive` (the resident watcher holds its lock, or `None` under
  cron), `since_last_poll`, `last_error` while cycles fail, `polls_every` and
  `overdue`. The CLI writes the line; `describe()` and `failure_summary` went.
  The "N consecutive failed cycles" phrase is written once, in
  notifications' not-polling banner; the status line no longer counts.
  `next_poll_in`, a poll interval after the last good poll, is the pacing
  rule the hub's health line reads (web interface, step 10).
- Exports: `Watcher`, `WatcherHealth` and `Health`.
- **Done** (`4a459999`): `__main__` builds the container, configures its
  log, checks the config from the one read, takes the single-watcher lock
  through `Watcher.take_lock()` and runs. It creates no folders and trims no
  logs.
- **Done** (browser mode, step 5): the resident watcher (`run_forever`, not a
  dry run) starts board API's hub on `hub_port` before a cycle until it
  binds, logging a port that will not, and shows it the PRs it holds (those
  it polls, dismissed-forever ones left out) after each cycle.
  `_holdings.py` answers the hub's `Holdings` from change detection, PR
  windows, the pauses, the boards, the worklist and working copies' new
  `wrong_branch`, and sets the pause switch and asks for a release itself.
  One-shot runs serve no hub.
- **Done** (the commit that records this): a dry run is a set of adapters,
  not a flag. `PollingWatcher` has one path and no `dry_run` parameter;
  `make_container(dry_run=True)` appends wiring's dry-run parts, which
  provide a would-adapter for each writer the cycle touches: the queue's
  would-intake, change detection's would-save (it advances without writing
  and says `would save state for <pr>`, closing included), and the watcher's
  own `_would.py`: `WouldPlace` (the window it would open or the dismissal it
  would honour, counting what the would-intake took this cycle),
  `WouldTearDown` (reap and dismissed teardown), `WouldSave` (no heartbeat,
  failure count, thread cursor or thread news), `WouldServeHub` and
  `WouldDeliver`. The theme sync moved behind `Placement`. Each line goes
  through one `say`, which on a dry run prints it behind `[dry-run] ` and on
  a real run logs it at debug; the summary line lost its `[dry-run]` tag.
  Each PR's fetch still runs on the pool, and its advance, enqueue and
  thread settling run on the cycle's thread, so a PR's lines stay together.

### Conversation

Handles the life of each review thread on my PR and carrying it out: the
thread's states, which verbs are allowed when, running the agent for a fix,
landing an approved fix, posting replies, pulling GitHub threads, and checking
that comments still exist. Hides the rules of a thread's life, what a thread
record contains, and the order of side effects around each step (lock, run,
save, post), including what happens when one fails. It reaches GitHub only
through the GitHub module.

`src/github_orchestrator/conversation/`.

- **Done** (conversation aggregate, step 2): the five roles went. A PR's
  `ConversationManager` answers `editing(key)`, `get(key)`, `all()`, creation,
  the PR-level reads and the upkeep; `editing(key)` hands out an
  `EditableConversation` that takes every command as a method, so no caller
  names a thread by key past the manager. `recheck` takes a conversation.
  The internals are unchanged; `2026-09-28-conversation-aggregate-design.md`
  has the rest.

- **Done** (conversation aggregate, step 3): `editing` holds the record's lock
  for its block and saves on the way out. Every rule for whether a change may
  happen is in `_domain/machine.py`'s one ordered table, and each transition in
  `apply.py` only makes its change. Changes are sorted into commands
  (`commands.py`), events (`events.py`) and the manager's steps (`steps.py`:
  `Land`, `First`); `Change` names the three.

- **To do.** A stale event is still `Refused`, where the aggregate design says
  it is ignored. Two rules no test reaches: `Approve`'s landing-under-way
  refusal, which the outstanding operation refuses first, and `Posted`'s
  enrolled-only rule, which the review sender never breaks.

- **Done** (`a9f36830`): conversation stamps the time on reports, fails,
  declines and unparks from its own clock; `ConversationManager.now()` is gone.

- **To do.** An exceptional module, at 10 exports: `ConversationManagerFactory`, the five
  roles, `Conversation`, `Denied`, `ErrorCode` and `ThreadActivity`. `Review`
  goes if the board's projection can be written without naming it. At 23 after
  `1fdb6235` (from 41): the five roles went in, the command classes, `Command`
  and `ConversationManager` came out. At 16 after step 10b: `Refused` and `is_thread_key`
  went (`625070a2`), `UnreadableRecord` and `state_of` (`d30b9090`);
  `OperationKind`, `OperationState` and `ReasonCode` came in (`db86fe69`); and
  in the commit that records this, with the board's projection reading a
  conversation's parts off it without naming them and `rework` taking pointed
  lines as `(file, line, text)`, `Review`, `Operation`, `Fix`, `Comment`,
  `Brief` and `PointedLine` went (`6da22991`). `Review` could go. At 18 once
  `Classification` and `ConfidenceLevel` came in. The eight over the ten are
  the display enums the board writes: `ConversationState`, `OperationKind`,
  `OperationState`, `ReasonCode`, `Classification` and `ConfidenceLevel` type
  its contract's models, and `ReviewState` and `Verdict` are its one mapping
  to GitHub's words. Whether they count against the ten is not settled.

- **Done** (architecture review of 2026-10-01, candidate 7; the commit that
  records this): the projection no longer reads a conversation's parts and
  works out which operation is current from them, which reverses the choice
  of `6da22991`. `Conversation.views` answers one view per operation, in the
  record's order: what it carried, whether it is current (the run the fix is
  on, or the latest approve), and only for that one how far it got (the
  plan, the run's brief, onto and conflict, the classification, the landing's
  steps and commits, the reply it posted). `Conversation.proposal` answers
  what the settled fix left, with its id
  (`<producer>.proposal`, else `<key>.proposal`); `posted_by_board` the
  replies the board posted. The rule is tested in
  `tests/conversation/domain/test_views.py`. The projection names no new
  export: it reads the views' fields without naming their types, so the
  export count is unchanged. `Conversation` holds 10 public members, at the
  cap: the producer and the id format are private functions beside the views.

- **Done** (`df015c5e`, `37f83076`): `ConversationManagerFactory.of(pr)` takes nothing
  else. The worktree comes from working copies (`checkout(pr)` finds the
  worktree of the watched clone holding the PR's head branch), the role from
  change detection, whether a run is live from agent runs' History, and
  whether Claude is enabled from conversation's own config. The drain runs
  only in the PR manager's process, where agent runs started the run, so
  History can answer from memory. The role has one source in every process:
  the PR manager lost `--author` and asks change detection each tick, PR
  windows is told it only to style the window, the watcher places and revives
  windows by it, and the dashboard reads it off the facts it draws. A
  snapshot that does not say (none yet, or no `is_author` in it) leaves the
  role unknown, never the author's: until a poll saves it the manager takes
  nothing from the queue and starts no board, conversation refuses a draft
  or a thread opened by hand, and the watcher opens no window.

- **Done** (`1fdb6235`): `ConversationManager` splits into roles, whose methods may
  compose the `_application` functions; `of(pr)` answers a handle carrying the
  five, and each caller keeps the ones it uses:

  - **Upkeep**: poll, absorb thread activity, tick, counts, recheck a comment
    against GitHub (today's `check_later`).
  - **FixReports**: the agent's plan, step done, ready, declined, fail, and
    opening a thread by hand.
  - **Decisions**: approve, rework, start a session, retry, stop, resolve,
    reject, defer, unpark, reply, mark seen.
  - **Drafts**: open, edit, enrol, withdraw, discard, post now, send review.
  - **Reading**: conversations, one conversation, reviews, facts.

- **Done** (`1fdb6235`): callers call methods; the 22 command classes became
  private. `decide` went from the interface; `Upkeep.tick` drains, and now also
  when only a review is waiting.

- **Done** (the commit that records this): `tick(news, on_hold=…)` announces
  each fix whose run settled to the ThreadNews it is handed (fix ready, needs
  your call, fix failed), as `Polled.announce(news)` does for arrived
  comments, and answers nothing. The PR manager hands it its ThreadNews and no
  longer reads a settled fix's state, gist, author or reason.

- **Done** (`2b8687cd`): the 41 exported string constants went. Callers ask
  `Conversation`, `Fix`, `Operation` and `Review` whether the fix is settled,
  proposed, declined or failed, which operation holds the run and which
  produced the proposal, and whether an operation is a run or in flight. The
  board turns an operation's kind into its contract's `OperationKind` at its
  edge. Callers pass `is_author` where they passed a role word; the role
  came from the PR manager's `--author` flag (`63e217b9`) until `of(pr)`
  took it from change detection (`df015c5e`).

- **Done** (`db86fe69`, `d30b9090`): the rest of the questions.
  `Conversation.awaits_you` and `Conversation.standing` (the
  `ConversationState`) answer what `is_yours` and `state_of` did;
  `Fix.commits` answers `(base, head)` or nothing (`52117a74`). An operation's
  kind and state, a review's state and either's reason code are
  `OperationKind`, `OperationState` and `ReasonCode`, owned here, and the
  board's contract models are typed with them, so nothing converts by
  spelling; the 24 constants that spelled them went. `PrFacts.role` is
  `is_author`, which the board words as its `Role`. A declined fix's
  `Classification` and a proposal's `ConfidenceLevel` are conversation's
  enums too, in the board's words: the CLI's `--classification` choices, the
  agent's command line and the board's contract take them from there, and
  the record schema reads the stored `conversational` and `ambiguous` as
  `not-a-change` and `unclear`.

- **Done** (`52117a74`): the board gets git reads from working copies.
  `CommitDiff`, `ProposedChange`, `proposal_diff`, `proposed_change`,
  `has_commit` and `file_at` went; `Fix.commits` answers the range.

- **Done** (`625070a2`, `d30b9090`): one refusal type, `Denied(code, reason)`. FixReports answer the conversation or `Denied`, where they
  answered `Accepted`, `Refused`, `Deferred` or `None`, and the CLI prints the
  refusal's reason. `ErrorCode` keeps the 24 codes the domain gives; the 10
  HTTP-only codes (`PRECONDITION_FAILED`, `NO_SUCH_COMMIT`, `NO_SUCH_PATH`,
  `NOT_TEXT`, `RANGE_INVERTED`, `RANGE_TOO_WIDE`, `BODY_TOO_LONG`,
  `FOREIGN_ORIGIN`, `SERVER_ERROR`, `UNREADABLE_RECORD`) moved to the board. A
  record that will not parse comes back as a conversation in an unreadable
  state, and `UnreadableRecord` went from the exports. `LineAnchor` is gone;
  drafts take a `Location`.

- **Done** (`a2ea102f`): `migrate` and the `migrate-threads` command are
  deleted; on 2026-09-25 the live machine had no records left to migrate.

- **Done** (`62428b4b`): `list` went; the CLI's `thread list` formats
  `conversations()`, one line a thread, where it printed the stored records
  as JSON. **Done** (`898c1dc4`): `draft_command` and `test_parallelism_note`
  moved to agent runs.

- **Done** (`16434c8a`): conversation owns the thread record schema:
  fields, vocabulary, validation and migration between versions, in
  `_adapters/record_schema.py`, which takes its words from conversation's
  domain and reads a document's version. Its `Conversations` decides that
  threads, reviews, the poll cursor, the action line and the pending
  decisions are thread records' documents and which kind each is, encodes
  them, stamps `created_at` and `updated_at`, orders the listing and the
  reviews, and clips the agent's action line (`c7789e68`). The stored shas
  are read into `Sha` at load (`a33f3d08`).

- **Done** (`d62a133a` and step 10c's commits after it): conversation
  ships `conversation.fake`, the threads' own logic over in-memory records
  and change detection, and `tests/conversation/test_contract.py` runs the
  five roles through `ConversationManagerFactory.of(pr)` against it and the wired threads.
  The board's tests are served by it. `tests/conversation/internals.py` is
  deleted, and so are the seeding helpers in `tests/conversation/support.py`;
  every test reaches its state through public calls, and one that set up a
  state no public call produces was deleted (Q56). The layering test fails
  any test that imports a private name of conversation. A record written by
  hand is left only where the test's point is data already on disk.

- **Done** (the commit that records this): conversation no longer reads change
  detection's state files. The poll took its cursor from a PR's old
  `thread_snapshot` key when it had none of its own, a one-off migration from
  `c6408154`; no live state file still held the key, so the reader went, and
  with it `ThreadsConfig.state_dir`.

### Thread records

Handles keeping each review thread's documents on disk, one writer at a time,
and each thread's pending decisions: what the board asked for that the drain
has not applied yet. Hides the files, the atomic writes and the locking.

`src/github_orchestrator/thread_records/`.

- **Done** (`16434c8a`, `c7789e68`): it stores opaque documents as bytes:
  `save(kind, key, document)`, `load(kind, key)`, `list(kind)` (in the order
  they were last written), `lock(name)` and `delete(kind, key)`. Review
  threads names the kinds and keys and decides what each document holds,
  including its version. A document of kind K and key X is the file
  `<X percent-encoded>.K` and a lock named N is `<N>.lock`, so every file on
  disk keeps its name: threads are kind `json`, reviews `review`, the agent's
  action line `action`, the poll cursor kind `cursor` under key `poll`. It
  knows no field or state word; its copy of the vocabulary went, and with it
  the drift (a fix whose run is a `retry` no longer turns its record
  unreadable).
- **Done** (`6e12cc4e`, `c7789e68`): the per-thread "inbox" is pending
  decisions, and they are documents like the rest: conversation posts a
  decision as kind `intent`, reads a reply as kind `reply`, and clears either
  with `delete`. The files keep their names (`<key>.intent`, `<key>.reply`);
  no folder or file on the live machine was ever named inbox.
- **Done** (`fe35b902`): no workspace path is stored (see Git working
  copies).
- Exports (`c7789e68`): 3. `ThreadRecords` is written by wiring, the watcher
  and conversation; `PrRecords` and `UnreadableThread` by conversation's
  `Conversations`. `ThreadRecords` has 2 methods and `PrRecords` 5. On
  2026-09-25 all 126 records, 12 poll cursors and every action line in a copy
  of the live threads folder loaded through the new code as before.

### Board API

Handles the HTTP server behind the review board. Hides routes, the JSON read
model, conditional requests and how refusals map to HTTP. Its interface is the
HTTP contract it serves at `/api/openapi.json`, generated from
`board_api/_contract.py` and the routes, which changes only by a spec's
decision (browser mode added the manager's routes); the PR manager starts and
stops it. `tests/board_api/test_contract_copy.py` writes the front end's copy
of it (`frontend/tests/helpers/board-api-contract.json`) and the wire types
generated from it (`frontend/app/data/api.ts`), and fails when either was
behind. The hand-written `2026-09-22-board-api-contract.openapi.yaml` was
retired on 2026-10-01: it had drifted from what is served, and a generated
copy would have been a third rendering of one document.

`src/github_orchestrator/board_api/`.

- **Done** (`1fdb6235`, `52117a74`, `2b8687cd`): it uses conversation's
  Reading, Decisions and Drafts roles, and Upkeep for the recheck its comments
  read asks for, and working copies' git reads, and re-derives nothing: it
  names proposals by the id the conversation gives them.
- **Done** (architecture review of 2026-10-01, candidate 7): the projection
  renames a conversation's per-operation views and its proposal into the
  contract, and holds no rule for which operation is current, so a change to
  `Fix` or `Run` stops at conversation.
- **Done** (`625070a2`): it owns the contract's `ErrorCode`, the wire enum
  with the 10 HTTP-only codes it refuses with itself, and maps review
  threads' 24 onto it in one place.
- **Done** (`c900458c`): the preview seeds its threads through review
  threads' poll and absorb, and writes no queued payload of its own.
- **Done** (the commit that records this): the preview moved to its own
  top-level dev entry point, `github_orchestrator/preview/` (run it with
  `python -m github_orchestrator.preview`), which may depend on anything and
  which nothing in the program imports. `BOARD_API_PREVIEW_MAY_IMPORT` and the
  board's seven edges it explained (settings, wiring, GitHub, agent runs,
  change detection, the desktop, PR windows) went with it, and so did
  `tests/board_api/test_preview.py`, now `tests/preview/test_preview.py`.
- **Done** (browser mode, step 3): it defines `ManagerPanel`, the port the PR
  manager answers, and `ManagerStatus`, the snapshot it gives; `start` takes
  one. It serves them under `/api/manager` (a status, the agent's notes,
  Claude's output, and `:pause`, `:resume`, `:carry-on` and `:dismiss`, each
  answered `202`), added to the contract. Exports: `BoardApi`, `ManagerPanel`
  and `ManagerStatus`.
- **Done** (browser mode, step 5): its second role, **Hub**: `start(port, holdings)`, `show(prs)` and `stop()`. It defines `Holdings`, the port it
  reads each listed PR through and hands pause, resume and release to, and
  `HeldPr`, what that port answers; the watcher implements it. The hub
  serves `/api/pull-requests` and its `:pause`, `:resume` and `:release`
  (each `202`, release refused `409 not-frozen`), `/api/health` and the same
  app build, behind the boards' Host and Origin guards, now in `_guarded.py`
  for both. `/api/health` on either says which it `serves` and the hub's
  `hub_url`, so the page knows where it is and a board links back. Exports:
  `BoardApi`, `Hub`, `HeldPr`, `ManagerPanel` and `ManagerStatus`, five; the
  watcher's holdings answer `Holdings` without naming it.
- **Done** (web interface, step 2): `Dashboard` replaced `ManagerStatus`,
  and `ManagerPanel.dashboard()` its `status()`. `GET /api/dashboard`
  serves it nested (`pr`, `status`, `action`, `your_move`, `system`,
  `frozen`, `dismiss`, `notice`) in place of `GET /api/manager`; the
  commands keep their `/api/manager:<verb>` paths and point `Location` at
  the dashboard. `Dashboard` is one flat record because the budget leaves
  no room to export its parts. Exports: `BoardApi`, `Hub`, `HeldPr`,
  `ManagerPanel` and `Dashboard`, five.
- **Done** (web interface, step 3): the hub carries each held PR's board on
  its own address. `/pr/<number>/api/...` goes to that board's port with
  every method, the body, the status and the end-to-end headers, `Location`
  moved under `/pr/<number>`; an answer without a length streams through. A
  number the hub does not hold is `404`; a held PR whose board has no port or
  does not answer is `503 board-unreachable`. The hub judges `Host` and, on
  every method but `GET` and `HEAD`, `Origin` against itself, then asks the
  board with the board's own origin, so the board's guard is unchanged.
  `Holdings.board_port(pr)` answers the port without the rest of `held()`.
  `/pr/<number>/...` pages serve the app. Exports unchanged.
- **Done** (web interface, step 4): `GET /api/pull-requests` is the wall
  feed: per held PR its manager state, `board_url` `/pr/<number>`, the
  dashboard (the board's own where it answers within two seconds, every
  board asked at once, or its last answer for 30 seconds after; otherwise
  built through the `Dashboards` port, which
  the PR manager answers and wiring injects into the hub), and `moved_from`
  and `moved_at` where it changed group while the hub ran. Rows come by
  group, then in the order they joined it. `Dashboards` sits beside
  `Holdings` unexported. `Holdings.held()` and `HeldPr` went: the row's
  facts are the dashboard's, so the port answers only `manager(pr)` and
  `board_port(pr)` beside pause, resume and release, and the watcher no
  longer reads facts or the frozen verdict for it. `WallGroup`, the one
  definition of the groups and their order, is exported for the PR
  manager's snapshot to name. Exports: `BoardApi`, `Hub`, `ManagerPanel`,
  `Dashboard` and `WallGroup`, five.
- **Done** (web interface, step 6): `ManagerPanel.run_git(keys)` answers a
  captured git command's exit code, lines and seconds as a tuple, since the
  budget leaves no room for a value type; `POST /api/manager/git` serves it
  (`200`, the first 2000 lines, keys limited to the palette's `f`, `p`,
  `pra`, `s`, `l` and `d`). The hub waits 75 seconds on a board, past the
  palette's 60. Exports unchanged.
- **Done** (web interface, step 8, `0423a471`): it serves the PR's terminal
  sessions, reached through PR windows' `TerminalSessions`, which wiring
  hands to `ServedBoardApi` (a new edge, pinned to that one name): `GET` and
  `POST /api/terminal/sessions` list them and open one through
  `ManagerPanel.open_terminal` (`409 terminal-refused` with the manager's
  reason), and a websocket at `/api/terminal/sessions/{id}` carries the pty,
  output as binary frames, typing and a size frame back, `{"exit_code"}`
  and 1000 at the end, 4404 for a session that is gone. A websocket is
  refused before the upgrade on the same host and origin rule as a write.
  The hub carries it under `/pr/<n>/api/...`, dialling the board before it
  accepts the page, 4503 when the board does not answer. `ManagerPanel` has
  9 methods. Exports unchanged.
- **Done** (web interface, step 10, `eece68db`): the hub serves
  `GET /api/runs`, the run ledger's runs of the last seven days newest first,
  today's count and cost, and the watcher's health. It reads them through two
  ports it defines beside `Dashboards` and `Holdings`, unexported:
  `RunLedger.finished_since` and `finished_today`, which agent runs'
  `History` answers, and
  `WatcherPulse.health`, which the watcher's `WatcherHealth` answers, each by
  structure and injected by wiring into `HubProvider`. Exports unchanged.

### Board web app

Handles the review board in the browser. Hides presentation and in-browser
state. Its seam is the Board API over `fetch`, which FakeBoard already fakes.

`frontend/app/`.

- **Done** (browser mode, step 5): the application route reads `/api/health`
  once; on the hub `/` lands on the `prs` route, which lists the PRs with
  pause, resume, release for a frozen one and a link to each board, and asks
  for none of one PR's reads. On a board the header's logo links back to the hub
  (a fourth tab squeezed the PR name out at 1440px). FakeBoard serves as either, checked against the merged
  contract.
- **Done** (web interface, step 3): one route tree on the hub and on a board's
  own port: `prs`, and `pr/:number` holding `conversations`, `board` and
  `manager` (their names unchanged, by `resetNamespace`). The `here` service
  takes the number from the route and prefixes every per-PR request with
  `/pr/<number>` on the hub only; health, the hub's list and client errors
  stay unprefixed. Every per-PR service (threads, dashboard, reads, review,
  the diff) keeps its state in the `here` service's per-PR scope, which
  entering a different PR destroys whole, closing its streams and dropping its
  reaches from the banner. The list's Board link and the header's logo on the hub stay in the
  page. A load that fails shows the error page, which words
  `board-unreachable`. FakeBoard as the hub carries its board under
  `/pr/<number>/api`, checked against the proxy's own refusals and then the
  board's contract.
- **Done** (web interface, step 8, `049f8d35`): the Terminal tab, route
  `terminal`, lists the PR's sessions and draws the chosen one with
  xterm.js. The `terminal` service holds each session's websocket for the
  page's life, across tabs and PRs, so a steered session survives a look at
  the Board. The git palette's terminal commands, the tab's launchers and
  the board's "Open a session" open there. FakeBoard fakes the websocket
  beside `fetch`.
- **Done** (web interface, step 10): the Runs page, route `runs`, and the
  top bar the wall shares with it (`Wall | Runs` and the health line), both
  read from `/api/runs` on the wall's refresh. The Dashboard route takes
  `?pane=claude` to open on Claude's output.
- **Done** (PR diff tab, steps 4 and 5): the Diff tab, route `diff` with the
  scrolled-to file in `?file=`, reads `GET /api/pull-request/diff` and the
  inline conversations through the `pull-request-diff` service, and draws them
  with `pr-diff`, which reuses the proposal diff's rows, gaps and reveal. The
  board's draft composer draws the same component for one file and anchors by
  its selection; the anchor form and the head-only excerpt left the composer,
  and `code-context` draws only a posted thread's code. Both save through the drafts service's one flow.
- **Done** (architecture review of 2026-10-01, candidate 10): FakeBoard's
  threads come from the real machine. `tests/board_api/test_thread_phases.py`
  drives the conversation machine to every phase an author's and a reviewer's
  board reaches, reads each thread back through the served API, and rewrites
  `frontend/tests/helpers/thread-phases.ts` when it was behind;
  `FakeBoard.threadIn(phase)` offers them by the board's viewer role, and the
  ember suite checks each names its own phase. A test hand-builds a history
  only for one the recording does not hold.
- **Done** (architecture review of 2026-10-01, candidate 3; the commit that
  records this): `data/dashboard.ts` answers one reading of a PR's
  dashboard, `dashboardOf`, as `data/panel.ts` answers `panelOf` for a
  conversation: the move, its square and edge, the title, the band, why, the
  wall's cells, the status and system rows, since you last acted, the frozen
  branches and the dismiss wording. The wall row, the Dashboard tab, the PR
  view's header and the switcher draw only the reading, so the wall and the
  tab cannot word the same PR two ways. `data/wall.ts` keeps the wall's own
  work (sections, keys, failing runs, the moved marker) and no longer imports
  the dashboard module back. The tab's standing and not-live sentences and
  the dismissal sentence that the tab and pr-controls' toast both say are
  written there once. The board API's `Dashboard` carries facts and codes
  instead of the manager's sentences (`move` for `your_move`, `wants` and
  `blocker` with the checks, reviewers and counts for the action's label and
  detail, the since counts, `pr.author`, `undismiss_command`), and
  `dashboardOf` words them, so the served dashboard keeps the board API's
  decisions: no assembled sentences.

### Operator CLI

Handles the `github-orchestrator` command: setup, status, queue, logs, runs,
config, restart, undismiss, switch-repo, the thread verbs, and installing the
scheduler. Hides launchd, how everything is shown, and the syntax of the
commands an agent uses to report back.

`src/github_orchestrator/cli/`.

- **Done** (`9035226c`, `f7b4fea9`, `39831dc7`): it formats every output from
  typed values: queue entries, runs, the watcher's health, a PR's threads. It
  opens no other module's files: not `runs.jsonl`, not the watcher's
  heartbeat and failure record, not the process table.
- **Done** (`49a4f91f`, `a2ea102f`): `setup` and `switch-repo` write the
  config through settings. `switch-repo` calls each module's
  `archive_other_repos(keep, into)` (change detection, the event queue, agent
  runs' History and the pauses), passing the archive folder; thread records
  stay where they are.
- **Done** (`39831dc7`): `restart` and `confirm-restart` go through PR
  windows' `stop_managers()` and `manager(pr)`.
- **Done** (`cb88eeca`): `switch-repo` clones through GitHub's
  `Access.clone(repo, into)`, and `setup`'s hint for a missing clone no longer
  spells the gh command.
- **Done** (`898c1dc4`, `d7fdbd89`): it exposes its agent-facing command
  lines (`CliReportCommands`) to wiring, which hands them to agent runs as
  `ReportCommands`; the copies in conversation's prompts went. **Done**
  (`9cc83629`): the operator's lines too. `cli/_command_lines.py` spells the
  invocation once; wiring hands settings' `ConfigFile` the setup line for its
  config problems and the PR manager the undismiss line for its dashboard.
  Only the CLI and wiring name `github_orchestrator.cli`.
- **Done** (browser mode, step 5): `status` prints the hub's address on the
  line after the watcher's, says it is down while the watcher is not
  running, and that there is none under cron. Wiring hands it the address
  board API spells.

### Settings and runtime state

Handles `config.toml` (reading, writing and environment overrides), where log
files live, the environment a child process needs, and the per-PR switches
(paused, dismissed, board wanted). Hides the config's format and location,
how each setting is resolved, the log layout, and the switch files.

`src/github_orchestrator/settings/`.

- **Done** (`9035bba5`, `eafcf7ef`, `4689ad32`): no module outside settings
  and wiring imports a path helper. Seven modules no longer import settings at
  all, and the layering test refuses it. Exports went from 19 to 16. Each
  module that files things per repo now carries its own copy of the owner/name
  check; `Repo` in the kernel collapses them.
- **Done** (`49a4f91f`): settings owns the file. `load_settings` reads it
  once; a broken config still falls back to the defaults, and `ConfigFile`
  reports it, describes it, says where it is and writes it. **Done**
  (`887f1a4e`): the problem crosses as a value (`check() -> str | None`,
  and `describe()` carries it beside the rows); `ConfigError` stays inside.
  The
  entry points' second `load_config` went, `setup` and `switch-repo` write
  through `ConfigFile.write`, and the example file stays inside.
- **Done** (`4a459999`): `Logs.configure_logging(process)` picks the file,
  creates the folder, sets the level and, for the watcher, trims the
  scheduler logs. The CLI's `logs` and the scheduler templates ask
  `Logs.path(process)`. Only `settings/_logging.py` spells a log file name.
- **Done** (`a2ea102f`): `Settings.child_environment()` returns the two
  variables a child needs; PR windows merges it into each manager window and
  the CLI renders it into the plist and the cron block. No module outside
  settings and wiring sees `Settings`, `data_dir` or `config_path`; the
  preview gets its data folder in and the account back from
  `preview_container` (`887f1a4e`). Change detection and agent runs gained
  `archive_other_repos` so `switch-repo` needs no data dir, and
  `migrate-threads` went.
- **Done** (`852c0da8`): dismissals are `dismiss_forever(pr)`,
  `dismiss_until_next_event(pr)`, `is_hidden(pr, events_waiting)` (settings
  clears an until-event dismissal itself), `is_dismissed_forever(pr)` for the
  teardown reason, and `dismissal(pr)` returning the `Dismissal` enum for
  display. `DISMISS_MODES` and the mode strings went; the flag files keep
  their words, so the dismissals on disk still read.
- **Done** (`03ce9932`): the switches are three roles wiring provides
  separately, each caller taking only what it uses. **Pauses**: `paused`,
  `set_paused`, `paused_prs`, `forget`, `archive_other_repos` (archiving
  only ever moved pause flags). **Dismissals**: the six dismissal calls,
  `dismissed_prs` and `forget`. **Boards**: `board_wanted`, `want_board`,
  `board_port`, `forget`. `flagged` went; teardown asks each role to forget.
- Exports (`887f1a4e`): `Pauses`, `Dismissals`, `Boards`, `ConfigFile`,
  `Logs`, `Process` and `Dismissal`, seven against a budget of about five.
  `ConfigError` and `Settings` left. Later `Dismissal` took its display words
  as its values, so the CLI prints `dismissal.value` and no outside module
  writes the name: it left the exports, which are now six.
- **Done** (`d627d666`): `TMUX_SESSION` moved to PR windows. **Done**
  (`2e3a4eba`): `is_repo_spec` became `Repo.parse`.
- **Done** (`d627d666`): `REPO_ROOT` and the `UNSET_*` words stay inside.
  Wiring reads `Settings.repo_root`, setup reads the example through
  `example_config()`, and `describe_config` says which keys are unset.

### Mac desktop

Shows a banner, opens a URL, copies to the clipboard, and reads the system
appearance. Hides `osascript`, `open`, `pbcopy`, `defaults` and the per-badge
notification apps.

`src/github_orchestrator/desktop/`.

- **Done** (`b0bbff3a`): `appearance()` answers light or dark for PR
  windows' pane theme, and light away from the Mac.
- **Done** (`d42219da`): only notifications passes a badge. Notifications no
  longer re-exports `Badge`, and a layering test refuses it in any module
  outside notifications and the desktop.
- **Done** (`c0d7168d`): `announce` takes a link. The badge app keeps it in
  the notification and opens it when the banner is clicked.

## Out of scope

- The board's HTTP API. It does not change.
- The order of the narrowing work. It is its own step, after this spec.

## Not yet placed

Nothing. The git palette's `claude "/rebase-on-main"` is placed: agent runs'
PR work starts it (`rebase_in_session`, `898c1dc4`). The CLI's `gh repo clone`
is placed on GitHub's Access (`clone`, `cb88eeca`); it was `switch-repo` that
ran it, and `setup` only printed it as a hint.

## Appendix: decisions

Settled 2026-09-23, for the move.

- A module is a self-contained unit with a thin interface, testable on its own,
  handling one concrete piece of functionality; there should be about 10–15.
- The map started at 17. Event queue and Event response merged into the Inbox,
  whose way in is `add` and `next`, not a queue with a lookup beside it. Review
  rules and Review workflow merged into Review threads. The watcher cycle is the
  Master controller.
- Every module is a singleton, injected, reached only by calling methods on it.
  That includes the PR manager, not `run_loop`.
- Handles are allowed; they are part of the interface and must be thin.
- No internal seams: every test goes through the interface.
- GitHub's contract is the outcome. The queue's file layout is a leak, closed
  inside the Inbox.
- Dishka, with one wiring module.
- Each module ships its own fakes, checked by shared contract tests.
- The layering test grows to the whole repository as several small tests.
- From the edges in, no check-ins between waves. The frontend is the last wave.
- The board's error text is pinned once, in one table test; everything else
  asserts the error code. Frontend tests that pin DOM order or CSS are rewritten
  as behaviour.

Settled 2026-09-25, for the narrowing. The rules are in Interface rules and
the shared kernel; the per-module decisions are in each entry. Two of the
reasons are not visible from the code:

- `GH_TOKEN` was a holdover from the first gh wrapper (`82ef79cc`,
  2026-04-21). An agent that runs `gh` in a manager pane now uses the active
  gh account; if that breaks, this is where to look first.
- Roles are named by domain role, not by caller, so that a new caller never
  reshapes a module. The board uses three of conversation's roles and the
  watcher one, and neither owns them.
