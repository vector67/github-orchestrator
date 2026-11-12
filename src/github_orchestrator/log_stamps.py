import logging
from datetime import datetime


class OffsetStampedFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        return datetime.fromtimestamp(record.created).astimezone().isoformat(timespec="milliseconds")
