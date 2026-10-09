import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from aivudaos.core.apps.runtime import RuntimeService
from aivudaos.core import paths
from aivudaos.core.apps.systemd_runtime import SystemdRuntimeBackend
from aivudaos.core.config import service as config_module
from aivudaos.core.config.runtime_environment import validate_runtime_environment
from aivudaos.gateway.routes import config as config_routes
from aivudaos.gateway.schemas import ConfigUpdateRequest


class RuntimeEnvironmentTests(unittest.TestCase):
    def test_bootstrap_migrates_missing_setting_and_preserves_user_edits(self):
        import yaml

        for initial, expected in (({}, {'ROS_LOCALHOST_ONLY': '1'}),
                                  ({'runtime_environment': {}}, {}),
                                  ({'runtime_environment': {'ROS_LOCALHOST_ONLY': '0'}}, {'ROS_LOCALHOST_ONLY': '0'})):
            with self.subTest(initial=initial), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                root = Path(folder)
                for name in ('OS_CONFIG_PATH', 'SYS_CONFIG_PATH', 'USERS_CONFIG_PATH', 'MAGNET_CONFIG_PATH', 'CADDYFILE_PATH'):
                    stack.enter_context(patch.object(paths, name, root / (name + '.yaml')))
                stack.enter_context(patch.dict(os.environ, {'AIVUDAOS_EMBEDDED_MODE': '1'}))
                paths.OS_CONFIG_PATH.write_text(yaml.safe_dump(initial))
                paths._ensure_default_runtime_files()
                self.assertEqual(yaml.safe_load(paths.OS_CONFIG_PATH.read_text())['runtime_environment'], expected)

    def test_validation_preserves_strings_and_empty_values(self):
        values = {'ROS_LOCALHOST_ONLY': '1', 'EMPTY': '', 'TEXT': 'space $HOME "quoted" \\path %h'}
        self.assertEqual(validate_runtime_environment(values), values)
        for value in (None, [], {'BAD-NAME': '1'}, {'AIVUDA_APP_ID': 'x'}, {'ROS_LOCALHOST_ONLY': 1}, {'X': 'a\nInjected=1'}, {'X': '\x00'}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_runtime_environment(value)

    def test_config_default_and_explicit_deletion_persist(self):
        with tempfile.TemporaryDirectory() as root, patch.object(config_module, 'OS_CONFIG_PATH', Path(root) / 'os.yaml'):
            config = config_module.ConfigService(Mock(), Mock())
            first = config.update_os_config({}, 0, 'admin')
            self.assertEqual(first.data['runtime_environment'], {'ROS_LOCALHOST_ONLY': '1'})
            config.update_os_config({'runtime_environment': {}}, first.version, 'admin')
            self.assertEqual(config.get_os_setting('runtime_environment'), {})
            with self.assertRaises(ValueError):
                config.update_os_config({'runtime_environment': {'BAD': '\n'}}, 2, 'admin')
            self.assertEqual(config.get_os_config().version, 2)

    def make_runtime(self, root, environment, systemd):
        config = Mock()
        settings = {'runtime_environment': environment, 'runtime_process_manager': 'systemd' if systemd else 'popen', 'runtime_systemd_scope': 'user'}
        config.get_os_setting.side_effect = lambda key, default=None: settings.get(key, default)
        versioning = Mock()
        versioning.active_version.return_value = '1.0'
        versioning.active_install_path.return_value = root
        versioning.list_versions.return_value = ['1.0']
        runtime = RuntimeService(versioning, config, Mock())
        runtime._get_manifest = Mock(return_value=SimpleNamespace(name='Example'))
        runtime.get_runtime_state = Mock(return_value=SimpleNamespace(autostart=False, running=False))
        runtime._build_config_env = Mock(return_value={'AIVUDA_APP_ID': 'example'})
        runtime._build_exec_command = Mock(return_value=[sys.executable, '-c', 'import os,json; print(json.dumps(dict(os.environ)))'])
        runtime._decorate_command_for_realtime_logs = lambda command: command
        runtime._app_log_path = Mock(return_value=root / 'app.log')
        runtime._sync_runtime_row = Mock()
        runtime._ensure_guardian = Mock()
        runtime._watch_process_exit = Mock()
        runtime._systemd = Mock()
        runtime._systemd.is_available.return_value = True
        runtime._systemd.get_state.return_value = SimpleNamespace(running=True, pid=123, enabled=False)
        return runtime

    def test_popen_child_receives_values_overrides_and_removals(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            extra = {'ROS_LOCALHOST_ONLY': '1', 'EMPTY': '', 'TEXT': 'space $HOME "quotes" \\path %h'}
            runtime = self.make_runtime(root, extra, False)
            original_popen = subprocess.Popen
            children = []

            def spawn(*args, **kwargs):
                proc = original_popen(*args, **kwargs)
                children.append(proc)
                return proc

            with patch('aivudaos.core.apps.runtime.subprocess.Popen', side_effect=spawn), patch('aivudaos.core.apps.runtime.processes', return_value={}), patch.dict(os.environ, {'ROS_LOCALHOST_ONLY': '0'}):
                runtime.start('example')
                self.assertEqual(children[-1].wait(timeout=5), 0)
                actual = json.loads((root / 'app.log').read_text())
                for key, value in extra.items():
                    self.assertEqual(actual[key], value)
                self.assertEqual(actual['AIVUDA_APP_ID'], 'example')
                extra.clear()
                runtime.start('example')
                self.assertEqual(children[-1].wait(timeout=5), 0)
                actual = json.loads((root / 'app.log').read_text())
                self.assertEqual(actual['ROS_LOCALHOST_ONLY'], '0')  # inherited once override is removed
                self.assertNotIn('TEXT', actual)

    def test_systemd_start_restart_and_autostart_use_extra_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = self.make_runtime(Path(folder), {'ROS_LOCALHOST_ONLY': '1'}, True)
            for action in (lambda: runtime.start('example'), lambda: runtime.restart('example'), lambda: runtime.set_autostart('example', True)):
                with patch('aivudaos.core.apps.runtime.db_conn'):
                    action()
                self.assertEqual(runtime._systemd.write_unit.call_args.kwargs['environment']['ROS_LOCALHOST_ONLY'], '1')
                self.assertEqual(runtime._systemd.write_unit.call_args.kwargs['environment']['AIVUDA_APP_ID'], 'example')

    def test_unit_escaping_overrides_defaults_and_removes_old_variables(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            backend = SystemdRuntimeBackend(root, root)
            with patch.object(backend, 'unit_file_path', return_value=root / 'example.service'):
                backend.write_unit('example', 'user', ['/bin/true'], root, root / 'log', 'Example', {'ROS_LOCALHOST_ONLY': '1', 'TEXT': 'a\\b "q" %h $HOME', 'FORCE_COLOR': '0'})
                unit = (root / 'example.service').read_text()
                self.assertIn('Environment="ROS_LOCALHOST_ONLY=1"', unit)
                self.assertIn('Environment="TEXT=a\\\\b \\"q\\" %%h $HOME"', unit)
                self.assertIn('Environment="FORCE_COLOR=0"', unit)
                self.assertNotIn('EnvironmentFile=', unit)
                backend.write_unit('example', 'user', ['/bin/true'], root, root / 'log', 'Example', {})
                self.assertNotIn('ROS_LOCALHOST_ONLY', (root / 'example.service').read_text())

    def test_os_api_saves_and_refreshes_units_with_version_check(self):
        with tempfile.TemporaryDirectory() as root, patch.object(config_module, 'OS_CONFIG_PATH', Path(root) / 'os.yaml'):
            service = config_module.ConfigService(Mock(), Mock())
            service.update_os_config({}, 0, 'admin')
            runtime = Mock()
            runtime.refresh_runtime_environment.return_value = []
            with patch.object(config_routes, '_require_auth', return_value=SimpleNamespace(username='admin')), patch.object(config_routes, 'get_config_service', return_value=service), patch.object(config_routes, 'get_runtime_service', return_value=runtime):
                payload = ConfigUpdateRequest(data={'runtime_environment': {'ROS_LOCALHOST_ONLY': '0'}}, version=1)
                result = asyncio.run(config_routes.put_os_config(payload, 'token'))
                self.assertEqual(result['version'], 2)
                runtime.refresh_runtime_environment.assert_called_once_with()
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(config_routes.put_os_config(payload, 'token'))
                self.assertEqual(raised.exception.status_code, 409)
                runtime.refresh_runtime_environment.return_value = ['example: permission denied']
                result = asyncio.run(config_routes.put_os_config(ConfigUpdateRequest(data={'runtime_environment': {}}, version=2), 'token'))
                self.assertEqual(result['runtime_environment_refresh_errors'], ['example: permission denied'])

    def test_refresh_reconciles_units_without_restarting_apps(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = self.make_runtime(Path(folder), {'ROS_LOCALHOST_ONLY': '1'}, True)
            connection = Mock()
            connection.execute.return_value.fetchall.return_value = [{'app_id': 'example', 'autostart': 1}]
            with patch('aivudaos.core.apps.runtime.db_conn') as db:
                db.return_value.__enter__.return_value = connection
                self.assertEqual(runtime.refresh_runtime_environment(), [])
            self.assertEqual(runtime._systemd.write_unit.call_args.kwargs['environment']['ROS_LOCALHOST_ONLY'], '1')
            runtime._systemd.daemon_reload.assert_called_once_with('user')
            runtime._systemd.restart.assert_not_called()
