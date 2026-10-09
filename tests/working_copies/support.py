import subprocess
import threading
from collections.abc import Mapping
from pathlib import Path

from github_orchestrator.domain import Clone, Pr, Repo
from github_orchestrator.github import PullRequestState
from github_orchestrator.github.fake import FakeGitHub
from github_orchestrator.notifications.fake import FakeNotifications
from github_orchestrator.settings.fake import Settings
from github_orchestrator.wiring import WorkingCopiesWiring, wire
from github_orchestrator.working_copies import PrCheckout, WorkingCopies
from github_orchestrator.working_copies.fake import FakeWorkingCopies
from tests.builders import a_pr
from tests.conftest import fake_github, fake_notifications

REPO = "owner/name"
PR = 7
THE_PR = a_pr(PR, REPO)
BRANCH = "feature"


def clone_of(pr: Pr, repo_dir: Path, new_worktree_command: str = "") -> dict[Repo, Clone]:
    return {pr.repo: Clone(repo_dir, new_worktree_command)}


def real_working_copies(settings: Settings, github: FakeGitHub | None = None,
                        notifications: FakeNotifications | None = None,
                        clones: Mapping[Repo, Clone] | None = None) -> WorkingCopies:
    working_copies: WorkingCopies = wire(
        fake_github(github or FakeGitHub()),
        fake_notifications(notifications or FakeNotifications()),
        WorkingCopiesWiring(
            mismatched_dir=settings.mismatched_dir,
            worktree_conflicts_dir=settings.worktree_conflicts_dir,
            thread_worktrees_dir=settings.thread_worktrees_dir,
            clones=settings.repos if clones is None else clones,
            grace_seconds=settings.config.mismatch_grace_seconds,
            run_idle_seconds=settings.config.mismatch_run_idle_seconds,
        ),
    ).get(WorkingCopies)
    return working_copies


def copies_for(settings: Settings, pr: Pr, repo_dir: Path,
               branch: str = "main", new_worktree_command: str = "") -> WorkingCopies:
    github = FakeGitHub()
    github.add_pr(pr, PullRequestState(branch=branch))
    return real_working_copies(settings, github,
                               clones=clone_of(pr, repo_dir, new_worktree_command))


def found_checkout(settings: Settings, pr: Pr, repo_dir: Path) -> PrCheckout:
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo_dir)], check=True)
    checkout = copies_for(settings, pr, repo_dir).checkout(pr)
    assert checkout.no_worktree() is None
    return checkout


def branch_at(worktree: Path | str) -> str | None:
    if not Path(worktree).exists():
        return None
    shown = subprocess.run(["git", "-C", str(worktree), "rev-parse", "--abbrev-ref", "HEAD"],
                           capture_output=True, text=True)
    branch = shown.stdout.strip()
    return None if shown.returncode != 0 or branch in ("", "HEAD") else branch


def settle_progress() -> None:
    for counting in threading.enumerate():
        if counting.name.startswith("thread progress"):
            counting.join(timeout=10)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _identify(clone: Path) -> None:
    git(clone, "config", "user.email", "t@example.com")
    git(clone, "config", "user.name", "T")


def build_origin(root: Path) -> None:
    origin = root / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seed = root / "seed"
    subprocess.run(["git", "clone", "-q", str(origin), str(seed)], check=True)
    _identify(seed)
    (seed / "f").write_text("1\n")
    git(seed, "add", "f")
    git(seed, "commit", "-q", "-m", "first")
    git(seed, "push", "-q", "origin", "main")
    git(seed, "checkout", "-q", "-b", BRANCH)
    (seed / "g").write_text("one\ntwo\nthree\n")
    git(seed, "add", "g")
    git(seed, "commit", "-q", "-m", "feature work")
    git(seed, "push", "-q", "origin", BRANCH)
    repo = root / "repo"
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True)
    _identify(repo)


class GitWorld:
    def __init__(self, root: Path, settings: Settings) -> None:
        self.root = root
        self.repo_dir = root / "repo"
        self.github = FakeGitHub()
        self.github.add_pr(THE_PR, PullRequestState(branch=BRANCH))
        self.notifications = FakeNotifications()
        self.copies = real_working_copies(settings, self.github, self.notifications,
                                          clone_of(THE_PR, self.repo_dir))

    def commit(self, worktree: Path | str, files: dict[str, str], message: str) -> str:
        for name, text in files.items():
            (Path(worktree) / name).write_text(text)
        git(Path(worktree), "add", *files)
        git(Path(worktree), "commit", "-q", "-m", message)
        return git(Path(worktree), "rev-parse", "HEAD")

    def edit(self, worktree: Path | str, name: str, text: str) -> None:
        (Path(worktree) / name).write_text(text)

    def check_out(self, worktree: Path, branch: str) -> None:
        git(worktree, "checkout", "-q", branch)

    def local_worktree(self, path: Path, branch: str) -> None:
        git(self.repo_dir, "worktree", "add", "-q", "-b", branch, str(path))

    def lose_worktree(self, path: Path | str) -> None:
        git(self.repo_dir, "worktree", "remove", "--force", str(path))

    def branch_at(self, worktree: Path | str) -> str | None:
        return branch_at(worktree)

    def head_of(self, worktree: Path | str) -> str:
        return git(Path(worktree), "rev-parse", "HEAD")

    def has_branch(self, branch: str) -> bool:
        return subprocess.run(
            ["git", "-C", str(self.repo_dir), "rev-parse", "--verify", "--quiet",
             f"refs/heads/{branch}"], capture_output=True).returncode == 0

    def advance_base(self) -> tuple[str, str]:
        seed = self.root / "seed"
        git(seed, "checkout", "-q", "main")
        (seed / "m").write_text("more\n")
        git(seed, "add", "m")
        git(seed, "commit", "-q", "-m", "more main")
        git(seed, "push", "-q", "origin", "main")
        git(seed, "checkout", "-q", BRANCH)
        git(seed, "rebase", "-q", "main")
        git(seed, "push", "-q", "--force", "origin", BRANCH)
        return git(seed, "rev-parse", "main"), git(seed, "rev-parse", BRANCH)


class FakeWorld:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.repo_dir = root / "repo"
        self.github = FakeGitHub()
        self.github.add_pr(THE_PR, PullRequestState(branch=BRANCH))
        self.notifications = FakeNotifications()
        fake = FakeWorkingCopies(github=self.github, notifications=self.notifications)
        main = fake.add_repo(self.repo_dir, {"f": "1\n"}, "first")
        fake.publish(BRANCH, main, {"g": "one\ntwo\nthree\n"}, "feature work")
        self.copies = fake
        self.fake = fake

    def commit(self, worktree: Path | str, files: dict[str, str], message: str) -> str:
        return self.fake.commit(worktree, files, message)

    def edit(self, worktree: Path | str, name: str, text: str) -> None:
        self.fake.edit(worktree, name, text)

    def check_out(self, worktree: Path, branch: str) -> None:
        self.fake.check_out(worktree, branch)

    def local_worktree(self, path: Path, branch: str) -> None:
        self.fake.add_worktree(path, branch)

    def lose_worktree(self, path: Path | str) -> None:
        self.fake.lose_worktree(path)

    def branch_at(self, worktree: Path | str) -> str | None:
        return self.fake.branch_at(worktree)

    def head_of(self, worktree: Path | str) -> str | None:
        return self.fake.head_of(worktree)

    def has_branch(self, branch: str) -> bool:
        return branch in self.fake.branches

    def advance_base(self) -> tuple[str, str]:
        main = self.fake.publish("main", self.fake.origin["main"], {"m": "more\n"}, "more main")
        head = self.fake.publish(BRANCH, main, {"g": "one\ntwo\nthree\n"}, "feature work")
        return main, head
