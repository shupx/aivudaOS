import asyncio
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from aivudaos.gateway.routes import apps


class BulkRestartTests(unittest.TestCase):
    def run_restart(self, installed):
        runtime = Mock()
        runtime.get_installed_list.return_value = installed
        with patch.object(apps, '_require_auth'), \
                patch.object(apps, 'get_runtime_service', return_value=runtime), \
                patch.object(apps, '_queue_app_operation') as queue:
            queue.side_effect = lambda kind, app_id, task: (
                task() or {'app_id': app_id, 'operation_type': kind}
            )
            runtime.restart.return_value = None
            result = asyncio.run(apps.restart_running_apps('token'))
        return result, runtime

    def test_restarts_running_apps_regardless_of_autostart(self):
        result, runtime = self.run_restart([
            {'app_id': 'manual-running', 'running': True, 'autostart': False},
            {'app_id': 'auto-running', 'running': True, 'autostart': True},
            {'app_id': 'auto-stopped', 'running': False, 'autostart': True},
            {'app_id': 'manual-stopped', 'running': False, 'autostart': False},
            {'app_id': 'unknown-status', 'autostart': True},
        ])
        self.assertEqual(result['requested_count'], 2)
        self.assertEqual(result['queued_count'], 2)
        self.assertEqual(
            [call.args[0] for call in runtime.restart.call_args_list],
            ['manual-running', 'auto-running'],
        )

    def test_no_running_apps_queues_nothing(self):
        result, runtime = self.run_restart([
            {'app_id': 'auto-stopped', 'running': False, 'autostart': True},
        ])
        self.assertEqual(result['requested_count'], 0)
        self.assertEqual(result['operations'], [])
        runtime.restart.assert_not_called()

    def test_requires_auth_before_accessing_runtime(self):
        with patch.object(apps, '_require_auth', side_effect=HTTPException(401)), \
                patch.object(apps, 'get_runtime_service') as runtime:
            with self.assertRaises(HTTPException):
                asyncio.run(apps.restart_running_apps('invalid'))
            runtime.assert_not_called()


if __name__ == '__main__':
    unittest.main()
