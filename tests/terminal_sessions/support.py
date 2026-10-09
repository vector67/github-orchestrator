import subprocess

import dishka

from github_orchestrator.settings.fake import Settings
from github_orchestrator.terminal_sessions import Terminals, TerminalSessions
from github_orchestrator.wiring import (
    TerminalSessionsWiring,
    terminal_sessions_dir,
    wire,
)
from tests.builders import a_pr


def _container(settings: Settings, first_connection_seconds: float) -> dishka.Container:
    return wire(TerminalSessionsWiring(
        subprocess.Popen, settings.child_environment(), terminal_sessions_dir(settings),
        a_pr(1, "octocat/terminals"), first_connection_seconds=first_connection_seconds))


def real_terminal_sessions(settings: Settings, *,
                           first_connection_seconds: float = 30.0) -> TerminalSessions:
    sessions: TerminalSessions = _container(settings, first_connection_seconds).get(
        TerminalSessions)
    return sessions


def real_terminals(settings: Settings) -> Terminals:
    terminals: Terminals = _container(settings, 30.0).get(Terminals)
    return terminals
