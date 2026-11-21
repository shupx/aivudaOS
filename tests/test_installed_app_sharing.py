import io
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aivudaos.core.apps import sharing
from aivudaos.core.db.connection import db_conn
from aivudaos.core.db.schema import init_db


class InstalledAppSharingTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        apps = self.root / "apps"
        for target, value in (("aivudaos.core.db.connection.DB_PATH", self.root / "test.db"),
                              ("aivudaos.core.apps.sharing.APPS_DIR", apps)):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        init_db()
        self.version = apps / "demo" / "versions" / "1"
        self.version.mkdir(parents=True)
        with db_conn() as conn:
            conn.execute("INSERT INTO app_installation VALUES ('demo','1',?,'installed',1,NULL)",
                         (str(self.version),))

    def test_rotation_and_expiration(self):
        with patch("aivudaos.core.apps.sharing.time.time", return_value=500):
            first = sharing.issue_share()
            second = sharing.issue_share()
            self.assertFalse(sharing.share_is_valid(first))
            self.assertTrue(sharing.share_is_valid(second))
        with patch("aivudaos.core.apps.sharing.time.time", return_value=4100):
            self.assertFalse(sharing.share_is_valid(second))

    def test_legacy_install_without_original_archive(self):
        (self.version / "manifest.yaml").write_text("app_id: demo\n")
        filename = "中文" * 30 + ".sh"
        script = self.version / filename
        script.write_bytes(b"echo demo\n")
        script.chmod(0o755)
        (self.version / "entry").symlink_to(filename)
        (self.root / "outside").write_text("private")
        (self.version / "external").symlink_to(os.path.relpath(str(self.root / "outside"), str(self.version)))
        output = io.BytesIO()
        sharing.package_version("demo", "1", output)
        self.assertEqual(len(output.getvalue()), sharing.package_version("demo", "1"))
        output.seek(0)
        with tarfile.open(fileobj=output) as archive:
            self.assertEqual(set(archive.getnames()), {"manifest.yaml", filename, "entry"})
            self.assertEqual(archive.getmember(filename).mode, 0o755)
            self.assertEqual(archive.getmember("entry").linkname, filename)
        self.assertEqual(sharing.installed_releases()[0]["manifest"]["name"], "demo")
        with self.assertRaises(FileNotFoundError):
            sharing.package_version("demo", "../1")
