import subprocess
from typing import Any

from github_orchestrator.desktop import Badge
from github_orchestrator.desktop.fake import Announcement, FakeDesktop

BADGE_APPS = {"GHO Ready.app": Badge.READY, "GHO Failed.app": Badge.FAILED,
           "GHO Needs You.app": Badge.NEEDS_YOU, "GHO Info.app": Badge.INFO,
           "GHO Comments.app": Badge.COMMENTS}




class Failure:
    def __init__(self, returncode: int, stderr: str) -> None:
        self.returncode = returncode
        self.stderr = stderr


class ScriptedMac:
    def __init__(self, world: FakeDesktop | None = None) -> None:
        self.world = world if world is not None else FakeDesktop()
        self._answers: dict[str, list[Any]] = {}

    def answer(self, program: str, *answers: Any) -> "ScriptedMac":
        self._answers.setdefault(program, []).extend(answers)
        return self

    def __call__(self, argv: list[str], *, input: str | None = None,
                 text: bool = False, capture_output: bool = False,
                 timeout: float | None = None, **_: Any) -> subprocess.CompletedProcess[Any]:
        program = argv[0]
        scripted = self._answers.get(program)
        if scripted:
            answer = scripted.pop(0)
            if isinstance(answer, BaseException):
                raise answer
            return self._completed(argv, answer.returncode, answer.stderr, text)
        if not self.world.macos:
            raise FileNotFoundError(2, "No such file or directory", program)
        if program == "open" and "--args" in argv:
            return self._announce(argv, text)
        if program == "open":
            self.world.opened.append(argv[1])
            return self._completed(argv, 0, "", text)
        if program == "xcode-select":
            return subprocess.CompletedProcess(argv, 0, "/Library/Developer/CommandLineTools\n", "")
        raise AssertionError(f"the Mac stand-in does not know {argv!r}")


    def _announce(self, argv: list[str], text: bool) -> subprocess.CompletedProcess[Any]:
        app, rest = argv[3], argv[argv.index("--args") + 1:]
        flags = rest[0::2]
        if argv[1:3] != ["-n", "-g"] or flags not in (["--title", "--body", "--id"],
                                                      ["--title", "--body", "--id", "--open"]):
            return self._completed(argv, 1, f"unexpected argv {argv!r}", text)
        badge = BADGE_APPS[app.rsplit("/", 1)[-1]]
        link = rest[7] if len(flags) == 4 else None
        self.world.announcements.append(Announcement(badge, rest[1], rest[3], rest[5], link))
        return self._completed(argv, 0, "", text)

    @staticmethod
    def _completed(argv: list[str], returncode: int, stderr: str,
                   text: bool) -> subprocess.CompletedProcess[Any]:
        return subprocess.CompletedProcess(
            args=argv, returncode=returncode,
            stdout="" if text else b"", stderr=stderr if text else stderr.encode(),
        )
