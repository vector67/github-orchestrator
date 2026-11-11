import enum
import itertools
import os
import shlex
import shutil
from collections.abc import Callable
from pathlib import Path

CHATGPT_APP_CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"

Which = Callable[[str], str | None]
Exists = Callable[[str], bool]


def is_setting(word: str) -> bool:
    return word.partition("=")[0].isidentifier() and "=" in word


def _config_dir(command: str) -> str | None:
    settings = dict(word.split("=", 1) for word in itertools.takewhile(is_setting, shlex.split(command)))
    return settings.get("CLAUDE_CONFIG_DIR")


def _under(home: Path, path: str) -> Path:
    if path == "~" or path.startswith("~/"):
        return home / path[2:]
    return Path(path)


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

    @property
    def verdict_model(self) -> str:
        return {Agent.CLAUDE: "sonnet", Agent.CODEX: "gpt-6-luna"}[self]

    def skill_folder(self, home: Path, command: str) -> Path:
        config_dir = _config_dir(command) if self is Agent.CLAUDE else None
        if config_dir is not None:
            return _under(home, config_dir) / "skills"
        return home / {Agent.CLAUDE: ".claude", Agent.CODEX: ".agents"}[self] / "skills"
