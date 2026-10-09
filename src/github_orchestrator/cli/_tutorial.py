from collections.abc import Callable

TOUR = "/?tour=1"


def tutorial(hub_url: str, opened: Callable[[str], None], *, terminal: bool, agent: str,
             described: str) -> None:
    if not terminal:
        opened(TOUR)
        return
    print(f"""What the installer set up on this machine:

  uv      Installs github-orchestrator and the Python it runs on, into ~/.local/bin.
  gh      GitHub's command line. The watcher reads your pull requests and sends your
          replies through its login.
  {agent:<7} {described}, which the agents that work on your pull requests run in.

  The watcher runs as a LaunchAgent on macOS, or a systemd user unit on Linux, so it
  starts when you log in. It polls GitHub and serves the board.
  On macOS, if you said yes to notifications, it also tells you when a PR needs you.

The board is at {hub_url}

Next:
  github-orchestrator open      Open the board.
  github-orchestrator setup     Pick the repos to watch and the options.
  github-orchestrator doctor    Check all of the above and say how to fix what fails.
  github-orchestrator tutorial  Take the board's tour again.""")
