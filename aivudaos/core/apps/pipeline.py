"""Execute saved application startup profiles against the existing runtime."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from aivudaos.core.apps.operations import AppOperationManager
from aivudaos.core.apps.pipeline_config import (
    PipelineConflict, PipelineStore, build_execution_plan, build_stop_plan,
    ros2_template, validate_config,
)
from aivudaos.core.apps.pipeline_probes import ReadinessProber
from aivudaos.core.apps.runtime import RuntimeService
from aivudaos.core.errors import AppOperationConflictError, AppRuntimeError

logger = logging.getLogger(__name__)


def _profile(config, name):
    for profile in config['profiles']:
        if profile['name'] == name:
            return profile
    raise ValueError('Unknown pipeline profile: {}'.format(name))


class PipelineOrchestrator:
    def __init__(self, store: PipelineStore, runtime: RuntimeService,
                 operations: AppOperationManager, prober=None) -> None:
        self.store = store
        self.runtime = runtime
        self.operations = operations
        self.prober = prober or ReadinessProber(runtime)
        self._lock = threading.RLock()
        self._active = None
        self._thread = None

    @staticmethod
    def _missing_apps(config, installed):
        assigned = {node['app_id'] for profile in config['profiles'] for group in profile['groups']
                    for node in group['items']}
        return ['App is not installed: ' + app for app in sorted(assigned.difference(installed))]

    def validate(self, config, installed=None):
        result = validate_config(config)
        if result['valid']:
            if installed is None:
                installed = self.runtime.list_installed_app_ids()
            errors = self._missing_apps(config, installed)
            if errors:
                return {'valid': False, 'errors': errors, 'preview': {}}
        return result

    def describe(self, config=None):
        config = self.store.load(for_editing=True) if config is None else config
        apps = self.runtime.get_installed_list()
        validation = self.validate(config, [app['app_id'] for app in apps])
        profile = _profile(config, config['default_profile'])
        assigned = {node['app_id'] for group in profile['groups'] for node in group['items']}
        with self._lock:
            active = self._active
        return {'config': config, 'validation': validation, 'installed_apps': apps,
                'unassigned_apps': [app for app in apps if app['app_id'] not in assigned],
                'active_operation': active}

    def save(self, config):
        ownership_changed = False

        def apply_ownership(old, new):
            nonlocal ownership_changed
            errors = self._missing_apps(new, self.runtime.list_installed_app_ids())
            if errors:
                raise ValueError('; '.join(errors))
            if old['takeover_autostart'] != new['takeover_autostart']:
                ownership_changed = True
                self.runtime.configure_pipeline_autostart(new['takeover_autostart'])

        with self._lock:
            if self._active:
                raise AppOperationConflictError('Cannot edit a running pipeline')
            try:
                saved = self.store.save(config, before_replace=apply_ownership)
            except Exception:
                if ownership_changed:
                    # A systemd command or atomic replacement failed. Reconcile
                    # partially updated units against the durable configuration.
                    self.runtime.configure_pipeline_autostart(self.store.load(for_editing=True)['takeover_autostart'])
                raise
        return self.describe(saved)

    def startup(self):
        config = self.store.load(for_editing=True)
        if not config['takeover_autostart']:
            return None
        self.runtime.configure_pipeline_autostart(True)
        return self.queue('run', config['default_profile'])

    def shutdown(self):
        with self._lock:
            worker = self._thread
            if self._active:
                try:
                    self.operations.request_cancel(self._active['operation_id'], 'Gateway shutdown')
                except AppOperationConflictError:
                    pass  # The worker just published its terminal event.
        if worker:
            worker.join()

    def queue(self, action: str, profile: Optional[str] = None,
              group_id: Optional[str] = None) -> Dict[str, Any]:
        if action not in ('run', 'stop'):
            raise ValueError('Unknown pipeline action')
        if action == 'stop' and group_id is not None:
            raise ValueError('Stop the entire profile to preserve reverse dependency order')
        with self._lock:
            if self._active:
                raise AppOperationConflictError('A pipeline operation is already running')
            config = self.store.load()
            selected = _profile(config, profile if profile is not None else config['default_profile'])
            execution = _Execution(self, selected, action, group_id)
            record = self.operations.start_operation('pipeline_' + action, None,
                                                     reserved_apps=tuple(execution.reservations))
            execution.operation_id = record.operation_id
            self.operations.register_cancel_handler(record.operation_id, execution.cancel.set)
            info = {'operation_id': record.operation_id, 'profile': selected['name'],
                    'group_id': group_id, 'action': action, 'status': 'queued'}
            self._active = info
            self._thread = threading.Thread(target=self._worker, args=(execution,), daemon=True)
            try:
                self._thread.start()
            except RuntimeError:
                self._active = self._thread = None
                self.operations.mark_failed(record.operation_id, 'Failed to start pipeline worker')
                raise
            return info

    def _worker(self, execution):
        op = execution.operation_id
        self.operations.mark_running(op)
        error = None
        try:
            execution.execute()
        except Exception:
            logger.exception('Pipeline worker failed: %s', op)
            error = 'Unexpected pipeline execution error'
        with self._lock:
            self._active = self._thread = None
            if execution.cancel.is_set():
                self.operations.mark_canceled(op, 'Pipeline canceled')
            elif error or execution.failures:
                self.operations.mark_failed(op, error or 'Pipeline failed: ' + ', '.join(execution.failures))
            else:
                self.operations.mark_completed(op, {'nodes': execution.states})


class _Execution:
    """A fixed plan snapshot. Only the coordinator mutates final node states."""

    def __init__(self, service, profile, action, group_id):
        self.runtime, self.prober, self.operations = service.runtime, service.prober, service.operations
        self.action = action
        self.policy = profile['on_failure']
        self.cancel = threading.Event()
        self.operation_id = None
        self.failures = []
        self.states = {}
        self.nodes = {n['app_id']: n for g in profile['groups'] for n in g['items']}
        self.plan = (build_stop_plan if action == 'stop' else build_execution_plan)(profile)
        if group_id is not None:
            self.plan = [stage for stage in self.plan if stage['group_id'] == group_id]
            if not self.plan:
                raise ValueError('Unknown or disabled pipeline group: {}'.format(group_id))
        targets = {node for stage in self.plan for batch in stage['batches'] for node in batch}
        self.reservations = set(targets)
        # A group-only start verifies its external prerequisites; it never starts
        # other groups. Reserve their apps, too, so UI actions cannot race probes.
        self.external = []
        if action == 'run' and group_id is not None:
            pending = list(targets)
            while pending:
                for dep in self.nodes[pending.pop()]['depends_on']:
                    if dep not in self.reservations:
                        self.reservations.add(dep)
                        pending.append(dep)
            external_ids = self.reservations - targets
            self.external = [node for stage in build_execution_plan(profile) for batch in stage['batches']
                             for node in batch if node in external_ids]

    def emit(self, kind, **fields):
        self.operations.publish(self.operation_id, kind, **fields)

    def update(self, group, node, state):
        self.emit('pipeline_node', group_id=group, app_id=node, status=state)
        return state

    def check_ready(self, node):
        self.prober.wait(node, self.nodes[node]['readiness'], self.cancel)

    def perform(self, group, node, degraded):
        if self.cancel.is_set():
            return self.update(group, node, 'skipped')
        step = 'stop' if self.action == 'stop' else 'start'
        try:
            if self.action == 'stop':
                self.update(group, node, 'stopping')
                self.runtime.stop(node)
                if self.runtime.get_runtime_state(node).running:
                    raise AppRuntimeError('App is still running')
                return self.update(group, node, 'stopped')
            self.update(group, node, 'starting')
            self.runtime.start(node)
            step = 'readiness'
            self.update(group, node, 'waiting_ready')
            self.check_ready(node)
            return self.update(group, node, 'degraded' if degraded else 'active')
        except Exception as exc:
            if self.cancel.is_set():
                # Cancel interrupts the probe, not the app it is observing.
                return self.update(group, node, 'degraded' if step == 'readiness' else 'failed')
            message = '{}: {} failed'.format(node, step)
            if step == 'readiness':
                message += ': {}'.format(exc)
            logger.warning('%s: %s', message, exc)
            self.emit('log', group_id=group, app_id=node, message=message)
            return self.update(group, node, 'failed')

    def execute(self):
        for stage in self.plan:
            for batch in stage['batches']:
                for node in batch:
                    self.update(stage['group_id'], node, 'queued')
        for node in self.external:
            if self.cancel.is_set():
                break
            unmet = any(self.states.get(dep) != 'active' for dep in self.nodes[node]['depends_on'])
            if self.failures and self.policy == 'abort':
                break
            if unmet and self.policy == 'skip_dependents':
                self.states[node] = 'skipped'
                continue
            try:
                self.check_ready(node)
                self.states[node] = 'degraded' if unmet else 'active'
            except Exception as exc:
                self.states[node] = 'failed'
                self.failures.append(node)
                self.emit('log', app_id=node, message='External prerequisite {} is not ready: {}'.format(node, exc))
        # Limit concurrency on smaller robot hosts, without converting a batch
        # into a series of start+wait calls. Every stage/batch ends at a barrier.
        with ThreadPoolExecutor(max_workers=8) as pool:
            for stage in self.plan:
                group = stage['group_id']
                stage_states = []
                self.emit('pipeline_stage', group_id=group, status='starting' if self.action == 'run' else 'stopping')
                for batch in stage['batches']:
                    futures = {}
                    abort = self.failures and (self.policy == 'abort' or self.action == 'stop')
                    for node in batch:
                        unmet = self.action == 'run' and any(
                            self.states.get(dep) != 'active' for dep in self.nodes[node]['depends_on'])
                        if abort or self.cancel.is_set() or (unmet and self.policy == 'skip_dependents'):
                            self.states[node] = self.update(group, node, 'skipped')
                        else:
                            futures[node] = pool.submit(self.perform, group, node, unmet)
                    for node, future in futures.items():
                        self.states[node] = future.result()
                        if self.states[node] == 'failed':
                            self.failures.append(node)
                    stage_states.extend(self.states[node] for node in batch)
                status = 'active' if self.action == 'run' else 'stopped'
                if 'failed' in stage_states:
                    status = 'failed'
                elif 'skipped' in stage_states or 'degraded' in stage_states:
                    status = 'skipped' if all(s == 'skipped' for s in stage_states) else 'degraded'
                self.emit('pipeline_stage', group_id=group, status=status)
        self.emit('log', message='Pipeline {} finished'.format(self.action))
