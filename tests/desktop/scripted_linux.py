import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScriptedLinux:
    installed: set[str] = field(default_factory=lambda: {
        "xdg-open", "notify-send"})
    ran: list[tuple[list[str], str | None]] = field(default_factory=list)

    def __call__(self, argv: list[str], *, input: str | None = None,
                 capture_output: bool = False, timeout: float | None = None,
                 **_: Any) -> subprocess.CompletedProcess[str]:
        if argv[0] not in self.installed:
            raise FileNotFoundError(2, "No such file or directory", argv[0])
        self.ran.append((argv, input))
        return subprocess.CompletedProcess(argv, 0, "", "")
