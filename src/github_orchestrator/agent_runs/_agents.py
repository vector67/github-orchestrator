import enum
import os
import shutil
from collections.abc import Callable
from pathlib import Path

CHATGPT_APP_CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"

Which = Callable[[str], str | None]
Exists = Callable[[str], bool]


class Agent(enum.StrEnum):
    CLAUDE = "claude"
    CODEX = "codex"

    @classmethod
    def default(cls) -> "Agent":
        return cls.CLAUDE

    @property
    def display_name(self) -> str:
        return {Agent.CLAUDE: "Claude", Agent.CODEX: "Codex"}[self]

    @property
    def described(self) -> str:
        return {Agent.CLAUDE: "Claude Code", Agent.CODEX: "the Codex CLI"}[self]

    def default_command(self, which: Which = shutil.which,
                        exists: Exists = os.path.exists) -> str:
        if self is Agent.CLAUDE:
            return "claude"
        on_path = which("codex")
        if on_path is not None:
            return on_path
        return CHATGPT_APP_CODEX if exists(CHATGPT_APP_CODEX) else "codex"

    @property
    def default_model(self) -> str:
        return {Agent.CLAUDE: "opus", Agent.CODEX: "gpt-6-luna"}[self]

    @property
    def default_summary_model(self) -> str:
        return {Agent.CLAUDE: "haiku", Agent.CODEX: "gpt-6-luna"}[self]

    def skill_folder(self, home: Path) -> Path:
        return home / {Agent.CLAUDE: ".claude", Agent.CODEX: ".agents"}[self] / "skills"
