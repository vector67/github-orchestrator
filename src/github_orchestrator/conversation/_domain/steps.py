from dataclasses import dataclass

from github_orchestrator.conversation._domain.commands import Approve


@dataclass(frozen=True)
class Land(Approve):
    """The board driving an approve it has already taken.

    `Approve` is the operator asking, and is refused while a landing is under
    way; the drain carries that landing through its pick, push and answer by
    applying this instead, once per step.
    """


@dataclass(frozen=True)
class First:
    pass


Step = (
      Land
    | First
)
