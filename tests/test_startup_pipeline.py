"""Startup pipeline planning, operation semantics and authenticated HTTP contract."""
import asyncio
import copy
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aivudaos.core.apps.operations import AppOperationManager
from aivudaos.core.apps.pipeline import (
    PipelineConflict, PipelineOrchestrator, PipelineStore, build_execution_plan,
    build_stop_plan, ros2_template, validate_config,
)
from aivudaos.core.apps.runtime import RuntimeService
from aivudaos.core.errors import AppOperationConflictError, AppRuntimeError, AuthenticationError
from aivudaos.gateway.routes import apps, pipeline
from aivudaos.mcp_server import EmbeddedAPIClient, MCPServer
from startup_pipeline_probe_cases import TestReadinessProbes  # collected in this suite


def node(app_id, *deps, **fields):
    return dict(app_id=app_id, depends_on=list(deps), **fields)


def group(group_id, *nodes, **fields):
    return dict(id=group_id, items=list(nodes), **fields)


def config(*groups, **fields):
    return dict(version=0, takeover_autostart=False, default_profile='robot',
                profiles=[dict(name='robot', groups=list(groups), **fields)])


class Runtime:
    def __init__(self):
        self.running = set()
        self.calls = []
        self.broken = set()
        self.configure_pipeline_autostart = Mock()

    def list_installed_app_ids(self):
        return ['a', 'b', 'c', 'd', 'e']

    def get_installed_list(self):
        return [dict(app_id=n, running=n in self.running) for n in self.list_installed_app_ids()]

    def start(self, app_id):
        self.calls.append(('run', app_id))
        if app_id in self.broken:
            raise AppRuntimeError('Start failed')
        self.running.add(app_id)

    def stop(self, app_id):
        self.calls.append(('stop', app_id))
        self.running.discard(app_id)

    def get_runtime_state(self, app_id):
        return SimpleNamespace(running=app_id in self.running)


@pytest.fixture
def service(tmp_path):
    return PipelineOrchestrator(PipelineStore(tmp_path / 'config/startup_pipeline.yaml'),
                                Runtime(), AppOperationManager())


def finish(service, operation):
    op = operation['operation_id']
    events = []
    until = time.monotonic() + 8
    while time.monotonic() < until:
        chunk, done = service.operations.wait_events(op, events[-1]['seq'] if events else 0, .1)
        events.extend(chunk)
        if done:
            return events
    pytest.fail('Timed out waiting for operation ' + op)


def test_plans_follow_barriers_and_newly_ready_items():
    early = group('one', node('c', 'a', order=0), node('a', order=1), node('b', order=2), order=1)
    late = group('two', node('d', 'c'), node('e', enabled=False), order=2)
    profile = config(late, early)['profiles'][0]
    assert build_execution_plan(profile) == [dict(group_id='one', batches=[['a', 'b'], ['c']]),
                                             dict(group_id='two', batches=[['d']])]
    assert build_stop_plan(profile) == [dict(group_id='two', batches=[['d']]),
                                        dict(group_id='one', batches=[['c'], ['b', 'a']])]
    early['mode'] = 'sequential'
    assert build_execution_plan(profile)[0]['batches'] == [['a'], ['c'], ['b']]
    assert [g['id'] for g in ros2_template()] == ['middleware', 'hardware', 'perception', 'planning', 'telemetry']


@pytest.mark.parametrize('groups,reason', [
    ([group('x', node('a', 'b'), node('b', 'a'))], 'cycle'),
    ([group('x', node('a', 'b')), group('y', node('b'))], 'later group'),
    ([group('x', node('a')), group('y', node('a'))], 'Duplicate app_id'),
    ([group('x', node('a', 'b'))], 'unknown prerequisite'),
    ([group('x', node('a', 'b'), node('b', enabled=False))], 'disabled prerequisite'),
    ([group('x', node('a', readiness={'type': 'tcp', 'host': '192.0.2.1', 'port': 80}))], 'loopback'),
])
def test_invalid_plans(groups, reason):
    result = validate_config(config(*groups))
    assert not result['valid'] and result['preview'] == {}
    assert reason in ' '.join(result['errors'])


def test_layout_round_trip_is_optional_and_does_not_change_plans(tmp_path):
    store = PipelineStore(tmp_path / 'pipeline.yaml')
    legacy = store.save(config(group('one', node('a'), node('b', 'a'))))
    before = legacy['profiles'][0]
    assert 'layout' not in before
    edited = copy.deepcopy(legacy)
    layout = {'group:one': {'x': -15, 'y': 3.5, 'w': 320, 'h': 180},
              'app:a': {'x': 0, 'y': 20}}
    edited['profiles'][0]['layout'] = layout
    store.save(edited)
    after = store.load()['profiles'][0]
    assert after['layout'] == layout
    assert build_execution_plan(after) == build_execution_plan(before)
    assert build_stop_plan(after) == build_stop_plan(before)


@pytest.mark.parametrize('layout', [None, [], {1: {'x': 0, 'y': 0}}, {'a': []},
    {'a': {'x': 0}}, {'a': {'y': 0}}, {'a': {'x': True, 'y': 0}},
    {'a': {'x': '3', 'y': 0}}, {'a': {'x': float('nan'), 'y': 0}},
    {'a': {'x': 0, 'y': float('inf')}}, {'a': {'x': 0, 'y': 0, 'w': 0}},
    {'a': {'x': 0, 'y': 0, 'h': -1}}, {'a': {'x': 0, 'y': 0, 'z': 1}},
])
def test_invalid_layout_cannot_replace_saved_config(tmp_path, layout):
    store = PipelineStore(tmp_path / 'pipeline.yaml')
    with pytest.raises(ValueError, match='layout'):
        store.save(config(group('one'), layout=layout))
    assert not store.path.exists()


def test_invalid_saved_dag_remains_editable_but_never_runs(service):
    import yaml

    raw = config(group('x', node('a', 'b'), node('b', 'a')))
    service.store.path.parent.mkdir()
    service.store.path.write_text(yaml.safe_dump(raw), encoding='utf-8')
    response = service.describe()
    assert not response['validation']['valid']
    assert service.startup() is None  # Unused drafts cannot take over legacy boot.
    with pytest.raises(ValueError, match='cycle'):
        service.queue('run')
    response['config']['profiles'][0]['groups'][0]['items'][0]['depends_on'] = []
    assert service.save(response['config'])['validation']['valid']


def test_concurrent_saves_use_one_version(tmp_path):
    path = tmp_path / 'startup_pipeline.yaml'
    draft = PipelineStore(path).load()
    assert draft['version'] == 0 and not draft['takeover_autostart']
    barrier = threading.Barrier(2)

    def race(name):
        value = config(group(name))
        barrier.wait(3)
        try:
            return PipelineStore(path).save(value)['version']
        except PipelineConflict:
            return 'conflict'

    with ThreadPoolExecutor(2) as pool:
        assert set(pool.map(race, ['left', 'right'])) == {1, 'conflict'}
    assert PipelineStore(path).load()['version'] == 1


def test_parallel_readiness_barrier_and_reverse_stop(service):
    service.save(config(group('early', node('a'), node('b')), group('late', node('c', 'b', 'a'))))
    barrier = threading.Barrier(2)
    ready = set()

    def wait(app_id, spec, cancel):
        if app_id != 'c':
            barrier.wait(3)  # Deadlocks/fails if start+probe was accidentally serialized.
        else:
            assert ready == {'a', 'b'}
        ready.add(app_id)

    service.prober.wait = wait
    events = finish(service, service.queue('run'))
    assert events[-1]['status'] == 'completed' and ready == {'a', 'b', 'c'}
    assert {'pipeline_stage', 'pipeline_node', 'log'} <= {e['type'] for e in events}
    assert finish(service, service.queue('stop'))[-1]['status'] == 'completed'
    stopped = [n for action, n in service.runtime.calls if action == 'stop']
    assert stopped[0] == 'c' and set(stopped[1:]) == {'a', 'b'}


def test_sequential_and_external_prerequisites(service):
    service.save(config(group('first', node('a')), group('second', node('c', 'b'), node('b', 'a'), mode='sequential')))
    assert finish(service, service.queue('run', group_id='second'))[-1]['status'] == 'failed'
    assert service.runtime.calls == []
    service.runtime.running.add('a')
    assert finish(service, service.queue('run', group_id='second'))[-1]['status'] == 'completed'
    assert service.runtime.calls == [('run', 'b'), ('run', 'c')]
    finish(service, service.queue('stop'))
    assert service.runtime.calls[-3:] == [('stop', 'c'), ('stop', 'b'), ('stop', 'a')]


@pytest.mark.parametrize('policy,expected', [
    ('abort', ['failed', 'skipped', 'skipped', 'skipped']),
    ('skip_dependents', ['failed', 'skipped', 'skipped', 'active']),
    ('continue', ['failed', 'degraded', 'degraded', 'active']),
])
def test_failure_policies(service, policy, expected):
    service.save(config(group('one', node('a')), group('two', node('b', 'a'), node('c', 'b'), node('d')),
                        on_failure=policy))
    service.runtime.broken.add('a')
    events = finish(service, service.queue('run'))
    outcomes = {e['app_id']: e['status'] for e in events if e['type'] == 'pipeline_node'}
    assert [outcomes[n] for n in 'abcd'] == expected
    assert events[-1]['status'] == 'failed'


def test_takeover_is_opt_in_and_stale_save_has_no_side_effect(service):
    assert service.startup() is None
    service.runtime.configure_pipeline_autostart.assert_not_called()
    draft = config(group('x', node('a')))
    draft['takeover_autostart'] = True
    saved = service.save(draft)['config']
    service.runtime.configure_pipeline_autostart.assert_called_once_with(True)
    assert finish(service, service.startup())[-1]['status'] == 'completed'
    with pytest.raises(PipelineConflict):
        service.save(config())
    assert service.runtime.configure_pipeline_autostart.call_count == 2
    saved['takeover_autostart'] = False
    service.save(saved)
    service.runtime.configure_pipeline_autostart.assert_called_with(False)
    assert service.startup() is None


def test_systemd_takeover_disables_without_stopping_or_erasing_preferences(tmp_path, monkeypatch):
    runtime = RuntimeService(Mock(), Mock(), Mock())
    monkeypatch.setattr(runtime, '_should_use_systemd', lambda scope: True)
    monkeypatch.setattr(runtime, '_systemd_scope', lambda: 'user')
    monkeypatch.setattr(runtime, 'list_installed_app_ids', lambda: ['a', 'b'])
    runtime._systemd = Mock()
    (tmp_path / 'a').touch()
    runtime._systemd.unit_file_path.side_effect = lambda n, scope: tmp_path / n
    runtime.configure_pipeline_autostart(True)
    runtime._systemd.set_enabled.assert_called_once_with('a', 'user', False, defer_reload=True)
    runtime._systemd.stop.assert_not_called()
    reconcile = Mock(return_value=[])
    monkeypatch.setattr(runtime, '_reconcile_systemd_units', reconcile)
    runtime.configure_pipeline_autostart(False)
    reconcile.assert_called_once_with('user')


def test_takeover_save_failure_does_not_commit_config(service):
    service.runtime.configure_pipeline_autostart.side_effect = [AppRuntimeError('permission denied'), None]
    draft = config()
    draft['takeover_autostart'] = True
    with pytest.raises(AppRuntimeError):
        service.save(draft)
    assert not service.store.load()['takeover_autostart']
    service.runtime.configure_pipeline_autostart.assert_called_with(False)


def test_api_auth_preview_save_run_cancel_and_reverse_stop(service, monkeypatch):
    app = FastAPI()
    app.include_router(pipeline.router, prefix='/aivuda_os')
    app.include_router(apps.router, prefix='/aivuda_os')
    monkeypatch.setattr(pipeline, 'get_pipeline_service', lambda: service)
    monkeypatch.setattr(apps, 'get_app_operation_manager', lambda: service.operations)

    def auth(token):
        if token != 'test':
            raise AuthenticationError('Invalid token')
        return SimpleNamespace(username='robot')

    monkeypatch.setattr(apps, 'get_auth_service', lambda: SimpleNamespace(validate_token=auth))
    base = '/aivuda_os/api/apps/pipeline'
    with TestClient(app) as http:
        draft = config(group('first', node('a')), group('second', node('b', 'a')))
        for method, path, body in [('GET', '', None), ('PUT', '', draft), ('POST', '/validate', draft),
                                   ('POST', '/run', {}), ('POST', '/stop', {})]:
            assert http.request(method, base + path, json=body, params={'token': 'bad'}).status_code == 401
        http.params = {'token': 'test'}
        assert http.post(base + '/validate', json=draft).json()['preview']['robot'][1]['batches'] == [['b']]
        assert not service.store.path.exists()
        invalid = copy.deepcopy(draft)
        invalid['profiles'][0]['groups'][0]['items'][0]['depends_on'] = ['b']
        assert not http.post(base + '/validate', json=invalid).json()['valid']
        assert http.put(base, json=invalid).status_code == 422
        assert http.put(base, json=draft).status_code == 200
        assert http.put(base, json=draft).status_code == 409
        info = http.get(base).json()
        assert [n['app_id'] for n in info['unassigned_apps']] == ['c', 'd', 'e']
        assert info['config']['version'] == 1 and info['validation']['valid']
        assert http.post(base + '/run', json={'profile': 'missing'}).status_code == 422
        probing = threading.Event()

        def wait(node_id, spec, cancel):
            probing.set()
            if cancel.wait(4):
                raise AppRuntimeError('Canceled')

        service.prober.wait = wait
        response = http.post(base + '/run')
        assert response.status_code == 202 and probing.wait(2)
        op = response.json()['operation_id']
        ops = '/aivuda_os/api/apps/operations/' + op
        assert http.get(base).json()['active_operation']['operation_id'] == op
        assert http.post(base + '/stop').status_code == 409
        with pytest.raises(AppOperationConflictError):
            service.operations.start_operation('restart', 'b')
        assert http.post(ops + '/cancel').status_code == 200
        sse = http.get(ops + '/events').text
        assert 'event: pipeline_node' in sse and 'event: completed' in sse
        assert http.get(ops).json()['status'] == 'canceled'
        assert service.runtime.running == {'a'}  # No rollback or surprise start of b.
        stopped = http.post(base + '/stop')
        assert stopped.status_code == 202 and finish(service, stopped.json())[-1]['status'] == 'completed'
        assert service.runtime.calls[-2:] == [('stop', 'b'), ('stop', 'a')]


@pytest.mark.parametrize('takeover', [False, True])
def test_gateway_startup_selects_exactly_one_autostart_path(service, monkeypatch, takeover):
    from aivudaos.gateway import main

    legacy = Mock(return_value={'started': [], 'failed': []})
    service.runtime.start_autostart_apps = legacy
    for name, obj in [('ensure_dirs', Mock()), ('init_db', Mock()), ('get_magnet_service', Mock()),
                      ('get_pipeline_service', lambda: service), ('get_runtime_service', lambda: service.runtime)]:
        monkeypatch.setattr(main, name, obj)
    draft = config(group('drivers', node('a')))
    draft['takeover_autostart'] = takeover
    service.store.save(draft)
    startup = main.create_app().router.on_startup[0]
    asyncio.run(startup())
    assert legacy.call_count == (0 if takeover else 1)
    if takeover:
        # Wait for the gateway-queued operation without canceling it on shutdown.
        for _ in range(100):
            if not service.describe()['active_operation']:
                break
            time.sleep(.01)
        assert service.runtime.calls == [('run', 'a')]
        service.runtime.configure_pipeline_autostart.assert_called_once_with(True)
    else:
        assert not service.runtime.calls
        service.runtime.configure_pipeline_autostart.assert_not_called()


def test_reads_during_takeover_keep_per_app_preference(tmp_path, monkeypatch):
    from aivudaos.core.db import connection, schema

    monkeypatch.setattr(connection, 'DB_PATH', tmp_path / 'test.db')
    schema.init_db()
    runtime = RuntimeService(Mock(), Mock(), Mock())
    runtime._sync_runtime_row('a', running=False, pid=None, autostart=True)
    monkeypatch.setattr(runtime, '_should_use_systemd', lambda scope: True)
    monkeypatch.setattr(runtime, '_systemd_scope', lambda: 'user')
    runtime._systemd = Mock()
    runtime._systemd.get_state.return_value = SimpleNamespace(running=True, pid=100, enabled=False)
    runtime.configure_pipeline_autostart(True)
    assert runtime.get_runtime_state('a').autostart
    runtime._sync_runtime_row('a', running=True, pid=100, autostart=False)  # live unit is disabled
    assert runtime.get_runtime_state('a').autostart
    runtime.set_autostart('a', False)
    assert not runtime.get_runtime_state('a').autostart
    runtime.set_autostart('a', True)
    assert runtime.get_runtime_state('a').autostart
    runtime._systemd.set_enabled.assert_not_called()


def test_mcp_names_and_explicit_pipeline_credentials():
    server = MCPServer(EmbeddedAPIClient())
    names = {tool['name'] for tool in server.tools}
    assert {'get_startup_pipeline', 'run_startup_pipeline', 'stop_startup_pipeline'} <= names
    with pytest.raises(ValueError, match='session token'):
        server.call_tool('run_startup_pipeline', {})
