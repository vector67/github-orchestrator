from github_orchestrator.watcher._config import WatcherConfig


class TourFile:
    def __init__(self, config: WatcherConfig) -> None:
        self._path = config.tour_due

    def due(self) -> bool:
        return self._path.exists()

    def arm(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.touch()

    def seen(self) -> None:
        self._path.unlink(missing_ok=True)
