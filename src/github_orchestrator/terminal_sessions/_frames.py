import struct
from collections.abc import Iterator

OUTPUT = b"o"
EXIT = b"x"
INPUT = b"i"
RESIZE = b"r"
RESUME = b"f"

_HEADER = struct.Struct("!cI")
_SIZE = struct.Struct("!HH")


def framed(kind: bytes, payload: bytes = b"") -> bytes:
    return _HEADER.pack(kind, len(payload)) + payload


def sized(columns: int, rows: int) -> bytes:
    return _SIZE.pack(columns, rows)


def size_of(payload: bytes) -> tuple[int, int]:
    columns, rows = _SIZE.unpack(payload)
    return columns, rows


class Unframer:
    def __init__(self) -> None:
        self._buffer = bytearray()

    def fed(self, data: bytes) -> Iterator[tuple[bytes, bytes]]:
        self._buffer += data
        while len(self._buffer) >= _HEADER.size:
            kind, length = _HEADER.unpack_from(self._buffer)
            end = _HEADER.size + length
            if len(self._buffer) < end:
                return
            payload = bytes(self._buffer[_HEADER.size:end])
            del self._buffer[:end]
            yield kind, payload
