from github_orchestrator.conversation._domain.commands import Command
from github_orchestrator.conversation._domain.events import Event
from github_orchestrator.conversation._domain.steps import Step

Change = Command | Event | Step
