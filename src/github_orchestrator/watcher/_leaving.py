import threading


class Leaving:
    def __init__(self) -> None:
        self._asked = threading.Event()

    def ask(self) -> None:
        self._asked.set()

    def asked(self) -> bool:
        return self._asked.is_set()
