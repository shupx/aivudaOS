import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aivudaos.core.db.connection import db_conn


class DatabaseConnectionTest(unittest.TestCase):
    def test_scope_closes_handles_and_preserves_transactions(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("aivudaos.core.db.connection.DB_PATH", Path(tmp) / "test.db"):
                with db_conn() as first:
                    first.execute("CREATE TABLE checks (value INTEGER)")
                    first.execute("INSERT INTO checks VALUES (1)")
                with self.assertRaises(sqlite3.ProgrammingError):
                    first.execute("SELECT 1")

                with self.assertRaises(ValueError):
                    with db_conn() as second:
                        second.execute("INSERT INTO checks VALUES (2)")
                        raise ValueError("abort")
                with self.assertRaises(sqlite3.ProgrammingError):
                    second.execute("SELECT 1")
                with db_conn() as third:
                    self.assertEqual([row[0] for row in third.execute("SELECT value FROM checks")], [1])
