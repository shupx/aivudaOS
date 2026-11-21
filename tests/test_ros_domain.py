import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml
from fastapi import HTTPException

from aivudaos.core.apps.runtime import RuntimeService
from aivudaos.core.config import ros_domain, service
from aivudaos.gateway.routes import config as routes
from aivudaos.gateway.schemas import ConfigUpdateRequest


class RosDomainTests(unittest.TestCase):
    def test_detection_and_idempotent_migration(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True), \
                patch.object(ros_domain.shutil, "which", return_value=None), \
                patch.object(Path, "glob", return_value=[]):
            path = Path(tmp) / "sys.yaml"
            path.write_text("sys: {role: {id: 2}}\n_version: 4\n")
            ros_domain.ensure_ros_domain(path, {})
            self.assertNotIn(ros_domain.DOMAIN_KEY, path.read_text())
            os.environ["ROS_VERSION"] = "2"
            os.environ["ROS_DOMAIN_ID"] = "8"
            ros_domain.ensure_ros_domain(path, {"ROS_DOMAIN_ID": "0"})
            first = path.read_bytes()
            data = yaml.safe_load(first)
            self.assertEqual(ros_domain.configured_domain(data), 0)
            self.assertEqual(data["sys"]["role"]["id"], 2)
            self.assertEqual(data["_version"], 5)
            ros_domain.ensure_ros_domain(path, {"ROS_DOMAIN_ID": "7"})
            self.assertEqual(path.read_bytes(), first)

    def test_save_and_launch_environment(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(service, "SYS_CONFIG_PATH", Path(tmp) / "sys.yaml"), \
                patch.object(service, "OS_CONFIG_PATH", Path(tmp) / "os.yaml"), \
                patch.object(routes, "_require_auth", return_value=Mock(username="admin")), \
                patch.object(routes, "get_magnet_service") as magnets, \
                patch.object(routes, "get_runtime_service") as runtime_service, \
                patch.object(routes, "has_ros2", return_value=True):
            cfg = service.ConfigService()
            runtime = RuntimeService(Mock(), cfg, Mock())
            cfg.update_os_config({"runtime_environment": {"ROS_DOMAIN_ID": "8"}}, 0, "admin")
            magnets.return_value.blocked_paths_for_sys_update.return_value = []
            runtime_service.return_value.refresh_runtime_environment.return_value = []
            def save(value, version):
                req = ConfigUpdateRequest(version=version, data={"sys": {ros_domain.DOMAIN_KEY: value}})
                with patch.object(routes, "get_config_service", return_value=cfg):
                    return asyncio.run(routes.put_config(req, "test"))
            self.assertEqual(save(232, 0)["version"], 1)
            runtime_service.return_value.refresh_runtime_environment.assert_called_once()
            with patch("aivudaos.core.apps.runtime.has_ros2", return_value=True):
                self.assertEqual(runtime._build_runtime_env()["ROS_DOMAIN_ID"], "232")
            with patch("aivudaos.core.apps.runtime.has_ros2", return_value=False):
                self.assertEqual(runtime._build_runtime_env()["ROS_DOMAIN_ID"], "8")
            for bad in (-1, 233, True, 1.5, "4"):
                with self.assertRaises(HTTPException) as exc:
                    save(bad, 1)
                self.assertEqual(exc.exception.status_code, 400)
            with self.assertRaises(HTTPException) as exc:
                save(7, 0)
            self.assertEqual(exc.exception.status_code, 409)
            self.assertEqual(ros_domain.configured_domain(cfg.get_sys_config().data), 232)
