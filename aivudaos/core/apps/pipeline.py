"""Execute saved application startup profiles against the existing runtime."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from aivudaos.core.apps.operations import AppOperationManager
from aivudaos.core.apps.pipeline_config import (
    PipelineConflict, PipelineStore, build_execution_plan, build_stop_plan,
    reverse_plan, ros2_template, validate_config,
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

    def describe(self, config=None, *, list_view=False):
        config = self.store.load(for_editing=True) if config is None else config
        result = {'config': config}
        if not list_view:
            apps = self.runtime.get_installed_list()
            profile = _profile(config, config['default_profile'])
            assigned = {node['app_id'] for group in profile['groups'] for node in group['items']}
            result.update(validation=self.validate(config, [app['app_id'] for app in apps]),
                          installed_apps=apps, unassigned_apps=[app for app in apps if app['app_id'] not in assigned])
        with self._lock:
            result['active_operation'] = self._active
        return result

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
        if action not in ('run', 'stop', 'restart'):
            raise ValueError('Unknown pipeline action')
        with self._lock:
            if self._active:
                raise AppOperationConflictError('A pipeline operation is already running')
            config, plans = self.store.load_with_plans()
            selected = _profile(config, profile if profile is not None else config['default_profile'])
            execution = _Execution(self, selected, plans[selected['name']], action, group_id)
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

    def __init__(self, service, profile, full_plan, action, group_id):
        self.runtime, self.prober, self.operations = service.runtime, service.prober, service.operations
        self.action = action
        self.policy = profile['on_failure']
        self.cancel = threading.Event()
        self.operation_id = None
        self.failures = []
        self.states = {}
        self.nodes = {n['app_id']: n for g in profile['groups'] for n in g['items']}
        self.plan = full_plan
        self.group_id = group_id
        if group_id is not None:
            self.plan = [stage for stage in full_plan if stage['group_id'] == group_id]
            if not self.plan:
                raise ValueError('Unknown or disabled pipeline group: {}'.format(group_id))
        targets = {node for stage in self.plan for batch in stage['batches'] for node in batch}
        self.reservations = set(targets)
        self.external = []
        self.downstream = set()
        if group_id is not None and action in ('run', 'restart'):
            # Keep external prerequisites reserved through both phases of a restart.
            deps = {node: item['depends_on'] for node, item in self.nodes.items()}
            external_ids = self._reachable_outside(targets, deps)
            self.reservations.update(external_ids)
            self.external = [node for stage in full_plan for batch in stage['batches']
                             for node in batch if node in external_ids]
        if group_id is not None and action in ('stop', 'restart'):
            followers = {}
            for node, item in self.nodes.items():
                for dep in item['depends_on']:
                    followers.setdefault(dep, []).append(node)
            self.downstream = self._reachable_outside(targets, followers)

    @staticmethod
    def _reachable_outside(targets, neighbors):
        seen, pending = set(targets), list(targets)
        while pending:
            for neighbor in neighbors.get(pending.pop(), ()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    pending.append(neighbor)
        return seen - targets

    def emit(self, kind, **fields):
        self.operations.publish(self.operation_id, kind, **fields)

    def update(self, group, node, state):
        self.emit('pipeline_node', group_id=group, app_id=node, status=state)
        return state

    def check_ready(self, node):
        self.prober.wait(node, self.nodes[node]['readiness'], self.cancel)

    def perform(self, group, node, phase, degraded):
        if self.cancel.is_set():
            return self.update(group, node, 'skipped')
        step = phase
        try:
            if phase == 'stop':
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

    def warn_running_dependents(self):
        running = []
        for node in sorted(self.downstream):
            if self.cancel.is_set():
                return
            try:
                if self.runtime.get_runtime_state(node).running:
                    running.append(node)
            except Exception:
                # This check is advisory. It must not prevent the requested stop.
                logger.warning('Could not check downstream app %s', node, exc_info=True)
        if running:
            self.emit('log', group_id=self.group_id, message=(
                'Downstream apps are running and will remain running: ' + ', '.join(running)))

    def unmet_dependencies(self, node):
        return any(self.states.get(dep) != 'active' for dep in self.nodes[node]['depends_on'])

    def check_external(self):
        for node in self.external:
            if self.cancel.is_set():
                break
            unmet = self.unmet_dependencies(node)
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

    def execute_phase(self, phase, plan, pool):
        starting = phase == 'start'
        for stage in plan:
            for batch in stage['batches']:
                for node in batch:
                    self.update(stage['group_id'], node, 'queued')
        if starting:
            self.check_external()
        else:
            self.warn_running_dependents()
        for stage in plan:
            group = stage['group_id']
            stage_states = set()
            self.emit('pipeline_stage', group_id=group, status='starting' if starting else 'stopping')
            for batch in stage['batches']:
                futures = {}
                abort = self.failures and (self.policy == 'abort' or not starting)
                for node in batch:
                    unmet = starting and self.unmet_dependencies(node)
                    if abort or self.cancel.is_set() or (unmet and self.policy == 'skip_dependents'):
                        self.states[node] = self.update(group, node, 'skipped')
                    else:
                        futures[node] = pool.submit(self.perform, group, node, phase, unmet)
                for node, future in futures.items():
                    self.states[node] = future.result()
                    if self.states[node] == 'failed':
                        self.failures.append(node)
                stage_states.update(self.states[node] for node in batch)
            status = 'active' if starting else 'stopped'
            if 'failed' in stage_states:
                status = 'failed'
            elif 'skipped' in stage_states or 'degraded' in stage_states:
                status = 'skipped' if stage_states == {'skipped'} else 'degraded'
            self.emit('pipeline_stage', group_id=group, status=status)

    def execute(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            if self.action in ('stop', 'restart'):
                self.execute_phase('stop', reverse_plan(self.plan), pool)
            if self.action != 'stop' and not self.failures and not self.cancel.is_set():
                self.execute_phase('start', self.plan, pool)
        self.emit('log', message='Pipeline {} finished'.format(self.action))
