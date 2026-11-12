import os
import shutil
import tempfile
from pathlib import Path


def write_atomically(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, writing = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.",
                                           suffix=".writing")
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        if path.exists():
            shutil.copymode(path, writing)
        os.replace(writing, path)
    except BaseException:
        Path(writing).unlink(missing_ok=True)
        raise
