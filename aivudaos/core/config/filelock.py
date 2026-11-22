from __future__ import annotations

import os
import tempfile
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Dict, Iterator, Optional, Tuple

_locks: Dict[str, threading.RLock] = {}
_meta_lock = threading.Lock()
# Track only YAML files actually replaced by this operation (including magnet
# recipients and lazy migrations), never a snapshot of the whole config tree.
_Revision = Tuple[int, int, int, int]
_Journal = Dict[Path, Tuple[Optional[bytes], Optional[int], _Revision]]
_journal: ContextVar[Optional[_Journal]] = ContextVar("config_write_journal", default=None)


def get_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _meta_lock:
        if key not in _locks:
            _locks[key] = threading.RLock()
        return _locks[key]


def _revision(info: os.stat_result) -> _Revision:
    return info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size


@contextmanager
def rollback_config_writes_on_error() -> Iterator[None]:
    journal: _Journal = {}
    token = _journal.set(journal)
    try:
        yield
    except BaseException:
        for path, (before, mode, written) in reversed(list(journal.items())):
            with get_lock(path):
                try:
                    current = path.stat()
                except FileNotFoundError:
                    continue
                if _revision(current) != written:
                    continue  # A different writer owns the current revision.
                if before is None:
                    path.unlink()
                else:
                    _atomic_replace(path, before, mode)
        raise
    finally:
        _journal.reset(token)


def atomic_write_text(path: Path, content: str) -> None:
    """Atomically replace a file; journal its previous contents when requested."""
    journal = _journal.get()
    with get_lock(path):
        if journal is None:
            _atomic_replace(path, content.encode("utf-8"))
            return
        try:
            current = path.stat()
        except FileNotFoundError:
            current = None
        previous = journal.get(path)
        if previous and current and _revision(current) == previous[2]:
            before, mode, _ = previous
        else:
            before = path.read_bytes() if current else None
            mode = current.st_mode if current else None
        written = _atomic_replace(path, content.encode("utf-8"))
        journal[path] = (before, mode, written)


def _atomic_replace(path: Path, content: bytes, mode: Optional[int] = None) -> _Revision:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            if mode is not None:
                os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
            written = _revision(os.fstat(stream.fileno()))
        os.replace(tmp_path, str(path))
        return written
    except BaseException:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise
