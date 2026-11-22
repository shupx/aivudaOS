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

        result = self.magnet.recompute(updated_by="test")

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
