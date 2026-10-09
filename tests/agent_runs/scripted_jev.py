import json
from typing import Any

from github_orchestrator.agent_runs.fake import FakeAgentRuns


class ScriptedJev:
    def __init__(self, world: FakeAgentRuns) -> None:
        self.world = world
        self.asked: list[dict[str, Any]] = []

    def ask(self, body: bytes) -> bytes:
        request: dict[str, Any] = json.loads(body)
        self.asked.append(request)
        choice = self.world.next_gist()
        if choice is None:
            raise OSError("Jev is unreachable")
        assert isinstance(choice, str), "ScriptedJev answers with the option it chose; queue a string"
        return json.dumps({"model": "jev-1.13.0", "answers": {
            name: {"type": "choice", "choice": choice, "confidence": 1.0,
                   "probabilities": {choice: 1.0}}
            for name in request["questions"]}}).encode()
