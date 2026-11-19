from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from typing import Iterator

from aivudaos.core.paths import DB_PATH


@contextmanager
def db_conn() -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(str(DB_PATH))) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        with conn:
            yield conn
