from __future__ import annotations

import logging
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from typing import Any

from github_orchestrator.agent_runs._command_lines import CommandLines

log = logging.getLogger(__name__)

SUMMARY_WORKERS = 4
SUMMARY_TIMEOUT = 300

Run = Callable[..., subprocess.CompletedProcess[Any]]


class Summaries:
    """Gist jobs off the caller's thread, `SUMMARY_WORKERS` at a time.

    The threads are daemons: nothing waits for a gist, and a manager shutting
    down does not sit on one. `SUMMARY_TIMEOUT` is the reaper that hands a lane
    back when the agent wedges, not a deadline anybody is waiting on.
    """

    def __init__(self, run: Run, command: list[str], model: str, lines: CommandLines) -> None:
        self._run = run
        self._lines = lines
        self._command = command
        self._model = model
        self._lanes = threading.Semaphore(SUMMARY_WORKERS)
        self._live: set[threading.Thread] = set()
        self._live_lock = threading.Lock()

    def summarize(self, prompt: str, done: Callable[[str], None], *,
                  label: str) -> None:
        if not self._model:
            return
        queued_at = time.monotonic()

        def work() -> None:
            log.info("gist for %s started on %s after waiting %.1fs for a lane",
                     label, self._model, time.monotonic() - queued_at)
            asked_at = time.monotonic()
            gist = self._ask(prompt)
            took = time.monotonic() - asked_at
            if gist:
                log.info("gist for %s written in %.1fs", label, took)
                done(gist)
            else:
                log.info("gist for %s came back empty after %.1fs", label, took)

        self._later(work)

    def drain(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self._live_lock:
            pending = list(self._live)
        for thread in pending:
            thread.join(max(0.0, deadline - time.monotonic()))
        return not any(thread.is_alive() for thread in pending)

    def _later(self, work: Callable[[], None]) -> None:
        def run() -> None:
            try:
                with self._lanes:
                    work()
            except Exception:
                log.exception("gist job failed")
            finally:
                with self._live_lock:
                    self._live.discard(threading.current_thread())

        thread = threading.Thread(target=run, name="gist", daemon=True)
        with self._live_lock:
            self._live.add(thread)
        thread.start()

    def _ask(self, prompt: str) -> str | None:
        try:
            with tempfile.TemporaryDirectory() as scratch:
                done = self._run(
                    [*self._command, *self._lines.gist(self._model)],
                    input=prompt, capture_output=True, text=True,
                    timeout=SUMMARY_TIMEOUT, env=self._lines.env(), cwd=scratch,
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
                return str(raw.strip())
        return None
