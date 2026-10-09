import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aivudaos.core.config.apt_sources import AptSourcesError, AptSourcesService


class AptSourcesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.apt = self.root / 'apt'
        (self.apt / 'sources.list.d').mkdir(parents=True)
        self.legacy = self.apt / 'sources.list'
        self.modern = self.apt / 'sources.list.d' / 'ubuntu.sources'
        self.service = AptSourcesService(apt_dir=self.apt, backup_dir=self.root / 'backups')
        self.service._run_apt_update = Mock(return_value='updated')
        self.service._run_privileged = Mock(side_effect=self.run_privileged)
        self.root_patch = patch('aivudaos.core.config.apt_sources.os.geteuid', return_value=0)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.tmp.cleanup()

    def run_privileged(self, command, **kwargs):
        if command[0] == 'install':
            shutil.copyfile(command[-2], command[-1])
        elif command[0] == 'mkdir':
            Path(command[-1]).mkdir(parents=True, exist_ok=True)

    def check_roundtrip(self, path, before, after, expected_format):
        path.write_text(before)
        read = self.service.read_sources()
        self.assertEqual(read['path'], str(path))
        self.assertEqual(read['format'], expected_format)
        result = self.service.write_sources(after)
        self.assertEqual(path.read_text(), after)
        backups = self.service.list_backups()
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0]['created_at'])
        self.assertEqual(Path(backups[0]['path']).read_text(), before)
        self.service.restore_backup(result['backup']['backup_id'])
        self.assertEqual(path.read_text(), before)
        self.assertEqual(len(self.service.list_backups()), 2)
        self.assertEqual(self.service._run_apt_update.call_count, 2)

    def test_legacy_ubuntu_roundtrip_and_existing_backup_ids(self):
        self.check_roundtrip(self.legacy, 'deb http://archive.ubuntu.com/ubuntu jammy main\n', 'deb https://mirror.example/ubuntu jammy main\n', 'list')
        backup_id = self.service.list_backups()[0]['backup_id']
        self.assertFalse(backup_id.startswith('sources.list.'))
        self.assertTrue(self.service._resolve_backup_path(backup_id).exists())

    def test_ubuntu_24_deb822_roundtrip_preserves_other_sources(self):
        self.legacy.write_text('# Ubuntu sources moved to ubuntu.sources\n')
        third_party = self.apt / 'sources.list.d' / 'ros2.sources'
        third_party.write_text('third-party source')
        before = 'Types: deb\nURIs: http://archive.ubuntu.com/ubuntu\nSuites: noble noble-updates\nComponents: main universe\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
        self.check_roundtrip(self.modern, before, before.replace('http://archive.ubuntu.com', 'https://mirror.example'), 'deb822')
        self.assertEqual(self.legacy.read_text(), '# Ubuntu sources moved to ubuntu.sources\n')
        self.assertEqual(third_party.read_text(), 'third-party source')

    def test_backups_remain_associated_with_original_file_after_migration(self):
        self.legacy.write_text('deb http://archive.ubuntu.com/ubuntu jammy main\n')
        old = self.service.write_sources('deb https://mirror.example/ubuntu jammy main\n')['backup']['backup_id']
        self.modern.write_text('Types: deb\nURIs: http://archive.ubuntu.com/ubuntu\nSuites: noble\nComponents: main\n')
        self.assertEqual(self.service.list_backups(), [])
        with self.assertRaises(AptSourcesError) as raised:
            self.service.restore_backup(old)
        self.assertEqual(raised.exception.code, 'BACKUP_TARGET_MISMATCH')
        modern_id = self.service.write_sources(self.modern.read_text())['backup']['backup_id']
        self.modern.unlink()
        with self.assertRaises(AptSourcesError) as raised:
            self.service.restore_backup(modern_id)
        self.assertEqual(raised.exception.code, 'BACKUP_TARGET_MISMATCH')

    def test_explicit_path_overrides_detection(self):
        self.modern.write_text('Types: deb\n')
        service = AptSourcesService(sources_path=self.legacy, backup_dir=self.root / 'backups')
        self.assertEqual(service._sources_path, self.legacy)

    def test_invalid_backup_id_cannot_escape_backup_directory(self):
        for backup_id in ('../../etc/passwd', 'ubuntu.sources.../x', ''):
            with self.subTest(backup_id=backup_id), self.assertRaises(AptSourcesError):
                self.service.restore_backup(backup_id)
