import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aivudaos.core.apps.runtime import RuntimeService
from aivudaos.core.errors import AppRuntimeError
from aivudaos.core.db.connection import db_conn
from aivudaos.core.db.schema import init_db

from aivudaos.core.apps import process_cleanup
from aivudaos.core.apps.process_cleanup import processes, remember, terminate

HELPER = Path(__file__).resolve().parents[1] / 'aivudaos/core/apps/process_cleanup.py'


class CleanupTests(unittest.TestCase):
    def launch_tree(self, stubborn=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        output = Path(temp.name) / 'pid'
        child = "import signal,time; " + ("signal.signal(signal.SIGTERM,signal.SIG_IGN); " if stubborn else "") + "time.sleep(60)"
        code = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c',%r],start_new_session=True); open(%r,'w').write(str(p.pid)); time.sleep(60)" % (child, str(output))
        proc = subprocess.Popen([sys.executable, '-c', code], start_new_session=True)
        def reap():
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=3)
        self.addCleanup(reap)
        end = time.monotonic() + 5
        while not output.exists() and time.monotonic() < end:
            time.sleep(0.02)
        pid = int(output.read_text())
        self.addCleanup(lambda: self.kill_if_alive(pid))
        time.sleep(0.1)
        return proc, pid

    @staticmethod
    def kill_if_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def test_stop_includes_child_with_new_session(self):
        proc, child = self.launch_tree()
        stamp = processes()[proc.pid][2]
        terminate({proc.pid: stamp}, proc.pid, stamp, timeout=0.3)
        proc.wait(timeout=2)
        self.assertNotIn(child, processes())

    def test_stubborn_child_escalates(self):
        proc, child = self.launch_tree(stubborn=True)
        stamp = processes()[proc.pid][2]
        terminate({proc.pid: stamp}, proc.pid, stamp, timeout=0.3)
        proc.wait(timeout=2)
        self.assertNotIn(child, processes())

    def test_recycled_identity_does_not_signal(self):
        proc, child = self.launch_tree()
        terminate({proc.pid: 'wrong'}, proc.pid, 'wrong', timeout=0.1)
        self.assertIsNone(proc.poll())
        self.assertIn(child, processes())

    def test_remembered_children_survive_reparenting_until_cleanup(self):
        proc, child = self.launch_tree()
        stamp = processes()[proc.pid][2]
        tree = {proc.pid: stamp}
        remember(tree, proc.pid, stamp)
        proc.kill()
        proc.wait()
        terminate(tree, proc.pid, stamp, timeout=0.3)
        self.assertNotIn(child, processes())

    def test_guardian_eof_cleans_detached_app(self):
        proc, child = self.launch_tree(stubborn=True)
        guardian = subprocess.Popen([sys.executable, str(HELPER)], stdin=subprocess.PIPE)
        stamp = processes()[proc.pid][2]
        guardian.stdin.write((json.dumps({'action': 'add', 'pid': proc.pid, 'stamp': stamp}) + '\n').encode())
        guardian.stdin.flush()
        time.sleep(0.3)
        guardian.stdin.close()  # Same EOF that parent SIGKILL produces.
        guardian.wait(timeout=10)
        proc.wait(timeout=2)
        self.assertEqual(guardian.returncode, 0)
        self.assertNotIn(child, processes())

    def test_guardian_reads_one_process_table_for_two_roots(self):
        additions = b''.join((json.dumps({'action': 'add', 'pid': pid, 'stamp': str(pid)}) + '\n').encode()
                             for pid in (100, 200))
        table = {100: (1, 100, '100'), 101: (100, 101, '101'),
                 200: (1, 200, '200'), 201: (200, 201, '201')}
        with patch.object(process_cleanup.sys, 'stdin'), \
             patch.object(process_cleanup.select, 'select', return_value=([True], [], [])), \
             patch.object(process_cleanup.os, 'read', side_effect=[additions, b'']), \
             patch.object(process_cleanup, 'processes', return_value=table) as scan, \
             patch.object(process_cleanup, 'terminate') as cleanup:
            process_cleanup.guardian()
        scan.assert_called_once_with()
        cleanup.assert_any_call({100: '100', 101: '101'}, 100, '100')
        cleanup.assert_any_call({200: '200', 201: '201'}, 200, '200')

    def runtime_for(self, proc):
        runtime = RuntimeService(Mock(), Mock(), Mock())
        runtime._versioning.list_versions.return_value = ['1.0.0']
        runtime._should_use_systemd = Mock(return_value=False)
        runtime.get_runtime_state = Mock(return_value=SimpleNamespace(pid=proc.pid, autostart=True))
        runtime._sync_runtime_row = Mock()
        stamp = processes()[proc.pid][2]
        runtime._owned_processes['fixture'] = (proc, stamp, {proc.pid: stamp})
        return runtime

    def test_runtime_stop_updates_state_only_after_descendants_exit(self):
        proc, child = self.launch_tree()
        runtime = self.runtime_for(proc)
        def verify(*args, **kwargs):
            self.assertIsNotNone(proc.poll())
            self.assertNotIn(child, processes())
            self.assertFalse(kwargs['running'])
            self.assertTrue(kwargs['autostart'])
        runtime._sync_runtime_row.side_effect = verify
        runtime.stop('fixture')
        runtime._sync_runtime_row.assert_called_once()

    def test_failed_cleanup_does_not_record_stopped(self):
        proc, child = self.launch_tree()
        runtime = self.runtime_for(proc)
        with patch('aivudaos.core.apps.runtime.terminate', side_effect=RuntimeError('failed')):
            with self.assertRaises(AppRuntimeError):
                runtime.stop('fixture')
        runtime._sync_runtime_row.assert_not_called()

    def test_shutdown_limits_scope_to_owned_popen_apps(self):
        runtime = RuntimeService(Mock(), Mock(), Mock())
        runtime.stop = Mock()
        runtime.shutdown()
        runtime.stop.assert_not_called()
        self.assertTrue(runtime._closing)


class PersistedProcessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        db = patch('aivudaos.core.db.connection.DB_PATH', self.root / 'test.db')
        db.start()
        self.addCleanup(db.stop)

    def runtime(self):
        runtime = RuntimeService(Mock(), Mock(), Mock())
        runtime._versioning.active_install_path.return_value = self.root
        runtime._versioning.active_version.return_value = '1.0'
        runtime._versioning.list_versions.return_value = ['1.0']
        runtime._should_use_systemd = Mock(return_value=False)
        runtime._get_manifest = Mock()
        runtime._build_exec_command = Mock(return_value=[sys.executable, '-c', 'import time; time.sleep(60)'])
        runtime._decorate_command_for_realtime_logs = lambda command: command
        runtime._build_runtime_env = Mock(return_value={})
        runtime._build_config_env = Mock(return_value={})
        runtime._app_log_path = Mock(return_value=self.root / 'current.log')
        runtime._ensure_guardian = Mock()
        runtime._watch_process_exit = Mock()
        return runtime

    def test_parallel_starts_and_recovered_start_share_one_launch(self):
        init_db()
        runtime = self.runtime()
        self.addCleanup(runtime.shutdown)
        gate = Barrier(4)
        def start(_):
            gate.wait(timeout=5)
            return runtime.start('app')['running']

        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertTrue(all(pool.map(start, range(4))))
        runtime._build_exec_command.assert_called_once()
        self.assertEqual(runtime._should_use_systemd.call_count, 4)
        proc = runtime._owned_processes['app'][0]
        log = self.root / 'current.log'
        log.write_text('original output')

        recovered = self.runtime()  # No Popen handle or in-memory ownership.
        state = recovered.get_runtime_state('app')
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        self.assertEqual((state.pid, state.process_identity),
                         (proc.pid, boot + ':' + processes()[proc.pid][2]))
        self.assertTrue(recovered.start('app')['running'])
        recovered._build_exec_command.assert_not_called()
        self.assertEqual(log.read_text(), 'original output')
        recovered._mark_stopped_if_pid_matches('app', proc.pid, boot + ':999999999', 1)
        self.assertTrue(recovered.get_runtime_state('app').running)
        recovered.stop('app')
        self.assertIsNotNone(proc.wait(timeout=3))
        self.assertFalse(recovered.get_runtime_state('app').running)
        self.assertIsNone(recovered.get_runtime_state('app').process_identity)

    def test_migration_does_not_adopt_a_live_pid_or_recycled_identity(self):
        with db_conn() as conn:
            conn.execute('CREATE TABLE app_runtime (app_id TEXT PRIMARY KEY, running INTEGER, '
                         'autostart INTEGER, pid INTEGER, last_started_at INTEGER, last_stopped_at INTEGER)')
            conn.execute('INSERT INTO app_runtime VALUES (?,1,1,?,5,NULL)', ('legacy', os.getpid()))
        init_db()
        init_db()  # Safe on an already migrated database.
        runtime = self.runtime()
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        stamp = processes()[os.getpid()][2]
        for app_id, identity in [('legacy', None), ('reused', boot + ':0'), ('reboot', 'other-boot:' + stamp)]:
            with self.subTest(app_id=app_id):
                if identity is not None:
                    runtime._sync_runtime_row(app_id, running=True, pid=os.getpid(), autostart=True,
                                              process_identity=identity, last_started_at=5)
                with patch('aivudaos.core.apps.runtime.terminate') as cleanup:
                    runtime.stop(app_id)
                    cleanup.assert_not_called()
                state = runtime.get_runtime_state(app_id)
                self.assertFalse(state.running)
                self.assertIsNone(state.pid)
                self.assertIsNone(state.process_identity)
                self.assertEqual(state.last_started_at, 5)
                self.assertTrue(state.autostart)

    def test_temporary_systemd_query_failure_preserves_cached_unit_state(self):
        init_db()
        runtime = self.runtime()
        runtime._should_use_systemd.return_value = True
        runtime._systemd.get_state = Mock(side_effect=subprocess.CalledProcessError(1, 'systemctl'))
        runtime._sync_runtime_row('unit', running=True, pid=1234, autostart=True, last_started_at=5)
        with patch('aivudaos.core.apps.runtime._process_identity') as check:
            state = runtime.get_runtime_state('unit')
            check.assert_not_called()
        self.assertTrue(state.running)
        self.assertEqual(state.pid, 1234)
        with db_conn() as conn:
            row = conn.execute('SELECT running, pid, last_stopped_at FROM app_runtime WHERE app_id=?', ('unit',)).fetchone()
        self.assertEqual(tuple(row), (1, 1234, None))

    def test_stop_checks_identity_again_if_pid_changes_after_state_query(self):
        init_db()
        runtime = self.runtime()
        runtime._sync_runtime_row('app', running=True, pid=99, process_identity='boot:10', autostart=False)
        with patch('aivudaos.core.apps.runtime._process_identity', side_effect=['boot:10', 'boot:11']), \
             patch('aivudaos.core.apps.runtime.terminate') as cleanup:
            runtime.stop('app')
            cleanup.assert_not_called()
