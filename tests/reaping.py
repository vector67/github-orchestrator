import ctypes
import os
import select
import signal
import subprocess
import sys

MOST_CHILDREN = 4096
FOLLOWED_EVENTS = select.KQ_NOTE_FORK | select.KQ_NOTE_EXIT if hasattr(select, "kqueue") else 0

_reaper: subprocess.Popen[bytes] | None = None
_spares: int | None = None


def reap_what_this_process_leaves() -> int | None:
    global _reaper, _spares
    if not hasattr(select, "kqueue"):
        return None
    told, telling = os.pipe()
    _reaper = subprocess.Popen([sys.executable, "-I", __file__, str(os.getpid()), str(told)],
                               pass_fds=(told,), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               start_new_session=True)
    os.close(told)
    assert _reaper.stdout is not None
    _reaper.stdout.read(1)
    _reaper.stdout.close()
    _spares = telling
    return _reaper.pid


def spare(pid: int) -> None:
    if _spares is not None:
        os.write(_spares, f"{pid}\n".encode())


def _children_of(pid: int) -> list[int]:
    found = (ctypes.c_int * MOST_CHILDREN)()
    count = int(ctypes.CDLL(None).proc_listchildpids(pid, found, ctypes.sizeof(found)))
    return list(found[:max(count, 0)])


class _Followed:
    def __init__(self) -> None:
        self.queue = select.kqueue()
        self.pids: set[int] = set()

    def follow(self, pid: int) -> None:
        if pid in self.pids or pid == os.getpid():
            return
        try:
            self.queue.control([select.kevent(pid, select.KQ_FILTER_PROC, select.KQ_EV_ADD,
                                              FOLLOWED_EVENTS)], 0)
        except ProcessLookupError:
            return
        self.pids.add(pid)
        for child in _children_of(pid):
            self.follow(child)

    def take(self, events: list[select.kevent]) -> None:
        for event in events:
            if event.fflags & select.KQ_NOTE_FORK:
                for child in _children_of(event.ident):
                    self.follow(child)
            if event.fflags & select.KQ_NOTE_EXIT:
                self.pids.discard(event.ident)


def _spared(spares: int) -> set[int]:
    os.set_blocking(spares, False)
    told = b""
    try:
        while chunk := os.read(spares, 4096):
            told += chunk
    except BlockingIOError:
        pass
    return {int(pid) for pid in told.split()}


def _reap(root: int, spares: int) -> None:
    followed = _Followed()
    followed.follow(root)
    sys.stdout.buffer.write(b"\0")
    sys.stdout.close()
    while root in followed.pids:
        followed.take(followed.queue.control(None, 64))
    followed.take(followed.queue.control(None, 1024, 0))
    for pid in followed.pids - _spared(spares):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


if __name__ == "__main__":
    _reap(int(sys.argv[1]), int(sys.argv[2]))
