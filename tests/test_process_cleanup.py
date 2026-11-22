import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aivudaos.core.apps.runtime import RuntimeService
from aivudaos.core.errors import AppRuntimeError

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
