from github_orchestrator.change_detection.interface import (
    BecameUnmergeable,
    Mergeability,
    UnmergeableReason,
)

UNMERGEABLE: dict[Mergeability | None, BecameUnmergeable] = {
    Mergeability.CONFLICTS: BecameUnmergeable(UnmergeableReason.CONFLICTS),
    Mergeability.BEHIND: BecameUnmergeable(UnmergeableReason.BASE_UPDATED),
    Mergeability.BLOCKED: BecameUnmergeable(UnmergeableReason.BLOCKED),
}

REBASE_STATES = frozenset(state for state, event in UNMERGEABLE.items() if event.rebase)
