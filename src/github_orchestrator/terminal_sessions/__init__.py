from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from github_orchestrator.terminal_sessions.interface import (
        Terminals,
        TerminalSessions,
    )

__all__ = [
    "TerminalSessions",
    "Terminals",
]


def __getattr__(name: str) -> object:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from github_orchestrator.terminal_sessions import interface
    return getattr(interface, name)
