import io
import asyncio
import json
import tempfile
import unittest
import zipfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

import aivudaos.core.apps.installer as installer_module
import aivudaos.core.apps.versioning as versioning_module
import aivudaos.core.config.service as config_module
import aivudaos.core.db.connection as connection_module
from aivudaos.core.apps.installer import InstallerService
from aivudaos.core.apps.magnet import MagnetService
import aivudaos.core.apps.magnet as magnet_module
from aivudaos.core.apps.runtime import RuntimeService
from aivudaos.core.apps.versioning import VersioningService
from aivudaos.core.config.app_migration import migrate_app_parameters
from aivudaos.core.config.service import ConfigService
from aivudaos.core.db.schema import init_db
from aivudaos.core.errors import AppRuntimeError


def object_schema(properties, **kwargs):
    return {"type": "object", "properties": properties, **kwargs}


class MigrationRulesTests(unittest.TestCase):
    def test_recursive_priority_new_fields_dynamic_keys_and_explicit_empty_values(self):
        schema = object_schema({
            "network": object_schema({"port": {"type": "integer", "maximum": 100}, "host": {"type": "string"}}),
            "enabled": {"type": "boolean"}, "name": {"type": "string"},
            "nullable": {"type": ["string", "null"]}, "count": {"type": "integer"},
        })
        source = {"network": {"port": 900, "host": "custom"}, "enabled": False,
                  "name": "", "nullable": None, "count": 0, "dynamic": {"user-key": 7}}
        target = {"network": {"port": 80}}
        defaults = {"network": {"port": 40, "host": "localhost"}, "new": 5}
        original = deepcopy((source, target, defaults))
        data, warnings, valid = migrate_app_parameters(source, target, defaults, schema)
        self.assertTrue(valid)
        self.assertEqual(data, {**source, "network": {"port": 80, "host": "custom"}, "new": 5})
        self.assertEqual([w["path"] for w in warnings], ["$.network.port"])
        self.assertEqual(warnings[0]["action"], "used_target")
        self.assertEqual((source, target, defaults), original)

    def test_all_incompatible_fields_warn_and_fall_back_independently(self):
        schema = object_schema({
            "port": {"type": "integer", "minimum": 1, "maximum": 100},
            "mode": {"enum": ["safe"]}, "name": {"type": "string", "pattern": "[a-z]+"},
            "items": {"type": "array", "minItems": 1, "items": {"type": "integer"}},
            "nested": object_schema({"keep": {"type": "integer"}}, additionalProperties=False),
        }, additionalProperties=False)
        source = {"port": "bad", "mode": "fast", "name": "UPPER", "items": [1, "bad"],
                  "nested": {"keep": 99, "gone": 1}, "removed": 2}
        defaults = {"port": 10, "mode": "safe", "name": "robot", "items": [2], "nested": {"keep": 1}}
        data, warnings, valid = migrate_app_parameters(source, {"port": 500}, defaults, schema)
        self.assertTrue(valid)
        self.assertEqual(data, {**defaults, "nested": {"keep": 99}})
        self.assertEqual({w["path"] for w in warnings},
                         {"$.port", "$.mode", "$.name", "$.items", "$.nested.gone", "$.removed"})
        self.assertEqual(len([w for w in warnings if w["path"] == "$.port"]), 2)

    def test_arrays_are_whole_and_empty_arrays_are_preserved(self):
        schema = object_schema({"items": {"type": "array", "items": {"type": "integer"}}})
        for value in ([], [5, 6]):
            data, warnings, valid = migrate_app_parameters({"items": value}, {"items": [3]}, {"items": [1]}, schema)
            self.assertEqual(data["items"], value)
            self.assertTrue(valid)
            self.assertFalse(warnings)

    def test_missing_required_fields_warn_without_losing_valid_siblings(self):
        schema = object_schema({"required": {"type": "integer"}, "keep": {"type": "integer"}}, required=["required"])
        data, warnings, valid = migrate_app_parameters({"required": "bad", "keep": 8}, {}, {}, schema)
        self.assertEqual(data, {"keep": 8})
        self.assertFalse(valid)
        self.assertEqual(warnings[-1]["action"], "requires_configuration")

    def test_object_enum_falls_back_as_one_value(self):
        schema = object_schema({"mode": {"type": "object", "enum": [{"choice": "safe"}]}})
        data, warnings, valid = migrate_app_parameters({"mode": {"choice": "fast"}}, {}, {"mode": {"choice": "safe"}}, schema)
        self.assertTrue(valid)
        self.assertEqual(data, {"mode": {"choice": "safe"}})
        self.assertEqual(warnings[0]["action"], "used_default")

    def test_missing_nested_required_preserves_all_other_fields(self):
        schema = object_schema({
            "nested": object_schema({"keep": {"type": "integer"}, "missing": {"type": "integer"}}, required=["missing"]),
            "sibling": {"type": "integer"},
        })
        source = {"nested": {"keep": 7, "missing": "bad"}, "sibling": 99}
        data, warnings, valid = migrate_app_parameters(source, {}, {}, schema)
        self.assertEqual(data, {"nested": {"keep": 7}, "sibling": 99})
        self.assertFalse(valid)
        self.assertTrue(any(w["path"] == "$.nested.missing" and w["action"] == "requires_configuration" for w in warnings))

    def test_invalid_container_falls_back_to_target_object(self):
        schema = object_schema({"nested": object_schema({"keep": {"type": "integer"}})})
        data, warnings, valid = migrate_app_parameters({"nested": "bad"}, {"nested": {"keep": 7}}, {"nested": {"keep": 1}}, schema)
        self.assertEqual(data, {"nested": {"keep": 7}})
        self.assertTrue(valid)
        self.assertEqual(warnings[0]["path"], "$.nested")


class MigrationFlowTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for module, name, value in [
            (config_module, "APP_CONFIG_DIR", self.root / "config/apps"),
            (connection_module, "DB_PATH", self.root / "db.sqlite"),
            (versioning_module, "APPS_DIR", self.root / "apps"),
            (versioning_module, "APP_RUNTIME_DATA_DIR", self.root / "runtime"),
            (installer_module, "UPLOAD_TEMP_DIR", self.root / "uploads"),
        ]:
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        init_db()
        self.config = ConfigService()
        self.versioning = VersioningService()
        self.magnet = Mock()
        self.installer = InstallerService(self.versioning, self.config, self.magnet)
        self.runtime = RuntimeService(self.versioning, self.config, self.magnet)
        self.installer._caddy = Mock()
        self.runtime._caddy = Mock()
        self.runtime.get_runtime_state = Mock(return_value=Mock(running=False))
        self.schema = object_schema({"port": {"type": "integer", "minimum": 1, "maximum": 100},
                                     "keep": {"type": "string"}}, additionalProperties=False)

    def package(self, version, defaults=None, schema=None):
        defaults = defaults if defaults is not None else {"port": 10, "keep": "default"}
        schema = schema if schema is not None else self.schema
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("manifest.yaml", yaml.safe_dump({
                "app_id": "demo", "version": version, "run": {"entrypoint": "start.sh"},
                "default_config_path": "defaults.yaml", "config_schema_path": "schema.yaml",
            }))
            archive.writestr("defaults.yaml", yaml.safe_dump(defaults))
            archive.writestr("schema.yaml", yaml.safe_dump(schema))
            archive.writestr("start.sh", "#!/bin/sh\nexit 0\n")
        return output.getvalue()

    def install(self, version, **kwargs):
        return self.installer.install_from_upload(self.package(version), "demo.zip", **kwargs)

    def update(self, version, data):
        cfg = self.config.get_app_config("demo", version)
        return self.config.update_app_config("demo", version, data, cfg.version)

    def test_install_upgrade_and_switch_back_inherit_current_values(self):
        first = self.install("1")
        self.assertTrue(first["config_valid"])
        self.assertFalse(first["config_migration_warnings"])
        self.update("1", {"port": 80, "keep": "custom"})
        old_file = self.config.app_config_path("demo", "1").read_bytes()
        result = self.install("2")
        self.assertTrue(result["ok"])
        self.assertEqual(self.config.get_app_config("demo", "2").data, {"port": 80, "keep": "custom"})
        self.assertEqual(self.config.app_config_path("demo", "1").read_bytes(), old_file)
        self.update("2", {"port": 90, "keep": "new"})
        source_file = self.config.app_config_path("demo", "2").read_bytes()
        result = self.runtime.switch_version("demo", "1")
        self.assertEqual(result["active_version"], "1")
        self.assertEqual(self.config.get_app_config("demo", "1").data, {"port": 90, "keep": "new"})
        self.assertEqual(self.config.app_config_path("demo", "2").read_bytes(), source_file)
        self.assertEqual(self.config.app_default_config_path("demo", "1").name, "1_default.yaml")

    def test_switch_uses_target_then_default_and_warns(self):
        self.install("1")
        self.update("1", {"port": 60, "keep": "target"})
        self.install("2")
        self.update("2", {"port": 1000, "keep": "source", "removed": 7})
        source_file = self.config.app_config_path("demo", "2").read_bytes()
        self.runtime.get_runtime_state.return_value.running = True
        self.runtime.stop = Mock()
        self.runtime.start = Mock()
        result = self.runtime.switch_version("demo", "1", restart=True)
        self.assertTrue(result["config_valid"])
        self.assertEqual(self.config.get_app_config("demo", "1").data, {"port": 60, "keep": "source"})
        self.assertEqual({w["path"] for w in result["config_migration_warnings"]}, {"$.port", "$.removed"})
        self.runtime.stop.assert_called_once_with("demo")
        self.runtime.start.assert_called_once_with("demo")
        self.assertEqual(self.config.app_config_path("demo", "2").read_bytes(), source_file)

    def test_overwrite_nonactive_version_uses_its_own_parameters(self):
        self.install("1")
        self.update("1", {"port": 70, "keep": "own"})
        self.install("2")
        self.update("2", {"port": 80, "keep": "active"})
        self.update("1", {"port": 1000, "keep": "own", "removed": 1})
        events = []
        result = self.install("1", overwrite=True, event_cb=lambda kind, payload: events.append((kind, payload)))
        self.assertEqual(self.config.get_app_config("demo", "1").data, {"port": 10, "keep": "own"})
        self.assertTrue(result["config_migration_warnings"])
        self.assertTrue(any(payload.get("status") == "warning" for _, payload in events))
        self.assertEqual(self.config.get_app_config("demo", "2").data, {"port": 80, "keep": "active"})

    def test_overwrite_active_version_adapts_changed_schema_and_defaults(self):
        self.install("1")
        self.update("1", {"port": 80, "keep": "user"})
        schema = object_schema({"port": {"type": "string"}, "keep": {"type": "string"}, "added": {"type": "boolean"}}, additionalProperties=False)
        defaults = {"port": "new-default", "keep": "changed", "added": True}
        result = self.installer.install_from_upload(self.package("1", defaults, schema), "demo.zip", overwrite=True)
        self.assertEqual(self.config.get_app_config("demo", "1").data, {**defaults, "keep": "user"})
        self.assertEqual(self.config.get_app_default_config("demo", "1"), defaults)
        self.assertTrue(result["config_valid"])
        self.assertEqual(result["config_migration_warnings"][0]["path"], "$.port")

    def test_missing_required_configuration_allows_switch_but_not_restart(self):
        self.install("1")
        self.install("2")
        # Simulate an installed legacy version whose schema now requires input.
        with connection_module.db_conn() as conn:
            manifest = json.loads(conn.execute("SELECT manifest FROM app_installation WHERE version='1'").fetchone()[0])
            manifest["config_schema"]["required"] = ["missing"]
            manifest["config_schema"]["properties"]["missing"] = {"type": "string"}
            conn.execute("UPDATE app_installation SET manifest=? WHERE version='1'", (json.dumps(manifest),))
            conn.commit()
        self.runtime.get_runtime_state.return_value.running = True
        self.runtime.stop = Mock()
        self.runtime.start = Mock()
        result = self.runtime.switch_version("demo", "1", restart=True)
        self.assertTrue(result["ok"])
        self.assertFalse(result["config_valid"])
        self.assertEqual(self.versioning.active_version("demo"), "1")
        self.runtime.stop.assert_called_once()
        self.runtime.start.assert_not_called()
        with self.assertRaises(AppRuntimeError):
            self.runtime._ensure_version_config_ready("demo", "1", self.runtime._get_manifest("demo", "1"))

    def test_magnet_old_value_cannot_abort_migration_to_narrower_schema(self):
        with patch.object(config_module, "SYS_CONFIG_PATH", self.root / "sys.yaml"), \
                patch.object(magnet_module, "MAGNET_CONFIG_PATH", self.root / "magnets.yaml"):
            magnet = MagnetService(self.config, self.versioning)
            self.installer._magnet = magnet
            self.runtime._magnet = magnet
            def schema(maximum):
                return object_schema({"sys": object_schema({"port": {"type": "integer", "maximum": maximum}})})
            self.installer.install_from_upload(self.package("1", {"sys": {"port": 900}}, schema(1000)), "demo.zip")
            result = self.installer.install_from_upload(self.package("2", {"sys": {"port": 10}}, schema(100)), "demo.zip")
            self.assertTrue(result["ok"])
            self.assertTrue(result["config_valid"])
            self.assertTrue(result["config_migration_warnings"])
            self.assertEqual(self.config.get_app_config("demo", "2").data["sys"]["port"], 10)
            self.assertTrue(magnet.list_groups()["conflicts"])

    def test_upgrade_api_returns_warnings_and_restarts_with_valid_configuration(self):
        from fastapi import UploadFile
        from aivudaos.gateway.routes import apps as routes
        self.install("1")
        self.update("1", {"port": 1000, "keep": "user"})
        runtime = Mock()
        runtime.get_runtime_state.return_value.running = True
        with patch.object(routes, "_require_auth"), \
                patch.object(routes, "get_installer_service", return_value=self.installer), \
                patch.object(routes, "get_runtime_service", return_value=runtime):
            result = asyncio.run(routes.upgrade_app("demo", UploadFile(filename="demo.zip", file=io.BytesIO(self.package("2"))), "token"))
        self.assertTrue(result["upgraded"])
        self.assertTrue(result["restarted"])
        self.assertTrue(result["config_migration_warnings"])
        runtime.restart.assert_called_once_with("demo")
        self.assertEqual(self.config.get_app_config("demo", "2").data, {"port": 10, "keep": "user"})

    def test_switch_api_returns_migration_warning_details(self):
        from aivudaos.gateway.routes import apps as routes
        from aivudaos.gateway.schemas import AppSwitchVersionRequest
        self.install("1")
        self.install("2")
        self.update("2", {"port": 1000, "keep": "user"})
        with patch.object(routes, "_require_auth"), patch.object(routes, "get_runtime_service", return_value=self.runtime):
            result = asyncio.run(routes.switch_version("demo", AppSwitchVersionRequest(version="1", restart=False), "token"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["config_migration_warnings"][0]["action"], "used_target")

    def test_caddy_rejection_does_not_modify_target_parameters(self):
        from aivudaos.core.errors import InvalidConfigError
        self.install("1")
        self.install("2")
        self.update("2", {"port": 90, "keep": "source"})
        target = self.config.app_config_path("demo", "1").read_bytes()
        self.runtime._caddy.validate_candidate.side_effect = InvalidConfigError("Rejected route")
        with self.assertRaises(AppRuntimeError):
            self.runtime.switch_version("demo", "1")
        self.assertEqual(self.config.app_config_path("demo", "1").read_bytes(), target)
        self.assertEqual(self.versioning.active_version("demo"), "2")

    def test_legacy_config_is_migrated_with_no_directory_layout_change(self):
        legacy = self.config.app_legacy_config_path("demo", "1")
        legacy.parent.mkdir(parents=True)
        legacy.write_text(yaml.safe_dump({"_version": 4, "port": 30, "keep": "legacy"}))
        self.install("1")
        self.assertEqual(self.config.get_app_config("demo", "1").data, {"port": 30, "keep": "legacy"})
        files = {str(p.relative_to(self.root / "config/apps")) for p in (self.root / "config/apps").rglob("*.yaml")}
        self.assertEqual(files, {"demo/1.yaml", "demo/1/1.yaml", "demo/1/1_default.yaml"})

    def test_missing_source_file_inherits_effective_source_defaults(self):
        self.installer.install_from_upload(self.package("1", {"port": 75, "keep": "source-default"}), "demo.zip")
        self.config.app_config_path("demo", "1").unlink()
        self.install("2")
        self.assertEqual(self.config.get_app_config("demo", "2").data, {"port": 75, "keep": "source-default"})

    def test_repeat_switch_same_version_does_not_rewrite_unchanged_config(self):
        self.install("1")
        before = self.config.app_config_path("demo", "1").read_bytes()
        self.runtime.switch_version("demo", "1")
        self.assertEqual(self.config.app_config_path("demo", "1").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
