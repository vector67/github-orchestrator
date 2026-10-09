import subprocess
from collections.abc import Sequence
from dataclasses import dataclass

from github_orchestrator.agent_runs import Agent
from github_orchestrator.cli._config import Run, Which
from github_orchestrator.cli._findings import Finding, fail, ok, warn

MACOS = "darwin"
MCP_LIST_TIMEOUT = 120


@dataclass(frozen=True)
class Requirement:
    program: str
    purpose: str
    macos: str
    linux: str

    def install(self, platform: str) -> str:
        return self.macos if platform == MACOS else self.linux

    def named(self, agent: Agent, agent_program: str) -> str:
        return agent_program if self.program == agent.value else self.program


GH_RELEASES = "https://github.com/cli/cli/releases/latest"
CLAUDE_INSTALLER = "curl -fsSL https://claude.ai/install.sh | bash"
CODEX_INSTALLER = "npm install -g @openai/codex"
LOGIN_TIMEOUT = 30

GH = Requirement("gh", "GitHub API access and auth",
                 f"download the macOS zip from {GH_RELEASES} and put its bin/gh in ~/.local/bin",
                 f"download the linux_amd64 or linux_arm64 tarball from {GH_RELEASES} and put "
                 "its bin/gh in ~/.local/bin")
GIT = Requirement("git", "worktrees and commits", "xcode-select --install",
                  "install git with your distribution's package manager, e.g. sudo apt install git")
AGENT_REQUIREMENTS = {
    Agent.CLAUDE: Requirement("claude", "every agent run", CLAUDE_INSTALLER, CLAUDE_INSTALLER),
    Agent.CODEX: Requirement("codex", "every agent run",
                             f"install the ChatGPT app, which carries codex, or {CODEX_INSTALLER}",
                             CODEX_INSTALLER),
}


def requirements_for(agent: Agent) -> tuple[Requirement, ...]:
    return (GH, AGENT_REQUIREMENTS[agent], GIT)


def requirement_fixes(which: Which, agent: Agent, agent_program: str,
                      platform: str) -> list[tuple[str, str | None]]:
    return [(requirement.named(agent, agent_program),
             None if which(requirement.named(agent, agent_program)) is not None
             else requirement.install(platform))
            for requirement in requirements_for(agent)]


def agent_findings(agent: Agent, argv: Sequence[str], run: Run) -> list[Finding]:
    if agent is Agent.CODEX:
        return [codex_login_finding(argv, run)]
    return [atlassian_finding(argv, run)]


def codex_login_finding(codex: Sequence[str], run: Run) -> Finding:
    try:
        said = run([*codex, "login", "status"], capture_output=True, text=True,
                   timeout=LOGIN_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        return fail(f"could not ask codex whether it is logged in: {exc}", "codex login status")
    status = next((line.strip() for line in f"{said.stderr}\n{said.stdout}".splitlines()
                   if line.strip()), f"codex login status exited {said.returncode}")
    if said.returncode != 0:
        return fail(f"codex is not logged in: {status}", "codex login")
    return ok(f"codex is logged in: {status}")


def atlassian_finding(claude: Sequence[str], run: Run) -> Finding:
    try:
        listed = run([*claude, "mcp", "list"], capture_output=True, text=True,
                     timeout=MCP_LIST_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        return _could_not_check(str(exc))
    if listed.returncode != 0:
        return _could_not_check(f"claude mcp list exited {listed.returncode}")
    atlassian = [line for line in listed.stdout.splitlines() if "atlassian" in line.lower()]
    if any("✔ Connected" in line for line in atlassian):
        return ok("the Atlassian MCP server is connected in Claude")
    found = "is not connected" if atlassian else "does not seem to be available"
    return warn(f"the Atlassian MCP server {found} in Claude, so reviews run without each PR's "
                "Jira ticket",
                "enable the Atlassian connector on claude.ai, or claude mcp add")


def _could_not_check(reason: str) -> Finding:
    return warn(f"could not check for the Atlassian MCP server, which reviews use to read each "
                f"PR's Jira ticket ({reason})",
                "claude mcp list shows whether it is there")
