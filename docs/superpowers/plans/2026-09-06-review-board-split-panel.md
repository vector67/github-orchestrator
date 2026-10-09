# Review board split panel implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the review board into a two-pane page: short reorderable rows on the left, one comment open in a panel on the right, with a Haiku-written gist per row and a status for comments deleted on GitHub.

**Architecture:** The server keeps rendering HTML for anything a reviewer wrote (rows, the panel) but hands the client ordering metadata as JSON (`/rows`), and the inline script owns the order, a pointer-hold that defers moves, and the panel's lifecycle. A gist is generated at candidate creation through a small `claude --print` spawn. A deleted comment is detected on panel open and recorded as a new `removed` status or a `comment_deleted` flag.

**Tech Stack:** Python 3 stdlib HTTP server, vendored htmx for the panel and POSTs, plain `fetch()` for the row poll, no build step. pytest with recorded subprocesses; two node tests for the script.

**Spec:** `docs/superpowers/specs/2026-09-06-review-board-split-panel-design.md`

## Global constraints

- Commit subjects are `GITHUB-ORCHESTRATOR: <lowercase imperative>`. Never on `main`. No co-author trailer. Branch is `feat/board-split-panel`.
- TDD: write the failing test, run it, watch it fail, then the minimal implementation. Run the full suite after every task: `uv run pytest tests/ -n 4 -q`. Never `-n auto`.
- No code comments. Names and structure explain the code.
- Source files (`.py`, `.js`) are opened with `ReadAST` then `Read` with a range; never `cat`/`sed -n` on them.
- Anything GitHub wrote is escaped with `html.escape` before it reaches markup. The client never builds markup from reviewer text.
- The suite never spawns `claude` or `gh`. Stub `subprocess.run` in the module under test, or the `gh_api` name where the caller imports it.
- The board's two node tests (`node --check` and the stub-DOM run) keep `@pytest.mark.no_replay`.
- New tests that spawn git run live first (`--no-replay`), then `make record`, and `tests/recorded_subprocesses.json` is committed with the change.
- Every status-keyed table must handle `removed`; `_STRIP_CLASSES` is indexed with `[status]`.
- Prose in docs follows the unslop rules: no em dashes, sentence-case headings, plain words.

## File structure

New:

- `src/github_orchestrator/common/claude_env.py`: `claude_env()`, the one env scrub.
- `src/github_orchestrator/common/summarize.py`: `fallback_summary`, `summarize_comment`, `SUMMARY_WORKERS`, `SUMMARY_MAX_CHARS`, `SUMMARY_TIMEOUT`.
- `src/github_orchestrator/github_pr_agent_manager/presence.py`: `comment_exists`, `refresh_presence`, `note_absence`, `checks_presence`.
- `src/github_orchestrator/github_pr_agent_manager/candidate_repair.py`: `rebuild_candidate`, `RepairUnavailable`.
- `tests/common/test_claude_env.py`, `tests/common/test_summarize.py`, `tests/github_pr_agent_manager/test_presence.py`, `tests/github_pr_agent_manager/test_candidate_repair.py`.

Modified:

- `common/config.py`: `summary_model` field, `SUMMARY_MODEL` constant. `config.toml.example`: its entry.
- `common/candidates.py`: `REMOVED`, transitions, `set_fields`, sort with missing `created_at` last.
- `common/candidate_git.py`: worktree lock, `summary_model` on `open_candidate`, gist write.
- `github_pr_agent_manager/claude_run.py`: uses `claude_env()`.
- `github_pr_agent_manager/candidate_dispatch.py`: pooled `materialize_candidates` taking `summary_model`.
- `github_pr_agent_manager/handlers.py`: passes `SUMMARY_MODEL`.
- `github_pr_agent_manager/candidate_land.py`: `_approve` and `_closing_reply` honour `comment_deleted`.
- `github_pr_agent_manager/review_board.py`: `band_of`, `sort_key`, `render_row`, `row_payload`, `render_rows`, `render_panel`, `panel_state`, `/rows`, `/panel/<id>`, `/panel/<id>/state`, POST returns row JSON, new `_PAGE`, retirements.
- `cli/__main__.py`: `cmd_candidate_open` passes the model and says it is waiting.
- `CLAUDE.md`, `README.md`: review board sections.
- Tests beside each of those.

______________________________________________________________________

### Task 1: one env scrub for every claude spawn

**Files:**

- Create: `src/github_orchestrator/common/claude_env.py`
- Modify: `src/github_orchestrator/github_pr_agent_manager/claude_run.py:228`
- Test: `tests/common/test_claude_env.py`

**Interfaces:**

- Produces: `claude_env() -> dict[str, str]`, the process environment without `ANTHROPIC_API_KEY`.

- [ ] **Step 1: Write the failing test**

```python
from github_orchestrator.common.claude_env import claude_env


def test_claude_env_drops_the_console_key_and_keeps_the_rest(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("KEEP_ME", "1")
    env = claude_env()
    assert "ANTHROPIC_API_KEY" not in env
    assert env["KEEP_ME"] == "1"


def test_claude_env_is_a_copy_not_the_live_environ(monkeypatch):
    monkeypatch.setenv("KEEP_ME", "1")
    env = claude_env()
    env["KEEP_ME"] = "2"
    import os
    assert os.environ["KEEP_ME"] == "1"
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/common/test_claude_env.py -q`
Expected: `ModuleNotFoundError: github_orchestrator.common.claude_env`

- [ ] **Step 3: Write the module and use it in `build_claude_run`**

`src/github_orchestrator/common/claude_env.py`:

```python
import os


def claude_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
```

In `claude_run.py`, add `from github_orchestrator.common.claude_env import claude_env` to the imports and replace line 228 with:

```python
    env = claude_env()
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/common/test_claude_env.py tests/github_pr_agent_manager/test_claude_run.py -q`
Expected: all pass; `test_build_claude_run_invokes_claude_with_expected_argv` still asserts the key is absent.

- [ ] **Step 5: Full suite, then commit**

Run: `uv run pytest tests/ -n 4 -q`

```bash
git add src/github_orchestrator/common/claude_env.py src/github_orchestrator/github_pr_agent_manager/claude_run.py tests/common/test_claude_env.py
git commit -m "GITHUB-ORCHESTRATOR: share the claude env scrub through one function"
```

______________________________________________________________________

### Task 2: the `summary_model` config key

**Files:**

- Modify: `src/github_orchestrator/common/config.py:71` (dataclass) and `:170` (constants)
- Modify: `config.toml.example` (after the `claude_model` block)
- Test: `tests/common/test_config.py`

**Interfaces:**

- Produces: `OrchestratorConfig.summary_model: str = "haiku"`; module constant `SUMMARY_MODEL`.

- [ ] **Step 1: Write the failing test**

Add to `tests/common/test_config.py`, using whatever valid-config helper the file already has for the three required keys (look for the fixture the `claude_model` test uses and reuse it; if none, the minimal file is below):

```python
VALID_KEYS = (
    'gh_account = "someone"\n'
    'watch_repo = "owner/name"\n'
    'local_path = "/tmp/checkout"\n'
)


def test_summary_model_defaults_to_haiku(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(VALID_KEYS)
    assert load_config(path).summary_model == "haiku"


def test_summary_model_loads_from_the_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(VALID_KEYS + 'summary_model = "sonnet"\n')
    assert load_config(path).summary_model == "sonnet"


def test_summary_model_must_be_a_string(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(VALID_KEYS + "summary_model = 3\n")
    with pytest.raises(ConfigError):
        load_config(path)
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/common/test_config.py -q -k summary_model`
Expected: `AttributeError: 'OrchestratorConfig' object has no attribute 'summary_model'`

- [ ] **Step 3: Add the field, the constant and the example entry**

In the dataclass after `claude_model: str = "opus"`:

```python
    summary_model: str = "haiku"
```

After `CLAUDE_MODEL = _loaded_config.claude_model`:

```python
SUMMARY_MODEL = _loaded_config.summary_model
```

In `config.toml.example`, directly under the `# claude_model = "opus"` line:

```toml

# The model that writes the one-line gist under each row on the review board,
# passed as `claude --model <this>` to a short `claude --print` run per new
# comment. It reads one comment and answers one line, so the cheapest model
# is the right one. `claude_enabled = false` skips it and rows show the
# comment's own first line instead.
# summary_model = "haiku"
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/common/test_config.py -q`
Expected: pass. If a test enumerates the example file's keys against the dataclass, it now sees both.

- [ ] **Step 5: Full suite, then commit**

```bash
git add src/github_orchestrator/common/config.py config.toml.example tests/common/test_config.py
git commit -m "GITHUB-ORCHESTRATOR: add the summary_model config key"
```

______________________________________________________________________

### Task 3: the gist module

**Files:**

- Create: `src/github_orchestrator/common/summarize.py`
- Test: `tests/common/test_summarize.py`

**Interfaces:**

- Consumes: `claude_env()` from Task 1.

- Produces: `fallback_summary(body: str) -> str`; `summarize_comment(body: str, path: str | None, line: int | None, model: str) -> str | None`; constants `SUMMARY_WORKERS = 4`, `SUMMARY_MAX_CHARS = 60`, `SUMMARY_TIMEOUT = 20`.

- [ ] **Step 1: Write the failing tests**

````python
import subprocess

import pytest

from github_orchestrator.common import summarize
from github_orchestrator.common.summarize import (
    SUMMARY_MAX_CHARS,
    SUMMARY_TIMEOUT,
    fallback_summary,
    summarize_comment,
)


def test_fallback_is_the_first_non_empty_line():
    assert fallback_summary("\n\nplease rename this\nand that") == "please rename this"


def test_fallback_skips_a_leading_code_fence_block():
    body = "```python\nx = 1\n```\nthe real point"
    assert fallback_summary(body) == "the real point"


def test_fallback_clips_to_the_cap_with_an_ellipsis():
    body = "a" * 100
    out = fallback_summary(body)
    assert len(out) == SUMMARY_MAX_CHARS
    assert out.endswith("…")


def test_fallback_of_an_empty_body_is_empty():
    assert fallback_summary("") == ""
    assert fallback_summary("```\n```") == ""


def _completed(stdout="", returncode=0):
    return subprocess.CompletedProcess(["claude"], returncode, stdout=stdout, stderr="")


def test_summarize_spawns_claude_print_with_the_model_and_no_console_key(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return _completed("db connection is never closed\n")

    monkeypatch.setattr(summarize.subprocess, "run", fake_run)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    out = summarize_comment("leaks the connection", "api.py", 42, "haiku")
    assert out == "db connection is never closed"
    argv, kwargs = calls[0]
    assert argv == ["claude", "--print", "--model", "haiku"]
    assert "ANTHROPIC_API_KEY" not in kwargs["env"]
    assert kwargs["timeout"] == SUMMARY_TIMEOUT
    assert "api.py:42" in kwargs["input"]
    assert "leaks the connection" in kwargs["input"]


def test_summarize_takes_the_first_non_empty_line_and_clips_it(monkeypatch):
    monkeypatch.setattr(summarize.subprocess, "run",
                        lambda *a, **k: _completed("\n" + "b" * 90 + "\nsecond"))
    out = summarize_comment("x", None, None, "haiku")
    assert len(out) == SUMMARY_MAX_CHARS and out.endswith("…")


@pytest.mark.parametrize("outcome", [
    _completed("", 0),
    _completed("boom", 1),
])
def test_summarize_returns_none_on_empty_output_or_failure(monkeypatch, outcome):
    monkeypatch.setattr(summarize.subprocess, "run", lambda *a, **k: outcome)
    assert summarize_comment("x", None, None, "haiku") is None


def test_summarize_returns_none_on_timeout(monkeypatch):
    def slow(*a, **k):
        raise subprocess.TimeoutExpired(["claude"], SUMMARY_TIMEOUT)

    monkeypatch.setattr(summarize.subprocess, "run", slow)
    assert summarize_comment("x", None, None, "haiku") is None
````

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/common/test_summarize.py -q`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write the module**

````python
from __future__ import annotations

import logging
import subprocess

from github_orchestrator.common.claude_env import claude_env

log = logging.getLogger(__name__)

SUMMARY_WORKERS = 4
SUMMARY_MAX_CHARS = 60
SUMMARY_TIMEOUT = 20


def _clip(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= SUMMARY_MAX_CHARS:
        return text
    return text[: SUMMARY_MAX_CHARS - 1].rstrip() + "…"


def fallback_summary(body: str) -> str:
    in_fence = False
    for raw in (body or "").splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line:
            continue
        return _clip(line)
    return ""


def _prompt(body: str, path: str | None, line: int | None) -> str:
    where = f"{path}:{line}" if path and line is not None else (path or "the pull request")
    return (
        "Summarise this pull request review comment in one line of at most "
        f"{SUMMARY_MAX_CHARS} characters: lowercase, no trailing period, say what "
        "the reviewer wants changed. Reply with the line alone.\n\n"
        f"Comment on {where}:\n\n{body}"
    )


def summarize_comment(body: str, path: str | None, line: int | None,
                      model: str) -> str | None:
    try:
        done = subprocess.run(
            ["claude", "--print", "--model", model],
            input=_prompt(body, path, line), capture_output=True, text=True,
            timeout=SUMMARY_TIMEOUT, env=claude_env(),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.warning("comment summary spawn failed: %s", exc)
        return None
    if done.returncode != 0:
        log.warning("comment summary exited %d: %s", done.returncode,
                    (done.stderr or "").strip()[:200])
        return None
    for raw in done.stdout.splitlines():
        if raw.strip():
            return _clip(raw.strip())
    return None
````

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/common/test_summarize.py -q`
Expected: pass.

- [ ] **Step 5: Full suite, then commit**

```bash
git add src/github_orchestrator/common/summarize.py tests/common/test_summarize.py
git commit -m "GITHUB-ORCHESTRATOR: add the one-line comment gist and its fallback"
```

______________________________________________________________________

### Task 4: `candidates.set_fields`

**Files:**

- Modify: `src/github_orchestrator/common/candidates.py` (after `transition`)
- Test: `tests/common/test_candidates.py`

**Interfaces:**

- Produces: `set_fields(candidates_dir, repo, pr, comment_id, **fields) -> dict | None`. Load, update, save. `None` when there is no record.

- [ ] **Step 1: Write the failing tests**

```python
def test_set_fields_writes_the_fields_and_keeps_the_rest(tmp_path):
    save_candidate(tmp_path, REPO, PR, make_record(status=READY, author="reviewer"))
    updated = set_fields(tmp_path, REPO, PR, COMMENT_ID, summary="rename the helper")
    assert updated["summary"] == "rename the helper"
    loaded = load_candidate(tmp_path, REPO, PR, COMMENT_ID)
    assert loaded["summary"] == "rename the helper"
    assert loaded["status"] == READY and loaded["author"] == "reviewer"


def test_set_fields_on_a_missing_record_writes_nothing_and_returns_none(tmp_path):
    assert set_fields(tmp_path, REPO, PR, COMMENT_ID, summary="x") is None
    assert load_candidate(tmp_path, REPO, PR, COMMENT_ID) is None
```

Add `set_fields` to the import list at the top of the file.

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/common/test_candidates.py -q -k set_fields`
Expected: `ImportError: cannot import name 'set_fields'`

- [ ] **Step 3: Implement**

After `transition` in `candidates.py`:

```python
def set_fields(candidates_dir: Path, repo: str, pr: int, comment_id: int,
               **fields) -> dict | None:
    record = load_candidate(candidates_dir, repo, pr, comment_id)
    if record is None:
        return None
    record.update(fields)
    save_candidate(candidates_dir, repo, pr, record)
    return record
```

- [ ] **Step 4: Run, then full suite, then commit**

```bash
git add src/github_orchestrator/common/candidates.py tests/common/test_candidates.py
git commit -m "GITHUB-ORCHESTRATOR: add set_fields for display-only record fields"
```

______________________________________________________________________

### Task 5: the gist inside `open_candidate`, worktree cuts behind a lock

**Files:**

- Modify: `src/github_orchestrator/common/candidate_git.py:26-76`
- Test: `tests/common/test_candidate_git.py`

**Interfaces:**

- Consumes: `fallback_summary`, `summarize_comment` (Task 3); `candidates.set_fields` (Task 4).

- Produces: `open_candidate(..., comment_created_at=None, summary_model: str | None = None) -> dict`. The record carries `summary`. `create_candidate_worktree` runs under a module lock `_worktree_lock`.

- [ ] **Step 1: Write the failing tests**

These use the file's existing `pr_worktree`, `worktrees_dir` and `candidates_dir` fixtures. Add `from github_orchestrator.common import candidate_git` at the top.

```python
def test_open_candidate_writes_the_fallback_gist_without_a_model(
        pr_worktree, worktrees_dir, candidates_dir, monkeypatch):
    def never(*args, **kwargs):
        raise AssertionError("no model was given, so nothing should spawn")

    monkeypatch.setattr(candidate_git, "summarize_comment", never)
    record = open_candidate(
        candidates_dir, worktrees_dir, "o/r", 7, pr_worktree,
        comment_id=11, comment_type="review", author="a", path="f.py", line=1,
        body="\nplease close the connection\nmore words",
    )
    assert record["summary"] == "please close the connection"
    assert load_candidate(candidates_dir, "o/r", 7, 11)["summary"] == (
        "please close the connection")


def test_open_candidate_writes_the_fallback_first_then_the_gist(
        pr_worktree, worktrees_dir, candidates_dir, monkeypatch):
    seen = []

    def fake_gist(body, path, line, model):
        seen.append(load_candidate(candidates_dir, "o/r", 7, 11)["summary"])
        assert model == "haiku"
        return "db connection is never closed"

    monkeypatch.setattr(candidate_git, "summarize_comment", fake_gist)
    record = open_candidate(
        candidates_dir, worktrees_dir, "o/r", 7, pr_worktree,
        comment_id=11, comment_type="review", author="a", path="f.py", line=1,
        body="leaks the connection", summary_model="haiku",
    )
    assert seen == ["leaks the connection"]
    assert record["summary"] == "db connection is never closed"
    assert load_candidate(candidates_dir, "o/r", 7, 11)["summary"] == (
        "db connection is never closed")


def test_open_candidate_keeps_the_fallback_when_the_gist_fails(
        pr_worktree, worktrees_dir, candidates_dir, monkeypatch):
    monkeypatch.setattr(candidate_git, "summarize_comment", lambda *a, **k: None)
    record = open_candidate(
        candidates_dir, worktrees_dir, "o/r", 7, pr_worktree,
        comment_id=11, comment_type="review", author="a", path="f.py", line=1,
        body="leaks the connection", summary_model="haiku",
    )
    assert record["summary"] == "leaks the connection"


def test_worktree_cuts_are_serialised_behind_the_module_lock(
        pr_worktree, worktrees_dir, monkeypatch):
    entered = []
    real_lock = candidate_git._worktree_lock

    class Spy:
        def __enter__(self):
            entered.append("in")
            return real_lock.__enter__()

        def __exit__(self, *exc):
            entered.append("out")
            return real_lock.__exit__(*exc)

    monkeypatch.setattr(candidate_git, "_worktree_lock", Spy())
    candidate_git.create_candidate_worktree(pr_worktree, worktrees_dir, "o/r", 7, 11)
    assert entered == ["in", "out"]
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/common/test_candidate_git.py --no-replay -q -k "gist or fallback or serialised"`
Expected: `AttributeError: module has no attribute 'summarize_comment'` / `_worktree_lock`.

- [ ] **Step 3: Implement**

At the top of `candidate_git.py` add `import threading` and:

```python
from github_orchestrator.common.summarize import fallback_summary, summarize_comment

_worktree_lock = threading.Lock()
```

Wrap the body of `create_candidate_worktree` in `with _worktree_lock:` (indent the existing body one level; the signature and return stay).

Change `open_candidate`:

```python
def open_candidate(
    candidates_dir: Path, worktrees_dir: Path, repo: str, pr: int,
    pr_worktree: str, *, comment_id: int, comment_type: str, author: str,
    path: str | None, line: int | None, body: str,
    comment_created_at: str | None = None,
    summary_model: str | None = None,
) -> dict:
    wt, branch, base_sha = create_candidate_worktree(
        pr_worktree, worktrees_dir, repo, pr, comment_id
    )
    record = {
        "comment_id": comment_id,
        "comment_type": comment_type,
        "author": author,
        "path": path,
        "line": line,
        "body": body,
        "comment_created_at": comment_created_at,
        "summary": fallback_summary(body),
        "status": candidates.QUEUED,
        "branch": branch,
        "worktree": str(wt),
        "base_sha": base_sha,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }
    candidates.save_candidate(candidates_dir, repo, pr, record)
    if summary_model:
        gist = summarize_comment(body, path, line, summary_model)
        if gist:
            record = candidates.set_fields(
                candidates_dir, repo, pr, comment_id, summary=gist) or record
    return record
```

- [ ] **Step 4: Run live, then re-record**

Run: `uv run pytest tests/common/test_candidate_git.py --no-replay -q`
Expected: pass.
Run: `make record` (the new tests cut worktrees; the recording must know them).
Run: `uv run pytest tests/ -n 4 -q`

- [ ] **Step 5: Commit**

```bash
git add src/github_orchestrator/common/candidate_git.py tests/common/test_candidate_git.py tests/recorded_subprocesses.json
git commit -m "GITHUB-ORCHESTRATOR: write a gist onto each new candidate"
```

______________________________________________________________________

### Task 6: pooled materialisation, and the CLI says it is waiting

**Files:**

- Modify: `src/github_orchestrator/github_pr_agent_manager/candidate_dispatch.py:56-87`
- Modify: `src/github_orchestrator/github_pr_agent_manager/handlers.py:225-228`
- Modify: `src/github_orchestrator/cli/__main__.py:407-420`
- Test: `tests/github_pr_agent_manager/test_candidate_dispatch.py`, `tests/github_pr_agent_manager/test_handlers.py`, `tests/cli/test_candidate_commands.py`

**Interfaces:**

- Consumes: `open_candidate(..., summary_model=)` (Task 5); `SUMMARY_WORKERS` (Task 3); `SUMMARY_MODEL` (Task 2).

- Produces: `materialize_candidates(candidates_dir, worktrees_dir, repo, pr, pr_worktree, comments, summary_model: str | None = None) -> list[dict]`.

Ruled during execution: a four-worker pool takes `created_at` after the worktree lock releases, so the stamps left comment order and two pre-existing tests (the pool's start order, strictly increasing `created_at` per batch) went flaky. `open_candidate` gained `created_at: str | None = None` (it stamps `now` when omitted), and `materialize_candidates` pre-stamps every comment in comment order through `_stamps(count)`, bumping by one microsecond whenever a stamp would not exceed the previous one, before submitting to the pool. `created_at` is the board's sort key and the pool's start order, so it has to stay strictly increasing in comment order.

- [ ] **Step 1: Write the failing tests**

In `test_candidate_dispatch.py` (follow the file's existing pattern of monkeypatching `candidate_dispatch.open_candidate`):

```python
def test_materialize_hands_every_open_the_summary_model(tmp_path, monkeypatch):
    models = []

    def fake_open(*args, **kwargs):
        models.append(kwargs.get("summary_model"))
        return {"comment_id": kwargs["comment_id"], "status": "queued"}

    monkeypatch.setattr(candidate_dispatch, "open_candidate", fake_open)
    created = candidate_dispatch.materialize_candidates(
        tmp_path, tmp_path / "wt", "o/r", 1, str(tmp_path),
        [{"id": 1, "body": "a"}, {"id": 2, "body": "b"}], summary_model="haiku")
    assert models == ["haiku", "haiku"]
    assert [r["comment_id"] for r in created] == [1, 2]


def test_materialize_runs_opens_in_parallel_and_keeps_comment_order(tmp_path, monkeypatch):
    import threading
    import time
    started = threading.Barrier(2, timeout=5)

    def fake_open(*args, **kwargs):
        started.wait()
        return {"comment_id": kwargs["comment_id"], "status": "queued"}

    monkeypatch.setattr(candidate_dispatch, "open_candidate", fake_open)
    created = candidate_dispatch.materialize_candidates(
        tmp_path, tmp_path / "wt", "o/r", 1, str(tmp_path),
        [{"id": 5, "body": "a"}, {"id": 3, "body": "b"}])
    assert [r["comment_id"] for r in created] == [5, 3]
```

The barrier only releases when two opens overlap, so a serial loop hangs on `timeout=5` and fails.

In `test_handlers.py`, beside the existing `new-comments` materialise test:

```python
def test_new_comments_materialise_with_the_configured_summary_model(monkeypatch, tmp_path):
    seen = {}

    def fake(*args, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(handlers, "materialize_candidates", fake)
    monkeypatch.setattr(handlers, "SUMMARY_MODEL", "haiku")
    handlers.handle_event_with_role(
        {"type": "new-comments", "payload": {"comments": [{"id": 1}]}},
        "o/r", 1, str(tmp_path), True, tmp_path / "q", claude_enabled=True)
    assert seen["summary_model"] == "haiku"
```

In `tests/cli/test_candidate_commands.py` (follow how the file invokes `main` and captures stderr; if it uses `capsys`, so does this):

```python
def test_candidate_open_says_it_is_waiting_for_the_model(monkeypatch, tmp_path, capsys):
    body = tmp_path / "body.md"
    body.write_text("please rename")
    seen = {}

    def fake_open(*args, **kwargs):
        seen.update(kwargs)
        return {"worktree": "/wt"}

    monkeypatch.setattr(cli, "open_candidate", fake_open)
    monkeypatch.setattr(cli, "SUMMARY_MODEL", "haiku")
    monkeypatch.setattr(cli, "_claude_enabled", lambda: True)
    cli.main(["candidate", "open", "--pr", "1", "--comment-id", "9",
              "--author", "a", "--body-file", str(body), "--worktree", str(tmp_path)])
    out, err = capsys.readouterr()
    assert seen["summary_model"] == "haiku"
    assert "waiting for haiku" in err
    assert out.strip() == "/wt"


def test_candidate_open_passes_no_model_while_claude_is_disabled(monkeypatch, tmp_path, capsys):
    body = tmp_path / "body.md"
    body.write_text("please rename")
    seen = {}
    monkeypatch.setattr(cli, "open_candidate",
                        lambda *a, **k: (seen.update(k), {"worktree": "/wt"})[1])
    monkeypatch.setattr(cli, "_claude_enabled", lambda: False)
    cli.main(["candidate", "open", "--pr", "1", "--comment-id", "9",
              "--author", "a", "--body-file", str(body), "--worktree", str(tmp_path)])
    assert seen["summary_model"] is None
    assert "waiting" not in capsys.readouterr().err
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/github_pr_agent_manager/test_candidate_dispatch.py tests/github_pr_agent_manager/test_handlers.py tests/cli/test_candidate_commands.py -q -k "summary_model or parallel or waiting"`

- [ ] **Step 3: Implement**

`candidate_dispatch.py`: add `from concurrent.futures import ThreadPoolExecutor` and `from github_orchestrator.common.summarize import SUMMARY_WORKERS`. Replace `materialize_candidates`:

```python
def materialize_candidates(
    candidates_dir: Path, worktrees_dir: Path, repo: str, pr: int,
    pr_worktree: str, comments: list[dict],
    summary_model: str | None = None,
) -> list[dict]:
    def _open(comment: dict) -> dict | None:
        try:
            comment_id = comment["id"]
            if load_candidate(candidates_dir, repo, pr, comment_id) is not None:
                log.info(
                    "materialize %s#%d: comment %d already has a record; skipping",
                    repo, pr, comment_id,
                )
                return None
            return open_candidate(
                candidates_dir, worktrees_dir, repo, pr, pr_worktree,
                comment_id=comment_id,
                comment_type=comment.get("comment_type", "review"),
                author=comment.get("author", "ghost"),
                path=comment.get("path"),
                line=comment.get("line"),
                body=comment.get("body", ""),
                comment_created_at=comment.get("created_at"),
                summary_model=summary_model,
            )
        except Exception:
            log.exception(
                "materialize %s#%d: comment %s failed; skipping it",
                repo, pr, comment.get("id"),
            )
            return None

    with ThreadPoolExecutor(max_workers=SUMMARY_WORKERS) as pool:
        opened = list(pool.map(_open, comments))
    return [record for record in opened if record is not None]
```

`handlers.py`: import `SUMMARY_MODEL` from `github_orchestrator.common.config` and pass `summary_model=SUMMARY_MODEL` in the `materialize_candidates(...)` call (the branch already returns early when `claude_enabled` is false).

`cli/__main__.py`: import `SUMMARY_MODEL` alongside the other config names, add

```python
def _claude_enabled() -> bool:
    return load_config(CONFIG_TOML_PATH).claude_enabled
```

and change `cmd_candidate_open`:

```python
def cmd_candidate_open(args):
    body = Path(args.body_file).read_text()
    model = SUMMARY_MODEL if _claude_enabled() else None
    if model:
        print(f"waiting for {model} to write the comment's one-line gist…",
              file=sys.stderr)
    try:
        record = open_candidate(
            CANDIDATES_DIR, CANDIDATE_WORKTREES_DIR, args.repo, args.pr,
            args.worktree, comment_id=args.comment_id,
            comment_type=args.comment_type, author=args.author,
            path=args.path, line=args.line, body=body, summary_model=model,
        )
    except CandidateGitError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    print(record["worktree"])
```

If the CLI already has a helper that reads `claude_enabled` for `claude_disabled_notice`, reuse that name instead of adding `_claude_enabled`, and patch that name in the tests.

- [ ] **Step 4: Run, full suite, commit**

```bash
git add src/github_orchestrator/github_pr_agent_manager/candidate_dispatch.py src/github_orchestrator/github_pr_agent_manager/handlers.py src/github_orchestrator/cli/__main__.py tests/github_pr_agent_manager/test_candidate_dispatch.py tests/github_pr_agent_manager/test_handlers.py tests/cli/test_candidate_commands.py
git commit -m "GITHUB-ORCHESTRATOR: materialise candidates four at a time and pass the gist model through"
```

______________________________________________________________________

### Task 7: the `removed` status, and records with no `created_at` sort last

**Files:**

- Modify: `src/github_orchestrator/common/candidates.py:19-41` and `:98`
- Modify: `src/github_orchestrator/github_pr_agent_manager/review_board.py` (`_ACTIONS`, `_STATUS_LABELS`, `render_summary`'s `counted`, the `.status.*` CSS)
- Test: `tests/common/test_candidates.py`, `tests/github_pr_agent_manager/test_review_board.py`

**Interfaces:**

- Produces: `candidates.REMOVED = "removed"`; `ALLOWED_TRANSITIONS` gains `REMOVED` as a key (`{COMMITTED, DISMISSED}`) and as a member of the seven unfinished statuses' sets; `list_candidates` sorts `(created_at missing, created_at, comment_id)`.

- [ ] **Step 1: Write the failing tests**

`tests/common/test_candidates.py` (add `REMOVED` to the import):

```python
UNFINISHED = (QUEUED, WORKING, READY, SKIPPED, FAILED, REJECTED, COMMITTED)


@pytest.mark.parametrize("status", UNFINISHED)
def test_every_unfinished_status_can_become_removed(status):
    assert REMOVED in ALLOWED_TRANSITIONS[status]


@pytest.mark.parametrize("status", [APPROVED, DISMISSED])
def test_a_settled_status_never_becomes_removed(status):
    assert REMOVED not in ALLOWED_TRANSITIONS[status]


def test_removed_can_only_land_or_be_dismissed():
    assert ALLOWED_TRANSITIONS[REMOVED] == {COMMITTED, DISMISSED}


def test_a_record_with_no_created_at_sorts_last(tmp_path):
    save_candidate(tmp_path, REPO, PR, make_record(comment_id=30, created_at="2026-08-28T10:00:01Z"))
    save_candidate(tmp_path, REPO, PR, {"comment_id": 5, "status": REMOVED})
    save_candidate(tmp_path, REPO, PR, make_record(comment_id=10, created_at="2026-08-28T10:00:00Z"))
    ids = [r["comment_id"] for r in list_candidates(tmp_path, REPO, PR)]
    assert ids == [10, 30, 5]
```

`tests/github_pr_agent_manager/test_review_board.py`:

```python
def test_a_removed_card_offers_dismiss_and_approve_only_with_a_sha(tmp_path):
    with_sha = card_for(tmp_path, make_record(status=candidates.REMOVED,
                                              candidate_sha="abc123", comment_deleted=True))
    assert buttons_of(with_sha) == {"approve", "dismiss"}
    without = card_for(tmp_path, make_record(status=candidates.REMOVED, comment_deleted=True))
    assert buttons_of(without) == {"dismiss"}


def test_the_removed_pill_says_the_comment_was_deleted(tmp_path):
    card = card_for(tmp_path, make_record(status=candidates.REMOVED, comment_deleted=True))
    assert '<span class="status removed">comment deleted</span>' in card


def test_the_summary_counts_removed_cards_when_there_are_any(tmp_path):
    candidates.save_candidate(tmp_path, REPO, PR,
                              make_record(status=candidates.REMOVED, comment_deleted=True))
    assert "1 comment deleted" in review_board.render_summary(tmp_path, REPO, PR)
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/common/test_candidates.py tests/github_pr_agent_manager/test_review_board.py -q -k "removed or created_at_sorts_last"`

- [ ] **Step 3: Implement**

`candidates.py`:

```python
REMOVED = "removed"

ALLOWED_TRANSITIONS = {
    QUEUED: {WORKING, SKIPPED, DISMISSED, REMOVED},
    WORKING: {READY, SKIPPED, FAILED, QUEUED, REMOVED},
    READY: {READY, QUEUED, COMMITTED, REJECTED, DISMISSED, REMOVED},
    SKIPPED: {REJECTED, DISMISSED, REMOVED},
    FAILED: {QUEUED, REJECTED, DISMISSED, REMOVED},
    REJECTED: {READY, DISMISSED, REMOVED},
    COMMITTED: {APPROVED, REMOVED},
    REMOVED: {COMMITTED, DISMISSED},
    APPROVED: set(),
    DISMISSED: set(),
}
```

and the sort in `list_candidates`:

```python
    records.sort(key=lambda r: (not r.get("created_at"),
                                r.get("created_at", ""), r.get("comment_id", 0)))
```

`review_board.py`:

```python
_ACTIONS = {
    candidates.QUEUED: ("dismiss",),
    candidates.READY: ("approve", "reject", "decline"),
    candidates.COMMITTED: ("approve",),
    candidates.SKIPPED: ("reject", "dismiss"),
    candidates.FAILED: ("retry",),
    candidates.REMOVED: ("approve", "dismiss"),
}

_STATUS_LABELS = {
    candidates.APPROVED: "landed",
    candidates.COMMITTED: "committed locally, not pushed",
    candidates.REJECTED: "in rework",
    candidates.REMOVED: "comment deleted",
}
```

In `render_summary`'s `counted` tuple add `(candidates.REMOVED, False),` after `DISMISSED`. In the stylesheet, beside `.status.needs-you`:

```css
  .status.removed { color: var(--danger); border-color: var(--danger); }
```

The existing `approve` filter at `review_board.py:1066` (`status == READY and not candidate_sha`) must also cover `REMOVED`:

```python
    if status in (candidates.READY, candidates.REMOVED) and not record.get("candidate_sha"):
        actions = tuple(d for d in actions if d != "approve")
```

- [ ] **Step 4: Run the whole suite and fix what the new status trips**

Run: `uv run pytest tests/ -n 4 -q`. Tests that iterate `ALLOWED_TRANSITIONS` (for example `test_every_status_that_renders_a_card_labels_a_stale_reason`, `test_each_status_pill_carries_its_status_class`, `test_summary_labels_every_status_it_counts`) now include `removed`. Read each failure; the fix is a label, a class or a `reason` prefix for `removed`, not a skip. For the `verdict` dict at `review_board.py:1028`, add `candidates.REMOVED: "before the comment was deleted: "`.

- [ ] **Step 5: Commit**

```bash
git add src/github_orchestrator/common/candidates.py src/github_orchestrator/github_pr_agent_manager/review_board.py tests/common/test_candidates.py tests/github_pr_agent_manager/test_review_board.py
git commit -m "GITHUB-ORCHESTRATOR: add the removed status for comments deleted mid-work"
```

______________________________________________________________________

### Task 8: landing and closing a card whose comment is gone

**Files:**

- Modify: `src/github_orchestrator/github_pr_agent_manager/candidate_land.py:303-330` and `:433-453`
- Test: `tests/github_pr_agent_manager/test_candidate_land.py`

**Interfaces:**

- Consumes: `comment_deleted` flag; `REMOVED` (Task 7).

- Produces: `_approve` skips the reply and writes `reply_note = "no reply: the comment was deleted"` when `record["comment_deleted"]`; `_closing_reply` refuses a reply on such a record; `_dismiss` on a record with no `worktree`/`branch` runs no git.

- [ ] **Step 1: Write the failing tests**

Follow `test_candidate_land.py`'s existing fixtures for a landable record and the `gh_api_post` stub. The shape:

```python
def test_approve_skips_the_reply_when_the_comment_was_deleted(tmp_path, monkeypatch, landable):
    posted = []
    monkeypatch.setattr(candidate_land, "gh_api_post", lambda *a, **k: posted.append(a))
    record = landable(status=candidates.REMOVED, comment_deleted=True, comment_type="review")
    candidates.write_intent(tmp_path, REPO, PR, record["comment_id"], "approve")
    candidate_land.drain_intents(tmp_path, REPO, PR, PR_WORKTREE, "win", run_alive=False)
    after = candidates.load_candidate(tmp_path, REPO, PR, record["comment_id"])
    assert posted == []
    assert after["status"] == candidates.APPROVED
    assert after["reply_note"] == "no reply: the comment was deleted"
    assert after["comment_deleted"] is True
    assert "reply_error" not in after


def test_dismiss_with_a_reply_on_a_deleted_comment_is_refused(tmp_path, monkeypatch):
    record = make_record(status=candidates.REMOVED, comment_deleted=True, comment_type="review")
    candidates.save_candidate(tmp_path, REPO, PR, record)
    candidates.write_intent(tmp_path, REPO, PR, record["comment_id"], "dismiss", "thanks anyway")
    monkeypatch.setattr(candidate_land, "gh_api_post",
                        lambda *a, **k: pytest.fail("nothing to post to"))
    candidate_land.drain_intents(tmp_path, REPO, PR, PR_WORKTREE, "win", run_alive=False)
    after = candidates.load_candidate(tmp_path, REPO, PR, record["comment_id"])
    assert after["status"] == candidates.REMOVED
    assert "deleted" in after["decision_error"]


def test_a_blank_dismiss_closes_a_minimal_removed_record_without_git(tmp_path, monkeypatch):
    record = {"comment_id": 77, "status": candidates.REMOVED, "comment_deleted": True}
    candidates.save_candidate(tmp_path, REPO, PR, record)
    candidates.write_intent(tmp_path, REPO, PR, 77, "dismiss")
    monkeypatch.setattr(candidate_land, "_git", lambda *a: pytest.fail("no branch to delete"))
    monkeypatch.setattr(candidate_land, "remove_worktree",
                        lambda *a: pytest.fail("no worktree to remove"))
    candidate_land.drain_intents(tmp_path, REPO, PR, PR_WORKTREE, "win", run_alive=False)
    assert candidates.load_candidate(tmp_path, REPO, PR, 77)["status"] == candidates.DISMISSED
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/github_pr_agent_manager/test_candidate_land.py -q -k deleted`

- [ ] **Step 3: Implement**

In `_approve`, the reply block becomes:

```python
    if not record.get("replied"):
        if record.get("comment_deleted"):
            record["reply_note"] = "no reply: the comment was deleted"
        elif record.get("comment_type") == "review":
```

(the rest of the `review` branch and the `else` branch are unchanged). In `_closing_reply`, after `if not reply: return {}`:

```python
    if record.get("comment_deleted"):
        _refuse(candidates_dir, repo, pr, comment_id, record, decision,
                "no reply posted: the comment was deleted from GitHub")
        return None
```

`_drop_candidate_checkout` already guards both fields with `.get`; the third test proves it.

- [ ] **Step 4: Run, full suite, commit**

```bash
git add src/github_orchestrator/github_pr_agent_manager/candidate_land.py tests/github_pr_agent_manager/test_candidate_land.py
git commit -m "GITHUB-ORCHESTRATOR: land and close a card whose comment was deleted without replying"
```

______________________________________________________________________

### Task 9: does the comment still exist on GitHub

**Files:**

- Create: `src/github_orchestrator/github_pr_agent_manager/presence.py`
- Test: `tests/github_pr_agent_manager/test_presence.py`

**Interfaces:**

- Consumes: `gh_api`, `GhError` from `common.gh`; `transition`, `set_fields`, `REMOVED`, `UNREADABLE` from `common.candidates`.

- Produces: `comment_exists(repo, pr, comment_type, comment_id) -> bool | None` (memoised `PRESENCE_TTL_SECONDS = 60`); `checks_presence(record) -> bool`; `note_absence(candidates_dir, repo, pr, record) -> dict`; `refresh_presence(candidates_dir, repo, pr, record) -> dict`; `UNFINISHED` frozenset; `_presence_memo` dict (tests clear it).

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from github_orchestrator.common import candidates
from github_orchestrator.common.gh import GhError
from github_orchestrator.github_pr_agent_manager import presence

REPO, PR = "o/r", 3


@pytest.fixture(autouse=True)
def _clear_memo():
    presence._presence_memo.clear()
    yield
    presence._presence_memo.clear()


def _record(status=candidates.READY, **extra):
    record = {"comment_id": 11, "status": status, "comment_type": "review",
              "created_at": "2026-09-06T10:00:00Z"}
    record.update(extra)
    return record


def test_a_404_means_gone_and_anything_else_means_unknown(monkeypatch):
    def gone(path):
        raise GhError("gh api failed (exit 1): gh: Not Found (HTTP 404)")

    monkeypatch.setattr(presence, "gh_api", gone)
    assert presence.comment_exists(REPO, PR, "review", 11) is False
    presence._presence_memo.clear()

    def down(path):
        raise GhError("gh api failed (exit 1): error connecting to api.github.com")

    monkeypatch.setattr(presence, "gh_api", down)
    assert presence.comment_exists(REPO, PR, "review", 11) is None


def test_the_path_follows_the_comment_type(monkeypatch):
    paths = []
    monkeypatch.setattr(presence, "gh_api", lambda path: paths.append(path) or {})
    presence.comment_exists(REPO, PR, "review", 1)
    presence.comment_exists(REPO, PR, "issue", 2)
    presence.comment_exists(REPO, PR, "review-summary", 3)
    assert paths == ["/repos/o/r/pulls/comments/1", "/repos/o/r/issues/comments/2",
                     "/repos/o/r/pulls/3/reviews/3"]
    assert presence.comment_exists(REPO, PR, "unknown-type", 4) is None


def test_the_answer_is_memoised_for_a_minute(monkeypatch):
    calls = []
    monkeypatch.setattr(presence, "gh_api", lambda path: calls.append(path) or {})
    clock = [1000.0]
    monkeypatch.setattr(presence.time, "monotonic", lambda: clock[0])
    assert presence.comment_exists(REPO, PR, "review", 11) is True
    clock[0] += 30
    assert presence.comment_exists(REPO, PR, "review", 11) is True
    assert len(calls) == 1
    clock[0] += 31
    presence.comment_exists(REPO, PR, "review", 11)
    assert len(calls) == 2


def test_an_unknown_answer_is_not_memoised(monkeypatch):
    calls = []

    def down(path):
        calls.append(path)
        raise GhError("error connecting")

    monkeypatch.setattr(presence, "gh_api", down)
    presence.comment_exists(REPO, PR, "review", 11)
    presence.comment_exists(REPO, PR, "review", 11)
    assert len(calls) == 2


@pytest.mark.parametrize("status", sorted(presence.UNFINISHED))
def test_an_unfinished_record_whose_comment_is_gone_becomes_removed(tmp_path, monkeypatch, status):
    candidates.save_candidate(tmp_path, REPO, PR, _record(status=status))
    monkeypatch.setattr(presence, "comment_exists", lambda *a: False)
    after = presence.refresh_presence(tmp_path, REPO, PR, _record(status=status))
    assert after["status"] == candidates.REMOVED
    assert after["comment_deleted"] is True


@pytest.mark.parametrize("status", [candidates.APPROVED, candidates.DISMISSED])
def test_a_settled_record_whose_comment_is_gone_is_only_flagged(tmp_path, monkeypatch, status):
    candidates.save_candidate(tmp_path, REPO, PR, _record(status=status, pushed=True))
    monkeypatch.setattr(presence, "comment_exists", lambda *a: False)
    after = presence.refresh_presence(tmp_path, REPO, PR, _record(status=status, pushed=True))
    assert after["status"] == status
    assert after["comment_deleted"] is True


@pytest.mark.parametrize("record", [
    _record(status=candidates.REMOVED, comment_deleted=True),
    _record(status=candidates.UNREADABLE),
    _record(comment_deleted=True),
    {"comment_id": 11, "status": candidates.REMOVED},
])
def test_records_with_nothing_to_check_are_left_alone(tmp_path, monkeypatch, record):
    monkeypatch.setattr(presence, "comment_exists",
                        lambda *a: pytest.fail("should not ask GitHub"))
    assert presence.refresh_presence(tmp_path, REPO, PR, dict(record)) == record


def test_a_present_or_unknown_answer_changes_nothing(tmp_path, monkeypatch):
    candidates.save_candidate(tmp_path, REPO, PR, _record())
    for answer in (True, None):
        monkeypatch.setattr(presence, "comment_exists", lambda *a, _a=answer: _a)
        after = presence.refresh_presence(tmp_path, REPO, PR, _record())
        assert after["status"] == candidates.READY
        assert "comment_deleted" not in after
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/github_pr_agent_manager/test_presence.py -q`

- [ ] **Step 3: Write the module**

```python
from __future__ import annotations

import logging
import time
from pathlib import Path

from github_orchestrator.common import candidates
from github_orchestrator.common.gh import GhError, gh_api

log = logging.getLogger(__name__)

PRESENCE_TTL_SECONDS = 60

UNFINISHED = frozenset({
    candidates.QUEUED, candidates.WORKING, candidates.READY, candidates.SKIPPED,
    candidates.FAILED, candidates.REJECTED, candidates.COMMITTED,
})

_PATHS = {
    "review": "/repos/{repo}/pulls/comments/{id}",
    "issue": "/repos/{repo}/issues/comments/{id}",
    "review-summary": "/repos/{repo}/pulls/{pr}/reviews/{id}",
}

_presence_memo: dict[tuple[str, int, int], tuple[float, bool]] = {}


def comment_exists(repo: str, pr: int, comment_type: str,
                   comment_id: int) -> bool | None:
    key = (repo, pr, comment_id)
    hit = _presence_memo.get(key)
    now = time.monotonic()
    if hit is not None and now - hit[0] < PRESENCE_TTL_SECONDS:
        return hit[1]
    path = _PATHS.get(comment_type)
    if path is None:
        return None
    try:
        gh_api(path.format(repo=repo, pr=pr, id=comment_id))
    except GhError as exc:
        if "HTTP 404" not in str(exc):
            log.warning("could not check %s#%d comment %d on GitHub: %s",
                        repo, pr, comment_id, exc)
            return None
        present = False
    else:
        present = True
    _presence_memo[key] = (now, present)
    return present


def checks_presence(record: dict) -> bool:
    return (
        bool(record.get("comment_type"))
        and record.get("status") not in (candidates.REMOVED, candidates.UNREADABLE)
        and not record.get("comment_deleted")
    )


def note_absence(candidates_dir: Path, repo: str, pr: int, record: dict) -> dict:
    comment_id = int(record["comment_id"])
    if record.get("status") in UNFINISHED:
        return candidates.transition(candidates_dir, repo, pr, comment_id,
                                     candidates.REMOVED, comment_deleted=True)
    return candidates.set_fields(candidates_dir, repo, pr, comment_id,
                                 comment_deleted=True) or record


def refresh_presence(candidates_dir: Path, repo: str, pr: int, record: dict) -> dict:
    if not checks_presence(record):
        return record
    present = comment_exists(repo, pr, str(record["comment_type"]),
                             int(record["comment_id"]))
    if present is False:
        return note_absence(candidates_dir, repo, pr, record)
    return record
```

- [ ] **Step 4: Run, full suite, commit**

```bash
git add src/github_orchestrator/github_pr_agent_manager/presence.py tests/github_pr_agent_manager/test_presence.py
git commit -m "GITHUB-ORCHESTRATOR: notice a comment deleted on GitHub when its card is opened"
```

______________________________________________________________________

### Task 10: rebuilding a record a stale client asks for

**Files:**

- Create: `src/github_orchestrator/github_pr_agent_manager/candidate_repair.py`
- Test: `tests/github_pr_agent_manager/test_candidate_repair.py`

**Interfaces:**

- Consumes: `gh_api`, `GhError`; `open_candidate` (Task 5); `candidates.save_candidate`, `load_candidate`, `REMOVED`.

- Produces: `rebuild_candidate(candidates_dir, worktrees_dir, repo, pr, pr_worktree, comment_id, summary_model) -> dict`; `RepairUnavailable(Exception)`; module lock `_repair_lock`.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from github_orchestrator.common import candidates
from github_orchestrator.common.gh import GhError
from github_orchestrator.github_pr_agent_manager import candidate_repair
from github_orchestrator.github_pr_agent_manager.candidate_repair import (
    RepairUnavailable,
    rebuild_candidate,
)

REPO, PR = "o/r", 3
NOT_FOUND = GhError("gh api failed (exit 1): gh: Not Found (HTTP 404)")


def _answering(answers):
    def fake(path):
        outcome = answers[path]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    return fake


def test_an_existing_record_is_returned_without_asking_github(tmp_path, monkeypatch):
    record = {"comment_id": 11, "status": candidates.READY, "created_at": "x"}
    candidates.save_candidate(tmp_path, REPO, PR, record)
    monkeypatch.setattr(candidate_repair, "gh_api", lambda p: pytest.fail("no lookup needed"))
    assert rebuild_candidate(tmp_path, tmp_path / "wt", REPO, PR, "/pr", 11, None)["status"] == "ready"


def test_a_live_review_comment_is_reopened_as_a_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(candidate_repair, "gh_api", _answering({
        "/repos/o/r/pulls/comments/11": {
            "user": {"login": "alice"}, "path": "api.py", "line": None,
            "original_line": 42, "body": "leaks", "created_at": "2026-09-06T10:00:00Z"},
    }))
    opened = {}

    def fake_open(*args, **kwargs):
        opened.update(kwargs)
        return {"comment_id": 11, "status": "queued"}

    monkeypatch.setattr(candidate_repair, "open_candidate", fake_open)
    record = rebuild_candidate(tmp_path, tmp_path / "wt", REPO, PR, "/pr", 11, "haiku")
    assert record["status"] == "queued"
    assert opened["comment_type"] == "review" and opened["author"] == "alice"
    assert opened["path"] == "api.py" and opened["line"] == 42
    assert opened["body"] == "leaks" and opened["summary_model"] == "haiku"
    assert opened["comment_created_at"] == "2026-09-06T10:00:00Z"


def test_the_lookup_falls_through_issue_comment_and_review(tmp_path, monkeypatch):
    monkeypatch.setattr(candidate_repair, "gh_api", _answering({
        "/repos/o/r/pulls/comments/11": NOT_FOUND,
        "/repos/o/r/issues/comments/11": NOT_FOUND,
        "/repos/o/r/pulls/3/reviews/11": {
            "user": {"login": "bob"}, "body": "LGTM but", "submitted_at": "2026-09-06T11:00:00Z"},
    }))
    opened = {}
    monkeypatch.setattr(candidate_repair, "open_candidate",
                        lambda *a, **k: (opened.update(k), {"comment_id": 11})[1])
    rebuild_candidate(tmp_path, tmp_path / "wt", REPO, PR, "/pr", 11, None)
    assert opened["comment_type"] == "review-summary"
    assert opened["path"] is None and opened["line"] is None
    assert opened["comment_created_at"] == "2026-09-06T11:00:00Z"


def test_a_comment_gone_everywhere_becomes_a_minimal_removed_record(tmp_path, monkeypatch):
    monkeypatch.setattr(candidate_repair, "gh_api", _answering({
        "/repos/o/r/pulls/comments/11": NOT_FOUND,
        "/repos/o/r/issues/comments/11": NOT_FOUND,
        "/repos/o/r/pulls/3/reviews/11": NOT_FOUND,
    }))
    monkeypatch.setattr(candidate_repair, "open_candidate",
                        lambda *a, **k: pytest.fail("nothing to open"))
    record = rebuild_candidate(tmp_path, tmp_path / "wt", REPO, PR, "/pr", 11, None)
    assert record["status"] == candidates.REMOVED and record["comment_deleted"] is True
    stored = candidates.load_candidate(tmp_path, REPO, PR, 11)
    assert stored["status"] == candidates.REMOVED
    assert "body" not in stored and "created_at" not in stored


def test_a_github_failure_that_is_not_404_raises_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(candidate_repair, "gh_api",
                        _answering({"/repos/o/r/pulls/comments/11": GhError("connection reset")}))
    with pytest.raises(RepairUnavailable):
        rebuild_candidate(tmp_path, tmp_path / "wt", REPO, PR, "/pr", 11, None)
    assert candidates.load_candidate(tmp_path, REPO, PR, 11) is None


def test_the_rebuild_runs_under_the_module_lock(tmp_path, monkeypatch):
    entered = []
    real = candidate_repair._repair_lock

    class Spy:
        def __enter__(self):
            entered.append("in")
            return real.__enter__()

        def __exit__(self, *exc):
            entered.append("out")
            return real.__exit__(*exc)

    monkeypatch.setattr(candidate_repair, "_repair_lock", Spy())
    candidates.save_candidate(tmp_path, REPO, PR, {"comment_id": 11, "status": "ready", "created_at": "x"})
    rebuild_candidate(tmp_path, tmp_path / "wt", REPO, PR, "/pr", 11, None)
    assert entered == ["in", "out"]
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/github_pr_agent_manager/test_candidate_repair.py -q`

- [ ] **Step 3: Write the module**

```python
from __future__ import annotations

import logging
import threading
from pathlib import Path

from github_orchestrator.common import candidates
from github_orchestrator.common.candidate_git import open_candidate
from github_orchestrator.common.gh import GhError, gh_api

log = logging.getLogger(__name__)

_repair_lock = threading.Lock()

_LOOKUPS = (
    ("review", "/repos/{repo}/pulls/comments/{id}"),
    ("issue", "/repos/{repo}/issues/comments/{id}"),
    ("review-summary", "/repos/{repo}/pulls/{pr}/reviews/{id}"),
)


class RepairUnavailable(Exception):
    pass


def _fetch_comment(repo: str, pr: int, comment_id: int) -> tuple[str, dict] | None:
    for comment_type, path in _LOOKUPS:
        try:
            data = gh_api(path.format(repo=repo, pr=pr, id=comment_id))
        except GhError as exc:
            if "HTTP 404" in str(exc):
                continue
            raise RepairUnavailable(str(exc)) from exc
        return comment_type, data if isinstance(data, dict) else {}
    return None


def _line_of(data: dict) -> int | None:
    for key in ("line", "original_line"):
        if data.get(key) is not None:
            return int(data[key])
    return None


def rebuild_candidate(candidates_dir: Path, worktrees_dir: Path, repo: str, pr: int,
                      pr_worktree: str, comment_id: int,
                      summary_model: str | None) -> dict:
    with _repair_lock:
        existing = candidates.load_candidate(candidates_dir, repo, pr, comment_id)
        if existing is not None:
            return existing
        found = _fetch_comment(repo, pr, comment_id)
        if found is None:
            record = {"comment_id": comment_id, "status": candidates.REMOVED,
                      "comment_deleted": True}
            candidates.save_candidate(candidates_dir, repo, pr, record)
            log.warning("rebuilt %s#%d comment %d as removed: GitHub no longer has it",
                        repo, pr, comment_id)
            return record
        comment_type, data = found
        log.warning("rebuilding %s#%d comment %d from GitHub: its record was gone",
                    repo, pr, comment_id)
        return open_candidate(
            candidates_dir, worktrees_dir, repo, pr, pr_worktree,
            comment_id=comment_id,
            comment_type=comment_type,
            author=str((data.get("user") or {}).get("login") or "ghost"),
            path=data.get("path"),
            line=_line_of(data),
            body=str(data.get("body") or ""),
            comment_created_at=data.get("created_at") or data.get("submitted_at"),
            summary_model=summary_model,
        )
```

- [ ] **Step 4: Run, full suite, commit**

```bash
git add src/github_orchestrator/github_pr_agent_manager/candidate_repair.py tests/github_pr_agent_manager/test_candidate_repair.py
git commit -m "GITHUB-ORCHESTRATOR: rebuild a candidate record a stale board asks for"
```

______________________________________________________________________

### Task 11: rows, bands and the `/rows` endpoint

**Files:**

- Modify: `src/github_orchestrator/github_pr_agent_manager/review_board.py` (new functions beside `_display_status`; route in `handle_get`)
- Test: `tests/github_pr_agent_manager/test_review_board.py`

**Interfaces:**

- Consumes: `_display_status`, `_relative_time`, `_format_elapsed`, `_settled_line`, `_QUEUED_LABEL`, `_STATUS_LABELS`, `comment_url`, `_COMMENT_TYPE_LABELS`, `candidates.read_intent`, `candidates.read_action`, `fallback_summary` (Task 3).

- Produces: `BAND_WANTS_YOU = 0`, `BAND_AGENT = 1`, `BAND_SETTLED = 2`; `band_of(record, intent) -> int`; `sort_key(record) -> str`; `render_row(record, repo, pr, intent, last_action=None) -> str`; `row_payload(candidates_dir, repo, pr, record) -> dict`; `render_rows(candidates_dir, repo, pr) -> str` (JSON); `render_counts(records) -> str`; `_JSON = "application/json; charset=utf-8"`; route `GET /rows`.

- [ ] **Step 1: Write the failing tests**

```python
def test_bands_follow_the_table_in_the_spec():
    band = review_board.band_of
    R = make_record
    assert band(R(status=candidates.READY), None) == review_board.BAND_WANTS_YOU
    assert band(R(status=candidates.READY, reason="conflict"), None) == review_board.BAND_WANTS_YOU
    assert band(R(status=candidates.COMMITTED), None) == review_board.BAND_WANTS_YOU
    assert band(R(status=candidates.APPROVED, pushed=False), None) == review_board.BAND_WANTS_YOU
    assert band(R(status=candidates.SKIPPED), None) == review_board.BAND_WANTS_YOU
    assert band(R(status=candidates.FAILED), None) == review_board.BAND_WANTS_YOU
    assert band(R(status=candidates.APPROVED, pushed=True, reply_error="x"), None) == review_board.BAND_WANTS_YOU
    assert band(R(status=candidates.REMOVED, comment_deleted=True), None) == review_board.BAND_WANTS_YOU
    assert band({"comment_id": 1, "status": candidates.UNREADABLE}, None) == review_board.BAND_WANTS_YOU
    assert band(R(status=candidates.QUEUED), None) == review_board.BAND_AGENT
    assert band(R(status=candidates.WORKING), None) == review_board.BAND_AGENT
    assert band(R(status=candidates.REJECTED), None) == review_board.BAND_AGENT
    assert band(R(status=candidates.READY), "approve") == review_board.BAND_AGENT
    assert band(R(status=candidates.COMMITTED), "approve") == review_board.BAND_AGENT
    assert band(R(status=candidates.APPROVED, pushed=True, replied=True), None) == review_board.BAND_SETTLED
    assert band(R(status=candidates.DISMISSED), None) == review_board.BAND_SETTLED


def test_the_sort_key_is_time_then_id_and_a_missing_time_sorts_last():
    early = review_board.sort_key(make_record(comment_id=9, created_at="2026-09-06T10:00:00.000000Z"))
    late = review_board.sort_key(make_record(comment_id=1, created_at="2026-09-06T10:00:01.000000Z"))
    none = review_board.sort_key({"comment_id": 5, "status": candidates.REMOVED})
    assert early < late < none
    assert none.startswith("~|")
    a = review_board.sort_key(make_record(comment_id=99, created_at="t"))
    b = review_board.sort_key(make_record(comment_id=100, created_at="t"))
    assert a < b


def row_for(tmp_path, record, intent=None, last_action=None):
    return review_board.render_row(record, REPO, PR, intent, last_action)


def test_a_row_is_head_gist_and_nothing_else_for_a_plain_ready_card(tmp_path):
    row = row_for(tmp_path, make_record(summary="rename the helper"))
    assert row.index('class="row-head"') < row.index('class="gist"')
    assert "rename the helper" in row
    assert 'class="aftermath"' not in row
    assert "<button" not in row and "<details" not in row


def test_the_row_head_scans_pill_author_type_anchor_age(tmp_path, monkeypatch):
    monkeypatch.setattr(review_board, "_now",
                        lambda: datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc))
    row = row_for(tmp_path, make_record(comment_type="review",
                                        comment_created_at="2026-08-28T10:00:00Z"))
    order = [row.index('class="status ready"'), row.index('class="author"'),
             row.index('class="ctype"'), row.index('class="anchor"'), row.index('class="when"')]
    assert order == sorted(order)
    assert 'href="https://github.com/acme/widgets/pull/54#discussion_r2314159"' in row


def test_a_row_without_a_stored_gist_falls_back_to_the_bodys_first_line(tmp_path):
    row = row_for(tmp_path, make_record(body="\nplease rename this helper\nmore"))
    assert '<p class="gist">please rename this helper</p>' in row


@pytest.mark.parametrize("record,intent,expected", [
    (dict(status=candidates.QUEUED), None, "waiting for an agent"),
    (dict(status=candidates.QUEUED, attempts=1), None, "waiting for an agent (attempt 2 of 3)"),
    (dict(status=candidates.READY, reason="tests failed"), None, "could not land: tests failed"),
    (dict(status=candidates.COMMITTED), None, "committed, not pushed"),
    (dict(status=candidates.APPROVED, pushed=True, replied=True, landed_sha="a1b2c3d4e5f6a7"), None,
     "✓ landed a1b2c3d4e5f6 · pushed · replied"),
    (dict(status=candidates.APPROVED, pushed=True, reply_error="thread locked"), None,
     "reply failed: thread locked"),
    (dict(status=candidates.SKIPPED, reason="conversational"), None, "skipped: conversational"),
    (dict(status=candidates.FAILED, reason="no such file"), None, "failed: no such file"),
    (dict(status=candidates.REJECTED), None, "rework session running"),
    (dict(status=candidates.DISMISSED, declined=True, closing_reply="thanks anyway"), None,
     "declined · replied on GitHub"),
    (dict(status=candidates.REMOVED, comment_deleted=True), None, "comment removed from GitHub"),
    (dict(status=candidates.READY), "approve", "approving…"),
    (dict(status=candidates.READY), "dismiss", "dismissing…"),
])
def test_the_third_line_reports_what_the_table_says(tmp_path, record, intent, expected):
    row = row_for(tmp_path, make_record(**record), intent)
    assert f'<p class="aftermath">{html.escape(expected)}</p>' in row


def test_a_plain_dismissed_row_has_no_third_line(tmp_path):
    assert 'class="aftermath"' not in row_for(tmp_path, make_record(status=candidates.DISMISSED))


def test_a_settled_row_whose_comment_was_deleted_says_so_on_its_line(tmp_path):
    row = row_for(tmp_path, make_record(status=candidates.DISMISSED, comment_deleted=True))
    assert "comment removed from GitHub" in row


def test_a_working_row_shows_elapsed_and_not_the_agents_action(tmp_path, monkeypatch):
    monkeypatch.setattr(review_board, "_now",
                        lambda: datetime(2026, 8, 28, 10, 2, 14, tzinfo=timezone.utc))
    row = row_for(tmp_path, make_record(status=candidates.WORKING,
                                        started_at="2026-08-28T10:00:00Z"), None, "Edit foo.py")
    assert "agent running 2m 14s" in row
    assert "Edit foo.py" not in row


def test_the_rejected_pill_reads_reworking(tmp_path):
    assert '<span class="status rejected">reworking</span>' in row_for(
        tmp_path, make_record(status=candidates.REJECTED))


def test_a_minimal_record_renders_the_id_and_what_happened(tmp_path):
    row = row_for(tmp_path, {"comment_id": 77, "status": candidates.REMOVED, "comment_deleted": True})
    assert "comment #77" in row
    assert 'class="gist"' not in row
    assert "removed from GitHub before this board could read it" in row
    unreadable = row_for(tmp_path, {"comment_id": 78, "status": candidates.UNREADABLE})
    assert "comment #78" in unreadable and "could not be read" in unreadable


def test_reviewer_text_in_a_row_is_escaped(tmp_path):
    row = row_for(tmp_path, make_record(author="<b>x</b>", summary="<script>1</script>",
                                        status=candidates.FAILED, reason="<i>r</i>"))
    assert "<b>" not in row and "<script>" not in row and "<i>" not in row


def test_rows_returns_json_with_counts_and_sorted_metadata(tmp_path):
    candidates.save_candidate(tmp_path, REPO, PR, make_record(comment_id=1, status=candidates.DISMISSED, created_at="2026-01-01T00:00:00Z"))
    candidates.save_candidate(tmp_path, REPO, PR, make_record(comment_id=2, status=candidates.READY, created_at="2026-01-01T00:00:01Z"))
    candidates.save_candidate(tmp_path, REPO, PR, make_record(comment_id=3, status=candidates.WORKING, created_at="2026-01-01T00:00:02Z"))
    candidates.write_intent(tmp_path, REPO, PR, 2, "approve")
    status, ctype, body = get(tmp_path, "/rows")
    assert status == 200 and ctype == review_board._JSON
    payload = json.loads(body)
    assert "1 ready" in payload["summary"] and "card-state" not in payload["summary"]
    rows = {r["id"]: r for r in payload["rows"]}
    assert [r["id"] for r in payload["rows"]] == [1, 2, 3]
    assert rows[1]["band"] == 2 and rows[2]["band"] == 1 and rows[3]["band"] == 1
    assert rows[2]["sort"] < rows[3]["sort"]
    assert '<div class="row-head">' in rows[2]["html"]
    assert "approving…" in rows[2]["html"]


def test_a_row_that_fails_to_render_is_an_error_row_not_a_500(tmp_path, monkeypatch):
    candidates.save_candidate(tmp_path, REPO, PR, make_record(comment_id=1))

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(review_board, "render_row", boom)
    status, _, body = get(tmp_path, "/rows")
    assert status == 200
    row = json.loads(body)["rows"][0]
    assert row["band"] == review_board.BAND_WANTS_YOU
    assert "failed to render" in row["html"] and "comment 1" in row["html"]
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/github_pr_agent_manager/test_review_board.py -q -k "band or sort_key or row"`

- [ ] **Step 3: Implement**

Add `from github_orchestrator.common.summarize import fallback_summary` to the imports and `_JSON = "application/json; charset=utf-8"` beside `_HTML`. Beside `_display_status`:

```python
BAND_WANTS_YOU = 0
BAND_AGENT = 1
BAND_SETTLED = 2

_AGENT_STATUSES = frozenset({candidates.QUEUED, candidates.WORKING, candidates.REJECTED})


def band_of(record: dict, intent: str | None) -> int:
    if intent:
        return BAND_AGENT
    status = _display_status(record)
    if status in _AGENT_STATUSES:
        return BAND_AGENT
    if status == candidates.APPROVED:
        return BAND_WANTS_YOU if record.get("reply_error") else BAND_SETTLED
    if status == candidates.DISMISSED:
        return BAND_SETTLED
    return BAND_WANTS_YOU


def sort_key(record: dict) -> str:
    created = str(record.get("created_at") or "") or "~"
    try:
        comment_id = int(record.get("comment_id") or 0)
    except (TypeError, ValueError):
        comment_id = 0
    return f"{created}|{comment_id:020d}"
```

The pill logic lives in `render_card` today (`demoted`, `rebasing`, `pill`, `pill_class`). Lift it into a helper both can call:

```python
def _pill(record: dict, status: str) -> tuple[str, str]:
    if status == candidates.READY and record.get("reason"):
        return "failed to land", "needs-you"
    if status in (candidates.QUEUED, candidates.WORKING) and record.get("rebase_onto"):
        return "rebasing", status
    if status == candidates.APPROVED and record.get("reply_error"):
        return "needs you", "needs-you"
    if status == candidates.REJECTED:
        return "reworking", status
    return _STATUS_LABELS.get(status, status), status
```

and have `render_card` use `_pill` in place of its inline expression (its own tests keep passing because the outputs match for every status they cover; `rejected` now reads `reworking` on the card too, so update `test_the_rejected_pill_reads_as_the_rework_it_is_waiting_on` to the new wording and set `_STATUS_LABELS[REJECTED] = "reworking"`).

The third line:

```python
_MINIMAL_LINES = {
    candidates.UNREADABLE: "this card's record could not be read",
    candidates.REMOVED: "removed from GitHub before this board could read it",
}


def _is_minimal(record: dict) -> bool:
    return not record.get("author") and not record.get("body")


def _aftermath(record: dict, status: str, intent: str | None) -> str:
    if intent:
        return f"{_QUEUED_LABEL[intent]}…"
    if _is_minimal(record):
        return _MINIMAL_LINES.get(status, "")
    reason = str(record.get("reason") or "")
    if status == candidates.QUEUED:
        attempts = int(record.get("attempts") or 0)
        again = f" (attempt {attempts + 1} of {candidates.MAX_ATTEMPTS})" if attempts else ""
        return f"waiting for an agent{again}"
    if status == candidates.WORKING:
        return _running_text(record)
    if status == candidates.READY:
        return f"could not land: {reason}" if reason else ""
    if status == candidates.COMMITTED:
        return "committed, not pushed"
    if status == candidates.APPROVED and record.get("reply_error"):
        return f"reply failed: {record['reply_error']}"
    if status == candidates.SKIPPED:
        return f"skipped: {reason}" if reason else "skipped"
    if status == candidates.FAILED:
        return f"failed: {reason}" if reason else "failed"
    if status == candidates.REJECTED:
        return "rework session running"
    if status == candidates.REMOVED:
        return "comment removed from GitHub"
    line = _settled_line(record, status)
    if status == candidates.DISMISSED:
        line = line.lstrip("— ").strip()
        if line == "dismissed":
            line = ""
    if record.get("comment_deleted"):
        line = f"{line} · comment removed from GitHub" if line else "comment removed from GitHub"
    return line
```

`_running_line` returns a `<p>`; split it so both can share the text:

```python
def _running_text(record: dict) -> str:
    try:
        started = datetime.strptime(
            str(record.get("started_at")), "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return "agent running"
    seconds = max(int((_now() - started).total_seconds()), 0)
    return f"agent running {_format_elapsed(seconds)}"


def _running_line(record: dict) -> str:
    return f'<p class="agent-line">{_running_text(record)}</p>'
```

The row:

```python
def render_row(record: dict, repo: str, pr: int, intent: str | None,
               last_action: str | None = None) -> str:
    comment_id = int(record["comment_id"])
    status = _display_status(record)
    pill, pill_class = _pill(record, status)
    comment_type = str(record.get("comment_type") or "")
    type_label = _COMMENT_TYPE_LABELS.get(comment_type, comment_type)
    href = html.escape(comment_url(repo, pr, comment_type, comment_id), quote=True)
    path, line = record.get("path"), record.get("line")
    anchor_text = (f"{path}:{line}" if path and line is not None
                   else str(path or "") or f"comment #{comment_id}")
    head = [f'<span class="status {html.escape(pill_class)}">{html.escape(pill)}</span>']
    if record.get("author"):
        head.append(f'<span class="author">{html.escape(str(record["author"]))}</span>')
    if type_label:
        head.append(f'<span class="ctype">{html.escape(type_label)}</span>')
    head.append(f'<a class="anchor" href="{href}">{html.escape(anchor_text)}</a>')
    when_text = _relative_time(record.get("comment_created_at"))
    if when_text:
        head.append(f'<span class="when">{html.escape(when_text)}</span>')
    parts = [f'<div class="row-head">{"".join(head)}</div>']
    gist = str(record.get("summary") or "") or fallback_summary(str(record.get("body") or ""))
    if gist:
        parts.append(f'<p class="gist">{html.escape(gist)}</p>')
    aftermath = _aftermath(record, status, intent)
    if aftermath:
        parts.append(f'<p class="aftermath">{html.escape(aftermath)}</p>')
    return "".join(parts)
```

`last_action` is accepted so callers that have it can pass it, but the row never shows it; the panel does.

The payload and the endpoint:

```python
def _error_row(comment_id, message: str) -> str:
    escaped = html.escape(str(comment_id))
    return (f'<div class="row-head"><span class="status failed">error</span>'
            f'<span class="anchor">comment {escaped}</span></div>'
            f'<p class="aftermath">this card {html.escape(message)}; see agent-manager.log</p>')


def row_payload(candidates_dir: Path, repo: str, pr: int, record: dict) -> dict:
    comment_id = record.get("comment_id", 0)
    try:
        intent = candidates.read_intent(candidates_dir, repo, pr, int(comment_id))
    except (TypeError, ValueError):
        intent = None
    try:
        html_ = render_row(record, repo, pr, intent)
        band = band_of(record, intent)
    except Exception:
        log.exception("failed to render row %s for %s#%d", comment_id, repo, pr)
        html_, band = _error_row(comment_id, "failed to render"), BAND_WANTS_YOU
    return {"id": comment_id, "band": band, "sort": sort_key(record), "html": html_}


def render_counts(records: list[dict]) -> str:
    statuses = [_display_status(r) for r in records]
    counted = (
        (candidates.QUEUED, True),
        (candidates.WORKING, True),
        (candidates.READY, True),
        (candidates.COMMITTED, False),
        (candidates.APPROVED, True),
        (candidates.SKIPPED, False),
        (candidates.FAILED, False),
        (candidates.REJECTED, False),
        (candidates.DISMISSED, False),
        (candidates.REMOVED, False),
        (candidates.UNREADABLE, False),
    )
    overrides = {candidates.COMMITTED: "committed, not pushed"}
    return " · ".join(
        f"{statuses.count(s)} {overrides.get(s) or _STATUS_LABELS.get(s, s)}"
        for s, always in counted
        if always or statuses.count(s)
    )


def render_rows(candidates_dir: Path, repo: str, pr: int) -> str:
    records = candidates.list_candidates(candidates_dir, repo, pr)
    return json.dumps({
        "summary": render_counts(records),
        "rows": [row_payload(candidates_dir, repo, pr, r) for r in records],
    })
```

`render_summary` becomes `render_counts(records) + "".join(_card_state(...))` so its existing tests hold until Task 15 removes it. In `handle_get`, before the `/board` branch:

```python
    if path == "/rows":
        return 200, _JSON, render_rows(candidates_dir, repo, pr).encode()
```

- [ ] **Step 4: Run, full suite, commit**

```bash
git add src/github_orchestrator/github_pr_agent_manager/review_board.py tests/github_pr_agent_manager/test_review_board.py
git commit -m "GITHUB-ORCHESTRATOR: serve the board's rows as banded json"
```

______________________________________________________________________

### Task 12: the panel and its two routes

**Files:**

- Modify: `src/github_orchestrator/github_pr_agent_manager/review_board.py` (new `render_panel`, `panel_state`, `_panel_button`, routes; `_BoardServer`/`start_board`/`handle_get` gain `worktrees_dir` and `summary_model`)
- Modify: `src/github_orchestrator/github_pr_agent_manager/loop.py` where `start_board` is called (pass `CANDIDATE_WORKTREES_DIR` and `SUMMARY_MODEL`)
- Test: `tests/github_pr_agent_manager/test_review_board.py`

**Interfaces:**

- Consumes: `refresh_presence` (Task 9); `rebuild_candidate`, `RepairUnavailable` (Task 10); the card helpers `_comment_in_context`, `_comment_body`, `_land_notes`, `_running_line`, `_agent_statement`, `_LABELS`, `_TITLES`, `_TEXT_TAKING_DECISIONS`, `_QUEUED_LABEL`, `progress_line`.

- Produces: `render_panel(candidates_dir, repo, pr, repo_worktree, record, claude_enabled, base_branch, theme) -> str`; `panel_state(candidates_dir, repo, pr, record) -> str` (JSON); `_panel_button(comment_id, decision, status, label=None) -> str`; routes `GET /panel/<id>` and `GET /panel/<id>/state`; `handle_get(..., worktrees_dir: Path | None = None, summary_model: str | None = None)`.

- [ ] **Step 1: Write the failing tests**

Add a helper beside `get`:

```python
def get_panel(candidates_dir, comment_id, **kwargs):
    return get(candidates_dir, f"/panel/{comment_id}", **kwargs)
```

Tests:

```python
def test_the_panel_carries_its_state_on_the_body_element(tmp_path, fake_diff):
    candidates.save_candidate(tmp_path, REPO, PR, make_record(candidate_sha="abc", updated_at="u1"))
    candidates.write_intent(tmp_path, REPO, PR, 2314159, "approve")
    status, ctype, body = get_panel(tmp_path, 2314159)
    assert status == 200 and ctype == review_board._HTML
    html_ = body.decode()
    assert '<section id="panel-body"' in html_
    assert 'data-status="ready"' in html_ and 'data-intent="approve"' in html_
    assert 'data-updated="' in html_
    assert 'data-comment-deleted' not in html_


def test_the_panel_is_header_context_fix_notes_footer_in_that_order(tmp_path, fake_diff, fake_context):
    record = make_record(candidate_sha="abc123", tests="passed", agent_note="moved the close")
    candidates.save_candidate(tmp_path, REPO, PR, record)
    html_ = get_panel(tmp_path, 2314159)[2].decode()
    order = [html_.index('<header class="meta">'), html_.index("CONTEXT-2314159"),
             html_.index('<details class="diff"'), html_.index('class="tests"'),
             html_.index('class="agent-note"'), html_.index('<footer class="actions">')]
    assert order == sorted(order)
    assert 'id="panel-close"' in html_ and 'aria-label="close"' in html_
    assert 'class="gist"' not in html_


def test_an_in_progress_panel_warns_that_it_can_change(tmp_path, fake_context):
    for status in (candidates.QUEUED, candidates.WORKING, candidates.REJECTED):
        candidates.save_candidate(tmp_path, REPO, PR, make_record(status=status))
        html_ = get_panel(tmp_path, 2314159)[2].decode()
        assert 'class="under-work"' in html_
        assert "an agent is working on this" in html_
    candidates.save_candidate(tmp_path, REPO, PR, make_record(status=candidates.READY))
    assert 'class="under-work"' not in get_panel(tmp_path, 2314159)[2].decode()


def test_a_removed_panel_is_dimmed_under_a_bold_notice_and_still_offers_dismiss(tmp_path, fake_context):
    candidates.save_candidate(tmp_path, REPO, PR,
                              make_record(status=candidates.REMOVED, comment_deleted=True))
    html_ = get_panel(tmp_path, 2314159)[2].decode()
    assert '<h2 class="removed-banner">GitHub removed this comment</h2>' in html_
    assert 'class="panel-content dimmed"' in html_
    assert 'data-comment-deleted="1"' in html_
    assert buttons_of(html_) == {"dismiss"}


def test_a_settled_panel_whose_comment_was_deleted_keeps_its_content_legible(tmp_path, fake_context):
    candidates.save_candidate(tmp_path, REPO, PR, make_record(
        status=candidates.APPROVED, pushed=True, replied=True, landed_sha="abc1234",
        comment_deleted=True))
    html_ = get_panel(tmp_path, 2314159)[2].decode()
    assert '<p class="deleted-notice">GitHub no longer has this comment' in html_
    assert "removed-banner" not in html_ and "dimmed" not in html_


def test_panel_buttons_post_and_swap_nothing(tmp_path, fake_context):
    candidates.save_candidate(tmp_path, REPO, PR, make_record(candidate_sha="abc"))
    html_ = get_panel(tmp_path, 2314159)[2].decode()
    button = re.search(r'<button class="approve"[^>]*>', html_).group(0)
    assert 'hx-post="/candidate/2314159/decide"' in button
    assert 'hx-swap="none"' in button
    assert "hx-target" not in button and "hx-sync" not in button
    assert 'hx-include="#decide-body"' in button


def test_the_panel_state_is_the_fingerprint(tmp_path):
    candidates.save_candidate(tmp_path, REPO, PR, make_record(updated_at="u1", comment_deleted=True))
    candidates.write_intent(tmp_path, REPO, PR, 2314159, "approve")
    status, ctype, body = get(tmp_path, "/panel/2314159/state")
    assert status == 200 and ctype == review_board._JSON
    assert json.loads(body) == {"status": "ready", "intent": "approve",
                                "updated": "u1", "comment_deleted": True}


def test_both_panel_routes_refresh_presence_first(tmp_path, monkeypatch, fake_context):
    candidates.save_candidate(tmp_path, REPO, PR, make_record())
    seen = []

    def spy(candidates_dir, repo, pr, record):
        seen.append(record["comment_id"])
        return record

    monkeypatch.setattr(review_board, "refresh_presence", spy)
    get_panel(tmp_path, 2314159)
    get(tmp_path, "/panel/2314159/state")
    assert seen == [2314159, 2314159]


def test_a_gone_comment_re_renders_as_removed_on_the_same_request(tmp_path, monkeypatch, fake_context):
    candidates.save_candidate(tmp_path, REPO, PR, make_record())
    monkeypatch.setattr(review_board.presence, "comment_exists", lambda *a: False)
    html_ = get_panel(tmp_path, 2314159)[2].decode()
    assert 'data-status="removed"' in html_
    assert candidates.load_candidate(tmp_path, REPO, PR, 2314159)["status"] == candidates.REMOVED


def test_a_missing_record_is_rebuilt_and_its_panel_returned(tmp_path, monkeypatch, fake_context):
    def fake_rebuild(candidates_dir, worktrees_dir, repo, pr, pr_worktree, comment_id, summary_model):
        assert summary_model == "haiku" and worktrees_dir == tmp_path / "wt"
        record = make_record(comment_id=comment_id, status=candidates.QUEUED)
        candidates.save_candidate(candidates_dir, repo, pr, record)
        return record

    monkeypatch.setattr(review_board, "rebuild_candidate", fake_rebuild)
    status, _, body = review_board.handle_get(
        tmp_path, REPO, PR, WORKTREE, "/panel/2314159",
        worktrees_dir=tmp_path / "wt", summary_model="haiku")
    assert status == 200 and 'data-status="queued"' in body.decode()


def test_a_rebuild_github_cannot_answer_is_a_503_with_a_reason(tmp_path, monkeypatch):
    def down(*args, **kwargs):
        raise review_board.RepairUnavailable("connection reset")

    monkeypatch.setattr(review_board, "rebuild_candidate", down)
    status, ctype, body = get_panel(tmp_path, 2314159)
    assert status == 503 and ctype == review_board._JSON
    assert "connection reset" in json.loads(body)["error"]


def test_state_for_a_missing_record_is_404(tmp_path):
    assert get(tmp_path, "/panel/2314159/state")[0] == 404
```

`fake_context` already exists in the file (`:4500`); it renders `CONTEXT-<id>`.

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/github_pr_agent_manager/test_review_board.py -q -k panel`

- [ ] **Step 3: Implement**

Imports:

```python
from github_orchestrator.github_pr_agent_manager import presence
from github_orchestrator.github_pr_agent_manager.presence import refresh_presence
from github_orchestrator.github_pr_agent_manager.candidate_repair import (
    RepairUnavailable,
    rebuild_candidate,
)
```

Routes:

```python
_PANEL_RE = re.compile(r"^/panel/(\d+)$")
_PANEL_STATE_RE = re.compile(r"^/panel/(\d+)/state$")
```

The button for the panel:

```python
def _panel_button(comment_id: int, decision: str, status: str,
                  label: str | None = None) -> str:
    title = html.escape(_TITLES[decision], quote=True)
    vals = html.escape(
        json.dumps({"d": decision, "s": status, "i": ""}, separators=(",", ":")),
        quote=False,
    ).replace("'", "&#x27;")
    include = (' hx-include="#decide-body"'
               if decision in _TEXT_TAKING_DECISIONS else "")
    return (
        f'<button class="{html.escape(decision, quote=True)}" '
        f'title="{title}" '
        f'hx-post="/candidate/{comment_id}/decide" '
        f"hx-vals='{vals}' "
        f'hx-swap="none"{include}>'
        f"{html.escape(label or decision)}</button>"
    )


def _actions_for(record: dict, status: str, claude_enabled: bool) -> tuple[str, ...]:
    actions = _ACTIONS.get(status, ())
    if status in (candidates.READY, candidates.REMOVED) and not record.get("candidate_sha"):
        actions = tuple(d for d in actions if d != "approve")
    if record.get("comment_type") != "review":
        actions = tuple(d for d in actions if d != "decline")
    if status == candidates.APPROVED and record.get("reply_error"):
        actions = ("approve",)
    if not claude_enabled:
        actions = tuple(d for d in actions if d != "reject")
    return actions
```

Replace the matching block in `render_card` with a call to `_actions_for` so the two never drift.

The panel:

```python
_IN_PROGRESS = frozenset({candidates.QUEUED, candidates.WORKING, candidates.REJECTED})


def _panel_notes(record: dict, status: str, last_action: str | None,
                 progress: str | None) -> list[str]:
    parts = []
    if status == candidates.QUEUED:
        attempts = int(record.get("attempts") or 0)
        again = (f" (attempt {attempts + 1} of {candidates.MAX_ATTEMPTS})"
                 if attempts else "")
        parts.append(f'<p class="agent-line">waiting for an agent…{again}</p>')
    elif status == candidates.WORKING:
        parts.append(_running_line(record))
        if last_action:
            parts.append(f'<p class="agent-action">{html.escape(last_action)}</p>')
    if progress:
        parts.append(f'<p class="agent-progress">{html.escape(progress)}</p>')
    if record.get("reason"):
        verdict = {candidates.SKIPPED: "skipped: ",
                   candidates.FAILED: "failed: ",
                   candidates.READY: "could not land: ",
                   candidates.REJECTED: "before rework: ",
                   candidates.DISMISSED: "before dismissal: ",
                   candidates.REMOVED: "before the comment was deleted: "}.get(
                       status, "previous attempt failed: ")
        classes = "reason land-error" if status == candidates.READY else "reason"
        parts.append(f'<details class="{classes}"><summary>{verdict}'
                     f'{html.escape(str(record["reason"]))}</summary></details>')
    if record.get("rebase_conflict"):
        onto = html.escape(str(record.get("rebase_onto") or "")[:12])
        parts.append(f'<details class="reason land-error"><summary>could not land on '
                     f'{onto}: {html.escape(str(record["rebase_conflict"]))}'
                     "</summary></details>")
    if record.get("decision_error"):
        parts.append(f'<p class="land-error">{html.escape(str(record["decision_error"]))}</p>')
    if record.get("tests"):
        note = record.get("tests_note")
        text = f"tests {record['tests']}" + (f" — {note}" if note else "")
        parts.append(f'<p class="tests">{html.escape(text)}</p>')
    if record.get("agent_note"):
        parts.append(f'<p class="agent-note">{html.escape(str(record["agent_note"]))}</p>')
    parts.extend(_land_notes(record))
    return parts
```

`render_card` has this same block inline; make it call `_panel_notes` too (its output is identical) so there is one copy.

```python
def render_panel(candidates_dir: Path, repo: str, pr: int, repo_worktree: str,
                 record: dict, claude_enabled: bool = True,
                 base_branch: str | None = None, theme: str = "light") -> str:
    comment_id = int(record["comment_id"])
    status = _display_status(record)
    intent = candidates.read_intent(candidates_dir, repo, pr, comment_id)
    last_action = candidates.read_action(candidates_dir, repo, pr, comment_id)
    progress = (None if status in (candidates.APPROVED, candidates.DISMISSED)
                else progress_line(record.get("worktree"), record.get("base_sha")))
    pill, pill_class = _pill(record, status)
    comment_type = str(record.get("comment_type") or "")
    type_label = _COMMENT_TYPE_LABELS.get(comment_type, comment_type)
    href = html.escape(comment_url(repo, pr, comment_type, comment_id), quote=True)
    path, line = record.get("path"), record.get("line")
    anchor_text = (f"{path}:{line}" if path and line is not None
                   else str(path or "") or f"comment #{comment_id}")
    when_text = _relative_time(record.get("comment_created_at"))
    header = (
        '<header class="meta">'
        f'<span class="status {html.escape(pill_class)}">{html.escape(pill)}</span>'
        f'<span class="author">{html.escape(str(record.get("author") or ""))}</span>'
        + (f'<span class="ctype">{html.escape(type_label)}</span>' if type_label else "")
        + f'<a class="anchor" href="{href}">{html.escape(anchor_text)}</a>'
        + (f'<span class="when">{html.escape(when_text)}</span>' if when_text else "")
        + '<button id="panel-close" type="button" title="close" aria-label="close">×</button>'
        "</header>"
    )
    notices = []
    if status in _IN_PROGRESS:
        notices.append('<p class="under-work">an agent is working on this, so what '
                       "you see here can change</p>")
    removed = status == candidates.REMOVED
    if removed:
        notices.append('<h2 class="removed-banner">GitHub removed this comment</h2>')
    elif record.get("comment_deleted"):
        notices.append('<p class="deleted-notice">GitHub no longer has this comment; '
                       "everything here is still what happened</p>")
    anchored = bool(path) and path != "general" and line is not None
    if _is_minimal(record):
        content = [f'<p class="agent-line">{html.escape(_MINIMAL_LINES.get(status, ""))}</p>']
    else:
        content = [_comment_in_context(record, base_branch, theme) if anchored
                   else _comment_body(record)]
    if record.get("candidate_sha"):
        full = html.escape(str(record["candidate_sha"]))
        sha = html.escape(str(record["candidate_sha"])[:12])
        content.append(
            '<div class="fix-fold">'
            '<button class="copy-sha" title="copy the full commit hash">copy hash</button>'
            f'<code class="sha-full" hidden>{full}</code>'
            f'<details class="diff" hx-get="/candidate/{comment_id}/diff" '
            'hx-trigger="toggle once" hx-target="find .diff-slot" hx-swap="innerHTML">'
            f"<summary>view diff — agent committed {sha}</summary>"
            '<div class="diff-slot">loading diff…</div></details></div>')
    content.extend(_panel_notes(record, status, last_action, progress))
    buttons = "".join(
        _panel_button(comment_id, d, status, _LABELS.get((status, d)))
        for d in _actions_for(record, status, claude_enabled))
    footer = _action_footer(intent, buttons)
    statement = _agent_statement(record)
    attrs = (f' data-status="{html.escape(status, quote=True)}"'
             + (f' data-intent="{html.escape(intent, quote=True)}"' if intent else "")
             + (f' data-updated="{html.escape(str(record["updated_at"]), quote=True)}"'
                if record.get("updated_at") else "")
             + (' data-comment-deleted="1"' if record.get("comment_deleted") else "")
             + (f' data-statement="{html.escape(statement, quote=True)}"' if statement else ""))
    dimmed = " dimmed" if removed else ""
    return (f'<section id="panel-body"{attrs}>{header}{"".join(notices)}'
            f'<div class="panel-content{dimmed}">{"".join(content)}</div>'
            f"{footer}</section>")


def panel_state(candidates_dir: Path, repo: str, pr: int, record: dict) -> str:
    return json.dumps({
        "status": _display_status(record),
        "intent": candidates.read_intent(candidates_dir, repo, pr, int(record["comment_id"])),
        "updated": str(record.get("updated_at") or ""),
        "comment_deleted": bool(record.get("comment_deleted")),
    })


def _safe_panel(candidates_dir, repo, pr, repo_worktree, record, claude_enabled,
                base_branch, theme) -> str:
    try:
        return render_panel(candidates_dir, repo, pr, repo_worktree, record,
                            claude_enabled, base_branch, theme)
    except Exception:
        log.exception("failed to render the panel for %s for %s#%d",
                      record.get("comment_id"), repo, pr)
        return ('<section id="panel-body" data-status="error"><p class="land-error">'
                "this comment's panel failed to render; see agent-manager.log</p></section>")
```

In `handle_get`, add `worktrees_dir: Path | None = None, summary_model: str | None = None` to the signature and, after the `/rows` branch:

```python
    match = _PANEL_STATE_RE.match(path)
    if match:
        record = candidates.load_candidate(candidates_dir, repo, pr, int(match.group(1)))
        if record is None:
            return _not_found()
        record = refresh_presence(candidates_dir, repo, pr, record)
        return 200, _JSON, panel_state(candidates_dir, repo, pr, record).encode()
    match = _PANEL_RE.match(path)
    if match:
        comment_id = int(match.group(1))
        record = candidates.load_candidate(candidates_dir, repo, pr, comment_id)
        if record is None:
            try:
                record = rebuild_candidate(candidates_dir, worktrees_dir, repo, pr,
                                           repo_worktree, comment_id, summary_model)
            except RepairUnavailable as exc:
                return 503, _JSON, json.dumps({"error": str(exc)}).encode()
        record = refresh_presence(candidates_dir, repo, pr, record)
        body = _safe_panel(candidates_dir, repo, pr, repo_worktree, record,
                           claude_enabled, base_branch, _theme(parsed.query))
        return 200, _HTML, body.encode()
```

`_BoardServer.__init__`, `start_board` and `_BoardHandler.do_GET` thread `worktrees_dir` and `summary_model` through the same way `base_branch` is threaded today. In `loop.py`, the `start_board(...)` call passes `worktrees_dir=CANDIDATE_WORKTREES_DIR, summary_model=SUMMARY_MODEL if config.claude_enabled else None` (import both from `common.config`; `config` is the loaded settings object the loop already holds).

- [ ] **Step 4: Run, full suite, commit**

```bash
git add src/github_orchestrator/github_pr_agent_manager/review_board.py src/github_orchestrator/github_pr_agent_manager/loop.py tests/github_pr_agent_manager/test_review_board.py
git commit -m "GITHUB-ORCHESTRATOR: render one comment's panel and its fingerprint"
```

______________________________________________________________________

### Task 13: a decision answers with the row

**Files:**

- Modify: `src/github_orchestrator/github_pr_agent_manager/review_board.py:1394-1403` (`handle_post`)
- Test: `tests/github_pr_agent_manager/test_review_board.py:739-1058`

**Interfaces:**

- Consumes: `row_payload` (Task 11).

- Produces: `POST /candidate/<id>/decide` returns `200` or `409` with `_JSON` and the row payload.

- [ ] **Step 1: Rewrite the decide tests that read a card out of the POST**

Every test in `739-1058` that parses the response body as a card now parses JSON. The shape:

```python
def test_decide_writes_intent_and_returns_the_row(tmp_path):
    candidates.save_candidate(tmp_path, REPO, PR, make_record())
    status, ctype, body = post(tmp_path, "/candidate/2314159/decide", b"d=approve&s=ready")
    assert status == 200 and ctype == review_board._JSON
    row = json.loads(body)
    assert row["id"] == 2314159 and row["band"] == review_board.BAND_AGENT
    assert "approving…" in row["html"]
    assert candidates.read_intent(tmp_path, REPO, PR, 2314159) == "approve"


def test_a_refused_decision_answers_with_the_row_as_it_is(tmp_path):
    candidates.save_candidate(tmp_path, REPO, PR, make_record(status=candidates.WORKING))
    status, ctype, body = post(tmp_path, "/candidate/2314159/decide", b"d=approve&s=ready")
    assert status == 409 and ctype == review_board._JSON
    row = json.loads(body)
    assert '<span class="status working">' in row["html"]
    assert candidates.read_intent(tmp_path, REPO, PR, 2314159) is None
```

Walk the region test by test: keep every assertion about intents, payloads, 403s, 404s and 400s; change only how the body is read. `test_the_refusal_answers_with_the_card_as_it_actually_is` and `test_a_decide_response_that_lost_its_intent_still_hides_reject` become row assertions (`"reject"` no longer appears anywhere in a row, so the second one asserts the row's pill and band instead).

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/github_pr_agent_manager/test_review_board.py -q -k decide`

- [ ] **Step 3: Implement**

Replace the two `_safe_card(...)` returns at the end of `handle_post`:

```python
    body = json.dumps(row_payload(candidates_dir, repo, pr, record)).encode()
    if stale:
        log.info("refusing %s for %s#%d comment %d: the card said %r/%r, "
                 "the record is %r/%r", decision, repo, pr, comment_id, seen,
                 seen_intent, record.get("status"), queued)
        return 409, _JSON, body
    return 200, _JSON, body
```

`handle_post`'s `repo_worktree`, `claude_enabled`, `base_branch` parameters stay for now; Task 15 drops the ones nothing reads.

- [ ] **Step 4: Run, full suite, commit**

```bash
git add src/github_orchestrator/github_pr_agent_manager/review_board.py tests/github_pr_agent_manager/test_review_board.py
git commit -m "GITHUB-ORCHESTRATOR: answer a decision with the row it changes"
```

______________________________________________________________________

### Task 14a: the page: shell, stylesheet and the script's core

**Files:**

- Modify: `src/github_orchestrator/github_pr_agent_manager/review_board.py:189-780` (`_PAGE`), `render_page`
- Test: `tests/github_pr_agent_manager/test_review_board.py` (the script tests from `:1738` to `:3300`, the stub DOM at `:2016-2662`)

**Interfaces:**

- Consumes: `/rows` (Task 11), `/panel/<id>`, `/panel/<id>/state` (Task 12), POST row JSON (Task 13).
- Produces: the new page. Client state `selected`, `cursor`. Functions `reconcile`, `applyOrder`, `openRow`, `closePanel`, `mergeRow`, `lostContact`, `contactRestored`. Hooks for 14b: `applyOrder` honours `held()`, `releaseHold()`, `placeNotch()`, `keepSelectedInView()` exist as no-ops here and are filled in 14b.

This task replaces the script wholesale, so the tests that read the old script's text go with it. Delete, in `test_review_board.py`: every test between `:1816` (`test_keyboard_walk_tracks_the_focused_card_by_id`) and `:3300` (up to `save_every_status`) except the dialog wording tests that read `DIALOGS` (`:2702-2860` region: keep `dialog_spec`, `dialog_verbs`, `test_every_verb_but_retry_asks_in_a_dialog`, `test_the_dialogs_ask_in_the_operators_words`, `test_the_dialogs_that_take_text_say_where_it_goes`, `test_the_approve_dialog_takes_a_reply_and_the_submit_says_so`, `test_the_reject_dialog_takes_notes_and_the_submit_says_so`, `test_the_dismiss_dialog_takes_a_reply_and_the_submit_says_so`, `test_the_dialog_verbs_match_the_classes_the_buttons_carry`, `test_every_verb_the_board_renders_is_one_the_script_recognises`; the last two must read buttons out of `render_panel` instead of `render_card`), the banner wording tests (`:1907-1999`) which still apply, and the page-shell tests (`:1738-1797`). Also delete `_STUB_DOM` and `_BEHAVIOUR_ASSERTIONS`; this task writes new ones. Keep `handler_of`, `function_of`, `page_script`, `page_shell`, `joined_literals`.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_shell_is_two_panes_under_a_frozen_left_header(tmp_path):
    shell = page_shell(tmp_path)
    for needle in ('<div id="shell">', '<div id="left">', '<div id="left-header">',
                   '<ul id="rows" role="listbox"', '<aside id="panel"',
                   '<div id="panel-notch"', '<div id="panel-content">',
                   '<p id="empty-board" hidden>'):
        assert needle in shell, needle
    assert shell.index('id="left-header"') < shell.index('id="rows"') < shell.index('id="panel"')
    assert "hx-get=\"/board\"" not in shell and "hx-get=\"/summary\"" not in shell


def test_the_body_never_scrolls_and_the_panes_do(tmp_path):
    shell = page_shell(tmp_path)
    assert "100dvh" in css_rule(shell, "body") and "overflow: hidden" in css_rule(shell, "body")
    assert "overflow-y: auto" in css_rule(shell, "#rows")
    assert "overflow-y: auto" in css_rule(shell, "#panel-content")


def test_the_list_is_centred_closed_and_slides_left_open(tmp_path):
    shell = page_shell(tmp_path)
    assert "margin: 0 auto" in css_rule(shell, "#shell")
    assert "max-width: 62rem" in css_rule(shell, "#shell")
    assert "transition: max-width 200ms" in css_rule(shell, "#shell")
    assert "width: 28rem" in css_rule(shell, "body.open #left")
    assert "display: none" in css_rule(shell, "#panel")
    assert "display: flex" in css_rule(shell, "body.open #panel")


def test_the_selected_row_opens_into_the_panel(tmp_path):
    shell = page_shell(tmp_path)
    assert "border-right-color: transparent" in css_rule(shell, "body.open li.selected")
    assert "position: absolute" in css_rule(shell, "#panel-notch")
    assert "border-left: 1px solid var(--info)" in css_rule(shell, "#panel")


def test_the_page_script_rests_on_fetch_for_rows_and_htmx_for_the_panel(tmp_path):
    script = page_script(page_shell(tmp_path))
    assert 'fetch("/rows"' in script
    assert 'htmx.ajax("GET", "/panel/" + id' in script
    assert "/board" not in script and "card-state" not in script
    assert "heldStill" not in script and "paused" not in script


def test_the_legend_and_empty_state_describe_the_panel(tmp_path):
    shell = page_shell(tmp_path)
    legend = key_help_block(shell)
    assert "<dt>j</dt><dd>open the next comment</dd>" in legend
    assert "<dt>k</dt><dd>open the previous comment</dd>" in legend
    assert "<dt>Esc</dt><dd>close the open comment</dd>" in legend
    assert "act on the open comment" in legend
    empty = re.search(r'<p id="empty-board" hidden>(.*?)</p>', shell, re.DOTALL).group(1)
    assert "No comments on your PR" in empty
    assert "j and k open and walk the comments" in empty
```

`css_rule` and `key_help_block` already exist in the file. Then the two node tests, rewritten. `test_the_page_script_parses` is unchanged. The stub DOM and the assertions:

```python
_STUB_DOM = r"""
const listeners = new Map();
const on = (target, type, fn) => {
  const key = target.__id + ":" + type;
  (listeners.get(key) || listeners.set(key, []).get(key)).push(fn);
};
function fire(target, type, event) {
  event = event || {};
  event.defaultPrevented = false;
  event.preventDefault = function () { this.defaultPrevented = true; };
  event.target = event.target || target;
  (listeners.get(target.__id + ":" + type) || []).forEach((fn) => fn(event));
  return !event.defaultPrevented;
}
function classList(el) {
  const set = new Set();
  return {
    add: (n) => set.add(n), remove: (n) => set.delete(n), contains: (n) => set.has(n),
    toggle: (n, force) => { (force === undefined ? !set.has(n) : force) ? set.add(n) : set.delete(n); },
    list: () => Array.from(set),
  };
}
let NOW = 0;
function Date() { return {toLocaleTimeString: () => "09:41"}; }
Date.now = () => NOW;
let nextId = 0;
function element(tag, id) {
  const el = {
    __id: id || ("el" + (nextId++)), id: id || "", tagName: tag.toUpperCase(),
    children: [], parentNode: null, attributes: {}, dataset: {}, style: {},
    hidden: false, innerHTML: "", textContent: "", value: "", scrollTop: 0,
    offsetHeight: 40, clientHeight: 400, tabIndex: 0,
    rect: null, disabled: false,
    classList: null,
    get index() { return this.parentNode ? this.parentNode.children.indexOf(this) : 0; },
    get offsetTop() { return this.index * 40; },
    addEventListener(type, fn) { on(this, type, fn); },
    setAttribute(name, v) { this.attributes[name] = String(v); },
    getAttribute(name) { return this.attributes[name] === undefined ? null : this.attributes[name]; },
    appendChild(child) {
      if (child.parentNode) child.parentNode.removeChild(child);
      child.parentNode = this; this.children.push(child); return child;
    },
    removeChild(child) {
      this.children = this.children.filter((c) => c !== child); child.parentNode = null;
    },
    remove() { if (this.parentNode) this.parentNode.removeChild(this); },
    getBoundingClientRect() {
      const rect = this.rect || {top: this.index * 40, height: 40};
      return {top: rect.top, height: rect.height, bottom: rect.top + rect.height};
    },
    scrollTo(opts) { this.scrolledTo = opts; this.scrollTop = opts.top; },
    scrollIntoView() {},
    focus() { document.activeElement = this; },
    blur() { document.activeElement = null; },
    closest(sel) {
      let node = this;
      while (node) { if (node.matches && node.matches(sel)) return node; node = node.parentNode; }
      return null;
    },
    matches(sel) {
      if (sel === "li[role=option]") return this.tagName === "LI";
      if (sel === "a") return this.tagName === "A";
      if (sel === "#panel-close") return this.id === "panel-close";
      if (sel === "#panel-body button") return this.tagName === "BUTTON" && !!this.closest("#panel-body");
      if (sel === "#panel-body") return this.id === "panel-body";
      if (sel === '[role="button"]') return this.attributes.role === "button";
      return false;
    },
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
    querySelectorAll(sel) {
      if (sel.startsWith("#panel-body button.")) {
        const pb = document.getElementById("panel-body");
        return pb ? pb.querySelectorAll("button." + sel.slice("#panel-body button.".length)) : [];
      }
      const out = [];
      const walk = (node) => node.children.forEach((c) => { if (c.matches(sel) || (sel.startsWith("button.") && c.tagName === "BUTTON" && c.classList.contains(sel.slice(7)))) out.push(c); walk(c); });
      walk(this); return out;
    },
    animate() { this.animated = (this.animated || 0) + 1; return {}; },
  };
  el.classList = classList(el);
  return el;
}
const byId = {};
const make = (tag, id) => { const el = element(tag, id); if (id) byId[id] = el; return el; };
function findById(node, id) {
  for (const child of node.children) {
    if (child.id === id) return child;
    const hit = findById(child, id);
    if (hit) return hit;
  }
  return null;
}
const body = make("body", "body");
const shell = make("div", "shell"); body.appendChild(shell);
const left = make("div", "left"); shell.appendChild(left);
const leftHeader = make("div", "left-header"); left.appendChild(leftHeader);
const rowsEl = make("ul", "rows"); left.appendChild(rowsEl);
const panel = make("aside", "panel"); shell.appendChild(panel);
const notch = make("div", "panel-notch"); panel.appendChild(notch);
const panelContent = make("div", "panel-content"); panel.appendChild(panelContent);
["summary", "empty-board", "error-banner", "error-text", "error-card", "banner-close",
 "server-died", "key-help", "key-help-toggle", "disabled-notice"].forEach((id) => {
  const el = make(id === "key-help-toggle" || id === "banner-close" ? "button" : "div", id);
  leftHeader.appendChild(el);
});
byId["key-help"].hidden = true; byId["error-banner"].hidden = true;
byId["server-died"].hidden = true; byId["empty-board"].hidden = true;
const dialog = make("dialog", "decide-dialog");
dialog.open = false;
dialog.showModal = function () { this.open = true; };
dialog.close = function () { this.open = false; fire(this, "close", {}); };
const decideForm = make("form", "decide-form");
const decideBody = make("textarea", "decide-body");
const decideSubmit = make("button", "decide-submit");
const decideQuote = make("button", "decide-quote");
const decideCancel = make("button", "decide-cancel");
make("h2", "decide-question"); make("p", "decide-note");
const posted = [];
const ajaxed = [];
const htmx = {
  ajax: (verb, path, opts) => { ajaxed.push(verb + " " + path); return Promise.resolve(); },
  process: () => {},
};
const document = {
  activeElement: null,
  body: body,
  addEventListener: (type, fn) => on(document, type, fn),
  __id: "document",
  getElementById: (id) => byId[id] || findById(body, id),
  createElement: (tag) => element(tag),
  querySelector: (sel) => body.querySelector(sel),
  querySelectorAll: (sel) => body.querySelectorAll(sel),
  createRange: () => ({selectNodeContents: () => {}}),
};
const timers = [];
const setInterval = (fn, ms) => { timers.push({fn, ms}); return timers.length; };
const clearInterval = () => {};
const pendingTimeouts = [];
const setTimeout = (fn, ms) => { pendingTimeouts.push(fn); return pendingTimeouts.length; };
const clearTimeout = (id) => { if (id) pendingTimeouts[id - 1] = null; };
const requestAnimationFrame = (fn) => { fn(); return 1; };
const window = {
  __id: "window", innerHeight: 800,
  addEventListener: (type, fn) => on(window, type, fn),
  matchMedia: (q) => ({matches: false}),
  getSelection: () => ({removeAllRanges: () => {}, addRange: () => {}}),
};
const navigator = {};
let fetchQueue = [];
const fetch = (path) => {
  const next = fetchQueue.shift();
  if (!next) return Promise.reject(new Error("no scripted response for " + path));
  if (next.fail) return Promise.reject(new Error("dropped"));
  return Promise.resolve({ok: next.status === undefined || next.status < 400,
                          status: next.status || 200, json: () => Promise.resolve(next.body)});
};
const respond = (body, status) => fetchQueue.push({body, status});
const drop = () => fetchQueue.push({fail: true});
const flushTimeouts = () => { const fns = pendingTimeouts.splice(0); fns.forEach((fn) => fn && fn()); };
const tick = () => new Promise((r) => setImmediate(r));
const press = (key) => fire(document, "keydown", {key, metaKey: false, ctrlKey: false, altKey: false, shiftKey: key === "?"});
const row = (id, band, sort, html) => ({id, band, sort, html: html || ("<div class=\"row-head\">" + id + "</div>")});
const ids = () => rowsEl.children.map((li) => li.id);
const selectedIds = () => rowsEl.children.filter((li) => li.classList.contains("selected")).map((li) => li.id);
const pending = () => rowsEl.children.filter((li) => li.classList.contains("pending-move")).map((li) => li.id);
const R = (id) => document.getElementById(id);
const clickRow = (id) => fire(rowsEl, "click", {target: R(id)});
let checkFailures = 0;
function check(ok, what) { if (!ok) { console.error("FAIL: " + what); checkFailures += 1; } }
"""

_BEHAVIOUR_ASSERTIONS = r"""
(async () => {
const pollRows = timers.find((t) => t.ms === 2000).fn;

// A first poll lays the rows out in band order, and the counters land in the header.
respond({summary: "2 ready · 1 landed", rows: [
  row(1, 2, "2026-01-01T00:00:00Z|1"), row(2, 0, "2026-01-01T00:00:01Z|2"), row(3, 0, "2026-01-01T00:00:02Z|3")]});
await pollRows(); await tick();
check(ids().join() === "c-2,c-3,c-1", "rows sort by band then key: " + ids().join());
check(byId.summary.innerHTML === "2 ready · 1 landed", "the counters ride on the rows poll");
check(byId["empty-board"].hidden === true, "a board with rows hides the empty state");
check(R("c-2").attributes.role === "option" && R("c-2").attributes["aria-selected"] === "false",
      "a row is an unselected listbox option");

// Content changes land in place; a band change moves the row.
respond({summary: "", rows: [
  row(1, 0, "2026-01-01T00:00:00Z|1"), row(2, 0, "2026-01-01T00:00:01Z|2", "<div class=\"row-head\">changed</div>"),
  row(3, 0, "2026-01-01T00:00:02Z|3")]});
await pollRows(); await tick();
check(R("c-2").innerHTML.includes("changed"), "row content updates in place");
check(ids().join() === "c-1,c-2,c-3", "a band change reorders when nothing holds the list: " + ids().join());

// Nothing is selected until the user says so; j opens the top row and the panel.
check(selectedIds().length === 0 && !body.classList.contains("open"), "the page opens with the panel closed");
press("j"); flushTimeouts(); await tick();
check(selectedIds().join() === "c-1", "the first j selects the top row");
check(body.classList.contains("open"), "and opens the panel");
check(ajaxed.pop() === "GET /panel/1", "fetching that row's panel through htmx");
check(R("c-1").attributes["aria-selected"] === "true", "the selected row says so to a screen reader");
press("j"); flushTimeouts(); await tick();
check(selectedIds().join() === "c-2" && ajaxed.pop() === "GET /panel/2", "j walks to the next row and switches the panel");
press("j"); press("j"); flushTimeouts(); await tick();
check(selectedIds().join() === "c-3", "j clamps at the last row");
press("k"); flushTimeouts(); await tick();
check(selectedIds().join() === "c-2", "k walks back");

// Escape closes the panel and forgets the selection but not the position.
check(press("Escape") === false, "Escape is consumed while a panel is open");
check(selectedIds().length === 0 && !body.classList.contains("open"), "Escape closes the panel and clears the selection");
press("j"); flushTimeouts(); await tick();
check(selectedIds().join() === "c-3", "j after a close resumes below where the cursor was");
press("Escape");
press("k"); flushTimeouts(); await tick();
check(selectedIds().join() === "c-2", "k after a close resumes above where the cursor was");
press("Escape");

// Clicking: a row opens, the selected row closes, empty space closes, the × closes.
clickRow("c-2"); flushTimeouts(); await tick();
check(selectedIds().join() === "c-2", "clicking a row opens it");
clickRow("c-2"); await tick();
check(selectedIds().length === 0, "clicking the selected row closes the panel");
clickRow("c-3"); flushTimeouts(); await tick();
fire(rowsEl, "click", {target: rowsEl});
check(selectedIds().length === 0, "clicking empty space in the list closes the panel");
clickRow("c-3"); flushTimeouts(); await tick();
const closeButton = make("button", "panel-close"); panelContent.appendChild(closeButton);
fire(panel, "click", {target: closeButton});
check(selectedIds().length === 0, "the panel's × closes it");

// a/r/d act only on an open comment.
const panelBody = make("section", "panel-body");
panelBody.dataset.status = "ready";
const approve = make("button", "approve-button"); approve.classList.add("approve");
approve.click = () => { fire(body, "htmx:confirm", {detail: {elt: approve, issueRequest: () => posted.push("approve")}}); };
panelBody.appendChild(approve);
press("a");
check(posted.length === 0 && dialog.open === false, "a does nothing while the panel is closed");
clickRow("c-2"); flushTimeouts(); await tick();
panelContent.appendChild(panelBody);
press("a");
check(dialog.open === true && posted.length === 0, "a on an open comment asks in the dialog first");
fire(decideForm, "submit", {}); dialog.close();
check(posted.join() === "approve", "confirming posts the held request");
check(selectedIds().length === 0 && !body.classList.contains("open"), "and closes the panel the instant it is confirmed");

// The decision's response is a row, merged straight in.
fire(body, "htmx:afterRequest", {detail: {elt: approve, xhr: {status: 200, responseText: JSON.stringify(row(2, 1, "2026-01-01T00:00:01Z|2", "<div class=\"row-head\">approving…</div>"))}}});
check(R("c-2").innerHTML.includes("approving…"), "the row shows the queued decision from the POST's answer");
check(ids().join() === "c-1,c-3,c-2", "and moves to the band the answer names: " + ids().join());

// A row that vanishes from the poll leaves; if it was open, the panel closes and the banner says so.
clickRow("c-3"); flushTimeouts(); await tick();
respond({summary: "", rows: [row(1, 0, "2026-01-01T00:00:00Z|1"), row(2, 1, "2026-01-01T00:00:01Z|2")]});
await pollRows(); await tick();
check(ids().join() === "c-1,c-2", "a row absent from the poll is removed");
check(selectedIds().length === 0 && byId["error-banner"].hidden === false, "an open row that vanishes closes the panel and says so");

// An empty board shows the empty state.
respond({summary: "0 queued", rows: []});
await pollRows(); await tick();
check(byId["empty-board"].hidden === false, "an empty board shows its explanation");

// Two dropped polls take the panes down and leave the header; the next answer brings them back.
byId["error-banner"].hidden = true;
drop(); await pollRows(); await tick();
check(byId["server-died"].hidden === true, "one dropped poll does not take the board over");
drop(); await pollRows(); await tick();
check(byId["server-died"].hidden === false && rowsEl.hidden === true && panel.hidden === true,
      "a second dropped poll puts the notice up and hides both panes");
check(leftHeader.hidden === false && byId.summary.hidden === false, "the header is not among what hides");
check(press("j") === true && selectedIds().length === 0, "no key answers while the notice is up");
respond({summary: "", rows: [row(1, 0, "a|1")]});
await pollRows(); await tick();
check(byId["server-died"].hidden === true && rowsEl.hidden === false && panel.hidden === false,
      "the first answer back hands the panes back");

process.exit(checkFailures ? 1 : 0);
})();
"""
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/github_pr_agent_manager/test_review_board.py -q -k "shell or scrolls or slides or opens_into or rests_on or legend_and_empty or script_parses or stub_dom"`

- [ ] **Step 3: Write the new `_PAGE`**

Replace `_PAGE` from `<!doctype html>` to `</html>`. Keep the `:root` tokens, the status pill rules, the `.reason`, `.tests`, `.agent-*`, `.land-*`, `.comment-body`, `.comment-row`, `.fix-fold`, `.copy-sha`, `.sha-full`, `details.diff`, `details.reason`, `.actions`, `button`, `dialog`, `#decide-*`, `.error-banner`, `.server-died`, `#key-help`, `#key-help-toggle`, `h1.pr-header`, `p.disabled-notice` rules and the whole `.candidate-diff` / `.diff-row` / dark-mode block exactly as they are. Delete `article.candidate*`, `.card-slot`, `details.folded-card`, `details.card-fold`, `.paused-note`, `header.board-summary`, `p.board-intro`, `.empty-board`. Add:

```css
  body { margin: 0; height: 100dvh; overflow: hidden;
         font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         color: var(--fg); background: var(--bg); }
  #shell { display: flex; height: 100%; max-width: 62rem; margin: 0 auto;
           transition: max-width 200ms ease-out; }
  body.open #shell { max-width: 200rem; }
  #left { display: flex; flex-direction: column; min-height: 0; width: 62rem;
          max-width: 100%; box-sizing: border-box; padding: 2rem 1rem 0;
          transition: width 200ms ease-out; }
  body.open #left { width: 28rem; flex: 0 0 auto; padding-right: 0; }
  #left-header { flex: 0 0 auto; }
  #summary { color: var(--muted); margin: 0 0 1rem; }
  #rows { flex: 1 1 auto; min-height: 0; overflow-y: auto; list-style: none;
          margin: 0; padding: 1px 1px 1rem 1px; }
  li[role="option"] { border: 1px solid var(--border); border-radius: 6px;
                      padding: .45rem 1rem; margin: 0 0 .6rem; cursor: pointer;
                      background: var(--bg); }
  li[role="option"]:focus { outline: none; }
  li.selected { border-color: var(--info); box-shadow: 0 0 0 1px var(--info); }
  body.open li.selected { border-right-color: transparent; border-radius: 6px 0 0 6px;
                          box-shadow: none; margin-right: -1px; }
  .row-head { display: flex; flex-wrap: wrap; gap: .8em; align-items: baseline; }
  .gist { margin: .1rem 0 0; overflow: hidden; text-overflow: ellipsis;
          white-space: nowrap; }
  .aftermath { color: var(--muted); font-size: .85em; margin: .1rem 0 0;
               overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  #empty-board { color: var(--muted); border: 1px dashed var(--border);
                 border-radius: 6px; padding: .8rem 1rem; }
  #panel { display: none; position: relative; flex: 1 1 auto; min-width: 0;
           border-left: 1px solid var(--info); }
  body.open #panel { display: flex; flex-direction: column; }
  #panel-notch { position: absolute; left: -1px; width: 1px; box-sizing: border-box;
                 background: var(--bg); border-top: 1px solid var(--info);
                 border-bottom: 1px solid var(--info); }
  #panel-content { flex: 1 1 auto; min-height: 0; overflow-y: auto; padding: 0 1rem 1rem; }
  #panel-body > header.meta { position: sticky; top: 0; background: var(--bg);
                              padding: 2rem 0 .5rem; z-index: 1; }
  #panel-close { margin-left: auto; padding: 0 .6em; }
  .under-work { color: var(--warn); border: 1px solid var(--warn); border-radius: 6px;
                padding: .3rem .8rem; margin: .5rem 0; }
  .removed-banner { color: var(--danger); font-size: 1.15em; margin: .5rem 0; }
  .deleted-notice { color: var(--muted); font-size: .85em; margin: .5rem 0; }
  .panel-content.dimmed { opacity: .5; }
  li.pending-move { animation: pulse-border 1.6s ease-in-out infinite; }
  @keyframes pulse-border { 0%, 100% { border-color: var(--border); }
                            50% { border-color: var(--warn); } }
  @media (prefers-reduced-motion: reduce) {
    #shell, #left { transition: none; }
    li.pending-move { animation: none; border-color: var(--warn); }
  }
```

Change `header.meta` to `.meta` where the panel uses it, or keep `header.meta` since the panel renders `<header class="meta">`. Body markup:

```html
<body>
<div id="shell">
<div id="left">
<div id="left-header">
<h1 class="pr-header">__PR_HEADING__</h1>
__DISABLED_NOTICE__
<p id="error-banner" class="error-banner" role="status" aria-live="polite" hidden><button id="banner-close"
   class="close" type="button" title="dismiss" aria-label="dismiss this message">×</button><a id="error-card" href="#" hidden>the affected card</a><span id="error-text"></span></p>
<section id="server-died" class="server-died" hidden>
<h2>server died, please restart to continue working</h2>
</section>
<div id="summary"></div>
<p id="empty-board" hidden>No comments on your PR. j and k open and walk the comments; a, r and d act on the open one; Escape closes it.</p>
</div>
<ul id="rows" role="listbox" aria-label="review comments"></ul>
</div>
<aside id="panel" aria-label="the open comment">
<div id="panel-notch" hidden></div>
<div id="panel-content"></div>
</aside>
</div>
<button id="key-help-toggle" title="keyboard shortcuts" aria-label="keyboard shortcuts">?</button>
<div id="key-help" hidden>
<dl>
<dt>j</dt><dd>open the next comment</dd>
<dt>k</dt><dd>open the previous comment</dd>
<dt>a</dt><dd>approve the open comment (asks for your reply)</dd>
__KEY_HELP_REJECT__<dt>d</dt><dd>dismiss the open comment (asks for your reply)</dd>
<dt>Esc</dt><dd>close the open comment</dd>
<dt>?</dt><dd>this help</dd>
</dl>
<p class="key-help-footer">a, r and d act on the open comment in the right-hand panel. press any key to return</p>
</div>
<dialog id="decide-dialog"> … unchanged … </dialog>
<script src="/static/htmx.min.js"></script>
<script>
… the script below …
</script>
</body>
```

`render_page`'s `__KEY_HELP_REJECT__` line becomes `<dt>r</dt><dd>send the open comment back for rework (asks for your notes)</dd>`. `#key-help` keeps `position: fixed`; centre it with `top: 50%; left: 50%; transform: translate(-50%, -50%)`.

The script. Everything between `<script>` and `</script>`:

```js
const theme = () =>
  window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
const reducedMotion = () =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;
document.body.addEventListener("htmx:configRequest", (e) => {
  e.detail.parameters.theme = theme();
});
const POLL_MS = 2000;
const PANEL_DEBOUNCE_MS = 150;
const LOST_AFTER = 2;
const IN_PROGRESS = ["queued", "working", "rejected"];
const DECIDE = {a: "approve", r: "reject", d: "dismiss"};
const DECISIONS = ["approve", "reject", "dismiss", "retry", "decline"];
const rowsEl = () => document.getElementById("rows");
const panelEl = () => document.getElementById("panel");
const panelContent = () => document.getElementById("panel-content");
const panelBody = () => document.getElementById("panel-body");
const rowById = (id) => document.getElementById("c-" + id);
const rows = () => Array.from(rowsEl().children);
const idOf = (li) => li.id.slice(2);
let selected = null;
let cursor = null;

function compareRows(a, b) {
  const band = Number(a.dataset.band) - Number(b.dataset.band);
  if (band) return band;
  return a.dataset.sort < b.dataset.sort ? -1 : a.dataset.sort > b.dataset.sort ? 1 : 0;
}
function makeRow(id) {
  const li = document.createElement("li");
  li.id = "c-" + id;
  li.setAttribute("role", "option");
  li.setAttribute("aria-selected", "false");
  li.tabIndex = -1;
  return li;
}
function fillRow(li, item) {
  li.dataset.band = String(item.band);
  li.dataset.sort = item.sort;
  if (li.innerHTML !== item.html) li.innerHTML = item.html;
}
function mergeRow(item) {
  const id = String(item.id);
  let li = rowById(id);
  if (!li) {
    li = makeRow(id);
    fillRow(li, item);
    rowsEl().appendChild(li);
    if (held()) li.classList.add("pending-move");
  } else {
    fillRow(li, item);
  }
  return li;
}
function reconcile(payload) {
  const seen = new Set();
  payload.rows.forEach((item) => { seen.add(String(item.id)); mergeRow(item); });
  rows().forEach((li) => {
    if (seen.has(idOf(li))) return;
    const wasOpen = selected === idOf(li);
    li.remove();
    if (wasOpen) {
      closePanel();
      showBanner("that card is gone from the board — the comment's record was "
        + "removed while it was open", "", false);
    }
  });
  document.getElementById("summary").innerHTML = payload.summary;
  document.getElementById("empty-board").hidden = payload.rows.length > 0;
  applyOrder();
}
function applyOrder() {
  const current = rows();
  const target = current.slice().sort(compareRows);
  const moving = current.filter((li, i) => target[i] !== li);
  if (held()) {
    current.forEach((li) => li.classList.toggle("pending-move", target.indexOf(li) !== current.indexOf(li)));
    return;
  }
  current.forEach((li) => li.classList.remove("pending-move"));
  if (!moving.length) { placeNotch(); return; }
  const before = reducedMotion() ? null
    : new Map(current.map((li) => [li, li.getBoundingClientRect().top]));
  target.forEach((li) => rowsEl().appendChild(li));
  if (before) animateMoves(before);
  keepSelectedInView();
  placeNotch();
}
function animateMoves(before) {}
function keepSelectedInView() {}
function placeNotch() {}
const held = () => false;
function releaseHold() {}

let failures = 0;
async function pollRows() {
  try {
    const res = await fetch("/rows", {headers: {Accept: "application/json"}});
    if (!res.ok) throw new Error("HTTP " + res.status);
    const payload = await res.json();
    contactRestored();
    reconcile(payload);
  } catch (err) {
    lostContact("/rows");
  }
}
setInterval(pollRows, POLL_MS);
pollRows();

let panelTimer = null;
let panelFetch = 0;
let statePoll = null;
function markSelected() {
  rows().forEach((li) => {
    const on = selected !== null && idOf(li) === selected;
    li.classList.toggle("selected", on);
    li.setAttribute("aria-selected", String(on));
  });
}
function openRow(id) {
  cursor = id;
  if (selected === id) return;
  selected = id;
  document.body.classList.add("open");
  markSelected();
  releaseHold();
  const token = ++panelFetch;
  clearTimeout(panelTimer);
  panelTimer = setTimeout(() => { if (token === panelFetch) fetchPanel(id); }, PANEL_DEBOUNCE_MS);
  placeNotch();
}
function closePanel() {
  selected = null;
  document.body.classList.remove("open");
  markSelected();
  stopPanelPoll();
  clearTimeout(panelTimer);
  panelFetch += 1;
  if (!inFlightDecision) panelContent().innerHTML = "";
  placeNotch();
}
function fetchPanel(id) {
  htmx.ajax("GET", "/panel/" + id, {target: "#panel-content", swap: "innerHTML"});
}
function stopPanelPoll() {
  if (statePoll) clearInterval(statePoll);
  statePoll = null;
}
function startPanelPoll() {
  stopPanelPoll();
  statePoll = setInterval(refreshPanel, POLL_MS);
}
let savedPanelScroll = 0;
function swapPanel(id) {
  savedPanelScroll = panelContent().scrollTop;
  fetchPanel(id);
}
async function refreshPanel() {
  const body = panelBody();
  if (!body || selected === null) return;
  if (IN_PROGRESS.includes(body.dataset.status)) { swapPanel(selected); return; }
  try {
    const res = await fetch("/panel/" + selected + "/state");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const state = await res.json();
    contactRestored();
    const deleted = body.dataset.commentDeleted === "1";
    if (state.status !== body.dataset.status
        || (state.intent || "") !== (body.dataset.intent || "")
        || (state.updated || "") !== (body.dataset.updated || "")
        || !!state.comment_deleted !== deleted) swapPanel(selected);
  } catch (err) {
    lostContact("/panel/state");
  }
}
document.body.addEventListener("htmx:afterSwap", (e) => {
  const target = e.detail && e.detail.target;
  if (!target || target.id !== "panel-content") return;
  panelContent().scrollTop = savedPanelScroll;
  savedPanelScroll = 0;
  if (selected !== null) startPanelPoll();
  placeNotch();
});

rowsEl().addEventListener("click", (e) => {
  if (e.target.closest && e.target.closest("a")) return;
  const li = e.target.closest && e.target.closest("li[role=option]");
  if (!li) { if (selected !== null) closePanel(); return; }
  const id = idOf(li);
  if (selected === id) closePanel(); else openRow(id);
});
panelEl().addEventListener("click", (e) => {
  if (e.target.closest && e.target.closest("#panel-close")) closePanel();
});

… the DIALOGS table, openDialog, paintSubmit, the decide-quote / decide-body / decide-cancel / dialog close listeners exactly as today …

let inFlightDecision = false;
document.getElementById("decide-form").addEventListener("submit", () => {
  if (!deciding) return;
  inFlightDecision = true;
  deciding.issueRequest(true);
  closePanel();
});
document.body.addEventListener("htmx:confirm", (e) => {
  const elt = e.detail.elt;
  const decision = DECISIONS.find((d) => elt.classList.contains(d));
  if (!decision) return;
  const body = elt.closest("#panel-body");
  if (!body || !DIALOGS[decision]) return;
  e.preventDefault();
  elt.blur();
  openDialog(decision, e.detail.issueRequest, body.dataset.statement || "");
});
function parseRow(xhr) {
  try { return JSON.parse(xhr.responseText); } catch (err) { return null; }
}
document.body.addEventListener("htmx:afterRequest", (e) => {
  const elt = e.detail && e.detail.elt;
  if (!elt || !elt.matches || !elt.matches("#panel-body button")) return;
  inFlightDecision = false;
  if (selected === null) panelContent().innerHTML = "";
  const status = e.detail.xhr.status;
  if (status !== 200 && status !== 409) return;
  const item = parseRow(e.detail.xhr);
  if (item) { mergeRow(item); applyOrder(); }
  if (status === 409) {
    document.getElementById("error-card").hidden = true;
    showBanner("that card had moved on — the row now shows the candidate as it "
      + "actually is; open it and decide again if it still needs it", "", false);
  }
});
document.body.addEventListener("htmx:beforeSwap", (e) => {
  if (e.detail.xhr && e.detail.xhr.status === 409) e.detail.isError = false;
});

document.addEventListener("keydown", (e) => {
  const active = document.activeElement;
  const tag = (active || {}).tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (["Shift", "Meta", "Control", "Alt"].includes(e.key)) return;
  if (lostAt) return;
  if (decideDialog().open) return;
  const help = document.getElementById("key-help");
  if (!help.hidden) { help.hidden = true; return; }
  if (e.key === "?") { help.hidden = false; return; }
  if (active && active.matches && active.matches('[role="button"]')
      && (e.key === "Enter" || e.key === " ")) {
    e.preventDefault();
    active.click();
    return;
  }
  if (e.key === "Escape") {
    if (selected !== null) { e.preventDefault(); closePanel(); }
    return;
  }
  const list = rows();
  if (!list.length) return;
  if (e.key === "j" || e.key === "k") {
    releaseHold();
    const order = rows();
    const at = order.findIndex((li) => idOf(li) === cursor);
    const last = order.length - 1;
    const next = e.key === "j"
      ? (at < 0 ? order[0] : order[Math.min(at + 1, last)])
      : (at < 0 ? order[last] : order[Math.max(at - 1, 0)]);
    e.preventDefault();
    openRow(idOf(next));
    next.focus({preventScroll: true});
  } else if (DECIDE[e.key] && selected !== null) {
    const button = document.querySelector("#panel-body button." + DECIDE[e.key]);
    if (!button) return;
    const box = button.getBoundingClientRect();
    if (box.bottom <= 0 || box.top >= window.innerHeight) {
      button.scrollIntoView({block: "nearest"});
      return;
    }
    button.click();
  }
});
document.getElementById("key-help-toggle").addEventListener("click", (e) => {
  const help = document.getElementById("key-help");
  help.hidden = !help.hidden;
  e.currentTarget.blur();
});
document.getElementById("key-help").addEventListener("click", (e) => {
  e.currentTarget.hidden = true;
});

… the copy-sha click handler exactly as today …

function showBanner(text, detail, isFailure) { … as today … }
const REASONS = { … as today … };
function describe(status) { … as today … }
document.getElementById("banner-close").addEventListener("click", () => {
  document.getElementById("error-banner").hidden = true;
});
document.body.addEventListener("htmx:responseError", (e) => {
  const status = e.detail.xhr.status;
  const path = e.detail.pathInfo.requestPath;
  if (status === 409) return;
  if (status === 503 && /^\/panel\//.test(path)) {
    let reason = "";
    try { reason = JSON.parse(e.detail.xhr.responseText).error || ""; } catch (err) {}
    showBanner("the board could not check GitHub for that comment — " + reason, "HTTP 503 " + path, true);
    closePanel();
    return;
  }
  showBanner(describe(status), "HTTP " + status + " " + path, true);
  const id = (path.match(/\/(?:candidate|panel)\/(\d+)/) || [])[1];
  const anchor = document.getElementById("error-card");
  anchor.hidden = !(id && rowById(id));
  if (!anchor.hidden) anchor.href = "#c-" + id;
});

let lostAt = null;
let lostMessage = null;
let priorMessage = null;
let priorFailure = true;
const decideButtons = () => Array.from(document.querySelectorAll("#panel-body button"));
function panesVisible(visible) {
  rowsEl().hidden = !visible;
  panelEl().hidden = !visible;
  document.getElementById("key-help-toggle").hidden = !visible;
  document.getElementById("server-died").hidden = visible;
}
function lostContact(path) {
  if (lostAt) return;
  if (++failures < LOST_AFTER) return;
  lostAt = new Date();
  lostMessage = "cannot reach this page's server at "
    + lostAt.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})
    + " — the board is frozen (the manager may have stopped it, or exited); press v in the PR's tmux window to start it again";
  const banner = document.getElementById("error-banner");
  priorMessage = banner.hidden ? null : document.getElementById("error-text").textContent;
  priorFailure = !banner.classList.contains("notice");
  document.getElementById("error-card").hidden = true;
  showBanner(lostMessage, "no response from " + path, true);
  decideButtons().forEach((b) => { b.disabled = true; });
  document.getElementById("key-help").hidden = true;
  panesVisible(false);
}
function contactRestored() {
  failures = 0;
  if (!lostAt) return;
  lostAt = null;
  decideButtons().forEach((b) => { b.disabled = false; });
  panesVisible(true);
  const banner = document.getElementById("error-banner");
  const errorText = document.getElementById("error-text");
  if (errorText.textContent === lostMessage) {
    errorText.textContent = priorMessage === null ? "" : priorMessage;
    banner.className = priorFailure ? "error-banner" : "error-banner notice";
    banner.hidden = priorMessage === null;
  }
  lostMessage = null;
  priorMessage = null;
}
document.body.addEventListener("htmx:sendError", () => lostContact("htmx"));
document.body.addEventListener("htmx:timeout", () => lostContact("htmx"));
```

Order matters in one place: `inFlightDecision` is declared before `closePanel` runs, so put `let inFlightDecision = false;` above the panel functions rather than beside the submit listener. `held`, `releaseHold`, `animateMoves`, `keepSelectedInView` and `placeNotch` are stubs here and are filled in Task 14b.

- [ ] **Step 4: Run the node tests, the whole board file, then the full suite**

Run: `uv run pytest tests/github_pr_agent_manager/test_review_board.py -q`
Expected: pass, with the deleted tests gone. Read every remaining failure; if a test pins old behaviour the spec retired, delete it, and if it pins behaviour the spec keeps, fix the page.

- [ ] **Step 5: Commit**

```bash
git add src/github_orchestrator/github_pr_agent_manager/review_board.py tests/github_pr_agent_manager/test_review_board.py
git commit -m "GITHUB-ORCHESTRATOR: lay the board out as rows and a panel"
```

______________________________________________________________________

### Task 14b: the hold, the pulse, the moves, the notch

**Files:**

- Modify: `src/github_orchestrator/github_pr_agent_manager/review_board.py` (`_PAGE` script: replace the five stubs from 14a)
- Test: `tests/github_pr_agent_manager/test_review_board.py` (`_BEHAVIOUR_ASSERTIONS`, plus text tests)

**Interfaces:**

- Consumes: `applyOrder`, `mergeRow`, `openRow`, `rows()` from 14a.

- Produces: `held()`, `releaseHold()`, `animateMoves(before)`, `keepSelectedInView()`, `placeNotch()`; constants `HOLD_IDLE_MS = 10000`, `HOLD_CEILING_MS = 20000`, `HOLD_TICK_MS = 500`, `MOVE_MS = 220`.

- [ ] **Step 1: Write the failing tests**

Text tests:

```python
def test_the_hold_has_the_agreed_clocks(tmp_path):
    script = page_script(page_shell(tmp_path))
    assert "const HOLD_IDLE_MS = 10000;" in script
    assert "const HOLD_CEILING_MS = 20000;" in script
    assert "const MOVE_MS = 220;" in script
    assert "prefers-reduced-motion" in script


def test_the_pulse_is_amber_and_still_under_reduced_motion(tmp_path):
    shell = page_shell(tmp_path)
    assert "var(--warn)" in shell[shell.index("@keyframes pulse-border"):shell.index("@keyframes pulse-border") + 200]
    reduced = shell[shell.index("prefers-reduced-motion"):]
    assert "animation: none" in reduced and "border-color: var(--warn)" in reduced
```

Insert into `_BEHAVIOUR_ASSERTIONS`, before the `process.exit` line (the stub's `NOW` clock and `timers` list already exist):

```js
// ---- the hold ----
const holdTick = timers.find((t) => t.ms === 500).fn;
respond({summary: "", rows: [row(1, 0, "a|1"), row(2, 0, "a|2"), row(3, 1, "a|3")]});
await pollRows(); await tick();
check(ids().join() === "c-1,c-2,c-3", "start from a settled order");
NOW = 100000;
fire(rowsEl, "mouseenter", {});
respond({summary: "", rows: [row(1, 2, "a|1"), row(2, 0, "a|2"), row(3, 1, "a|3", "<div class=\"row-head\">fresh</div>")]});
await pollRows(); await tick();
check(ids().join() === "c-1,c-2,c-3", "a pointer over the list holds every move");
check(pending().includes("c-1"), "the row that wants to move pulses: " + pending().join());
check(R("c-3").innerHTML.includes("fresh"), "content still updates while the position is held");
fire(rowsEl, "mousemove", {}); NOW += 5000; holdTick();
check(ids().join() === "c-1,c-2,c-3", "five idle seconds is not a release");
NOW += 5000; holdTick();
check(ids().join() === "c-2,c-3,c-1", "ten idle seconds releases the hold and the moves land");
check(pending().length === 0, "and nothing pulses once it has moved");

fire(rowsEl, "mouseenter", {});
respond({summary: "", rows: [row(1, 0, "a|1"), row(2, 0, "a|2"), row(3, 1, "a|3")]});
await pollRows(); await tick();
check(ids().join() === "c-2,c-3,c-1", "held again");
for (let i = 0; i < 19; i++) { fire(rowsEl, "mousemove", {}); NOW += 1000; holdTick(); }
check(ids().join() === "c-2,c-3,c-1", "a moving pointer keeps the hold past the idle clock");
fire(rowsEl, "mousemove", {}); NOW += 1000; holdTick();
check(ids().join() === "c-1,c-2,c-3", "twenty seconds is the ceiling whatever the pointer does");

fire(rowsEl, "mouseenter", {});
respond({summary: "", rows: [row(1, 2, "a|1"), row(2, 0, "a|2"), row(3, 1, "a|3")]});
await pollRows(); await tick();
check(ids().join() === "c-1,c-2,c-3", "held a third time");
fire(rowsEl, "mouseleave", {});
check(ids().join() === "c-2,c-3,c-1", "the pointer leaving releases at once");

// A new comment while held appends at the bottom and pulses; release moves it home.
fire(rowsEl, "mouseenter", {});
respond({summary: "", rows: [row(1, 2, "a|1"), row(2, 0, "a|2"), row(3, 1, "a|3"), row(4, 0, "a|0")]});
await pollRows(); await tick();
check(ids().join() === "c-2,c-3,c-1,c-4", "a new row lands at the bottom while held");
check(pending().includes("c-4"), "and pulses");
press("j"); flushTimeouts(); await tick();
check(ids().join() === "c-4,c-2,c-3,c-1", "j releases the hold before it moves the cursor");
fire(rowsEl, "mouseleave", {});

// Moves animate through the Web Animations API unless motion is reduced.
R("c-4").animated = 0;
respond({summary: "", rows: [row(1, 2, "a|1"), row(2, 0, "a|2"), row(3, 1, "a|3"), row(4, 2, "a|0")]});
await pollRows(); await tick();
check(R("c-4").animated === 1, "a row that moved was animated");
window.matchMedia = (q) => ({matches: q.includes("reduced-motion")});
R("c-4").animated = 0;
respond({summary: "", rows: [row(1, 2, "a|1"), row(2, 0, "a|2"), row(3, 1, "a|3"), row(4, 0, "a|0")]});
await pollRows(); await tick();
check(R("c-4").animated === 0 && ids()[0] === "c-4", "under reduced motion the move is instant");
window.matchMedia = () => ({matches: false});

// The selected row is kept in view with a row of padding; the notch follows it.
press("Escape");
clickRow("c-1"); flushTimeouts(); await tick();
rowsEl.clientHeight = 200; rowsEl.scrollTop = 0;
respond({summary: "", rows: [row(1, 2, "a|1"), row(2, 2, "a|2"), row(3, 2, "a|3"), row(4, 2, "a|0"), row(5, 2, "a|4"), row(6, 2, "a|5"), row(7, 2, "a|6")]});
await pollRows(); await tick();
rowsEl.scrolledTo = null;
respond({summary: "", rows: [row(1, 2, "z|1"), row(2, 2, "a|2"), row(3, 2, "a|3"), row(4, 2, "a|0"), row(5, 2, "a|4"), row(6, 2, "a|5"), row(7, 2, "a|6")]});
await pollRows(); await tick();
check(ids()[ids().length - 1] === "c-1", "the selected row moved to the bottom");
check(rowsEl.scrolledTo && rowsEl.scrolledTo.top === 120, "and the list scrolled to keep it a row in from the edge: " + JSON.stringify(rowsEl.scrolledTo));
panel.rect = {top: 0, height: 400};
R("c-1").rect = {top: 380, height: 40};
placeNotch();
check(notch.style.top === "360px", "the notch clamps to the panel's bottom edge: " + notch.style.top);
R("c-1").rect = {top: 100, height: 40};
placeNotch();
check(notch.style.top === "100px" && notch.hidden === false, "and tracks the row when it is in view");
press("Escape");
check(notch.hidden === true, "no selection, no notch");
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/github_pr_agent_manager/test_review_board.py -q -k "hold or pulse or stub_dom"`

- [ ] **Step 3: Replace the five stubs**

```js
const HOLD_IDLE_MS = 10000;
const HOLD_CEILING_MS = 20000;
const HOLD_TICK_MS = 500;
const MOVE_MS = 220;
let heldSince = null;
let lastPointerMove = 0;
const held = () => heldSince !== null;
function releaseHold() {
  if (!held()) return;
  heldSince = null;
  applyOrder();
}
rowsEl().addEventListener("mouseenter", () => {
  heldSince = Date.now();
  lastPointerMove = heldSince;
});
rowsEl().addEventListener("mousemove", () => {
  if (held()) lastPointerMove = Date.now();
});
rowsEl().addEventListener("mouseleave", releaseHold);
setInterval(() => {
  if (!held()) return;
  const now = Date.now();
  if (now - lastPointerMove >= HOLD_IDLE_MS || now - heldSince >= HOLD_CEILING_MS) releaseHold();
}, HOLD_TICK_MS);

function animateMoves(before) {
  rows().forEach((li) => {
    const from = before.get(li);
    if (from === undefined || !li.animate) return;
    const delta = from - li.getBoundingClientRect().top;
    if (!delta) return;
    li.animate([{transform: "translateY(" + delta + "px)"}, {transform: "translateY(0)"}],
               {duration: MOVE_MS, easing: "ease-out"});
  });
}
function keepSelectedInView() {
  if (selected === null) return;
  const li = rowById(selected);
  if (!li) return;
  const list = rowsEl();
  const pad = li.offsetHeight;
  const top = li.offsetTop - list.scrollTop;
  const bottom = top + li.offsetHeight;
  const behavior = reducedMotion() ? "auto" : "smooth";
  if (top < pad) {
    list.scrollTo({top: Math.max(li.offsetTop - pad, 0), behavior: behavior});
  } else if (bottom > list.clientHeight - pad) {
    list.scrollTo({top: li.offsetTop + li.offsetHeight + pad - list.clientHeight, behavior: behavior});
  }
}
let notchQueued = false;
function placeNotch() {
  if (notchQueued) return;
  notchQueued = true;
  requestAnimationFrame(() => {
    notchQueued = false;
    const notch = document.getElementById("panel-notch");
    const li = selected !== null ? rowById(selected) : null;
    if (!li) { notch.hidden = true; return; }
    const panel = panelEl().getBoundingClientRect();
    const box = li.getBoundingClientRect();
    const top = Math.max(0, Math.min(box.top - panel.top, panel.height - box.height));
    notch.hidden = false;
    notch.style.top = top + "px";
    notch.style.height = box.height + "px";
  });
}
rowsEl().addEventListener("scroll", placeNotch);
window.addEventListener("resize", placeNotch);
```

Because `held` is a `const` arrow and `releaseHold` a function, both must be defined before `applyOrder`'s first call from `pollRows()`; place this block above the `setInterval(pollRows, POLL_MS)` line.

- [ ] **Step 4: Run the node tests, the board file, then the full suite**

Run: `uv run pytest tests/github_pr_agent_manager/test_review_board.py -q`, then `uv run pytest tests/ -n 4 -q`.

- [ ] **Step 5: Commit**

```bash
git add src/github_orchestrator/github_pr_agent_manager/review_board.py tests/github_pr_agent_manager/test_review_board.py
git commit -m "GITHUB-ORCHESTRATOR: hold the list still under the pointer and animate the moves"
```

______________________________________________________________________

### Task 15: retire what the rows replaced

**Files:**

- Modify: `src/github_orchestrator/github_pr_agent_manager/review_board.py`
- Test: `tests/github_pr_agent_manager/test_review_board.py`

**Interfaces:**

- Removes: `render_card`, `_safe_card`, `_error_card`, `_slotted`, `_sentinel`, `_EMPTY_BOARD`, `render_board`, `render_board_new`, `render_summary`, `_card_state`, `_button`, `_CARD_CLASSES`, `_STRIP_CLASSES`, `_settled_strip`, routes `/board`, `/board/new`, `/summary`, `GET /candidate/<id>`, `_CANDIDATE_RE`; `handle_post`'s unused `repo_worktree`, `claude_enabled`, `base_branch` parameters and the `_theme_of` call it made.

- Keeps: `render_counts`, `render_row`, `render_panel`, `_panel_button`, `_action_footer`, `_pill`, `_actions_for`, `_panel_notes`, `_settled_line`, `_landed_line`, `render_diff_fragment`, `render_context_fragment`, `/candidate/<id>/diff`, `/candidate/<id>/expand`, `POST /candidate/<id>/decide`.

- [ ] **Step 1: Delete the tests that pin the retired surface**

In `test_review_board.py`, remove: the card poll tests (`:121-200`), `card_for`/`buttons_of` callers that render a card (rewrite the ones that still matter to call `render_panel` through `get_panel`; the button-set tests at `:212-431` become panel tests, one per status, asserting `buttons_of(panel_html)`), the fold/collapse tests (`:443-636`), `test_board_lists_every_candidate_newest_last_with_sentinel`, `test_board_new_*`, the empty-state-in-sentinel tests (`:1124-1167`), `test_broken_diff_breaks_neither_the_board_nor_the_diff_route` (keep the diff-route half), `test_the_error_card_names_the_comment*`, `test_an_unreadable_candidate_file_holds_its_place_on_the_board` and `test_a_stood_in_card_is_inert` (replace with one `/rows` test asserting the unreadable row's html and band), `test_a_single_card_poll_clears_the_floor`, `test_the_server_gzips_a_card_when_asked` (make it gzip `/rows`), `test_card_header_scanning_order` (the row version exists from Task 11), the summary fingerprint tests (`:3381-3510`), `test_summary_*` that call `render_summary` (rewrite against `render_counts`), the sentinel test at `:4110`, the context tests that call `render_card` or `/board` (`:4297-4570`: rewrite each to render the panel; `test_a_board_hands_every_cards_context_the_base_branch_and_theme` becomes a `/rows`-does-not-render-context test, asserting the context renderer is never called by `/rows`).

The two rules to apply test by test: a test that pins something the spec keeps (escaping, a button set, the diff route, the theme parameter, the 403s) is rewritten against the row or the panel; a test that pins a retired mechanism is deleted.

- [ ] **Step 2: Run to see what still references the retired names**

Run: `uv run pytest tests/github_pr_agent_manager/test_review_board.py -q 2>&1 | tail -20`

- [ ] **Step 3: Delete the code**

Remove each name in the "Removes" list, then run `uv run python -c "import github_orchestrator.github_pr_agent_manager.review_board"` to catch a dangling reference. `handle_get` loses the `/board`, `/board/new`, `/summary` and `_CANDIDATE_RE` branches. `handle_post` becomes:

```python
def handle_post(candidates_dir: Path, repo: str, pr: int, raw_path: str,
                request_body: bytes, headers, port: int) -> tuple[int, str, bytes]:
```

and `_BoardHandler.do_POST` and the test helper `post` drop the arguments it no longer takes. Check `loop.py` and any other caller with `grep -rn "handle_post\|render_board\|render_summary\|render_card" src/ tests/`.

- [ ] **Step 4: Run the full suite, then `--durations=20`**

Run: `uv run pytest tests/ -n 4 -q` and `uv run pytest tests/github_pr_agent_manager/test_review_board.py -q --durations=20`. Nothing new should be above 0.2s.

- [ ] **Step 5: Commit**

```bash
git add src/github_orchestrator/github_pr_agent_manager/review_board.py src/github_orchestrator/github_pr_agent_manager/loop.py tests/github_pr_agent_manager/test_review_board.py
git commit -m "GITHUB-ORCHESTRATOR: retire the card, the sentinel and the summary fingerprints"
```

______________________________________________________________________

### Task 16: the documentation

**Files:**

- Modify: `CLAUDE.md` (the "Review board" subsection under Architecture; the "Filesystem state" rule about sibling files; the Skills paragraph if it names `candidate open`)

- Modify: `README.md:345-421` (the "Review board" section)

- Test: none; `make fmt-check`.

- [ ] **Step 1: Rewrite CLAUDE.md's review board section**

Replace the bullets that describe retired mechanisms (the collapsed `folded-card`, `card-fold`, `heldStill`, the `card-slot` marker, per-card timers and the `/summary` fingerprints, the `/board/new` sentinel, the htmx settle strobe, the focus-by-id restore, the "id restore is the whole mechanism" paragraph) with bullets for what replaced them, each carrying its reason in the file's own voice. Cover, one bullet each: rows and the panel (what lives where and why: reordering is safe only because rows carry no click targets); `/rows` as JSON with band and sort key, client-owned order, and why htmx was not used for it; the three bands and the intent rule; the hold, its two clocks and the ceiling, and why j/k release it; the amber pulse and why not red; the panel's fingerprint poll versus whole-panel polling for in-progress cards; the notch; the gist (`summarize_comment`, `summary_model`, `claude_env`, why it is not in `runs.jsonl`, why never regenerated); `removed` versus `comment_deleted` and the `declined` precedent; the presence check and why the poll cannot see a deletion; the stale-client repair and the amended rule; approve skipping the reply on a deleted comment. Keep every bullet that still holds (the diff pipeline, the contrast tests, the dialog, the sanitiser, the `[role="button"]` keys, the takeover's `hidden` rule).

Add, where "The POST handlers do no git work" is:

> `GET /panel/<id>` is the one read that may write: when a client asks for a record that is no longer on disk, it fetches the comment from GitHub and rebuilds the record, cutting a worktree if the comment is alive, because nothing but the client that was showing the row knows the record is gone, and the watermark has moved past the comment so no poll will ever bring it back. It runs behind `_repair_lock`. Everything else the board does on a GET is a read.

Amend the Filesystem state rule "Anything written once a tick for display goes to a sibling file" with: "A field written once, like `summary` or `comment_deleted`, goes on the record through `candidates.set_fields`; the writers that hold a loaded record for long enough to lose it are in `candidate_land`, and they never touch those fields."

Keep every sentence plain: no em dashes, no "leverage", sentence-case headings.

- [ ] **Step 2: Rewrite README's review board section**

Describe: the two panes; that a row is a comment and the panel is where you read and act; `j`/`k` open and walk, click to open, click again or Escape to close; `a`/`r`/`d` act on the open comment; what the pill colours mean; that cards wanting a decision sit above cards an agent has, above settled ones, and that a card pulsing amber is waiting for your pointer to leave the list before it moves; the gist line and `summary_model`; what `comment deleted` means and what a card that says "GitHub no longer has this comment" means; that a `?` shows the keys.

- [ ] **Step 3: Format and commit**

Run: `make fmt` then `make fmt-check`.

```bash
git add CLAUDE.md README.md
git commit -m "GITHUB-ORCHESTRATOR: document the board's rows, panel and deleted-comment states"
```

______________________________________________________________________

### Task 17: record, verify, and check the whole branch

**Files:**

- Modify: `tests/recorded_subprocesses.json`

- [ ] **Step 1: Re-record**

Run: `make record`. Then `uv run pytest tests/ -n 4 -q` twice: once to see the replay is complete (no `RecordingMismatch`, and the summary's count of unrecorded tests is zero), once to see it is stable.

- [ ] **Step 2: Run the live suite once**

Run: `uv run pytest tests/ --no-replay -n 4 -q`. Expected: pass. Report the counts.

- [ ] **Step 3: Check every intermediate commit passes**

```bash
for sha in $(git rev-list --reverse main..HEAD); do
  git checkout -q "$sha" && uv run pytest tests/ -n 4 -q -x >/tmp/suite-$sha.log 2>&1 && echo "ok $sha" || echo "FAIL $sha"
done
git checkout -q feat/board-split-panel
```

Any `FAIL` is fixed with a `fixup!` commit and `git rebase -i --autosquash main` (see the `fixup-old-commit` skill), then this loop runs again.

- [ ] **Step 4: Open the board once, by hand, against a real PR**

Run `uv run python -m github_orchestrator.cli status` to find a PR with candidates, press `v` in its tmux window, and walk: open a row, watch the notch, approve something safe or dismiss a test card, watch the panel close and the row move, park the pointer over the list while a card changes and watch it pulse, press `j` and watch it release. Note anything that feels wrong in the decision log as `open`; the animation numbers are tuned here.

- [ ] **Step 5: Commit the recording**

```bash
git add tests/recorded_subprocesses.json
git commit -m "GITHUB-ORCHESTRATOR: re-record the suite for the board's rows and panel"
```
