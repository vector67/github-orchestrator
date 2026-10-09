import logging
import socket
from collections.abc import Set
from pathlib import Path

from github_orchestrator.domain import Pr, Repo
from github_orchestrator.settings._paths import repo_subdir
from github_orchestrator.settings.interface import Dismissal

log = logging.getLogger(__name__)

PORT_RANGE = range(8730, 8830)
_STORED = {"until-event": Dismissal.UNTIL_NEXT_EVENT, "forever": Dismissal.FOREVER}
_WORDS = {dismissal: word for word, dismissal in _STORED.items()}


def _is_free(port: int) -> bool:
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _flag_prs(flag_dir: Path) -> set[Pr]:
    if not flag_dir.exists():
        return set()
    flagged = set()
    for path in flag_dir.glob("*/*/*.flag"):
        owner, name, pr_file = path.relative_to(flag_dir).parts
        try:
            flagged.add(Pr(Repo(owner, name), int(pr_file[: -len(".flag")])))
        except ValueError:
            continue
    return flagged


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def _remove(pr: Pr, *paths: Path) -> bool:
    ok = True
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            log.warning("reap %s: failed to remove %s", pr, path, exc_info=True)
            ok = False
    return ok


def _flag_file(flag_dir: Path, pr: Pr) -> Path:
    return repo_subdir(flag_dir, pr.repo) / f"{pr.number}.flag"


class FlagFileHolds:
    def __init__(self, on_hold_dir: Path) -> None:
        self._on_hold_dir = on_hold_dir

    def on_hold(self, pr: Pr) -> bool:
        return _flag_file(self._on_hold_dir, pr).exists()

    def set_on_hold(self, pr: Pr, on_hold: bool) -> None:
        flag = _flag_file(self._on_hold_dir, pr)
        if on_hold:
            _touch(flag)
        else:
            flag.unlink(missing_ok=True)

    def on_hold_prs(self) -> set[Pr]:
        return _flag_prs(self._on_hold_dir)

    def forget(self, pr: Pr) -> bool:
        return _remove(pr, _flag_file(self._on_hold_dir, pr))

    def archive_other_repos(self, keep: Set[Repo], into: Path) -> list[Path]:
        archived: list[Path] = []
        if not self._on_hold_dir.exists():
            return archived
        for owner_dir in self._on_hold_dir.iterdir():
            if not owner_dir.is_dir():
                continue
            for repo_dir in list(owner_dir.iterdir()):
                if not repo_dir.is_dir():
                    continue
                if (owner_dir.name, repo_dir.name) in {(repo.owner, repo.name) for repo in keep}:
                    continue
                dest_parent = into / owner_dir.name
                dest_parent.mkdir(parents=True, exist_ok=True)
                dest = dest_parent / repo_dir.name
                repo_dir.rename(dest)
                archived.append(dest)
        return archived


class FlagFileDismissals:
    def __init__(self, dismissed_dir: Path) -> None:
        self._dismissed_dir = dismissed_dir

    def dismissal(self, pr: Pr) -> Dismissal | None:
        path = _flag_file(self._dismissed_dir, pr)
        if not path.exists():
            return None
        try:
            word = path.read_text().strip()
        except (OSError, UnicodeDecodeError):
            return None
        return _STORED.get(word)

    def _dismiss(self, pr: Pr, dismissal: Dismissal) -> None:
        path = _flag_file(self._dismissed_dir, pr)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_WORDS[dismissal])

    def dismiss_forever(self, pr: Pr) -> None:
        self._dismiss(pr, Dismissal.FOREVER)

    def dismiss_until_next_event(self, pr: Pr) -> None:
        self._dismiss(pr, Dismissal.UNTIL_NEXT_EVENT)

    def is_hidden(self, pr: Pr, events_waiting: bool) -> bool:
        dismissal = self.dismissal(pr)
        if dismissal is Dismissal.UNTIL_NEXT_EVENT and events_waiting:
            log.info("%s: an event is waiting — ending its dismissal until the next event", pr)
            self.undismiss(pr)
            return False
        return dismissal is not None

    def is_dismissed_forever(self, pr: Pr) -> bool:
        return self.dismissal(pr) is Dismissal.FOREVER

    def undismiss(self, pr: Pr) -> bool:
        try:
            _flag_file(self._dismissed_dir, pr).unlink()
        except FileNotFoundError:
            return False
        return True

    def dismissed_prs(self) -> set[Pr]:
        return _flag_prs(self._dismissed_dir)

    def forget(self, pr: Pr) -> bool:
        return _remove(pr, _flag_file(self._dismissed_dir, pr))


class FlagFileBoards:
    def __init__(self, board_dir: Path) -> None:
        self._board_dir = board_dir

    def _port_file(self, pr: Pr) -> Path:
        return repo_subdir(self._board_dir, pr.repo) / f"{pr.number}.port"

    def board_wanted(self, pr: Pr) -> bool:
        return _flag_file(self._board_dir, pr).exists()

    def want_board(self, pr: Pr, wanted: bool) -> None:
        flag = _flag_file(self._board_dir, pr)
        if wanted:
            _touch(flag)
        else:
            flag.unlink(missing_ok=True)

    def _assigned_ports(self) -> set[int]:
        ports = set()
        for path in self._board_dir.glob("*/*/*.port"):
            try:
                ports.add(int(path.read_text().strip()))
            except (OSError, ValueError):
                continue
        return ports

    def _pick_port(self) -> int:
        taken = self._assigned_ports()
        for port in PORT_RANGE:
            if port not in taken and _is_free(port):
                return port
        raise RuntimeError(
            f"no free board port between {PORT_RANGE.start} and {PORT_RANGE.stop - 1}"
        )

    def board_port(self, pr: Pr) -> int:
        path = self._port_file(pr)
        try:
            return int(path.read_text().strip())
        except (OSError, ValueError):
            pass
        port = self._pick_port()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(port))
        return port

    def ports_in_use(self) -> tuple[int, int]:
        return sum(not _is_free(port) for port in PORT_RANGE), len(PORT_RANGE)

    def forget(self, pr: Pr) -> bool:
        return _remove(pr, self._port_file(pr), _flag_file(self._board_dir, pr))
