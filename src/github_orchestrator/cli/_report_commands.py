from collections.abc import Sequence

from github_orchestrator.cli._command_lines import MODULE
from github_orchestrator.conversation import Classification
from github_orchestrator.domain import Pr, Side

SKIPPED_AS = tuple(one.value for one in Classification if not one.asks_a_reply)
REPLIED_AS = tuple(one.value for one in Classification if one.asks_a_reply)
TEST_OUTCOMES = ("passed", "failed", "unverified")

_REQUIRED = {
    "plan": frozenset({"--pr", "--thread-id", "--step"}),
    "step": frozenset({"--pr", "--thread-id", "--done"}),
    "skip": frozenset({"--pr", "--thread-id", "--classification", "--reason"}),
    "reply": frozenset({"--pr", "--thread-id", "--classification", "--body"}),
    "ticket": frozenset({"--pr", "--thread-id", "--project", "--title", "--body", "--reply"}),
    "ready": frozenset({"--pr", "--thread-id", "--sha", "--tests"}),
    "fail": frozenset({"--pr", "--thread-id", "--reason"}),
    "filed": frozenset({"--pr", "--thread-id", "--key", "--url"}),
    "draft": frozenset({"--pr", "--path", "--line", "--body-file"}),
}


class CliReportCommands:
    def __init__(self, python: str) -> None:
        self._python = python

    def _invocation(self, verb: str, pr: Pr, key: str | None) -> list[str]:
        words = [f"{self._python} -m {MODULE}",
                 f"thread {verb}", f"--repo {pr.repo}", f"--pr {pr.number}"]
        if key is not None:
            words.append(f"--thread-id {key}")
        return words

    def _command(self, verb: str, pr: Pr, key: str | None,
                 arguments: Sequence[tuple[str, str]]) -> str:
        words = self._invocation(verb, pr, key)
        for flag, value in arguments:
            words.append(f"{flag} {value}" if flag in _REQUIRED[verb] else f"[{flag} {value}]")
        return " ".join(words)

    def skip(self, pr: Pr, key: str, *, reason: str) -> str:
        return self._command("skip", pr, key, [("--classification", "|".join(SKIPPED_AS)),
                                               ("--reason", reason)])

    def reply(self, pr: Pr, key: str, *, body: str) -> str:
        return self._command("reply", pr, key, [("--classification", "|".join(REPLIED_AS)),
                                                ("--body", body)])

    def ticket(self, pr: Pr, key: str, *, project: str, title: str, body: str,
               reply: str) -> str:
        return self._command("ticket", pr, key, [("--project", project), ("--title", title),
                                                 ("--body", body), ("--reply", reply)])

    def plan(self, pr: Pr, key: str, steps: Sequence[tuple[str, str]]) -> str:
        words = self._invocation("plan", pr, key)
        for text, path in steps:
            words += [f'--step "{text}"', f"--file {path}"]
        return " ".join(words)

    def step(self, pr: Pr, key: str, *, done: str) -> str:
        return self._command("step", pr, key, [("--done", done)])

    def ready(self, pr: Pr, key: str, *, sha: str, tests_note: str, note: str, summary: str,
              confidence: str, confidence_note: str) -> str:
        return self._command("ready", pr, key, [
            ("--sha", sha), ("--tests", "|".join(TEST_OUTCOMES)), ("--tests-note", tests_note),
            ("--note", note), ("--summary", summary), ("--confidence", confidence),
            ("--confidence-note", confidence_note)])

    def fail(self, pr: Pr, key: str, *, reason: str) -> str:
        return self._command("fail", pr, key, [("--reason", reason)])

    def filed(self, pr: Pr, key: str, *, ticket: str, url: str) -> str:
        return self._command("filed", pr, key, [("--key", ticket), ("--url", url)])

    def draft(self, pr: Pr, *, path: str, line: str, start_line: str, body_file: str) -> str:
        return self._command("draft", pr, None, [
            ("--path", path), ("--line", line), ("--start-line", start_line),
            ("--start-side", f"{Side.AFTER.value}|{Side.BEFORE.value}"),
            ("--side", f"{Side.AFTER.value}|{Side.BEFORE.value}"), ("--body-file", body_file)])
