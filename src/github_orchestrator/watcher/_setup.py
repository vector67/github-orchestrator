import logging
import secrets
import threading
from collections.abc import Callable, Sequence, Set
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from github_orchestrator.board_api.interface import (
    CloneProgress,
    CloneSpot,
    CloneState,
    FieldRefusal,
    RepoChoice,
    Requirement,
    SetupOptions,
    SetupProgress,
    SetupRead,
    SetupRepo,
    SetupWrite,
    TourMarker,
    WriteState,
)
from github_orchestrator.domain import Clone, HubState, Repo, UtcClock
from github_orchestrator.github import Access
from github_orchestrator.pr_processes import PrProcesses
from github_orchestrator.settings import ConfigFile
from github_orchestrator.watcher._config import WatcherConfig
from github_orchestrator.watcher._leaving import Leaving

log = logging.getLogger(__name__)

LISTED_FOR = timedelta(minutes=1)
HOME = "~/"
CLONES = "repositories"


class Sweep(Protocol):
    def archive_other_repos(self, keep: Set[Repo], into: Path) -> list[Path]: ...


@dataclass(frozen=True)
class Archives:
    state: Sweep
    queues: Sweep
    transcripts: Sweep
    on_hold: Sweep

    def sweep(self, keep: Set[Repo], into: Path) -> list[Path]:
        return [
            *self.state.archive_other_repos(keep, into / "state"),
            *self.queues.archive_other_repos(keep, into / "queues"),
            *self.transcripts.archive_other_repos(keep, into / "transcripts"),
            *self.on_hold.archive_other_repos(keep, into / "on_hold"),
        ]


@dataclass(frozen=True)
class SetupSeams:
    clone_problem: Callable[[Repo, Path], str | None]
    requirements: Callable[[], Sequence[tuple[str, str | None]]]
    run_in: Callable[[Callable[[], None]], None]
    agent_name: str


def _parsed(repo: str) -> Repo | None:
    try:
        return Repo.parse(repo)
    except ValueError:
        return None


class ConfigSetup:
    def __init__(self, config: WatcherConfig, clock: UtcClock, seams: SetupSeams, *,
                 config_file: ConfigFile, access: Access, pr_processes: PrProcesses,
                 archives: Archives, leaving: Leaving, tour: TourMarker) -> None:
        self._config = config
        self._clock = clock
        self._seams = seams
        self._config_file = config_file
        self._access = access
        self._pr_processes = pr_processes
        self._archives = archives
        self._leaving = leaving
        self._tour = tour
        self._lock = threading.Lock()
        self._listed: dict[str, tuple[datetime, list[RepoChoice]]] = {}
        self._progress: dict[str, SetupProgress] = {}

    def read(self) -> SetupRead:
        rows = {row.key: row for row in self._config_file.describe().rows}
        account = rows["gh_account"]
        return SetupRead(
            state=self._config_file.state(),
            config_path=self._config_file.location(),
            problem=self._config_file.check(),
            active_account=self._access.active_account(),
            account=None if account.unset else str(account.value),
            repos=tuple(SetupRepo(str(entry.repo), entry.local_path,
                                  entry.new_worktree_command or "")
                        for entry in self._config_file.repos()),
            options=SetupOptions(str(rows["agent_model"].value),
                                 bool(rows["agents_enabled"].value),
                                 int(str(rows["max_thread_runs"].value))),
            hub_port=int(str(rows["hub_port"].value)),
            agent_name=self._seams.agent_name,
            requirements=tuple(Requirement(program, fix)
                               for program, fix in self._seams.requirements()),
        )

    def scopes(self, login: str) -> tuple[str, ...] | str:
        refused = self._access.check_login(login)
        return refused if refused is not None else self._access.scopes(login)

    def repos(self, login: str) -> list[RepoChoice] | str:
        now = self._clock()
        with self._lock:
            kept = self._listed.get(login)
        if kept is not None and now - kept[0] < LISTED_FOR:
            return kept[1]
        found = self._access.repos_of(login)
        if isinstance(found, str):
            return found
        choices = [RepoChoice(one.repo, one.can_push, one.has_my_prs, one.default_branch)
                   for one in found]
        with self._lock:
            self._listed[login] = (now, choices)
        return choices

    def repo(self, login: str, repo: Repo) -> RepoChoice | str:
        found = self._access.repo_of(login, repo)
        if isinstance(found, str):
            return found
        return RepoChoice(found.repo, found.can_push, found.has_my_prs, found.default_branch)

    def clone(self, repo: Repo) -> CloneSpot:
        written = next((entry.local_path for entry in self._config_file.repos()
                        if entry.repo == repo), f"{HOME}{CLONES}/{repo.name}")
        path = self._expanded(written)
        exists = path.exists()
        return CloneSpot(repo, written, exists,
                         exists and self._seams.clone_problem(repo, path) is None)

    def write(self, asked: SetupWrite) -> SetupProgress | list[FieldRefusal]:
        refused = self._refusals(asked)
        if refused:
            return refused
        operation = f"setup_{secrets.token_hex(6)}"
        clones = []
        for one in asked.repos:
            path = self._expanded(one.local_path)
            clones.append(CloneProgress(Repo.parse(one.repo), str(path),
                                        CloneState.FOUND if path.exists() else CloneState.WAITING))
        with self._lock:
            self._progress[operation] = SetupProgress(operation, WriteState.CLONING, tuple(clones))
        self._seams.run_in(lambda: self._carried_out(operation, asked))
        with self._lock:
            return self._progress[operation]

    def progress(self, operation: str) -> SetupProgress | None:
        with self._lock:
            return self._progress.get(operation)

    def move_aside(self) -> str | None:
        if self._config_file.state() is not HubState.BROKEN:
            return None
        moved = self._config_file.move_aside(self._clock())
        log.info("setup: moved the broken config aside to %s; restarting into setup", moved)
        self._leaving.ask()
        return moved

    def _expanded(self, written: str) -> Path:
        if written.startswith(HOME):
            return self._config.home / written[len(HOME):]
        return Path(written)

    def _refusals(self, asked: SetupWrite) -> list[FieldRefusal]:
        if self._config_file.state() is HubState.BROKEN:
            return [FieldRefusal("config", f"{self._config_file.describe().problem}; move it "
                                           "aside before writing a new one")]
        no_token = self._access.check_login(asked.account)
        if no_token is not None:
            return [FieldRefusal("gh_account", no_token)]
        refused = []
        seen: set[Repo] = set()
        for index, one in enumerate(asked.repos):
            refused += self._refused_repo(f"repos[{index}]", asked.account, one, seen)
        config_refused = self._config_file.check_write(self._values(asked),
                                                       repos=self._clones(asked))
        if config_refused is not None:
            refused.append(FieldRefusal("config", config_refused))
        return refused

    def _refused_repo(self, field: str, account: str, one: SetupRepo,
                      seen: set[Repo]) -> list[FieldRefusal]:
        repo = _parsed(one.repo)
        if repo is None:
            return [FieldRefusal(f"{field}.repo", f"{one.repo!r} is not owner/name")]
        if repo in seen:
            return [FieldRefusal(f"{field}.repo", f"{repo} is picked twice")]
        seen.add(repo)
        unseen = self._access.check_access(account, repo)
        if unseen is not None:
            return [FieldRefusal(f"{field}.repo", unseen)]
        path = self._expanded(one.local_path)
        problem = self._seams.clone_problem(repo, path) if path.exists() else None
        if problem is not None:
            return [FieldRefusal(f"{field}.local_path",
                                 f"{path} holds something that is not a clone of {repo}: "
                                 f"{problem}")]
        return []

    def _values(self, asked: SetupWrite) -> dict[str, str | int | bool]:
        options = asked.options
        return {"gh_account": asked.account, "agent_model": options.agent_model,
                "agents_enabled": options.agents_enabled,
                "max_thread_runs": options.max_thread_runs,
                **({} if asked.hub_port is None else {"hub_port": asked.hub_port})}

    def _clones(self, asked: SetupWrite) -> dict[Repo, Clone]:
        return {repo: Clone(Path(one.local_path), one.new_worktree_command)
                for one in asked.repos if (repo := _parsed(one.repo)) is not None}

    def _moved(self, operation: str, state: WriteState, *, error: str | None = None,
               archived: tuple[str, ...] = (), kept_worktrees: tuple[str, ...] = ()) -> None:
        with self._lock:
            self._progress[operation] = replace(
                self._progress[operation], state=state, error=error, archived=archived,
                kept_worktrees=kept_worktrees)

    def _cloned(self, operation: str, index: int, state: CloneState,
                error: str | None = None) -> None:
        with self._lock:
            progress = self._progress[operation]
            clones = list(progress.clones)
            clones[index] = replace(clones[index], state=state, error=error)
            self._progress[operation] = replace(progress, clones=tuple(clones))

    def _carried_out(self, operation: str, asked: SetupWrite) -> None:
        try:
            self._carry_out(operation, asked)
        except Exception as failed:
            log.exception("setup: the write %s failed", operation)
            self._moved(operation, WriteState.FAILED, error=str(failed))

    def _carry_out(self, operation: str, asked: SetupWrite) -> None:
        with self._lock:
            clones = self._progress[operation].clones
        for index, clone in enumerate(clones):
            if clone.state is CloneState.FOUND:
                continue
            self._cloned(operation, index, CloneState.CLONING)
            refused = self._cloned_into(clone.repo, Path(clone.path))
            if refused is not None:
                self._cloned(operation, index, CloneState.FAILED, refused)
                self._moved(operation, WriteState.FAILED,
                            error=f"could not clone {clone.repo}: {refused}")
                return
            self._cloned(operation, index, CloneState.CLONED)
        repos = self._clones(asked)
        keep = set(repos)
        into = self._config.archive_dir / self._clock().strftime("%Y%m%d-%H%M%S")
        archived = self._archives.sweep(keep, into)
        closed = self._pr_processes.close_other_repos(keep)
        first = self._config_file.state() is HubState.SETUP
        self._config_file.write(self._values(asked), repos=repos)
        if first:
            self._tour.arm()
        log.info("setup: wrote %s watching %s; restarting", self._config_file.location(),
                 ", ".join(str(repo) for repo in repos))
        self._moved(operation, WriteState.RESTARTING,
                    archived=tuple(str(path) for path in archived),
                    kept_worktrees=tuple(sorted(worktree for worktree in closed.values()
                                                if worktree is not None)))
        self._leaving.ask()

    def _cloned_into(self, repo: Repo, path: Path) -> str | None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return str(exc)
        log.info("setup: cloning %s into %s", repo, path)
        return self._access.clone(repo, path)
