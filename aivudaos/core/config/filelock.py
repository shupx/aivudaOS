from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

_locks: dict[str, threading.Lock] = {}
_meta_lock = threading.Lock()


def get_lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _meta_lock:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def atomic_write_text(path: Path, content: str) -> None:
    """Write content to a temporary file then atomically rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        os.write(fd, content.encode("utf-8"))
        os.fsync(fd)
        os.close(fd)
        os.rename(tmp_path, str(path))
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
