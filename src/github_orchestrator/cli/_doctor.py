import re
import socket
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from urllib.parse import urlsplit

from github_orchestrator.cli._config import CliConfig, Run, Which
from github_orchestrator.cli._findings import Finding, Level, fail, ok, warn
from github_orchestrator.cli._hub import PROBE_SECONDS, HealthBody, HubHealth
from github_orchestrator.cli._install_checks import (
    MACOS,
    Requirement,
    agent_findings,
    requirements_for,
)
from github_orchestrator.cli._service import RESTART, Service
from github_orchestrator.cli._skill import skill_finding
from github_orchestrator.cli._status import ago
from github_orchestrator.cli._tool_install import (
    PACKAGE,
    Install,
    checkout_of,
    install_of,
)
from github_orchestrator.cli._update import UPDATE, newer_release
from github_orchestrator.desktop import Desktop
from github_orchestrator.domain import HubState, Repo
from github_orchestrator.github import Access
from github_orchestrator.settings import Boards, ConfigFile
from github_orchestrator.watcher import Releases, WatcherHealth

COMMAND_TIMEOUT = 30
CONNECT_SECONDS = 1.0
GITHUB_REMOTE = re.compile(r"github\.com[:/](?P<repo>[^/]+/[^/]+?)(?:\.git)?/?$")


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=CONNECT_SECONDS):
            return True
    except OSError:
        return False


def clone_finding(run: Run, repo: Repo, path: Path) -> Finding:
    if not path.is_dir():
        return fail(f"no clone of {repo} at {path}", f"gh repo clone {repo} {path}")
    try:
        said = run(["git", "-C", str(path), "remote", "get-url", "origin"],
                   capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        return fail(f"could not read the origin of {path}: {exc}", "see the git line above")
    if said.returncode == 128:
        return fail(f"{path} is not a git repository",
                    f"move {path} aside, then gh repo clone {repo} {path}")
    url = str(said.stdout).strip()
    found = GITHUB_REMOTE.search(url)
    if said.returncode != 0 or found is None or found.group("repo") != str(repo):
        origin = url or str(said.stderr).strip()
        return fail(f"{path}'s origin is {origin}, not {repo}",
                    f"git -C {path} remote set-url origin https://github.com/{repo}.git")
    return ok(f"the clone at {path} has origin {repo}")


def clone_problem(run: Run) -> Callable[[Repo, Path], str | None]:
    def problem(repo: Repo, path: Path) -> str | None:
        found = clone_finding(run, repo, path)
        return None if found.level is Level.OK else found.reason
    return problem


class InstanceChecks:
    def __init__(self, config: CliConfig, config_file: ConfigFile, which: Which, run: Run,
                 service: Service, hub_health: HubHealth, watcher_health: WatcherHealth,
                 access: Access) -> None:
        self._config = config
        self._access = access
        self._service = service
        self._hub_health = hub_health
        self._watcher_health = watcher_health
        self._config_file = config_file
        self._which = which
        self._run = run

    def findings(self) -> list[Finding]:
        service = self._service.check()
        answer = self._hub_health(self._config.hub_url)
        return [
            *self._parses(),
            *self._hub_port(answer, service.pid),
            *(finding for requirement in requirements_for(self._config.agent)
              for finding in self._requirement(requirement, service.path)),
            *service.findings,
            *self._github(),
            self._hub(answer, service.pid),
            self._watcher(answer),
        ]

    def _github(self) -> list[Finding]:
        if self._config_file.check() is not None or self._which("gh") is None:
            return []
        account = self._config.gh_account
        refused = self._access.check_login(account)
        if refused is not None:
            return [fail(refused, f"gh auth login, as {account}")]
        return [ok(f"gh has a token for {account}"),
                *(finding for repo, clone in self._config.repos.items()
                  for finding in (self._sees(account, repo),
                                  clone_finding(self._run, repo, clone.path)))]

    def _sees(self, account: str, repo: Repo) -> Finding:
        unseen = self._access.check_access(account, repo)
        return ok(f"{account} can see {repo}") if unseen is None else fail(
            unseen, f"ask for access to {repo} for {account}; if it is private, gh's token "
                    "needs the repo scope: gh auth refresh --scopes repo")

    def _hub_port(self, answer: HealthBody | None, pid: int | None) -> list[Finding]:
        port = urlsplit(self._config.hub_url).port or 0
        if answer is not None:
            if answer.get("pid") == pid:
                return [ok(f"hub_port {port} is held by this instance's hub")]
            return []
        if not _listening(port):
            return [ok(f"hub_port {port} is free")]
        names_it = (f"lsof -nP -iTCP:{port} -sTCP:LISTEN" if self._config.platform == MACOS
                    else f"ss -ltnp 'sport = :{port}'")
        return [fail(f"hub_port {port} is held by a program that does not answer /api/health "
                     "as a hub",
                     f"{RESTART} if that is this instance's hub; otherwise set hub_port in "
                     f"{self._config_file.location()} to a free port, or stop what holds it "
                     f"({names_it} names it)")]

    def _hub(self, answer: HealthBody | None, pid: int | None) -> Finding:
        hub_url = self._config.hub_url
        if answer is None:
            return fail(f"the hub at {hub_url} does not answer /api/health within "
                        f"{PROBE_SECONDS:g}s",
                        f"{RESTART}; github-orchestrator logs shows why")
        answering = answer.get("pid")
        if answering != pid:
            started = "no watcher" if pid is None else f"pid {pid}"
            return fail(f"the hub at {hub_url} answers from pid {answering}, not from the watcher "
                        f"the service started ({started})",
                        f"stop pid {answering}, then {RESTART}")
        state, expected = answer.get("state"), self._config_file.state()
        if state != expected:
            return fail(f"the hub at {hub_url} is in {state}, but its config is {expected} now",
                        RESTART)
        return ok(f"the hub answers at {hub_url} from the watcher, pid {pid}, {state}")

    def _watcher(self, answer: HealthBody | None) -> Finding:
        if answer is not None and answer.get("state") != HubState.WATCHING:
            return ok("the watcher polls nothing until the config is complete")
        health = self._watcher_health.health()
        since = health.since_last_poll
        if health.last_error is not None:
            good = ("no poll has ever succeeded" if since is None
                    else f"last good poll {ago(since)} ago")
            return fail(f"the watcher is failing ({good}): {' '.join(health.last_error.split())}",
                        "github-orchestrator logs shows the whole error")
        if not (answer is not None or health.alive):
            return fail("the watcher is not running", RESTART)
        if since is None:
            return warn("the watcher is running but has not finished a poll yet",
                        "github-orchestrator logs shows what it is doing")
        if health.overdue:
            return fail(f"the watcher last polled {ago(since)} ago, but polls every "
                        f"{ago(health.polls_every)}", RESTART)
        return ok(f"the watcher last polled {ago(since)} ago")

    def _parses(self) -> list[Finding]:
        location = self._config_file.location()
        problem = self._config_file.check()
        legacy = self._config_file.describe().legacy
        old = ([warn(f"config {location} still writes {' and '.join(legacy)}, the old form",
                     f"{RESTART} rewrites it and keeps the old one beside it")]
               if legacy and problem is None else [])
        if problem is not None and self._config_file.state() is HubState.SETUP:
            return [warn(problem, "github-orchestrator setup")]
        if problem is not None:
            return [fail(problem, f"edit {location}")]
        return [ok(f"config {location} parses"), *old]

    def _requirement(self, requirement: Requirement, service_path: str | None) -> list[Finding]:
        program = requirement.named(self._config.agent, self._config.agent_program)
        found = self._which(program)
        if found is None:
            return [fail(f"{program} is not on PATH; it is needed for {requirement.purpose}",
                         requirement.install(self._config.platform))]
        here = ok(f"gh {self._gh_version(found)} at {found}" if requirement.program == "gh"
                  else f"{program} at {found}")
        if service_path is None or self._which(program, path=service_path) is not None:
            return [here]
        return [here, fail(f"{program} is not on the watcher's PATH ({service_path})",
                           f"github-orchestrator restart, from a shell whose PATH finds {program}")]

    def _gh_version(self, gh: str) -> str:
        try:
            said = self._run([gh, "--version"], capture_output=True, text=True,
                             timeout=COMMAND_TIMEOUT)
        except (OSError, subprocess.SubprocessError):
            return "(version unknown)"
        words = str(said.stdout).split()
        return words[2] if said.returncode == 0 and len(words) > 2 else "(version unknown)"


class MachineChecks:
    def __init__(self, config: CliConfig, run: Run, which: Which, desktop: Desktop,
                 boards: Boards, service: Service, hub_health: HubHealth,
                 releases: Releases) -> None:
        self._config = config
        self._hub_health = hub_health
        self._releases = releases
        self._run = run
        self._which = which
        self._desktop = desktop
        self._boards = boards
        self._service = service

    def findings(self) -> list[Finding]:
        used, out_of = self._boards.ports_in_use()
        install = install_of(self._config.python)
        newer = newer_release(self._config, self._hub_health(self._config.hub_url),
                              self._releases)
        return [
            self._install(install),
            *([] if newer is None else [warn(f"github-orchestrator {newer} is out", UPDATE)]),
            self._command(install),
            skill_finding(self._config.agent.skill_folder(self._config.home)),
            *agent_findings(self._config.agent, self._config.agent_argv, self._run),
            self._notifications(),
            ok(f"{used} of {out_of} board ports are in use"),
        ]

    def _install(self, install: Install) -> Finding:
        running = f"{PACKAGE} {self._config.version or '(version unknown)'}"
        if install.source is None:
            return warn(f"{running} runs from {install.venv}, not a uv tool install",
                        install.reinstall)
        return ok(f"{running}, a uv tool in {install.venv}, installed from {install.source}")

    def _command(self, install: Install) -> Finding:
        found = self._which(PACKAGE)
        if found is None:
            return fail(f"{PACKAGE} is not on PATH", "uv tool update-shell, then open a new terminal")
        target = Path(found).resolve()
        if install.source is not None and target == (install.venv / "bin" / PACKAGE).resolve():
            return ok(f"{PACKAGE} on PATH ({found}) is the uv tool's command")
        checkout = checkout_of(target.parent.parent)
        if checkout is not None:
            return fail(f"{PACKAGE} on PATH ({found}) is a link into the checkout at {checkout}, "
                        "not a uv tool's command", install.reinstall)
        return fail(f"{PACKAGE} on PATH ({found}) is {target}, not this install's command",
                    install.reinstall)

    def _notifications(self) -> Finding:
        missing = self._desktop.notifications(self._service.check().path or self._config.shell_path)
        if missing is None:
            return ok("desktop notifications are set up")
        return warn(*missing)


def report(sections: Sequence[tuple[str, list[Finding]]]) -> None:
    for title, findings in sections:
        print(title)
        for finding in findings:
            print(f"  {finding.level.value:<4}  {finding.reason}")
            if finding.fix:
                print(f"        fix: {finding.fix}")
        print()
    if any(finding.level is Level.FAIL for _, findings in sections for finding in findings):
        sys.exit(1)
