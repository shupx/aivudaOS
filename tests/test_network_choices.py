import asyncio
import threading
import unittest
from contextlib import ExitStack
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

from aivudaos.core.apps import device_network
from aivudaos.core.apps.config_validation import validate_config_data
from aivudaos.core.apps.network_choices import app_config_schema
from aivudaos.core.apps.runtime import RuntimeService
from aivudaos.core.config.app_migration import migrate_app_parameters
from aivudaos.core.errors import AppRuntimeError, InvalidConfigError
from aivudaos.gateway.routes import apps
from aivudaos.gateway.schemas import AppConfigUpdateRequest


class NetworkChoicesTest(unittest.TestCase):
    fields = {'interface': 'nic', 'address': 'src', 'destination': 'dst'}
    group = {'x-device-ipv4': fields, 'properties': {
        'nic': {'type': 'string', 'enum': ['auto'], 'x-device-choice': 'interface'},
        'src': {'type': 'string', 'enum': ['auto'], 'x-device-choice': 'address'},
        'dst': {'type': 'string'}}}
    schema = {'properties': {'net': group, 'mode': {'enum': ['safe', 'fast']}}}
    data = {'net': {'nic': 'eth0', 'src': '10.0.0.2', 'dst': '192.168.1.150'}, 'mode': 'safe'}
    cards = {'eth0': {'up': True, 'addresses': ['10.0.0.2']},
             'eth1': {'up': True, 'addresses': ['192.168.1.5']}}

    def test_live_choices_and_manual_source(self):
        with patch.object(device_network, 'interfaces', return_value=self.cards), \
             patch.object(device_network, 'direct_route', return_value=('eth1', '192.168.1.5')):
            group = app_config_schema(self.schema, self.data)['properties']['net']['properties']
            self.assertIn('192.168.1.5', group['nic']['enumLabels'][0])
            self.assertEqual(group['src']['enumLabels'][0], 'auto · 10.0.0.2')
        with patch.object(device_network, 'interfaces', return_value=self.cards) as read:
            validate_config_data(self.data, self.schema)
            read.assert_called_once_with()

    def test_point_to_point_interface_with_direct_route_is_selectable(self):
        source = '192.168.1.5'
        rows = [
            {'ifname': name, 'link_type': 'none', 'flags': flags,
             'addr_info': [{'local': source, 'family': 'inet', 'scope': 'global'}]}
            for name, flags in [('wg0', ['POINTOPOINT', 'UP', 'LOWER_UP']), ('lo', ['LOOPBACK', 'UP'])]
        ]
        route = [{'dev': 'wg0', 'prefsrc': source}]
        config = {'net': {'nic': 'auto', 'src': 'auto', 'dst': self.data['net']['dst']}}
        with patch.object(device_network, 'ip_json', side_effect=[rows, route]) as probe:
            group = app_config_schema(self.schema, config)['properties']['net']['properties']
        self.assertEqual(group['nic']['enum'], ['auto', 'wg0'])
        self.assertEqual(group['nic']['enumLabels'][0], 'auto · wg0 · ' + source)
        self.assertEqual(group['src']['enum'], ['auto', source])
        self.assertEqual(probe.call_count, 2)

    def test_discovery_failure_keeps_offline_choices_and_reset_metadata(self):
        with patch.object(device_network, 'interfaces', side_effect=FileNotFoundError):
            group = app_config_schema(self.schema, self.data)['properties']['net']['properties']
        self.assertIn('eth0', group['nic']['enum'])
        self.assertIn('10.0.0.2', group['src']['enum'])
        for key in ('nic', 'dst'):
            self.assertEqual(group[key]['resetAutoSibling'], 'src')

    def test_unrelated_schema_never_reads_the_network(self):
        with patch.object(device_network, 'interfaces') as read:
            self.assertEqual(app_config_schema({'type': 'string'}, {}), {'type': 'string'})
            read.assert_not_called()

    def test_invalid_network_selection_does_not_probe_the_device(self):
        with patch.object(device_network, 'interfaces') as read:
            group = app_config_schema(self.schema, {'net': {'nic': None}})['properties']['net']['properties']
            self.assertEqual(group['nic']['enum'], ['auto'])
            self.assertEqual(group['dst']['resetAutoSibling'], 'src')
            read.assert_not_called()

    def test_offline_exemption_only_applies_to_the_same_annotated_leaf(self):
        stored = [self.data, {'net': {'nic': 'eth1', 'src': 'auto'}}]
        schema = {'items': self.schema}
        with patch.object(device_network, 'interfaces', return_value={}) as read:
            validate_config_data(stored, schema, previous_data=deepcopy(stored))
            read.assert_not_called()
            with self.assertRaisesRegex(InvalidConfigError, 'must be one of'):
                validate_config_data(stored[::-1], schema, previous_data=stored)
            bad = {'mode': 'not-allowed'}
            with self.assertRaisesRegex(InvalidConfigError, 'mode must be one of'):
                validate_config_data(bad, self.schema, previous_data=bad)

    def test_runtime_and_migration_preserve_saved_offline_values_only(self):
        config = Mock()
        config.get_app_config.return_value = SimpleNamespace(version=1, data=self.data)
        manifest = SimpleNamespace(config_schema=self.schema, default_config=self.data)
        runtime = RuntimeService(Mock(), config, Mock())
        with patch.object(device_network, 'interfaces', return_value={}) as read:
            runtime._ensure_version_config_ready('demo', '1', manifest)
            data, warnings, valid = migrate_app_parameters(self.data, self.data, {}, self.schema)
            self.assertEqual((data, warnings, valid), (self.data, [], True))
            read.assert_not_called()
            config.get_app_config.return_value = SimpleNamespace(version=0, data={})
            with self.assertRaises(AppRuntimeError):
                runtime._ensure_version_config_ready('demo', '1', manifest)
            config.init_app_config.assert_not_called()

    def test_config_endpoints_read_network_once_per_request_off_loop(self):
        loop_thread = threading.get_ident()

        def in_worker(result):
            def collect(*args):
                self.assertNotEqual(threading.get_ident(), loop_thread)
                return result
            return collect

        schema = {'properties': {'net': self.group, 'net2': self.group}}
        cfg = SimpleNamespace(data={'net': self.data['net'], 'net2': self.data['net']}, version=1, updated_at=None)
        with ExitStack() as stack:
            mock = lambda name, **kw: stack.enter_context(patch.object(apps, name, **kw))
            mock('_require_auth')
            mock('_get_manifest_from_db', return_value={'config_schema': schema})
            mock('_get_constraints_for_app', return_value=[])
            config = mock('get_config_service').return_value
            config.get_app_config.return_value = cfg
            config.get_app_default_config.return_value = {}
            mock('get_runtime_service').return_value.get_installed_list.return_value = [
                {'app_id': app_id, 'active_version': '1'} for app_id in ('one', 'two')]
            magnet = mock('get_magnet_service').return_value
            magnet.readonly_paths_for_app.return_value = []
            magnet.list_groups.return_value = {'items': [{'bindings': [
                {'kind': 'app', 'path': ' net.src ', 'app_id': 'one', 'app_version': '1'},
            ]}]}
            read = stack.enter_context(patch.object(device_network, 'interfaces', side_effect=in_worker(self.cards)))
            route = stack.enter_context(patch.object(device_network, 'direct_route', side_effect=in_worker(('eth0', '10.0.0.2'))))
            result = asyncio.run(apps.get_active_configs('token'))
            self.assertEqual([item['readonly_paths'] for item in result['items']], [['net.src'], []])
            magnet.list_groups.assert_called_once_with()
            magnet.readonly_paths_for_app.assert_not_called()
            read.assert_called_once_with()
            route.assert_called_once_with('192.168.1.150', self.cards)
            asyncio.run(apps.get_app_config('one', 'token', '1'))
            self.assertEqual((read.call_count, route.call_count), (2, 2))

    def test_put_keeps_saved_selections_but_rejects_new_offline_values(self):
        loop_thread = threading.get_ident()

        def offline():
            self.assertNotEqual(threading.get_ident(), loop_thread)
            return {}

        config, magnet, versioning = Mock(), Mock(), Mock()
        config.get_app_config.return_value = SimpleNamespace(data=self.data, version=1)
        versioning.list_versions.return_value = ['1']
        magnet.blocked_paths_for_app_update.return_value = []
        with patch.object(apps, '_require_auth'), patch.object(apps, '_validate_equal_constraints', return_value=[]), \
             patch.object(apps, 'get_config_service', return_value=config), patch.object(apps, 'get_magnet_service', return_value=magnet), \
             patch.object(apps, 'get_versioning_service', return_value=versioning), \
             patch.object(apps, '_get_manifest_from_db', return_value={'config_schema': self.schema}), \
             patch.object(device_network, 'interfaces', side_effect=offline) as read:
            def put(data):
                return asyncio.run(apps.put_app_config('one', AppConfigUpdateRequest(data=data, app_version='1', version=1), 'token'))

            self.assertTrue(put(dict(self.data, mode='fast'))['ok'])
            read.assert_not_called()
            for key, value in [('nic', 'eth99'), ('src', '192.168.2.99')]:
                data = deepcopy(self.data)
                data['net'][key] = value
                with self.assertRaises(HTTPException) as rejected:
                    put(data)
                self.assertEqual(rejected.exception.status_code, 400)
                self.assertIn(key, rejected.exception.detail)
            config.update_app_config.assert_called_once()
