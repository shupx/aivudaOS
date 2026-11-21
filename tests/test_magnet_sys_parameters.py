import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import aivudaos.core.apps.magnet as magnet_module
import aivudaos.core.apps.versioning as versioning_module
import aivudaos.core.config.service as config_service_module
import aivudaos.core.db.connection as connection_module
from aivudaos.core.apps.magnet import MagnetService
from aivudaos.core.apps.versioning import VersioningService
from aivudaos.core.config.service import ConfigService
from aivudaos.core.db.schema import init_db
from aivudaos.core.errors import ConfigVersionConflictError, InvalidConfigError


class MagnetSysParametersTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config_dir = self.root / "config"
        self.app_config_dir = self.config_dir / "apps"
        self.apps_dir = self.root / "apps"
        self.data_dir = self.root / "data"
        self.config_dir.mkdir(parents=True)
        self.app_config_dir.mkdir(parents=True)
        self.apps_dir.mkdir(parents=True)
        self.data_dir.mkdir(parents=True)

        self.sys_path = self.config_dir / "sys.yaml"
        self.magnet_path = self.config_dir / "magnets.yaml"
        self.db_path = self.data_dir / "aivuda.db"

        self.sys_path.write_text(
            yaml.dump(
                {
                    "_version": 1,
                    "_updated_at": None,
                    "_updated_by": "system",
                    "sys": {"role": {"id": 1}},
                },
                default_flow_style=False,
                allow_unicode=True,
            ),
            "utf-8",
        )

        self.patchers = [
            patch.object(config_service_module, "SYS_CONFIG_PATH", self.sys_path),
            patch.object(config_service_module, "APP_CONFIG_DIR", self.app_config_dir),
            patch.object(magnet_module, "MAGNET_CONFIG_PATH", self.magnet_path),
            patch.object(versioning_module, "APPS_DIR", self.apps_dir),
            patch.object(versioning_module, "APP_RUNTIME_DATA_DIR", self.data_dir / "runtime"),
            patch.object(connection_module, "DB_PATH", self.db_path),
        ]
        for item in self.patchers:
            item.start()

        init_db()
        self.config = ConfigService()
        self.versioning = VersioningService()
        self.magnet = MagnetService(self.config, self.versioning)

    def tearDown(self) -> None:
        for item in reversed(self.patchers):
            item.stop()
        self.tmp.cleanup()

    def test_recompute_adds_missing_sys_parameter_and_group(self) -> None:
        self._install_app(
            "robot-app",
            "1.0.0",
            schema=self._schema_for_sys_leaf("robot_type", {"type": "string", "description": "Robot type"}),
            default_config={"sys": {"robot_type": "quad"}},
        )

        with patch.object(self.magnet, '_get_manifest', wraps=self.magnet._get_manifest) as manifest:
            result = self.magnet.recompute(updated_by="test")
        manifest.assert_called_once_with('robot-app', '1.0.0')

        sys_data = self.config.get_sys_config().data
        self.assertEqual(sys_data["sys"]["robot_type"], "quad")
        self.assertEqual(sys_data["_sys_schema"]["sys.robot_type"]["description"], "Robot type")
        self.assertEqual(result["groups"], 1)
        groups = self.magnet.list_groups()["items"]
        self.assertEqual(groups[0]["path"], "sys.robot_type")
        self.assertEqual(groups[0]["value"], "quad")
        self.assertEqual(
            {binding["kind"] for binding in groups[0]["bindings"]},
            {"sys", "app"},
        )

    def test_recompute_adds_nested_sys_parameter(self) -> None:
        self._install_app(
            "nested-app",
            "1.0.0",
            schema={
                "type": "object",
                "properties": {
                    "sys": {
                        "type": "object",
                        "properties": {
                            "aaa": {
                                "type": "object",
                                "properties": {
                                    "bbb": {"type": "integer"},
                                },
                            },
                        },
                    },
                },
            },
            default_config={"sys": {"aaa": {"bbb": 7}}},
        )

        self.magnet.recompute(updated_by="test")

        sys_data = self.config.get_sys_config().data
        self.assertEqual(sys_data["sys"]["aaa"]["bbb"], 7)
        self.assertEqual(sys_data["_sys_schema"]["sys.aaa.bbb"]["type"], "integer")

    def test_existing_sys_parameter_and_schema_are_not_overwritten(self) -> None:
        self._write_sys_config(
            {
                "sys": {"robot_type": None},
                "_sys_schema": {
                    "sys.robot_type": {
                        "type": ["string", "null"],
                        "description": "Existing schema",
                    },
                },
            }
        )
        self._install_app(
            "robot-app",
            "1.0.0",
            schema=self._schema_for_sys_leaf(
                "robot_type",
                {"type": ["string", "null"], "description": "App schema"},
            ),
            default_config={"sys": {"robot_type": "quad"}},
        )

        self.magnet.recompute(updated_by="test")

        sys_data = self.config.get_sys_config().data
        self.assertIsNone(sys_data["sys"]["robot_type"])
        self.assertEqual(sys_data["_sys_schema"]["sys.robot_type"]["description"], "Existing schema")

    def test_missing_schema_is_added_for_existing_sys_parameter(self) -> None:
        self._write_sys_config({"sys": {"robot_type": "manual"}})
        self._install_app(
            "robot-app",
            "1.0.0",
            schema=self._schema_for_sys_leaf("robot_type", {"type": "string", "description": "App schema"}),
            default_config={"sys": {"robot_type": "quad"}},
        )

        self.magnet.recompute(updated_by="test")

        sys_data = self.config.get_sys_config().data
        self.assertEqual(sys_data["sys"]["robot_type"], "manual")
        self.assertEqual(sys_data["_sys_schema"]["sys.robot_type"]["description"], "App schema")

    def test_multiple_apps_use_stable_first_value(self) -> None:
        self._install_app(
            "z-app",
            "1.0.0",
            schema=self._schema_for_sys_leaf("robot_type", {"type": "string"}),
            default_config={"sys": {"robot_type": "z-value"}},
        )
        self._install_app(
            "a-app",
            "1.0.0",
            schema=self._schema_for_sys_leaf("robot_type", {"type": "string"}),
            default_config={"sys": {"robot_type": "a-value"}},
        )

        self.magnet.recompute(updated_by="test")

        sys_data = self.config.get_sys_config().data
        self.assertEqual(sys_data["sys"]["robot_type"], "a-value")

    def test_sys_parameter_remains_after_app_is_removed(self) -> None:
        self._install_app(
            "robot-app",
            "1.0.0",
            schema=self._schema_for_sys_leaf("robot_type", {"type": "string"}),
            default_config={"sys": {"robot_type": "quad"}},
        )
        self.magnet.recompute(updated_by="test")

        with connection_module.db_conn() as conn:
            conn.execute("DELETE FROM app_installation WHERE app_id = ?", ("robot-app",))
            conn.commit()
        self.magnet.recompute(updated_by="test")

        sys_data = self.config.get_sys_config().data
        self.assertEqual(sys_data["sys"]["robot_type"], "quad")
        self.assertEqual(self.magnet.list_groups()["items"], [])

    def test_ros_domain_fields_are_excluded_from_magnets(self) -> None:
        self._install_app(
            "camera-app",
            "1.0.0",
            schema={
                "type": "object",
                "properties": {
                    "ros": {
                        "type": "object",
                        "properties": {
                            "domain_id": {"type": "integer", "minimum": -1, "maximum": 232},
                            "setup_script": {"type": "string"},
                        },
                    },
                },
            },
            default_config={"ros": {"domain_id": 2, "setup_script": "/opt/ros/jazzy/setup.bash"}},
        )
        self._install_app(
            "policy-app",
            "1.0.0",
            schema={
                "type": "object",
                "properties": {
                    "ros": {
                        "type": "object",
                        "properties": {
                            "domain_id": {"type": "integer", "minimum": -1, "maximum": 232},
                            "setup_script": {"type": "string"},
                        },
                    },
                },
            },
            default_config={"ros": {"domain_id": 5, "setup_script": "/opt/ros/jazzy/setup.bash"}},
        )

        self.magnet.recompute(updated_by="test")

        groups = self.magnet.list_groups()["items"]
        self.assertEqual([g["path"] for g in groups], ["ros.setup_script"])
        self.assertEqual(self.config.get_app_config("camera-app", "1.0.0").data["ros"]["domain_id"], 2)
        self.assertEqual(self.config.get_app_config("policy-app", "1.0.0").data["ros"]["domain_id"], 5)
        self.assertNotIn("ros.domain_id", self.magnet.readonly_paths_for_app("camera-app", "1.0.0"))
        self.assertNotIn("ros.domain_id", self.magnet.readonly_paths_for_app("policy-app", "1.0.0"))

    def _install_network_app(self, app, source_key, allowed_nics=None):
        nic = {"type": "string"}
        if allowed_nics is not None:
            nic["enum"] = allowed_nics
        schema = {"properties": {"net": {
            "x-device-ipv4": {"interface": "nic", "address": source_key, "destination": "dst"},
            "properties": {"nic": nic, "dst": {"type": "string"}, source_key: {"type": "string"}},
        }}}
        self._install_app(app, "1", schema, {"net": {"nic": "eth0", "dst": "10.0.0.5", source_key: "10.0.0.2"}})

    def _set_magnet(self, path, value, version=None):
        registry = self.magnet.list_groups()
        group = next(group for group in registry["items"] if group["path"] == path)
        self.magnet.update_group_value(group["group_id"], value,
                                       registry["version"] if version is None else version, "test")

    def test_network_magnet_resets_only_changed_unbound_sources(self):
        # Two apps share a source binding; the other two declare their own source keys.
        apps = (("a", "src"), ("b", "src"), ("c", "lidar_ip"), ("d", "local_ip"))
        for app, source in apps:
            self._install_network_app(app, source)
        self.magnet.recompute()
        for path, value in (("net.nic", "eth1"), ("net.dst", "10.2.0.9")):
            for app, source in apps:
                cfg = self.config.get_app_config(app, "1")
                if app in ("c", "d"):
                    cfg.data["net"][source] = "10.0.0.7"
                    self.config.update_app_config(app, "1", cfg.data, cfg.version)
            self.magnet.recompute()
            self.assertEqual(self.config.get_app_config("c", "1").data["net"]["lidar_ip"], "10.0.0.7")
            self._set_magnet(path, value)
            for app, source in apps:
                net = self.config.get_app_config(app, "1").data["net"]
                self.assertEqual(net[path.split(".")[1]], value)
                self.assertEqual(net[source], "10.0.0.2" if app in ("a", "b") else "auto")

    def test_rejected_network_magnet_keeps_configs_and_sources(self):
        self._install_network_app("a", "source_a")
        self._install_network_app("b", "source_b", allowed_nics=["eth0", "eth1"])
        self.magnet.recompute()
        with self.assertRaises(InvalidConfigError):
            self._set_magnet("net.nic", "eth2")
        with self.assertRaises(ConfigVersionConflictError):
            self._set_magnet("net.nic", "eth1", version=0)
        for app in ("a", "b"):
            net = self.config.get_app_config(app, "1").data["net"]
            self.assertEqual(net["nic"], "eth0")
            self.assertEqual(net["source_" + app], "10.0.0.2")

    def test_domain_arrays_remain_editable_without_disabling_other_array_groups(self):
        lanes = {"type": "array", "items": {"type": "object", "properties": {
            "domain_id": {"type": ["integer", "null"]},
        }}}
        schema = {"type": "object", "properties": {
            "lanes": lanes, "empty_lanes": lanes,
            "sys": {"properties": {"lanes": lanes}},
            "env": {"type": "array"}, "tags": {"type": "array"},
        }}
        for app, domain in (("camera-app", 2), ("policy-app", 5)):
            records = [{"domain_id": domain}]
            self._install_app(app, "1.0.0", schema, {
                "lanes": records, "empty_lanes": [], "sys": {"lanes": records},
                "env": [{"name": "ROS_DOMAIN_ID", "value": str(domain)}], "tags": [app],
            })

        self.magnet.recompute(updated_by="test")

        self.assertEqual([g["path"] for g in self.magnet.list_groups()["items"]], ["tags"])
        self.assertNotIn("lanes", self.config.get_sys_config().data["sys"])
        for app, domain in (("camera-app", 2), ("policy-app", 5)):
            data = self.config.get_app_config(app, "1.0.0").data
            self.assertEqual(data["lanes"], [{"domain_id": domain}])
            self.assertEqual(data["sys"]["lanes"], data["lanes"])
            self.assertEqual(data["env"][0]["value"], str(domain))
            after = dict(data, lanes=[{"domain_id": 13}])
            self.assertEqual(self.magnet.blocked_paths_for_app_update(app, "1.0.0", data, after), [])

    def test_shared_arrays_cannot_introduce_or_overwrite_domains(self):
        schema = {"properties": {"env": {"type": "array"}}}
        ordinary = [{"name": "MODE", "value": "auto"}]
        protected = [{"name": "ROS_DOMAIN_ID", "value": "3"}]
        for app in ("app-a", "app-b"):
            self._install_app(app, "1.0.0", schema, {"env": ordinary})
        self.magnet.recompute()
        snapshot = self.magnet.list_groups()
        group = snapshot["items"][0]
        with self.assertRaisesRegex(InvalidConfigError, "ROS domain"):
            self.magnet.update_group_value(group["group_id"], protected, snapshot["version"], "test")
        self.assertEqual(self.magnet.list_groups(), snapshot)
        for app in ("app-a", "app-b"):
            self.assertEqual(self.config.get_app_config(app, "1.0.0").data["env"], ordinary)

        # A stale registry must not erase a domain that now exists on a recipient.
        second = self.config.get_app_config("app-b", "1.0.0")
        self.config.update_app_config("app-b", "1.0.0", {"env": protected}, second.version, "test")
        with self.assertRaisesRegex(InvalidConfigError, "ROS domain"):
            self.magnet.update_group_value(group["group_id"], [], snapshot["version"], "test")
        self.assertEqual(self.config.get_app_config("app-a", "1.0.0").data["env"], ordinary)
        self.assertEqual(self.config.get_app_config("app-b", "1.0.0").data["env"], protected)

    def test_recompute_does_not_replay_a_stale_shared_domain_array(self):
        schema = {"properties": {"env": {"type": "array"}}}
        for app in ("app-a", "app-b"):
            self._install_app(app, "1.0.0", schema, {"env": []})
        self.magnet.recompute()
        registry = yaml.safe_load(self.magnet_path.read_text("utf-8"))
        registry["groups"][0]["value"] = [{"key": "ROS_DOMAIN_ID", "value": "3"}]
        self.magnet_path.write_text(yaml.safe_dump(registry), "utf-8")
        result = self.magnet.recompute()
        self.assertEqual((result["groups"], result["conflicts"]), (0, 1))
        for app in ("app-a", "app-b"):
            self.assertEqual(self.config.get_app_config(app, "1.0.0").data["env"], [])

    def test_only_opaque_domain_ids_without_ros_evidence_remain_magnet_bound(self):
        text = {"type": ["string", "null"], "description": "Identity provider domain ID"}
        schema = {"properties": {
            "identity": {"properties": {"domain_id": text}},
            "ros": {"properties": {"domain_id": text}},
            "camera": {"properties": {"domain_id": text}},
            "alias": {"type": "string", "x-ros-domain": True},
        }}
        for app, domain in (("camera-app", "2"), ("policy-app", "5")):
            self._install_app(app, "1.0.0", schema, {
                "identity": {"domain_id": "id-" + domain}, "ros": {"domain_id": "invalid"},
                "camera": {"domain_id": domain}, "alias": "invalid",
            })
        self.magnet.recompute(updated_by="test")
        self.assertEqual([g["path"] for g in self.magnet.list_groups()["items"]], ["identity.domain_id"])
        config = self.config.get_app_config("policy-app", "1.0.0").data
        self.assertEqual(config["identity"]["domain_id"], "id-2")
        self.assertEqual(config["camera"]["domain_id"], "5")

    def _install_app(self, app_id, version, schema, default_config):
        version_dir = self.apps_dir / app_id / "versions" / version
        version_dir.mkdir(parents=True)
        manifest = {
            "app_id": app_id,
            "name": app_id,
            "version": version,
            "run": {"entrypoint": "./start.sh", "args": []},
            "default_config": default_config,
            "config_schema": schema,
        }
        with connection_module.db_conn() as conn:
            conn.execute(
                """
                INSERT INTO app_installation (app_id, version, install_path, status, installed_at, manifest)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (app_id, version, str(version_dir), "installed", 1, json.dumps(manifest)),
            )
            conn.commit()
        self.config.init_app_config(app_id, version, default_config, overwrite_default=True)
        self.versioning.activate_version(app_id, version)

    def _write_sys_config(self, data):
        raw = {
            "_version": 1,
            "_updated_at": None,
            "_updated_by": "system",
        }
        raw.update(data)
        self.sys_path.write_text(
            yaml.dump(raw, default_flow_style=False, allow_unicode=True),
            "utf-8",
        )

    @staticmethod
    def _schema_for_sys_leaf(name, leaf_schema):
        return {
            "type": "object",
            "properties": {
                "sys": {
                    "type": "object",
                    "properties": {
                        name: leaf_schema,
                    },
                },
            },
        }


if __name__ == "__main__":
    unittest.main()
