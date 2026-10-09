# Board bottom bar, Defer and Reject Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish phase 6 of the review board redesign — give the panel's bottom bar
two zones and three button weights, and add the Defer and Reject verbs with their
ways back, so the `deferred` and `rejected` states the board already draws become
reachable.

**Architecture:** Three layers, unchanged. New domain commands (`Reject`, `Defer`,
`Unpark`, `Wake`) return effects; `decide` turns a drained intent into one of them;
the board adapter renders the verbs the read model offers. The bar's two zones come
from one new weight column on the decisions table, not from new rendering paths.
`Next ready →` and `Reply to N` never leave the browser.

**Tech Stack:** Python 3.12, dataclasses, htmx, plain ES modules, pytest under
subprocess replay, node for the page harness.

**Spec:** `docs/superpowers/specs/2026-09-12-review-board-redesign-design.md`,
phase 6, as amended 2026-09-15. Read §"What this adds to the domain", §"States and
groups", §Reject, §Defer, §"Resolve on GitHub", and notes 8, 12 and 13.

## Global Constraints

- **Layering.** `domain/` imports the standard library only. `application/` imports
  the domain and the ports it defines itself — never an adapter, never
  `common/config.py`. `tests/review/test_layering.py` fails the moment one crosses.
- **No colour literals under `review/`.** Every colour is `adapters/palette.py`, one
  frozen `Palette` per mode. A test names the file that writes a hex.
- **Contrast.** A colour used as type clears WCAG AA on its ground
  (`test_board_contrast.py`). Row fills cap at 20%.
- **Records.** Every read-modify-write of a conversation goes through
  `records.update`, which holds the `.lock`. Writes are tmp, fsync, rename.
- **`make record` after any page-JS edit.** The node page harness spawn is a
  recorded subprocess keyed on argv, cwd and stdin; an edited `<script>` changes the
  stdin key and the test fails with `RecordingMismatch` until re-recorded.
- **Speed.** The whole suite is about twelve seconds under replay. A single test past
  0.2s wants a reason. Run `--durations=20` after adding a test that spawns anything.
- **Parallelism caps at 4 workers:** `uv run pytest tests/ -n 4`. Never `-n auto`.
- **No comments in code.** Naming and structure carry the meaning.
- **Commits.** Subject is `GITHUB-ORCHESTRATOR: <lowercase imperative>`. Never add a
  co-author trailer. Branch is `board-bottom-bar`; never commit on `main`.
- **Keys.** `n` is next ready and `p` stays reserved for phase 8's previous. This
  plan claims `x` reject, `f` defer, `u` unpark.

## File Structure

| File                                         | Responsibility                              | Change                                                      |
| -------------------------------------------- | ------------------------------------------- | ----------------------------------------------------------- |
| `review/domain/conversation.py`              | the conversation and its fix                | add `wake_on`, `defer_note`, `closing_into`                 |
| `review/domain/commands.py`                  | the operator's and the world's commands     | add `Reject`, `Defer`, `Unpark`, `Wake`                     |
| `review/domain/apply.py`                     | the state machines                          | add `_reject`, `_defer`, `_unpark`, `_wake`, dispatch cases |
| `review/application/read_model/decisions.py` | which verbs a word offers, and their weight | add the weight table, extend `ACTIONS`                      |
| `review/application/read_model/panel.py`     | the panel read model                        | `Action.weight`, `Affordance`, `PanelView.affordances`      |
| `review/application/decide.py`               | intent → command                            | three new `match` arms                                      |
| `review/application/tick.py`                 | the manager's per-pass work                 | the wake check                                              |
| `review/application/ports.py`                | the ports the application runs through      | add the `PullRequests` port                                 |
| `review/adapters/records/inbox.py`           | the intent file format                      | widen the modifier slot                                     |
| `review/adapters/records/document.py`        | the JSON document                           | encode/decode the new fields                                |
| `review/adapters/pull_requests.py`           | **new** — CI state and another PR's state   | the `PullRequests` adapter                                  |
| `review/adapters/board/render.py`            | the panel's HTML                            | two-zone `_action_footer`                                   |
| `review/adapters/board/page.py`              | CSS, the dialog, the page script            | weights, wake picker, keys, affordances                     |
| `review/adapters/board/routes.py`            | the board's HTTP surface                    | accept the new decisions                                    |
| `review/compose.py`                          | the port bundle                             | wire the new adapter                                        |

______________________________________________________________________

### Task 1: Action weight and the bar's two zones

The bar today is a flat row where the first action is `.primary` and the rest are
identical outlined buttons. The design gives it three weights and pushes the
low-prominence verbs to the right behind `margin-left:auto`. Weight is a property of
`(word, decision)`, exactly like `LABELS` already is.

**Files:**

- Modify: `src/github_orchestrator/review/application/read_model/decisions.py`
- Modify: `src/github_orchestrator/review/application/read_model/panel.py:117-123` (`Action`), `:327-341` (`actions_for`)
- Modify: `src/github_orchestrator/review/adapters/board/render.py:266-297` (`panel_button`, `_action_footer`)
- Modify: `src/github_orchestrator/review/adapters/board/page.py` (the `button` and `.actions` rules, around `:77-83` and `:222-226`)
- Test: `tests/review/application/test_read_model.py`, `tests/review/adapters/board/test_board_panel.py`

**Interfaces:**

- Produces: `weight_of(word: str, decision: str) -> str` returning `"primary"`,
  `"secondary"` or `"ghost"`; `Action.weight: str`; a footer whose ghost buttons sit
  in `<span class="ghost-zone">`.

- [ ] **Step 1: Write the failing test for the weight table**

In `tests/review/application/test_read_model.py`:

```python
from github_orchestrator.review.application.read_model.decisions import weight_of


@pytest.mark.parametrize("word, decision, expected", [
    (PROPOSED, "approve", "primary"),
    (PROPOSED, "session", "secondary"),
    (PROPOSED, "resolve", "ghost"),
    (FAILED, "retry", "primary"),
    (DECLINED, "session", "primary"),
])
def test_weight_of_places_a_decision_in_a_zone(word, decision, expected):
    assert weight_of(word, decision) == expected
```

`(DECLINED, "session")` is the one override: a declined fix offers no approve, so its
rework button is the primary.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/review/application/test_read_model.py -k weight_of -v`
Expected: FAIL, `ImportError: cannot import name 'weight_of'`

- [ ] **Step 3: Write the weight table**

In `decisions.py`, below `LABELS`:

```python
WEIGHTS = {
    "approve": "primary",
    "retry": "primary",
    "session": "secondary",
    "unpark": "secondary",
    "resolve": "ghost",
    "defer": "ghost",
    "reject": "ghost",
}

WEIGHT_OVERRIDES = {
    (DECLINED, "session"): "primary",
}


def weight_of(word: str, decision: str) -> str:
    return WEIGHT_OVERRIDES.get((word, decision), WEIGHTS[decision])
```

`"unpark"`, `"defer"` and `"reject"` are listed now so later tasks add no second
table; nothing offers them until Task 5.

- [ ] **Step 4: Run it and watch it pass**

Run: `uv run pytest tests/review/application/test_read_model.py -k weight_of -v`
Expected: PASS

- [ ] **Step 5: Write the failing test for `Action.weight`**

```python
def test_actions_carry_their_weight(tmp_path):
    view = panel_for(tmp_path, make_record(status=READY))
    weights = {action.decision: action.weight for action in view.actions}
    assert weights == {"approve": "primary", "session": "secondary",
                       "resolve": "ghost"}
```

- [ ] **Step 6: Run it and watch it fail**

Run: `uv run pytest tests/review/adapters/board/test_board_panel.py -k carry_their_weight -v`
Expected: FAIL, `AttributeError: 'Action' object has no attribute 'weight'`

- [ ] **Step 7: Add the field**

In `panel.py`, add `weight: str` to `Action`, and in `actions_for` pass
`weight=weight_of(word, decision)` beside the existing `label=` and `title=`. Import
`weight_of` alongside the other names from `decisions`.

- [ ] **Step 8: Run it and watch it pass**

Run: `uv run pytest tests/review/adapters/board/test_board_panel.py -k carry_their_weight -v`
Expected: PASS

- [ ] **Step 9: Write the failing test for the two zones**

```python
def test_ghost_actions_sit_in_their_own_zone(tmp_path):
    panel = panel_html(tmp_path, make_record(status=READY))
    assert '<span class="ghost-zone">' in panel
    zone = panel.split('<span class="ghost-zone">')[1]
    assert 'class="resolve ghost"' in zone
    assert 'class="approve primary"' not in zone
```

- [ ] **Step 10: Run it and watch it fail**

Run: `uv run pytest tests/review/adapters/board/test_board_panel.py -k ghost_actions -v`
Expected: FAIL, `assert '<span class="ghost-zone">' in panel`

- [ ] **Step 11: Partition the footer**

In `render.py`, `panel_button` takes the weight instead of the `primary` flag:

```python
def panel_button(key: str, action: Action, token: str) -> str:
    title = html.escape(action.title, quote=True)
    vals = html.escape(
        json.dumps({"d": action.decision, "s": token, "i": ""},
                   separators=(",", ":")),
        quote=False,
    ).replace("'", "&#x27;")
    included = ["#decide-body"] if action.takes_text else []
    if action.takes_delete:
        included.append("#decide-delete")
    include = f' hx-include="{", ".join(included)}"' if included else ""
    classes = f"{action.decision} {action.weight}"
    return (
        f'<button class="{html.escape(classes, quote=True)}" '
        f'title="{title}" '
        f'hx-post="/thread/{_url_key(key)}/decide" '
        f"hx-vals='{vals}' "
        f'hx-swap="none"{include}>'
        f"{html.escape(action.label)}</button>"
    )


def _action_footer(view: PanelView) -> str:
    if view.queued_label is not None:
        return ('<footer class="actions" id="panel-actions">'
                f'<span class="queued">queued: {view.queued_label}…</span>'
                "</footer>")
    buttons = "".join(panel_button(view.key, action, view.status_token)
                      for action in view.actions
                      if action.weight != "ghost")
    ghosts = "".join(panel_button(view.key, action, view.status_token)
                     for action in view.actions
                     if action.weight == "ghost")
    zone = f'<span class="ghost-zone">{ghosts}</span>' if ghosts else ""
    inner = buttons + zone
    return (f'<footer class="actions" id="panel-actions">{inner}</footer>'
            if inner else "")
```

- [ ] **Step 12: Style the weights**

In `page.py`, replace the `button.primary` rule with the three weights and add the
zone. Keep every colour on an existing palette token:

```css
  button { font: inherit; font-weight: 600; padding: .75em 1.5em;
           cursor: pointer; border: 2px solid var(--border-strong);
           background: var(--page); color: var(--text); }
  button.primary { background: var(--border-strong); color: var(--page); }
  button.secondary { background: transparent; }
  button.ghost { border-color: transparent; padding: 0; background: none;
                 font-weight: 350; text-decoration: underline;
                 text-underline-offset: 3px; }
  .ghost-zone { margin-left: auto; display: flex; gap: 1rem;
                align-items: center; flex-shrink: 1; min-width: 0; }
```

- [ ] **Step 13: Run the board suite**

Run: `uv run pytest tests/review/adapters/board/ -v`
Expected: PASS. Fix any test that asserted on the old `class="approve primary"`
single-class shape or on `.3em 1.1em` padding.

- [ ] **Step 14: Re-record and run everything**

Run: `make record && uv run pytest tests/ -n 4`
Expected: PASS. The page's `<style>` changed, so every node-harness recording is stale
until `make record`.

- [ ] **Step 15: Commit**

```bash
git add -A src/github_orchestrator/review tests/review tests/recorded_subprocesses.json
git commit -m "GITHUB-ORCHESTRATOR: give the panel's bottom bar two zones and three button weights"
```

______________________________________________________________________

### Task 2: Reject in the domain

Reject turns the fix down, drops its workspace, and optionally replies. Per spec note
12 it stops a running agent first. Per the 2026-09-15 amendment it does **not** keep
the workspace.

The reply path needs `closing_into`: `_closing` today returns a `PostReply` effect and
lets `ClosingReplyPosted` settle the conversation into `RESOLVED`. Reject reuses that
dance and has to land in `REJECTED` instead, so the intended terminal state is recorded
on the conversation when the verb is accepted.

**Files:**

- Modify: `src/github_orchestrator/review/domain/conversation.py:98-129`
- Modify: `src/github_orchestrator/review/domain/commands.py`
- Modify: `src/github_orchestrator/review/domain/apply.py:506-530` (`_settled`, `_closing`), `:563+` (`_dispatch`)
- Test: `tests/review/domain/test_conversation.py`

**Interfaces:**

- Consumes: nothing from Task 1.

- Produces: `commands.Reject(reply: str = "", delete_comment: bool = False)`;
  `Conversation.closing_into: str | None`; a `REJECTED` conversation whose fix is
  untouched but whose workspace is dropped.

- [ ] **Step 1: Write the failing test**

In `tests/review/domain/test_conversation.py`:

```python
def test_reject_drops_the_workspace_and_posts_nothing():
    conversation = replace(_created().conversation,
                           fix=Fix(state=PROPOSED, thread_sha="abc123"))

    outcome = apply(conversation, Reject())

    assert isinstance(outcome, Accepted)
    assert outcome.conversation.state == REJECTED
    assert outcome.conversation.fix.thread_sha == "abc123"
    assert outcome.effects == (DropWorkspace(),)


def test_reject_stops_a_running_agent_first():
    conversation = replace(_created().conversation, fix=Fix(state=RUNNING))

    outcome = apply(conversation, Reject())

    assert isinstance(outcome, Accepted)
    assert outcome.conversation.state == REJECTED
    assert StopRun() in outcome.effects


def test_reject_with_a_reply_posts_before_it_settles():
    conversation = replace(_created().conversation, fix=Fix(state=PROPOSED))

    outcome = apply(conversation, Reject(reply="not taking this"))

    assert isinstance(outcome, Accepted)
    assert outcome.conversation.state == OPEN
    assert outcome.conversation.closing_into == REJECTED
    assert outcome.effects == (PostReply(body="not taking this"),)


def test_a_posted_rejection_reply_settles_into_rejected():
    conversation = replace(_created().conversation, fix=Fix(state=PROPOSED),
                           closing_into=REJECTED)

    outcome = apply(conversation, ClosingReplyPosted(reply="no"))

    assert isinstance(outcome, Accepted)
    assert outcome.conversation.state == REJECTED
    assert outcome.conversation.closing_into is None


def test_reject_refuses_a_landed_fix():
    conversation = replace(_created().conversation, fix=Fix(state=LANDED))

    outcome = apply(conversation, Reject())

    assert isinstance(outcome, Refused)
    assert "landed" in outcome.reason
```

Add `Reject` to the `commands` import block and `PostReply`, `StopRun`,
`DropWorkspace` to the `effects` one if they are not already there.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/review/domain/test_conversation.py -k reject -v`
Expected: FAIL, `ImportError: cannot import name 'Reject'`

- [ ] **Step 3: Add the command and the field**

In `commands.py`:

```python
@dataclass(frozen=True)
class Reject:
    reply: str = ""
    delete_comment: bool = False
```

In `conversation.py`, add to `Conversation` after `closing_reply_id`:

```python
    closing_into: str | None = None
```

- [ ] **Step 4: Generalise the settle and add `_reject`**

In `apply.py`, `_settled` takes the state it settles into, and `_closing_reply_posted`
reads it off the conversation:

```python
def _settled(conversation: Conversation, state: str = RESOLVED,
             **fields) -> Accepted:
    settled = replace(conversation, state=state, closing_into=None, **fields)
    return Accepted(_with_fix(settled, decision_error=None),
                    (DropWorkspace(),))
```

Change `_closing_reply_posted` to settle into the recorded state:

```python
def _closing_reply_posted(conversation: Conversation, command) -> Accepted:
    return _settled(
        _with_transcript(conversation, command.comment, command.posted_key),
        conversation.closing_into or RESOLVED,
        closing_reply=command.reply,
        closing_reply_id=command.comment.id if command.comment else None,
    )
```

Add `_reject` beside `_closing`:

```python
def _reject(conversation: Conversation, command) -> Accepted | Refused:
    fix = conversation.fix
    if conversation.state not in (OPEN, REMOVED):
        return Refused(conversation,
                       f"a {conversation.state} conversation is already closed")
    if fix.state in (LANDING, LANDED):
        return Refused(conversation,
                       f"a {fix.state} fix is not the operator's to reject")
    stopping = (StopRun(),) if fix.state == RUNNING else ()
    if command.delete_comment and not conversation.comment_deleted:
        return Accepted(replace(conversation, closing_into=REJECTED),
                        stopping + (DeleteComment(),))
    if command.reply and not conversation.comment_deleted:
        return Accepted(replace(conversation, closing_into=REJECTED),
                        stopping + (PostReply(body=command.reply),))
    settled = _settled(conversation, REJECTED)
    return Accepted(settled.conversation, stopping + settled.effects)
```

Import `REJECTED` in `apply.py` if it is not already imported (it is, at `:53`).

- [ ] **Step 5: Dispatch it**

In `_dispatch`, beside the `Resolve()` case:

```python
        case Reject():
            return _reject(conversation, command)
```

Add `Reject` to the `commands` import at the top of `apply.py`, and to
`CLEARS_THE_REOPENED_MARK`, since rejecting is a verb of your own.

- [ ] **Step 6: Run them and watch them pass**

Run: `uv run pytest tests/review/domain/test_conversation.py -k reject -v`
Expected: PASS

- [ ] **Step 7: Run the whole domain and records suite**

Run: `uv run pytest tests/review/domain tests/review/adapters/test_records.py -n 4`
Expected: PASS. `_settled`'s signature changed; check every caller passes what it means.

- [ ] **Step 8: Persist `closing_into`**

In `records/document.py`, add `"closing_into": conversation.closing_into` to `encode`
and `closing_into=document.get("closing_into")` to `decode`.

- [ ] **Step 9: Write the round-trip test**

In `tests/review/adapters/test_records.py`:

```python
def test_closing_into_survives_a_round_trip():
    conversation = Conversation(key="PRRT_one", closing_into=REJECTED)

    assert decode(encode(conversation)).closing_into == REJECTED
```

- [ ] **Step 10: Run it**

Run: `uv run pytest tests/review/adapters/test_records.py -k closing_into -v`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add -A src/github_orchestrator/review tests/review
git commit -m "GITHUB-ORCHESTRATOR: add the reject command, which drops the fix's workspace"
```

______________________________________________________________________

### Task 3: Reject on the board

Wire the verb through the intent inbox, the decide service, the routes guard and the
decisions table, and correct the kicker the amendment falsified.

**Files:**

- Modify: `src/github_orchestrator/review/adapters/records/inbox.py:3`
- Modify: `src/github_orchestrator/review/application/decide.py:108-127`
- Modify: `src/github_orchestrator/review/application/read_model/decisions.py`
- Modify: `src/github_orchestrator/review/application/read_model/panel.py:96`
- Modify: `src/github_orchestrator/review/adapters/board/page.py:469` (`DECISIONS`), `:468` (`DECIDE`)
- Test: `tests/review/application/test_read_model.py`, `tests/review/application/test_decide.py`

**Interfaces:**

- Consumes: `commands.Reject` from Task 2; `weight_of` from Task 1.

- Produces: `"reject"` as a drainable decision; `ACTIONS` entries offering it.

- [ ] **Step 1: Write the failing test for the decisions offered**

```python
@pytest.mark.parametrize("word", [PROPOSED, DECLINED, FAILED, REMOVED, QUEUED])
def test_reject_is_offered_wherever_there_is_a_fix_to_turn_down(word):
    assert "reject" in ACTIONS[word]


@pytest.mark.parametrize("word", [LANDING, LANDED])
def test_reject_is_not_offered_once_the_fix_is_landing(word):
    assert "reject" not in ACTIONS.get(word, ())
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/review/application/test_read_model.py -k reject_is -v`
Expected: FAIL, `KeyError` or `assert 'reject' in ('resolve',)`

- [ ] **Step 3: Extend the tables**

In `decisions.py`:

```python
ACTIONS = {
    QUEUED: ("resolve", "reject"),
    PROPOSED: ("approve", "session", "resolve", "reject"),
    LANDING: ("approve",),
    DECLINED: ("session", "resolve", "reject"),
    FAILED: ("retry", "resolve", "reject"),
    REMOVED: ("approve", "resolve", "reject"),
}
```

Add to `QUEUED_LABELS`: `"reject": "rejecting"`. Add to `TITLES`:

```python
    "reject": ("turns this fix down and drops its worktree — the proposed diff "
               "goes with it, so bringing the conversation back re-runs the "
               "agent from scratch"),
```

Add `"reject"` to both `TEXT_TAKING_DECISIONS` and `DELETE_TAKING_DECISIONS`: the spec
gives Reject an optional reply and, on your own comment, the delete tick.

- [ ] **Step 4: Run it and watch it pass**

Run: `uv run pytest tests/review/application/test_read_model.py -k reject_is -v`
Expected: PASS

- [ ] **Step 5: Write the failing test for the drain**

In `tests/review/application/test_decide.py`:

```python
def test_a_reject_intent_becomes_a_reject_command(ports):
    command = _command(ports, Intent(decision="reject", payload="no thanks"))

    assert command == Reject(reply="no thanks", delete_comment=False)
```

- [ ] **Step 6: Run it and watch it fail**

Run: `uv run pytest tests/review/application/test_decide.py -k reject_intent -v`
Expected: FAIL, `NotImplementedError: reject`

- [ ] **Step 7: Wire the drain**

In `inbox.py`, `DECISIONS = ("approve", "session", "resolve", "retry", "reject")`.

In `decide.py`'s `_command`, beside the `"resolve"` arm:

```python
        case "reject":
            return Reject(reply=payload,
                          delete_comment=intent.delete_comment)
```

- [ ] **Step 8: Run it and watch it pass**

Run: `uv run pytest tests/review/application/test_decide.py -k reject_intent -v`
Expected: PASS

- [ ] **Step 9: Correct the falsified kicker**

In `panel.py:96`, `REJECTED: "Rejected · the fix is kept"` becomes
`REJECTED: "Rejected · the fix was dropped"`. Update the expectation at
`tests/review/application/test_read_model.py:1180` to match.

- [ ] **Step 10: Teach the page the decision**

In `page.py`, `const DECIDE = {a: "approve", r: "session", d: "resolve", x: "reject"};`
and `const DECISIONS = ["approve", "session", "resolve", "retry", "reject"];`.
Add to the `<dt>` legend: `<dt>x</dt><dd>reject the open comment (asks for your reply)</dd>`,
and reword the footer at `:441` from "a, r and d act on the open comment" to
"a, r, d and x act on the open comment".

- [ ] **Step 11: Re-record and run everything**

Run: `make record && uv run pytest tests/ -n 4`
Expected: PASS

- [ ] **Step 12: Commit**

```bash
git add -A src/github_orchestrator/review tests/review tests/recorded_subprocesses.json
git commit -m "GITHUB-ORCHESTRATOR: offer reject on the board"
```

______________________________________________________________________

### Task 4: Defer in the domain

Defer parks the conversation with nothing posted and its workspace kept. It carries a
wake condition and a private note. Like Reject it stops a running agent first.

Wake conditions, per spec §Defer: `"manual"`, `"ci"` (this PR's CI passes), and
`"pr:<number>"` (another PR closes).

**Files:**

- Modify: `src/github_orchestrator/review/domain/conversation.py`
- Modify: `src/github_orchestrator/review/domain/commands.py`
- Modify: `src/github_orchestrator/review/domain/apply.py`
- Modify: `src/github_orchestrator/review/adapters/records/document.py`
- Test: `tests/review/domain/test_conversation.py`, `tests/review/adapters/test_records.py`

**Interfaces:**

- Consumes: nothing from Tasks 1–3.

- Produces: `commands.Defer(wake_on: str = "manual", note: str = "")`;
  `Conversation.wake_on: str | None` and `Conversation.defer_note: str`;
  `WAKE_MANUAL`, `WAKE_CI`, `WAKE_PR_PREFIX` constants.

- [ ] **Step 1: Write the failing test**

```python
def test_defer_parks_the_conversation_and_keeps_its_workspace():
    conversation = replace(_created().conversation,
                           fix=Fix(state=PROPOSED, workspace="wt|branch"))

    outcome = apply(conversation, Defer(wake_on=WAKE_CI, note="after the rebase"))

    assert isinstance(outcome, Accepted)
    assert outcome.conversation.state == DEFERRED
    assert outcome.conversation.wake_on == WAKE_CI
    assert outcome.conversation.defer_note == "after the rebase"
    assert outcome.conversation.fix.workspace == "wt|branch"
    assert outcome.effects == ()


def test_defer_stops_a_running_agent_first():
    conversation = replace(_created().conversation, fix=Fix(state=RUNNING))

    outcome = apply(conversation, Defer())

    assert isinstance(outcome, Accepted)
    assert outcome.effects == (StopRun(),)


def test_defer_refuses_a_landing_fix():
    conversation = replace(_created().conversation, fix=Fix(state=LANDING))

    outcome = apply(conversation, Defer())

    assert isinstance(outcome, Refused)
    assert "landing" in outcome.reason
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/review/domain/test_conversation.py -k defer -v`
Expected: FAIL, `ImportError: cannot import name 'Defer'`

- [ ] **Step 3: Add the constants, the field and the command**

In `conversation.py`, beside the state constants:

```python
WAKE_MANUAL = "manual"
WAKE_CI = "ci"
WAKE_PR_PREFIX = "pr:"
```

and on `Conversation`, after `closing_into`:

```python
    wake_on: str | None = None
    defer_note: str = ""
```

In `commands.py`:

```python
@dataclass(frozen=True)
class Defer:
    wake_on: str = WAKE_MANUAL
    note: str = ""
```

importing `WAKE_MANUAL` from `conversation`.

- [ ] **Step 4: Add `_defer` and dispatch it**

```python
def _defer(conversation: Conversation, command) -> Accepted | Refused:
    fix = conversation.fix
    if conversation.state != OPEN:
        return Refused(conversation,
                       f"a {conversation.state} conversation is not open to park")
    if fix.state in (LANDING, LANDED):
        return Refused(conversation,
                       f"a {fix.state} fix is not the operator's to park")
    parked = replace(conversation, state=DEFERRED, wake_on=command.wake_on,
                     defer_note=command.note)
    effects = (StopRun(),) if fix.state == RUNNING else ()
    return Accepted(_with_fix(parked, decision_error=None), effects)
```

In `_dispatch`:

```python
        case Defer():
            return _defer(conversation, command)
```

Add `Defer` to the `commands` import and to `CLEARS_THE_REOPENED_MARK`.

- [ ] **Step 5: Run it and watch it pass**

Run: `uv run pytest tests/review/domain/test_conversation.py -k defer -v`
Expected: PASS

- [ ] **Step 6: Persist the two fields**

In `document.py`'s `encode`: `"wake_on": conversation.wake_on` and
`"defer_note": conversation.defer_note`. In `decode`:
`wake_on=document.get("wake_on")` and
`defer_note=str(document.get("defer_note") or "")`.

- [ ] **Step 7: Write and run the round-trip test**

```python
def test_a_deferral_survives_a_round_trip():
    conversation = Conversation(key="PRRT_one", state=DEFERRED,
                                wake_on="pr:87", defer_note="blocked on that")

    decoded = decode(encode(conversation))

    assert decoded.wake_on == "pr:87"
    assert decoded.defer_note == "blocked on that"
```

Run: `uv run pytest tests/review/adapters/test_records.py -k deferral -v`
Expected: PASS

- [ ] **Step 8: Run the domain and records suites**

Run: `uv run pytest tests/review/domain tests/review/adapters/test_records.py -n 4`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add -A src/github_orchestrator/review tests/review
git commit -m "GITHUB-ORCHESTRATOR: add the defer command with its wake condition and note"
```

______________________________________________________________________

### Task 5: Defer on the board, with its wake picker

The intent file's first line is `<decision>[ <modifier>]`, and the modifier slot is
today restricted to `delete`. Defer needs it to carry the wake condition, so the
restriction becomes per-decision.

**Files:**

- Modify: `src/github_orchestrator/review/adapters/records/inbox.py`
- Modify: `src/github_orchestrator/review/application/decide.py`
- Modify: `src/github_orchestrator/review/application/read_model/decisions.py`
- Modify: `src/github_orchestrator/review/adapters/board/routes.py:364-376`
- Modify: `src/github_orchestrator/review/adapters/board/page.py` (the decide dialog around `:444-451`, `DECIDE`, `DECISIONS`, the legend)
- Test: `tests/review/adapters/test_records.py`, `tests/review/application/test_decide.py`, `tests/review/application/test_read_model.py`

**Interfaces:**

- Consumes: `commands.Defer` and the wake constants from Task 4.

- Produces: an intent whose first line reads `defer ci` or `defer pr:87`, with the
  private note as the payload.

- [ ] **Step 1: Write the failing test for the intent format**

```python
def test_a_defer_intent_carries_its_wake_condition_in_the_modifier():
    text = format_intent("defer", payload="blocked", modifier="pr:87")

    assert text == "defer pr:87\nblocked"
    assert parse_intent(text) == Intent(decision="defer", modifier="pr:87",
                                        payload="blocked")


def test_delete_is_still_the_only_modifier_a_resolve_takes():
    assert parse_intent("resolve pr:87") is None
    assert parse_intent("resolve delete").delete_comment is True
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/review/adapters/test_records.py -k modifier -v`
Expected: FAIL, `TypeError: format_intent() got an unexpected keyword argument 'modifier'`

- [ ] **Step 3: Widen the modifier slot**

In `inbox.py`:

```python
DECISIONS = ("approve", "session", "resolve", "retry", "reject", "defer")

DELETE_MODIFIER = "delete"

WAKE_MODIFIERS = ("manual", "ci")

ACTION_MAX_CHARS = 200


def _modifier_allowed(decision: str, modifier: str) -> bool:
    if modifier == "":
        return True
    if decision == "defer":
        return modifier in WAKE_MODIFIERS or modifier.startswith("pr:")
    return modifier == DELETE_MODIFIER


@dataclass(frozen=True)
class Intent:
    decision: str
    delete_comment: bool = False
    payload: str | None = None
    modifier: str = ""


def format_intent(decision: str, payload: str | None = None,
                  delete_comment: bool = False, modifier: str = "") -> str:
    if decision not in DECISIONS:
        raise ValueError(
            f"invalid decision {decision!r}; expected one of {DECISIONS}"
        )
    slot = modifier or (DELETE_MODIFIER if delete_comment else "")
    if not _modifier_allowed(decision, slot):
        raise ValueError(f"invalid modifier {slot!r} for {decision!r}")
    first = f"{decision} {slot}" if slot else decision
    return first if payload is None else f"{first}\n{payload}"


def parse_intent(text: str) -> Intent | None:
    first, separator, payload = text.partition("\n")
    decision, _, modifier = first.strip().partition(" ")
    if decision not in DECISIONS or not _modifier_allowed(decision, modifier):
        return None
    return Intent(
        decision=decision,
        delete_comment=modifier == DELETE_MODIFIER,
        payload=payload if separator else None,
        modifier=modifier,
    )
```

Add `modifier: str` to the `Intent` Protocol in `application/ports.py` so the
application can read it without importing the adapter.

- [ ] **Step 4: Run it and watch it pass**

Run: `uv run pytest tests/review/adapters/test_records.py -k modifier -v`
Expected: PASS

- [ ] **Step 5: Write the failing test for the drain**

```python
def test_a_defer_intent_becomes_a_defer_command(ports):
    command = _command(ports, Intent(decision="defer", modifier="pr:87",
                                     payload="blocked on that"))

    assert command == Defer(wake_on="pr:87", note="blocked on that")


def test_a_defer_intent_with_no_modifier_wakes_by_hand(ports):
    assert _command(ports, Intent(decision="defer")).wake_on == WAKE_MANUAL
```

- [ ] **Step 6: Run it and watch it fail**

Run: `uv run pytest tests/review/application/test_decide.py -k defer_intent -v`
Expected: FAIL, `NotImplementedError: defer`

- [ ] **Step 7: Wire the drain and the table**

In `decide.py`:

```python
        case "defer":
            return Defer(wake_on=intent.modifier or WAKE_MANUAL,
                         note=payload)
```

In `decisions.py`, add `"defer"` to `QUEUED`, `PROPOSED`, `DECLINED`, `FAILED` and
`REMOVED` in `ACTIONS`; add `"defer": "deferring"` to `QUEUED_LABELS`; and:

```python
    "defer": ("parks this comment with nothing posted to GitHub, keeping the "
              "agent's worktree and its proposal, until you bring it back or "
              "the condition you chose is met"),
```

`"defer"` joins `TEXT_TAKING_DECISIONS` (the payload is its private note) but **not**
`DELETE_TAKING_DECISIONS` — parking posts nothing and deletes nothing.

- [ ] **Step 8: Let the route carry a modifier**

In `routes.py`'s decide handler, beside `decision = (params.get("d") or [""])[0]`:

```python
    modifier = (params.get("m") or [""])[0]
    if not _modifier_allowed(decision, modifier):
        return 400, PLAIN, b"invalid modifier"
```

importing `_modifier_allowed` from `inbox`, and pass `modifier=modifier` into the
`queue_intent` call. Guarding here as well as in `format_intent` is what stops a
hand-made request writing an intent the drain then deletes as garbage — silently, per
the "half-written intent reads as no decision" rule.

Its test:

```python
def test_a_wake_condition_a_defer_cannot_take_is_refused(tmp_path):
    status, _, _ = post(tmp_path, "/thread/PRRT_one/decide?d=defer&m=tuesday")

    assert status == 400
```

- [ ] **Step 9: Give the dialog a wake picker**

In `page.py`, beside `#decide-delete-row` at `:449`:

```html
<label id="decide-wake-row" class="dialog-tick" hidden>wake it
<select id="decide-wake">
<option value="manual">when I bring it back</option>
<option value="ci">when this PR's CI passes</option>
<option value="pr">when another PR closes</option>
</select>
<input type="number" id="decide-wake-pr" min="1" placeholder="PR number" hidden>
</label>
```

Add the `defer` entry to `DIALOGS`:

```js
  defer: {
    question: "Park this comment until you want it back?",
    note: "Nothing is posted to GitHub. The agent's worktree and its proposal "
      + "are kept, and anything you write here is a private note on the board.",
    reply: true,
    wake: true,
    submit: () => "defer",
  },
```

In `openDialog`, show the row and reset it:

```js
  document.getElementById("decide-wake-row").hidden = !spec.wake;
  document.getElementById("decide-wake").value = "manual";
  document.getElementById("decide-wake-pr").hidden = true;
  document.getElementById("decide-wake-pr").value = "";
```

Reveal the number input when `pr` is chosen, and build the modifier at submit:

```js
document.getElementById("decide-wake").addEventListener("change", (e) => {
  document.getElementById("decide-wake-pr").hidden = e.target.value !== "pr";
});
function wakeModifier() {
  const row = document.getElementById("decide-wake-row");
  if (row.hidden) return "";
  const choice = document.getElementById("decide-wake").value;
  if (choice !== "pr") return choice;
  const number = document.getElementById("decide-wake-pr").value.trim();
  return number ? "pr:" + number : "manual";
}
```

and send it as `m` wherever the decide POST is built.

Add `f: "defer"` to `DECIDE`, `"defer"` to `DECISIONS`, and the legend row
`<dt>f</dt><dd>defer the open comment (asks when to wake it)</dd>`.

Its harness test:

```python
def test_choosing_another_pr_builds_a_numbered_wake_condition(tmp_path):
    built = run_page(tmp_path, """
openDialog("defer", null, "");
document.getElementById("decide-wake").value = "pr";
document.getElementById("decide-wake-pr").value = "87";
report(wakeModifier());
""")

    assert built == "pr:87"
```

- [ ] **Step 10: Re-record and run everything**

Run: `make record && uv run pytest tests/ -n 4`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add -A src/github_orchestrator/review tests/review tests/recorded_subprocesses.json
git commit -m "GITHUB-ORCHESTRATOR: offer defer on the board with its wake picker"
```

______________________________________________________________________

### Task 6: The ways back — Unpark

The spec's bar offers a way back on waiting, deferred, rejected and resolved, labelled
per state: "Bring back to Ready", "Undefer", "Reconsider", "Un-resolve". One command
serves all four. Per the amendment, coming back from `rejected` re-queues the agent
because the workspace is gone; from the other three the fix is untouched.

The domain already has a `Reopen` command — that is the poller's, carrying a reviewer's
comments. This one is the operator's and is named `Unpark`.

**Files:**

- Modify: `src/github_orchestrator/review/domain/commands.py`
- Modify: `src/github_orchestrator/review/domain/apply.py`
- Modify: `src/github_orchestrator/review/application/read_model/decisions.py`
- Modify: `src/github_orchestrator/review/application/decide.py`
- Modify: `src/github_orchestrator/review/adapters/records/inbox.py:3`
- Modify: `src/github_orchestrator/review/adapters/board/page.py`
- Test: `tests/review/domain/test_conversation.py`, `tests/review/application/test_read_model.py`

**Interfaces:**

- Consumes: the states from Tasks 2 and 4.

- Produces: `commands.Unpark(at: str)`; `ACTIONS` entries for the words `WAITING`,
  `DEFERRED`, `REJECTED` and `RESOLVED`.

- [ ] **Step 1: Write the failing test**

```python
def test_unparking_a_deferred_conversation_restores_its_proposal():
    conversation = replace(_created().conversation, state=DEFERRED,
                           wake_on=WAKE_CI, defer_note="later",
                           fix=Fix(state=PROPOSED, thread_sha="abc123",
                                   workspace="wt|branch"))

    outcome = apply(conversation, Unpark(at="2026-09-15T10:00:00Z"))

    assert isinstance(outcome, Accepted)
    assert outcome.conversation.state == OPEN
    assert outcome.conversation.fix.state == PROPOSED
    assert outcome.conversation.fix.thread_sha == "abc123"
    assert outcome.conversation.wake_on is None
    assert outcome.conversation.decidable_at == "2026-09-15T10:00:00Z"
    assert outcome.effects == ()


def test_unparking_a_rejected_conversation_requeues_the_agent():
    conversation = replace(_created().conversation, state=REJECTED,
                           fix=Fix(state=PROPOSED, thread_sha="abc123"))

    outcome = apply(conversation, Unpark(at="2026-09-15T10:00:00Z"))

    assert isinstance(outcome, Accepted)
    assert outcome.conversation.state == OPEN
    assert outcome.conversation.fix.state == QUEUED
    assert outcome.conversation.fix.attempts == 0
    assert outcome.conversation.fix.thread_sha is None
    assert CutWorkspace() in outcome.effects


def test_unparking_an_open_conversation_is_refused():
    outcome = apply(_created().conversation, Unpark(at="2026-09-15T10:00:00Z"))

    assert isinstance(outcome, Refused)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/review/domain/test_conversation.py -k unpark -v`
Expected: FAIL, `ImportError: cannot import name 'Unpark'`

- [ ] **Step 3: Add the command and the transition**

In `commands.py`:

```python
@dataclass(frozen=True)
class Unpark:
    at: str
```

In `apply.py`:

```python
PARKED = (WAITING_ON_REVIEWER, DEFERRED, REJECTED, RESOLVED)


def _unpark(conversation: Conversation, command) -> Accepted | Refused:
    if conversation.state not in PARKED:
        return Refused(conversation,
                       f"a {conversation.state} conversation is not parked")
    back = replace(conversation, state=OPEN, wake_on=None, defer_note="",
                   decidable_at=command.at)
    if conversation.state != REJECTED:
        return Accepted(back)
    requeued = _with_fix(back, state=QUEUED, attempts=0, started_at=None,
                         steps=frozenset(), thread_sha=None, workspace=None,
                         landed_base=None, landed_sha=None, push_error=None,
                         reply_error=None, decision_error=None,
                         reply_note=None)
    return Accepted(requeued, (CutWorkspace(), WriteGist(source=GIST_THREAD)))
```

Import `WAITING_ON_REVIEWER`, `DEFERRED` and `RESOLVED` in `apply.py` if absent.
Dispatch it beside the other verbs and add `Unpark` to `CLEARS_THE_REOPENED_MARK`.

- [ ] **Step 4: Run it and watch it pass**

Run: `uv run pytest tests/review/domain/test_conversation.py -k unpark -v`
Expected: PASS

- [ ] **Step 5: Write the failing test for the labels**

```python
@pytest.mark.parametrize("word, label", [
    (groups.WAITING, "bring back to Ready"),
    (groups.DEFERRED, "undefer"),
    (groups.REJECTED, "reconsider"),
    (groups.RESOLVED, "un-resolve"),
])
def test_each_parked_word_names_its_own_way_back(word, label):
    assert LABELS[(word, "unpark")] == label
    assert "unpark" in ACTIONS[word]
```

- [ ] **Step 6: Run it and watch it fail**

Run: `uv run pytest tests/review/application/test_read_model.py -k way_back -v`
Expected: FAIL, `KeyError: ('waiting', 'unpark')`

- [ ] **Step 7: Extend the tables and the drain**

In `decisions.py` add to `ACTIONS`:

```python
    WAITING: ("unpark", "resolve", "reject"),
    DEFERRED: ("unpark", "resolve", "reject"),
    REJECTED: ("unpark", "resolve"),
    RESOLVED: ("unpark",),
```

importing `WAITING`, `DEFERRED`, `REJECTED` and `RESOLVED` from `groups`. Add the four
`LABELS` rows above, `"unpark": "bringing it back"` to `QUEUED_LABELS`, and:

```python
    "unpark": ("brings this conversation back to Ready; from rejected it also "
               "re-runs the agent, because rejecting dropped the proposal"),
```

`"unpark"` takes neither text nor delete. In `inbox.py` add `"unpark"` to
`DECISIONS`; in `decide.py`:

```python
        case "unpark":
            return Unpark(at=ports.clock.now())
```

Note `decisions_for` must not strip `unpark` when Claude is disabled — bringing a
conversation back is git and record work, and the queued run simply waits.

- [ ] **Step 8: Run it and watch it pass**

Run: `uv run pytest tests/review/application/test_read_model.py -k way_back -v`
Expected: PASS

- [ ] **Step 9: Teach the page the decision**

`u: "unpark"` in `DECIDE`, `"unpark"` in `DECISIONS`, and the legend row
`<dt>u</dt><dd>bring the open comment back to Ready</dd>`.

- [ ] **Step 10: Re-record and run everything**

Run: `make record && uv run pytest tests/ -n 4`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add -A src/github_orchestrator/review tests/review tests/recorded_subprocesses.json
git commit -m "GITHUB-ORCHESTRATOR: give every parked conversation its way back"
```

______________________________________________________________________

### Task 7: The wake checks in tick

Spec note 14: the wake conditions are checked by the manager, not raised by the
watcher. The watcher's CI event fires only on a change and knows nothing about
conversations; the manager loop already reads the state snapshot each pass.

The application may not read the snapshot file itself — that would import
`common/paths`. It goes through a new port.

**Files:**

- Modify: `src/github_orchestrator/review/application/ports.py`
- Create: `src/github_orchestrator/review/adapters/pull_requests.py`
- Modify: `src/github_orchestrator/review/compose.py`
- Modify: `src/github_orchestrator/review/application/tick.py`
- Modify: `src/github_orchestrator/review/domain/commands.py`, `apply.py`
- Test: `tests/review/application/test_tick.py`, `tests/review/adapters/test_pull_requests.py`

**Interfaces:**

- Consumes: `DEFERRED`, `wake_on`, `WAKE_CI`, `WAKE_PR_PREFIX` from Task 4.

- Produces: `Ports.pull_requests` with `ci_green() -> bool | None` and
  `is_closed(number: int) -> bool | None`; `commands.Wake(reason: str, at: str)`.

- [ ] **Step 1: Write the failing domain test**

```python
def test_waking_returns_a_deferred_conversation_to_open_with_a_reason():
    conversation = replace(_created().conversation, state=DEFERRED,
                           wake_on=WAKE_CI, fix=Fix(state=PROPOSED))

    outcome = apply(conversation, Wake(reason="this PR's CI passed",
                                       at="2026-09-15T10:00:00Z"))

    assert isinstance(outcome, Accepted)
    assert outcome.conversation.state == OPEN
    assert outcome.conversation.wake_on is None
    assert outcome.conversation.decidable_at == "2026-09-15T10:00:00Z"
    assert outcome.conversation.fix.reply_note == "woken: this PR's CI passed"
    assert outcome.conversation.reopened is False


def test_waking_anything_but_a_deferred_conversation_is_refused():
    outcome = apply(_created().conversation,
                    Wake(reason="x", at="2026-09-15T10:00:00Z"))

    assert isinstance(outcome, Refused)
```

Spec note 8: a woken conversation returns to `open`, **not** to the top of Ready — it
is not a reviewer reply, so `reopened` stays false.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/review/domain/test_conversation.py -k waking -v`
Expected: FAIL, `ImportError: cannot import name 'Wake'`

- [ ] **Step 3: Add the command and the transition**

```python
@dataclass(frozen=True)
class Wake:
    reason: str
    at: str
```

```python
def _wake(conversation: Conversation, command) -> Accepted | Refused:
    if conversation.state != DEFERRED:
        return Refused(conversation,
                       f"a {conversation.state} conversation is not deferred")
    woken = replace(conversation, state=OPEN, wake_on=None, defer_note="",
                    decidable_at=command.at)
    return Accepted(_with_fix(woken,
                              reply_note=f"woken: {command.reason}"))
```

Dispatch it. `Wake` is **not** in `CLEARS_THE_REOPENED_MARK`: nobody spoke.

- [ ] **Step 4: Run it and watch it pass**

Run: `uv run pytest tests/review/domain/test_conversation.py -k waking -v`
Expected: PASS

- [ ] **Step 5: Write the failing test for the port and the pass**

In `tests/review/application/test_tick.py`:

```python
def test_a_ci_deferral_wakes_when_the_snapshot_goes_green(tmp_path, ports):
    ports.records.save(replace(_conversation(), state=DEFERRED,
                               wake_on=WAKE_CI))
    ports.pull_requests.green = True

    Runs().pump_and_schedule("o/r", 1, ports)

    assert ports.records.get("PRRT_one").state == OPEN


def test_a_ci_deferral_stays_parked_while_ci_is_red(tmp_path, ports):
    ports.records.save(replace(_conversation(), state=DEFERRED,
                               wake_on=WAKE_CI))
    ports.pull_requests.green = False

    Runs().pump_and_schedule("o/r", 1, ports)

    assert ports.records.get("PRRT_one").state == DEFERRED


def test_a_pr_deferral_wakes_when_that_pr_closes(tmp_path, ports):
    ports.records.save(replace(_conversation(), state=DEFERRED,
                               wake_on="pr:87"))
    ports.pull_requests.closed = {87: True}

    Runs().pump_and_schedule("o/r", 1, ports)

    assert ports.records.get("PRRT_one").state == OPEN


def test_an_unknown_ci_state_leaves_the_deferral_alone(tmp_path, ports):
    ports.records.save(replace(_conversation(), state=DEFERRED,
                               wake_on=WAKE_CI))
    ports.pull_requests.green = None

    Runs().pump_and_schedule("o/r", 1, ports)

    assert ports.records.get("PRRT_one").state == DEFERRED
```

A `None` answer means "could not tell" and must never wake anything — a failed `gh`
call would otherwise unpark every deferral on the board.

- [ ] **Step 6: Run it and watch it fail**

Run: `uv run pytest tests/review/application/test_tick.py -k deferral -v`
Expected: FAIL, `AttributeError: 'Ports' object has no attribute 'pull_requests'`

- [ ] **Step 7: Add the port**

In `ports.py`:

```python
class PullRequests(Protocol):
    def ci_green(self) -> bool | None: ...

    def is_closed(self, number: int) -> bool | None: ...
```

and `pull_requests: PullRequests` on the `Ports` dataclass.

- [ ] **Step 8: Add the wake pass to tick**

In `tick.py`, called from `pump_and_schedule` before `_pump`:

```python
    def _wake(self, repo: str, pr: int, ports: Ports) -> None:
        wanted = [c for c in ports.records.list()
                  if c.state == DEFERRED and c.wake_on
                  and c.wake_on != WAKE_MANUAL]
        if not wanted:
            return
        for conversation in wanted:
            reason = _wake_reason(conversation.wake_on, ports)
            if reason is not None:
                self._apply(ports, conversation.key,
                            Wake(reason=reason, at=ports.clock.now()))


def _wake_reason(wake_on: str, ports: Ports) -> str | None:
    if wake_on == WAKE_CI:
        return "this PR's CI passed" if ports.pull_requests.ci_green() else None
    if wake_on.startswith(WAKE_PR_PREFIX):
        number = wake_on[len(WAKE_PR_PREFIX):]
        if not number.isdigit():
            return None
        closed = ports.pull_requests.is_closed(int(number))
        return f"PR #{number} closed" if closed else None
    return None
```

The `if not wanted: return` guard is what keeps the common case — no deferrals — from
costing a `gh` call every pass.

- [ ] **Step 9: Run it and watch it pass**

Run: `uv run pytest tests/review/application/test_tick.py -k deferral -v`
Expected: PASS

- [ ] **Step 10: Write the adapter and its test**

`adapters/pull_requests.py` reads this PR's CI off the watcher's snapshot through
`common.paths.state_file` and asks `gh` about another PR:

```python
class PullRequests:
    def __init__(self, repo: str, pr: int, account: str) -> None:
        self._repo = repo
        self._pr = pr
        self._account = account

    def ci_green(self) -> bool | None:
        snapshot = _read_snapshot(self._repo, self._pr)
        if snapshot is None:
            return None
        status = snapshot.get("ci_status")
        return None if status is None else status == "success"

    def is_closed(self, number: int) -> bool | None:
        try:
            answer = gh_api(f"repos/{self._repo}/pulls/{number}",
                            account=self._account)
        except GhError:
            return None
        return answer.get("state") == "closed"
```

`ci_status` is the key the watcher writes, one of `"success"`, `"failure"` or
`"pending"` (`github_pr_watcher/poller.py:238` and the computation at `:240-246`).
Read it, never the `"checks"` list beside it — that is the per-run detail, and
recomputing green from it would duplicate `_CI_SUCCESS_CONCLUSIONS`.
`_read_snapshot` builds its path with `common.paths.state_file` and returns `None`
for a missing or unparseable file.

Test it against a written snapshot file and a recorded `gh` call:

```python
def test_a_green_snapshot_reads_as_green(tmp_path, monkeypatch):
    _write_snapshot(tmp_path, {"ci_status": "success"})

    assert PullRequests("o/r", 1, "vector67").ci_green() is True


def test_a_pending_snapshot_is_not_green(tmp_path, monkeypatch):
    _write_snapshot(tmp_path, {"ci_status": "pending"})

    assert PullRequests("o/r", 1, "vector67").ci_green() is False


def test_a_missing_snapshot_answers_it_cannot_tell(tmp_path, monkeypatch):
    assert PullRequests("o/r", 1, "vector67").ci_green() is None
```

- [ ] **Step 11: Compose it**

In `compose.py`, build a `PullRequests` from the repo, PR and `gh_account` and pass it
into the `Ports` bundle. `tests/review/test_layering.py` must still pass — the adapter
may import `common`, the application may not.

- [ ] **Step 12: Run everything**

Run: `make record && uv run pytest tests/ -n 4`
Expected: PASS

- [ ] **Step 13: Commit**

```bash
git add -A src/github_orchestrator/review tests/review tests/recorded_subprocesses.json
git commit -m "GITHUB-ORCHESTRATOR: wake a deferred conversation when its condition is met"
```

______________________________________________________________________

### Task 8: Next ready and Reply affordances

Two items on the bar that are not decisions: they never POST. `Next ready →` moves the
cursor to the first row of the ready group; `Reply to N` focuses the composer the panel
already renders.

**Files:**

- Modify: `src/github_orchestrator/review/application/read_model/panel.py`
- Modify: `src/github_orchestrator/review/adapters/board/render.py`
- Modify: `src/github_orchestrator/review/adapters/board/page.py`
- Test: `tests/review/adapters/board/test_board_panel.py`, `tests/review/adapters/board/test_page_script.py`

**Interfaces:**

- Consumes: `Action.weight` from Task 1; `READY_GROUP` and `GROUP_ORDER`, already in
  the page script at `page.py:470-473`.

- Produces: `Affordance(kind: str, label: str, weight: str)` and
  `PanelView.affordances: tuple[Affordance, ...]`; buttons carrying
  `data-affordance="next-ready"` and `data-affordance="reply"`.

- [ ] **Step 1: Write the failing test**

```python
def test_a_parked_panel_offers_next_ready(tmp_path):
    view = panel_for(tmp_path, make_record(status=DEFERRED))

    kinds = [affordance.kind for affordance in view.affordances]
    assert "next-ready" in kinds


def test_a_ready_panel_does_not_offer_next_ready(tmp_path):
    view = panel_for(tmp_path, make_record(status=READY))

    kinds = [affordance.kind for affordance in view.affordances]
    assert "next-ready" not in kinds


def test_a_panel_with_a_composer_offers_a_reply_affordance(tmp_path):
    view = panel_for(tmp_path, make_record(status=WORKING, author="anna"))

    reply = next(a for a in view.affordances if a.kind == "reply")
    assert reply.label == "Reply to anna"
    assert reply.weight == "secondary"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/review/adapters/board/test_board_panel.py -k affordance -v`
Expected: FAIL, `AttributeError: 'PanelView' object has no attribute 'affordances'`

- [ ] **Step 3: Add them to the read model**

In `panel.py`:

```python
@dataclass(frozen=True)
class Affordance:
    kind: str
    label: str
    weight: str


def affordances_for(conversation: Conversation, author: str,
                    has_composer: bool) -> tuple[Affordance, ...]:
    offered = []
    if group_of(conversation) != READY:
        offered.append(Affordance("next-ready", "Next ready →", "primary"))
    if has_composer and author:
        offered.append(Affordance("reply", f"Reply to {author}", "secondary"))
    return tuple(offered)
```

Add `affordances: tuple[Affordance, ...]` to `PanelView` and fill it where `actions=`
is filled, passing `view.reply is not None` for `has_composer`.

- [ ] **Step 4: Run it and watch it pass**

Run: `uv run pytest tests/review/adapters/board/test_board_panel.py -k affordance -v`
Expected: PASS

- [ ] **Step 5: Render them**

In `render.py`, a plain button with no hx attributes, placed before the ghost zone so
the primary affordance leads the bar:

```python
def _affordance_button(affordance: Affordance) -> str:
    return (
        f'<button type="button" class="affordance {affordance.weight}" '
        f'data-affordance="{html.escape(affordance.kind, quote=True)}">'
        f"{html.escape(affordance.label)}</button>"
    )
```

In `_action_footer`, render the affordances into the left zone ahead of the decision
buttons.

- [ ] **Step 6: Write the failing page-harness scenarios**

In `tests/review/adapters/board/test_board_page.py`, beside
`test_j_and_k_walk_the_rows_and_step_over_the_headings`, which is the model for these:

```python
def test_n_opens_the_first_row_that_is_ready_for_you(tmp_path):
    payload = rows_payload(("a", "done", "9"), ("b", "ready", "8"),
                           ("c", "ready", "7"))

    landed = run_page(tmp_path, f"""
reconcile({payload});
press("n");
report(selected);
""")

    assert landed == "b"


def test_the_next_ready_button_opens_the_first_ready_row(tmp_path):
    payload = rows_payload(("a", "done", "9"), ("b", "ready", "8"))

    landed = run_page(tmp_path, f"""
reconcile({payload});
const body = document.createElement("section");
body.id = "panel-body";
const bar = document.createElement("button");
bar.className = "affordance primary";
bar.dataset.affordance = "next-ready";
body.appendChild(bar);
panelContent().appendChild(body);
bar.click();
report(selected);
""")

    assert landed == "b"


def test_the_reply_button_focuses_the_composer(tmp_path):
    focused = run_page(tmp_path, """
const body = document.createElement("section");
body.id = "panel-body";
const box = document.createElement("textarea");
box.id = "reply-box";
const bar = document.createElement("button");
bar.className = "affordance secondary";
bar.dataset.affordance = "reply";
body.appendChild(box);
body.appendChild(bar);
panelContent().appendChild(body);
bar.click();
report(document.activeElement.id);
""")

    assert focused == "reply-box"
```

If `page_harness.js` has no `focus()` on its stub element, add one that records
`document.activeElement` — the stub DOM is ours to extend, and a focus call the
harness swallows would make the third test pass for the wrong reason.

- [ ] **Step 7: Run them and watch them fail**

Run: `uv run pytest tests/review/adapters/board/test_board_page.py -k "next_ready or reply_button" -v`
Expected: FAIL — `press("n")` does nothing and `selected` stays `"a"`.

- [ ] **Step 8: Handle them in the page script**

Delegate from the existing `#panel-body` click listener, before the decision sniffing
at `:1012` so an affordance is never read as a decision:

```js
const affordance = e.target.closest && e.target.closest("button.affordance");
if (affordance) {
  if (affordance.dataset.affordance === "reply") {
    const box = document.getElementById("reply-box");
    if (box) box.focus();
  } else {
    openFirstReadyRow();
  }
  return;
}
```

`openFirstReadyRow` walks `#rows` for the first `li[role="option"]` after the
`READY_GROUP` heading and opens it, reusing whatever `stepRow` already calls to open a
row. Bind `n` to it in the keydown handler beside `j` and `k`, and add the legend row
`<dt>n</dt><dd>open the next comment that is ready for you</dd>`.

- [ ] **Step 9: Run them and watch them pass**

Run: `uv run pytest tests/review/adapters/board/test_board_page.py -k "next_ready or reply_button" -v`
Expected: PASS

- [ ] **Step 10: Re-record and run everything**

Run: `make record && uv run pytest tests/ -n 4 --durations=20`
Expected: PASS, and no new test over 0.2s.

- [ ] **Step 11: Commit**

```bash
git add -A src/github_orchestrator/review tests/review tests/recorded_subprocesses.json
git commit -m "GITHUB-ORCHESTRATOR: put next ready and reply on the bottom bar"
```

______________________________________________________________________

### Task 9: The composer parks a ready conversation in Waiting on reviewer

Spec line 351: posting a reply "is the one command that parks an `open` conversation in
Waiting on reviewer." Without this nothing ever reaches `waiting_on_reviewer`, and the
way back Task 6 offers on that word is dead code.

Spec line 181: "On a row in Ready for you, posting parks the conversation in Waiting on
reviewer once the reply is on GitHub, with the fix untouched. … Everywhere else it
posts and the row does not move."

The domain cannot ask `group_of` whether a row is in Ready for you — that lives in the
application layer. It needs the same rule stated in its own terms.

**Files:**

- Modify: `src/github_orchestrator/review/domain/apply.py:540-552` (`_reply_posted`)
- Modify: `src/github_orchestrator/review/adapters/board/render.py:247-265` (`_reply_box`, the line under the box)
- Test: `tests/review/domain/test_conversation.py`

**Interfaces:**

- Consumes: `WAITING_ON_REVIEWER`; `Unpark` from Task 6 is its way back.

- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing test**

```python
def test_replying_on_a_ready_conversation_parks_it_on_the_reviewer():
    conversation = replace(_created().conversation,
                           fix=Fix(state=PROPOSED, thread_sha="abc123"))

    outcome = apply(conversation, ReplyPosted(comment=Comment(id=9, body="ok")))

    assert isinstance(outcome, Accepted)
    assert outcome.conversation.state == WAITING_ON_REVIEWER
    assert outcome.conversation.fix.state == PROPOSED
    assert outcome.conversation.fix.thread_sha == "abc123"


def test_replying_while_the_agent_works_moves_nothing():
    conversation = replace(_created().conversation, fix=Fix(state=RUNNING))

    outcome = apply(conversation, ReplyPosted(comment=Comment(id=9, body="ok")))

    assert isinstance(outcome, Accepted)
    assert outcome.conversation.state == OPEN


def test_replying_on_a_landed_conversation_moves_nothing():
    conversation = replace(_created().conversation, fix=Fix(state=LANDED))

    outcome = apply(conversation, ReplyPosted(comment=Comment(id=9, body="ok")))

    assert isinstance(outcome, Accepted)
    assert outcome.conversation.state == OPEN


def test_replying_on_a_reopened_conversation_parks_it():
    conversation = replace(_created().conversation, reopened=True,
                           fix=Fix(state=RUNNING))

    outcome = apply(conversation, ReplyPosted(comment=Comment(id=9, body="ok")))

    assert isinstance(outcome, Accepted)
    assert outcome.conversation.state == WAITING_ON_REVIEWER
```

The reopened case is the subtle one: a reopened conversation sits in Ready for you even
while its fix is `running`, so replying to it parks it like any other ready row.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/review/domain/test_conversation.py -k "parks_it or moves_nothing" -v`
Expected: FAIL on the first and last — `assert 'open' == 'waiting_on_reviewer'`. The two
`moves_nothing` tests pass already; they are there to pin what must not change.

- [ ] **Step 3: Park on reply**

In `apply.py`:

```python
def _ready_for_you(conversation: Conversation) -> bool:
    if conversation.state != OPEN:
        return False
    if conversation.reopened:
        return True
    return conversation.fix.state in (PROPOSED, DECLINED, FAILED)


def _reply_posted(conversation: Conversation, command) -> Accepted:
    replied = _with_transcript(conversation, command.comment,
                               command.posted_key)
    if command.comment is not None and command.comment.id is not None:
        replied = replace(
            replied,
            panel_reply_ids=replied.panel_reply_ids + (command.comment.id,))
    if _ready_for_you(conversation):
        replied = replace(replied, state=WAITING_ON_REVIEWER)
    return Accepted(_with_fix(replied, reply_error=None))
```

`_ready_for_you` reads the conversation as it arrived, not `replied`, because
`ReplyPosted` is in `CLEARS_THE_REOPENED_MARK` and the mark is what makes a reopened
row ready.

Import `WAITING_ON_REVIEWER` in `apply.py` if it is not already there.

- [ ] **Step 4: Run them and watch them pass**

Run: `uv run pytest tests/review/domain/test_conversation.py -k "parks_it or moves_nothing" -v`
Expected: PASS

- [ ] **Step 5: Say so under the composer**

`_reply_box` already writes "Posts on this thread." or "Posts on the PR, quoting this
comment." Spec line 180 wants the line to say what posting does to the row. Add a
`parks: bool` to `ReplyBox` in the read model, set from the same rule, and append
" Parks this on Waiting on reviewer." when it is true.

- [ ] **Step 6: Write and run its test**

```python
def test_the_composer_warns_a_ready_row_that_posting_parks_it(tmp_path):
    panel = panel_html(tmp_path, make_record(status=READY))

    assert "Parks this on Waiting on reviewer." in panel


def test_the_composer_says_nothing_about_parking_on_a_working_row(tmp_path):
    panel = panel_html(tmp_path, make_record(status=WORKING))

    assert "Parks this on" not in panel
```

Run: `uv run pytest tests/review/adapters/board/test_board_panel.py -k composer_warns -v`
Expected: PASS after Step 5, FAIL before it.

- [ ] **Step 7: Run the full suite**

Run: `make record && uv run pytest tests/ -n 4`
Expected: PASS. Several existing panel tests reply on a ready record and assert the row
does not move; those expectations are now wrong and the spec says so — change them, and
check each one against spec line 181 before you do.

- [ ] **Step 8: Commit**

```bash
git add -A src/github_orchestrator/review tests/review tests/recorded_subprocesses.json
git commit -m "GITHUB-ORCHESTRATOR: park a ready conversation on the reviewer when you reply"
```

______________________________________________________________________

### Task 10: The preview, the docs and the whole suite

`board/preview.py` already seeds one conversation per group, so the new bars are
viewable without a real PR. Make sure the seeds exercise the new verbs, then bring
`CLAUDE.md` in step.

**Files:**

- Modify: `src/github_orchestrator/review/adapters/board/preview.py:225-235`

- Modify: `CLAUDE.md`

- Test: the whole suite

- [ ] **Step 1: Give the preview a deferral with each wake condition**

The `WAITING_ON_REVIEWER`, `DEFERRED` and `REJECTED` seeds already exist at
`:227-233`. Give the deferred one a `wake_on="pr:87"` and a `defer_note`, so the
panel's parked kicker and its way back are both visible.

- [ ] **Step 2: Look at it**

Run: `uv run python -m github_orchestrator.review.adapters.board.preview`
Open the URL it prints and check each group's bar in both themes: the ghost zone sits
right, the primary leads, `Next ready →` appears on every parked row and not on ready
ones, and nothing wraps to a second line at 1280px.

- [ ] **Step 3: Update CLAUDE.md**

In the domain section, record that Reject drops the workspace and Unpark from rejected
re-queues; in the adapters table, add `pull_requests.py`. Keep both to a line or two —
the reasoning belongs in the spec and the commit messages.

- [ ] **Step 4: Run the full suite twice**

Run: `uv run pytest tests/ -n 4` then `uv run pytest tests/ --no-replay -n 4`
Expected: PASS both. The second spawns every subprocess for real and is the one that
catches a recording that agrees with a bug.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "GITHUB-ORCHESTRATOR: seed the preview with a deferral and document the new verbs"
```

______________________________________________________________________

## Out of scope

**Revert.** Spec line 345 already says "Revert is not built", and it stays unbuilt
here. It is the only verb that would retract something already pushed to the PR
branch, and `TITLES["approve"]` currently promises the opposite ("public, and the
board has no way to undo it"). It needs its own brainstorm.

**Records for conversations first seen resolved.** The last item in phase 6's own
sentence. `adapters/poller.py:69` filters a resolved review thread out of the fetch
entirely, so a conversation the reviewer had already resolved before the board saw it
never gets a record. That is a poller change, not a bar change, and it sits outside the
scope chosen for this plan. Phase 6 is not finished until it is done.

**A separate "Open a session" link.** The spec's bar lists "Send back for rework" as a
button and "Open a session" as a ghost link, but the code has only one verb —
`session`, labelled "send back for rework", which opens a tmux session. Splitting them
needs the autonomous `rework` run kind from phase 5, which is only half-built: the run
kind exists in the domain, no operator verb produces it. Left alone.
