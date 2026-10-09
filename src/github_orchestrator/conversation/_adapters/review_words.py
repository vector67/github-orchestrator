from github_orchestrator.conversation._domain.conversation import ReviewState
from github_orchestrator.conversation._domain.review import Verdict

_STATES_WRITTEN_BEFORE = {
    "APPROVED": ReviewState.APPROVED,
    "CHANGES_REQUESTED": ReviewState.CHANGES_REQUESTED,
    "COMMENTED": ReviewState.COMMENTED,
    "DISMISSED": ReviewState.DISMISSED,
    "PENDING": ReviewState.PENDING,
}

_VERDICTS_WRITTEN_BEFORE = {
    "APPROVE": Verdict.APPROVE,
    "REQUEST_CHANGES": Verdict.REQUEST_CHANGES,
    "COMMENT": Verdict.COMMENT,
}


def review_state_word(state: ReviewState | None) -> str | None:
    return None if state is None else state.value


def review_state_of(word: object) -> ReviewState | None:
    if not isinstance(word, str):
        return None
    return next((state for state in ReviewState if state.value == word),
                _STATES_WRITTEN_BEFORE.get(word))


def verdict_word(verdict: Verdict) -> str:
    return verdict.value


def verdict_of(word: object) -> Verdict:
    found = next((verdict for verdict in Verdict if verdict.value == word),
                 _VERDICTS_WRITTEN_BEFORE.get(word) if isinstance(word, str) else None)
    if found is None:
        raise ValueError(f"{word!r} is no review verdict")
    return found
