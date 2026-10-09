from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Iterator

BLOCK_SIZE = 64 * 1024
SCAN_BYTES = 4 * 1024 * 1024


def iter_lines_reverse(path: Path) -> Iterator[str]:
    try:
        handle = path.open("rb")
    except OSError:
        return
    with handle:
        try:
            handle.seek(0, os.SEEK_END)
            pos = handle.tell()
            pending = b""
            read_total = 0
            at_end = True
            while pos > 0 and read_total < SCAN_BYTES:
                read = min(BLOCK_SIZE, pos, SCAN_BYTES - read_total)
                pos -= read
                handle.seek(pos)
                chunk = handle.read(read)
                read_total += read
                if at_end:
                    at_end = False
                    chunk = chunk.removesuffix(b"\n")
                parts = (chunk + pending).split(b"\n")
                pending = parts[0]
                for part in reversed(parts[1:]):
                    yield part.decode("utf-8", errors="replace")
            if pos == 0 and pending:
                yield pending.decode("utf-8", errors="replace")
        except OSError:
            return


def tail_lines(path: Path, n: int) -> list[str]:
    if n <= 0:
        return []
    collected: list[str] = []
    for line in iter_lines_reverse(path):
        collected.append(line)
        if len(collected) >= n:
            break
    collected.reverse()
    return collected


def print_tail(path: Path, n: int) -> None:
    print(f"==> {path} <==")
    if not path.exists():
        print("(no log yet)")
        return
    for line in tail_lines(path, n):
        print(line)


def follow(run: Callable[..., Any], cmd: list[str]) -> None:
    try:
        run(cmd)
    except KeyboardInterrupt:
        return


def tail_command(path: Path, n: int) -> list[str]:
    return ["tail", "-n", str(n), "-F", str(path)]
