import json
import select
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from github_orchestrator.agent_runs import Agent, History, Run
from github_orchestrator.agent_runs.fake import FakeAgentRuns
from github_orchestrator.pr_processes import AgentChanges, PrProcesses
from github_orchestrator.wiring import AgentRunsWiring, ReportCommandsWiring, wire
from tests.agent_runs.pinned import PYTHON
from tests.agent_runs.scripted_claude import ScriptedClaude
from tests.conftest import clocks_of, fake_provider

MODEL = "opus"
SUMMARY_MODEL = "haiku"
PYTEST_WORKERS = 2


def real_agent_runs(world: FakeAgentRuns, claude: ScriptedClaude, data: Path,
                    clock: Callable[[], float] = time.monotonic,
                    summary_model: str = SUMMARY_MODEL,
                    command: str = "claude", agent: Agent = Agent.CLAUDE,
                    model: str = MODEL) -> History:
    history: History = wire(
        fake_provider(PrProcesses, world.pr_processes),
        fake_provider(AgentChanges, world.pr_processes),
        ReportCommandsWiring(str(PYTHON)),
        clocks_of(monotonic=clock),
        AgentRunsWiring(claude.popen, claude.run, agent=agent, command=command, model=model,
                        summary_model=summary_model, pytest_workers=PYTEST_WORKERS,
                        transcripts_dir=data / "transcripts",
                        runs_log=data / "runs.jsonl"),
    ).get(History)
    return history


def _until_it_writes(run: Run) -> None:
    stdout = getattr(getattr(run, "proc", None), "stdout", None)
    if stdout is None:
        time.sleep(0.01)
    else:
        select.select([stdout], [], [], 0.01)


def finish(run: Run, within: float = 10.0) -> None:
    deadline = time.monotonic() + within
    while run.pump():
        assert time.monotonic() < deadline, "the run did not end in time"
        _until_it_writes(run)


def pump_until(run: Run, done: Callable[[], bool], within: float = 10.0) -> None:
    deadline = time.monotonic() + within
    while True:
        run.pump()
        if done():
            return
        assert time.monotonic() < deadline, "the run never got there"
        _until_it_writes(run)


def ledger_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
