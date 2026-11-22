"""Exercise the HTTP, Caddy, SQLite, filesystem and Popen lifecycle together."""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path

import httpx

from gateway_fixture import CADDY, ROOT, free_port
from package_fixture import app_package


def package(version, bad_route=False):
    route = 'invalid_test_directive\n' if bad_route else 'respond /fixture-version "%s"\n' % version
    return app_package('fixture', version, {'port': 1234}, {'type': 'object', 'properties': {'port': {'type': 'integer'}}},
                       start='#!/bin/sh\nprintf "started-%s\\n"\nexec sleep 60\n' % version,
                       manifest={'caddyfile_config_path': 'route.caddy'}, files={'route.caddy': route})


def stop_process(proc):
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


@unittest.skipUnless(CADDY.is_file(), 'Supply a Caddy binary via AIVUDAOS_TEST_CADDY')
class AppLifecycleGatewayTests(unittest.TestCase):
    def test_failed_upgrades_preserve_routing_and_executable_app(self):
        with tempfile.TemporaryDirectory(prefix='aivuda-lifecycle-') as directory, ExitStack() as stack:
            root = Path(directory)
            workspace = root / 'workspace'
            binary = workspace / '.tools/caddy/caddy'
            binary.parent.mkdir(parents=True)
            binary.symlink_to(CADDY)
            port, backend = free_port(), free_port()
            while backend == port:
                backend = free_port()
            config = workspace / 'config/Caddyfile'
            config.parent.mkdir(parents=True)
            config.write_text((
                '{{\n admin unix/{admin}\n auto_https off\n}}\n'
                'http://127.0.0.1:{port} {{\n'
                ' # BEGIN AIVUDA APP IMPORTS\n # END AIVUDA APP IMPORTS\n'
                ' reverse_proxy /aivuda_os/* 127.0.0.1:{backend}\n}}\n'
            ).format(admin=root / 'admin.sock', port=port, backend=backend))
            env = dict(os.environ, AIVUDAOS_WS_ROOT=str(workspace), AIVUDAOS_EMBEDDED_MODE='1',
                       XDG_CONFIG_HOME=str(root / 'settings'), XDG_DATA_HOME=str(root / 'data'))
            log = stack.enter_context((root / 'services.log').open('w+'))
            for command in ([str(binary), 'run', '--config', str(config)],
                            [sys.executable, '-m', 'uvicorn', 'aivudaos.gateway.main:app',
                             '--host', '127.0.0.1', '--port', str(backend)]):
                proc = subprocess.Popen(command, cwd=str(ROOT), env=env, stdout=log, stderr=log)
                stack.callback(stop_process, proc)
            client = stack.enter_context(httpx.Client(base_url='http://127.0.0.1:%d' % port, trust_env=False))
            api = '/aivuda_os/api'
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    response = client.post(api + '/auth/login', json={'username': 'admin', 'password': 'admin123'})
                    if response.status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(0.05)
            else:
                self.fail((root / 'services.log').read_text())
            client.params = {'token': response.json()['access_token']}
            apps = api + '/apps/'

            def operation(path, success=True, **kwargs):
                queued = client.post(api + '/' + path, **kwargs)
                self.assertEqual(queued.status_code, 202, queued.text)
                url = apps + 'operations/' + queued.json()['operation_id']
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    record = client.get(url).json()
                    if record['done']:
                        self.assertEqual(record['status'], 'completed' if success else 'failed', record)
                        return record
                    time.sleep(0.05)
                self.fail('Operation did not complete: ' + path)

            def install(version, valid=True):
                return operation('apps/upload', success=valid, params={'overwrite': 'true'},
                                 files={'file': ('fixture.zip', package(version, not valid), 'application/zip')})

            v1, v2 = '1.0.0', '2.0.0'
            install(v1)
            imported = operation('config/import', json={
                'document': {'format_version': 1, 'payload': {'apps': [
                    {'app_id': 'fixture', 'version': v1, 'parameters': {'port': 4321}},
                ]}},
                'app_store_base_url': 'http://127.0.0.1/',
            })
            self.assertEqual(imported['result']['configured'], ['fixture'])
            # Fail at real Caddy reload, after the candidate has already been activated.
            for version in (v2, v1):
                failure = install(version, valid=False)
                self.assertIn('invalid_test_directive', failure['error'])
                versions = client.get(apps + 'fixture/versions').json()
                self.assertEqual((versions['active_version'], versions['versions']), (v1, [v1]))
                self.assertEqual(client.get('/fixture-version').text, v1)
                self.assertEqual(client.get(apps + 'fixture/config').json()['data'], {'port': 4321})
            operation('apps/fixture/start')
            status = apps + 'fixture/status'
            pid = client.get(status).json()['runtime']['pid']
            self.assertGreater(pid, 0)
            operation('apps/fixture/start')
            self.assertEqual(client.get(status).json()['runtime']['pid'], pid)
            logs = apps + 'fixture/logs'
            history = client.get(logs).json()
            self.assertIn('started-' + v1, history['chunk'])
            cursor = client.get(logs, params={'from_end': 'true'}).json()
            self.assertEqual((cursor['chunk'], cursor['offset'], cursor['next_offset']),
                             ('', history['size'], history['size']))
            self.assertTrue(cursor['eof'])
            fresh = 'new log line · after clear\n'
            with (workspace / 'data/logs/apps/fixture/current.log').open('ab') as stream:
                stream.write(fresh.encode('utf-8'))
            following = client.get(logs, params={'offset': cursor['next_offset']}).json()
            self.assertEqual(following['chunk'], fresh)
            self.assertEqual(following['next_offset'], cursor['next_offset'] + len(fresh.encode('utf-8')))
            operation('apps/fixture/restart')
            restarted = client.get(status).json()['runtime']
            self.assertTrue(restarted['running'])
            self.assertNotEqual(restarted['pid'], pid)
            operation('apps/fixture/stop')
            self.assertFalse(client.get(status).json()['runtime']['running'])
            install(v2)
            self.assertEqual(client.get('/fixture-version').text, v2)
            switch = client.post(apps + 'fixture/switch-version', json={'version': v1, 'restart': False})
            self.assertEqual(switch.status_code, 200, switch.text)
            self.assertEqual(client.get('/fixture-version').text, v1)
            operation('apps/fixture/uninstall', json={'purge': True})
            self.assertEqual(client.get(apps + 'installed').json()['items'], [])
            self.assertNotEqual(client.get('/fixture-version').text, v1)
