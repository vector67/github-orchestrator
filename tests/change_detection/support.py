import json
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from github_orchestrator.change_detection import ChangeDetection, Poll, PrEvent
from github_orchestrator.change_detection.fake import FakeChangeDetection
from github_orchestrator.domain import Pr
from github_orchestrator.github import PullRequestState
from github_orchestrator.github.fake import Check
from github_orchestrator.wiring import ChangeDetectionWiring, WouldSaveWiring, wire
from tests.builders import a_pr
from tests.conftest import clocks_of

ACCOUNT = "octocat"
REPO = "acme/widgets"
PR = 7
THE_PR = a_pr(PR, REPO)
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
POLLED_AT = "2026-09-23T11:00:00Z"


def state_file(state_dir: Path, pr: Pr) -> Path:
    return Path(state_dir) / pr.repo.owner / pr.repo.name / f"{pr.number}.json"


def now() -> datetime:
    return NOW


def disk_change_detection(state_dir: Path, *, clock: Callable[[], datetime] = now,
                          poll_interval: int = 60) -> ChangeDetection:
    change_detection: ChangeDetection = wire(
        ChangeDetectionWiring(state_dir, ACCOUNT, poll_interval),
        clocks_of(clock),
    ).get(ChangeDetection)
    return change_detection


def would_save_change_detection(state_dir: Path, said: list[str]) -> ChangeDetection:
    change_detection: ChangeDetection = wire(
        ChangeDetectionWiring(state_dir, ACCOUNT, 60),
        clocks_of(now),
        WouldSaveWiring(said.append),
    ).get(ChangeDetection)
    return change_detection


def fake_change_detection(*, clock: Callable[[], datetime] = now,
                          poll_interval: int = 60) -> FakeChangeDetection:
    return FakeChangeDetection(ACCOUNT, poll_interval, clock)


def passing(name: str = "tests") -> Check:
    return Check(name, "completed", "success", f"https://ci/{name}", f"{name} passed")


def failing(name: str = "tests") -> Check:
    return Check(name, "completed", "failure", f"https://ci/{name}", f"{name} failed")


def pr_state(**fields: Any) -> PullRequestState:
    return replace(PullRequestState(
        title="Add widgets", url="https://github.com/acme/widgets/pull/7",
        author=ACCOUNT, branch="PROJ-7-widgets", base_branch="main", head_sha="sha0",
        mergeable=True, mergeable_state="clean", checks=(passing(),),
        review_decision="REVIEW_REQUIRED",
    ), **fields)


def poll(state: PullRequestState | None = None, *, at: str = POLLED_AT,
         **fields: Any) -> Poll:
    return Poll(state=state or pr_state(), polled_at=at, **fields)


def seen(account: str, *, is_author: bool = True, polled_at: str = POLLED_AT,
         my_last_comment_at: str | None = None, comments_by_others: int = 0,
         unresolved_thread_count: int | None = None, **state: Any) -> Poll:
    author = account if is_author else None
    return Poll(PullRequestState(**{"author": author, **state}), polled_at,
                my_last_comment_at=my_last_comment_at, comments_by_others=comments_by_others,
                unresolved_thread_count=unresolved_thread_count)


def polled_on_disk(state_dir: Path, pr: Pr, *polls: Poll) -> None:
    change_detection = disk_change_detection(state_dir)
    for each in polls:
        change_detection.advance(pr, each, set())


def types(events: list[PrEvent]) -> list[str]:
    return [event.kind for event in events]


def remember(state_dir: Path, pr: Pr, snapshot: dict[str, Any]) -> None:
    path = state_file(state_dir, pr)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot))
