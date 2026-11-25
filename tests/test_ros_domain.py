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

    def test_migration_normalizes_existing_string_and_schema_once(self):
        key = ros_domain.DOMAIN_KEY
        with tempfile.TemporaryDirectory() as tmp, patch.object(ros_domain, "has_ros2", return_value=True):
            path = Path(tmp) / "sys.yaml"
            path.write_text(yaml.safe_dump({
                "sys": {key: "7", "name": "station"}, "_version": 2,
                "_sys_schema": {"sys." + key: {"type": "string", "enum": ["7"], "title": "ROS"},
                                "sys.name": {"type": "string"}},
            }))
            ros_domain.ensure_ros_domain(path, {"ROS_DOMAIN_ID": "9"})
            first = path.read_bytes()
            data = yaml.safe_load(first)
            self.assertEqual(data["_version"], 3)
            self.assertEqual(data["sys"], {key: 7, "name": "station"})
            self.assertEqual(data["_sys_schema"], {
                "sys." + key: {"type": "integer", "minimum": 0, "maximum": 232, "title": "ROS"},
                "sys.name": {"type": "string"},
            })
            ros_domain.ensure_ros_domain(path, {"ROS_DOMAIN_ID": "10"})
            self.assertEqual(first, path.read_bytes())

    def test_migration_skips_invalid_sources_and_always_creates_global_row(self):
        key = ros_domain.DOMAIN_KEY
        cases = [
            ({}, "", "8", 8),
            ({key: "233"}, "12", "8", 12),
            ({key: True}, "-1", "8", 8),
            ({key: 1.5}, False, "8", 8),
            ({}, "invalid", "233", 0),
        ]
        for shared, legacy, inherited, expected in cases:
            with self.subTest(shared=shared, legacy=legacy), patch.dict(os.environ, {"ROS_DOMAIN_ID": inherited}):
                data = {"sys": shared.copy()}
                self.assertTrue(ros_domain.populate_default_domain(data, {"ROS_DOMAIN_ID": legacy}))
                self.assertEqual(ros_domain.configured_domain(data), expected)
                self.assertEqual(data["_sys_schema"]["sys." + key]["type"], "integer")
                self.assertFalse(ros_domain.populate_default_domain(data, {"ROS_DOMAIN_ID": "22"}))

    def test_launch_and_save_repair_unmigrated_shared_default(self):
        key = ros_domain.DOMAIN_KEY
        for legacy, expected_launch in (("7", "7"), ("invalid", "8")):
            with self.subTest(legacy=legacy), tempfile.TemporaryDirectory() as tmp, \
                    patch.object(service, "SYS_CONFIG_PATH", Path(tmp) / "sys.yaml"), \
                    patch.object(service, "OS_CONFIG_PATH", Path(tmp) / "os.yaml"), \
                    patch.dict(os.environ, {"ROS_VERSION": "2", "ROS_DOMAIN_ID": "8"}), \
                    patch.object(routes, "_require_auth", return_value=Mock(username="admin")), \
                    patch.object(routes, "get_magnet_service") as magnets, \
                    patch.object(routes, "get_runtime_service") as runtime_service:
                cfg = service.ConfigService()
                service.SYS_CONFIG_PATH.write_text(yaml.safe_dump({"sys": {key: legacy}, "_version": 3}))
                cfg.update_os_config({"runtime_environment": {"ROS_DOMAIN_ID": ""}}, 0, "admin")
                runtime = RuntimeService(Mock(), cfg, Mock())
                self.assertEqual(runtime._build_runtime_env()["ROS_DOMAIN_ID"], expected_launch)
                self.assertEqual(cfg.get_sys_config().version, 3)  # Launch doesn't edit the file.

                magnets.return_value.blocked_paths_for_sys_update.return_value = []
                runtime_service.return_value.refresh_runtime_environment.return_value = []
                req = ConfigUpdateRequest(version=3, data={"sys": {key: 7}})
                with patch.object(routes, "get_config_service", return_value=cfg):
                    result = asyncio.run(routes.put_config(req, "test"))
                self.assertTrue(result["ok"])
                self.assertEqual(result["version"], 4)
                self.assertEqual(ros_domain.configured_domain(cfg.get_sys_config().data), 7)
                runtime_service.return_value.refresh_runtime_environment.assert_called_once_with()

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
