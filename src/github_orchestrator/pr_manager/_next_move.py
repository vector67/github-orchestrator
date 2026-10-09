from github_orchestrator.change_detection import Facts, ReviewerStatus


def reviewed_before(facts: Facts) -> bool:
    return facts.my_review not in (None, ReviewerStatus.PENDING)
