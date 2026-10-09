from typing import Protocol


class Server(Protocol):
    def keep_running(self) -> None: ...
