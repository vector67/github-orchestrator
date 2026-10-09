from github_orchestrator.cli._restart_all import Instance, _heading
from github_orchestrator.cli._setup import ReadLine


def _stop_instance(read_line: ReadLine, instance: Instance, *, force: bool) -> None:
    named = "" if instance.name is None else f" for {instance.name}"
    _heading(f"Stopping the watcher{named}")
    instance.service.stop()
    _heading(f"Stopping the agent managers{named}")
    stopped = instance.pr_processes.stop_managers()
    if stopped:
        print(f"Stopped {len(stopped)} agent manager(s): {', '.join(str(pr) for pr in sorted(stopped))}.")
    else:
        print("No agent manager processes running.")
    _heading(f"Closing the terminal sessions{named}")
    _close_terminals(instance, read_line, named, force=force)


def agreed(read_line: ReadLine, prompt: str) -> bool:
    try:
        return read_line(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _close_terminals(instance: Instance, read_line: ReadLine, named: str, *, force: bool) -> None:
    still_open = instance.terminals.count()
    if still_open == 0:
        print("No terminal sessions open.")
        return
    if not force and not agreed(
            read_line, f"Close the {still_open} terminal session(s) still open{named}? [y/N] "):
        print(f"Left {still_open} terminal session(s) open.")
        return
    print(f"Closed {instance.terminals.close()} terminal session(s).")


def stop(read_line: ReadLine, instances: list[Instance], *, force: bool) -> None:
    for instance in instances:
        _stop_instance(read_line, instance, force=force)
