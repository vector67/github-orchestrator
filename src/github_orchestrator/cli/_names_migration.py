from github_orchestrator.cli._restart_all import Instance, _heading
from github_orchestrator.cli._setup import ReadLine
from github_orchestrator.cli._stop import agreed
from github_orchestrator.thread_names import HeldFolder


def _line(held: HeldFolder) -> str:
    return f"  {held.pr}, thread {held.thread}: {held.folder}"


def clear_the_way(instance: Instance, read_line: ReadLine, *, force: bool) -> None:
    held = instance.migration.held()
    if not held:
        return
    named = "" if instance.name is None else f" for {instance.name}"
    _heading(f"Checking the thread names migration{named}")
    print("A terminal session is in each folder the thread names migration moves:")
    for one in held:
        print(_line(one))
    if force or agreed(read_line, "Close these sessions and migrate? [y/N] "):
        instance.migration.close_sessions()
        print("Closed them; the watcher migrates the thread names as it starts.")
        return
    print("Left them open. The watcher waits to migrate until they close, and the board "
          "offers Close sessions and migrate.")
