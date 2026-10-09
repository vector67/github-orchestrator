from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

BLOCK_SIZE = 64 * 1024


def iter_lines_reverse(path: Path, *, max_bytes: int) -> Iterator[str]:
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
            while pos > 0 and read_total < max_bytes:
                read = min(BLOCK_SIZE, pos, max_bytes - read_total)
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
