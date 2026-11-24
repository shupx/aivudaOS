"""Execute saved application startup profiles against the existing runtime."""
from __future__ import annotations

import logging
import threading
from contextlib import nullcontext
from collections import Counter, defaultdict, deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
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
        default = _profile(config, config['default_profile'])
        assigned = {node['app_id'] for group in default['groups']
                    for node in group['items']}
        return ['App is not installed: ' + app for app in sorted(assigned.difference(installed))]

    def validate(self, config, installed=None):
        return self._validate_inventory(config, validate_config(config), installed)

    def _validate_inventory(self, config, result, installed):
        if result['valid']:
            if installed is None:
                installed = self.runtime.list_installed_app_ids()
            errors = self._missing_apps(config, installed)
            if errors:
                return {'valid': False, 'errors': errors, 'preview': {}}
        return result

    def describe(self, config=None, *, list_view=False, _saved_preview=None):
        config = self.store.load(for_editing=True) if config is None else config
        result = {'config': config}
        if not list_view:
            apps = self.runtime.get_installed_list()
            profile = _profile(config, config['default_profile'])
            assigned = {node['app_id'] for group in profile['groups'] for node in group['items']}
            validation = (validate_config(config) if _saved_preview is None else
                          {'valid': True, 'errors': [], 'preview': _saved_preview})
            result.update(validation=self._validate_inventory(config, validation, (app['app_id'] for app in apps)),
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
                saved, preview = self.store.save_with_preview(config, before_replace=apply_ownership)
            except Exception:
                if ownership_changed:
                    # A systemd command or atomic replacement failed. Reconcile
                    # partially updated units against the durable configuration.
                    self.runtime.configure_pipeline_autostart(self.store.load(for_editing=True)['takeover_autostart'])
                raise
        return self.describe(saved, _saved_preview=preview)

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
              group_id: Optional[str] = None, with_deps: bool = False) -> Dict[str, Any]:
        if action not in ('run', 'stop', 'restart'):
            raise ValueError('Unknown pipeline action')
        if with_deps and (group_id is None or action == 'stop'):
            raise ValueError('with_deps requires a group run or restart')
        with self._lock:
            if self._active:
                raise AppOperationConflictError('A pipeline operation is already running')
            selected, plan = self.store.load_for_execution(profile)
            execution = _Execution(self, selected, plan, action, group_id, with_deps)
            if action != 'stop':
                missing = execution.reservations.difference(self.runtime.list_installed_app_ids())
                if missing:
                    raise ValueError('App is not installed: ' + ', '.join(sorted(missing)))
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
            session = self.prober.session() if isinstance(self.prober, ReadinessProber) else nullcontext()
            with session:
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

    def __init__(self, service, profile, full_plan, action, group_id, with_deps):
        self.runtime, self.prober, self.operations = service.runtime, service.prober, service.operations
        self.action = action
        self.policy = profile['on_failure']
        self.cancel = threading.Event()
        self.operation_id = None
        self.failures = []
        self.states = {}
        self.nodes = {n['app_id']: n for g in profile['groups'] for n in g['items']}
        self.group_id = group_id
        self.with_deps = with_deps
        self.groups = full_plan.members
        self.owner = {n: gid for gid, nodes in self.groups.items() for n in nodes}
        self.required, self.ordering = full_plan.required, full_plan.ordering
        if group_id is not None and group_id not in self.groups:
            raise ValueError('Unknown or disabled pipeline group: {}'.format(group_id))
        self.targets = list(self.owner) if group_id is None else self.groups[group_id]
        self.external = set()
        self.downstream = set()
        if group_id is not None and action in ('run', 'restart'):
            self.external = self._reachable_outside(self.targets, self.required)
        if group_id is not None and action in ('stop', 'restart'):
            followers = defaultdict(set)
            for node, deps in self.required.items():
                for dep in deps:
                    followers[dep].add(node)
            self.downstream = self._reachable_outside(self.targets, followers)
        self.reservations = set(self.targets) | self.external

    @staticmethod
    def _reachable_outside(targets, neighbors):
        seen, pending = set(targets), list(targets)
        while pending:
            for neighbor in neighbors.get(pending.pop(), ()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    pending.append(neighbor)
        return seen.difference(targets)

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
            if phase == 'external':
                if self.with_deps and not self.runtime.get_runtime_state(node).running:
                    self.runtime.start(node)
            else:
                self.update(group, node, 'starting')
                self.runtime.start(node)
            step = 'readiness'
            self.update(group, node, 'waiting_ready')
            self.check_ready(node)
            ready = 'completed' if self.nodes[node]['readiness']['type'] == 'exited_zero' else 'active'
            return self.update(group, node, 'degraded' if degraded else ready)
        except Exception as exc:
            if self.cancel.is_set():
                # Cancel interrupts the probe, not the app it is observing.
                return self.update(group, node, 'degraded' if step == 'readiness' else 'failed')
            message = '{}: {} failed: {}'.format(node, step, exc)
            if phase == 'external':
                message = 'External prerequisite {} is not ready: {}'.format(node, exc)
            logger.warning('%s', message)
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

    def execute_phase(self, phase, targets, pool):
        stopping = phase == 'stop'
        targets = list(targets)
        selected = set(targets)
        followers = defaultdict(list)
        pending = dict.fromkeys(targets, 0)
        for node in targets:
            for dep in self.ordering[node] & selected:
                before, after = (node, dep) if stopping else (dep, node)
                followers[before].append(after)
                pending[after] += 1
            self.update(self.owner[node], node, 'queued')
        ready = deque(n for n in targets if pending[n] == 0)
        outstanding = {}
        remaining = Counter(self.owner[n] for n in targets)
        stage_states = defaultdict(set)

        def finish(node, state):
            self.states[node] = state
            if state == 'failed':
                self.failures.append(node)
            group = self.owner[node]
            stage_states[group].add(state)
            remaining[group] -= 1
            if remaining[group] == 0:
                states = stage_states[group]
                if states == {'active', 'completed'}:
                    status = 'active'
                elif len(states) == 1:
                    status = state
                else:
                    status = 'failed' if 'failed' in states else 'degraded'
                self.emit('pipeline_stage', group_id=group, status=status)
            for child in followers[node]:
                pending[child] -= 1
                if pending[child] == 0:
                    ready.append(child)

        announced = set()
        while ready or outstanding:
            while ready and len(outstanding) < 8:
                node = ready.popleft()
                group = self.owner[node]
                if group not in announced:
                    self.emit('pipeline_stage', group_id=group, status='stopping' if stopping else 'starting')
                    announced.add(group)
                unmet = not stopping and any(self.states.get(d) not in ('active', 'completed') for d in self.required[node])
                if (self.cancel.is_set() or (self.failures and (stopping or self.policy == 'abort'))
                        or (unmet and self.policy == 'skip_dependents')):
                    finish(node, self.update(group, node, 'skipped'))
                else:
                    step = 'external' if phase == 'start' and node in self.external else phase
                    future = pool.submit(self.perform, group, node, step, unmet)
                    outstanding[future] = node
            if outstanding:
                done, _ = wait(outstanding, return_when=FIRST_COMPLETED)
                for future in done:
                    finish(outstanding.pop(future), future.result())

    def execute(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            if self.action == 'run':
                self.execute_phase('start', [n for n in self.owner if n in self.reservations], pool)
            elif self.external:
                self.execute_phase('external', [n for n in self.owner if n in self.external], pool)
            if self.action in ('stop', 'restart'):
                if self.failures or self.cancel.is_set():
                    self.emit('log', message='Restart canceled before stopping the group')
                    return
                self.warn_running_dependents()
                self.execute_phase('stop', reversed(self.targets), pool)
            if self.action == 'restart' and not self.failures and not self.cancel.is_set():
                self.execute_phase('start', self.targets, pool)
        self.emit('log', message='Pipeline {} finished'.format(self.action))
