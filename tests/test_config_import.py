import asyncio
import hashlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx

from aivudaos.core.config import import_service
from aivudaos.core.errors import AuthenticationError
from aivudaos.gateway.main import create_app


class ConfigImportTests(unittest.TestCase):
    def setUp(self):
        self.document = {
            "format_version": 1,
            "human_header": {"avahi_hostname": "other-machine"},
            "payload": {
                "system_parameters": {"avahi_hostname": "other-machine", "feature": True},
                "apps": [{"app_id": "demo", "version": "1.0.0", "parameters": {"port": 42},
                          "autostart": True, "running": True}],
            },
        }
        self.store = "http://127.0.0.1:9999/"

    def test_validation_rejects_bad_format_identity_and_remote_store(self):
        for key, value in (("format_version", True), ("format_version", 2)):
            document = dict(self.document, **{key: value})
            with self.assertRaises(ValueError):
                import_service.validate_import(document, self.store)
        self.document["payload"]["apps"][0]["app_id"] = "../escape"
        with self.assertRaises(ValueError):
            import_service.validate_import(self.document, self.store)
        self.document["payload"]["apps"][0]["app_id"] = "demo"
        self.document["payload"]["apps"][0]["version"] = "../bad"
        with self.assertRaises(ValueError):
            import_service.validate_import(self.document, self.store)
        self.document["payload"]["apps"][0]["version"] = "1.0.0"
        with self.assertRaises(ValueError):
            import_service.validate_import(self.document, "http://example.com/")

    def test_installs_verified_package_and_applies_config_without_running(self):
        package = b"archive"
        info = {"url": "/aivuda_app_store/files/apps/demo/1.0.0/package.zip",
                "size": len(package), "sha256": hashlib.sha256(package).hexdigest(),
                "filename": "demo-1.0.0.zip"}
        versioning = Mock()
        versioning.list_versions.return_value = []
        config = Mock()
        config.get_sys_config.return_value = SimpleNamespace(data={"other": 1, "avahi_hostname": "local"}, version=1)
        config.get_app_config.return_value = SimpleNamespace(data={"port": 1}, version=3)
        config.get_app_default_config.return_value = {"port": 1}
        installer = Mock()
        installer.install_from_upload.return_value = {"app_id": "demo", "version": "1.0.0"}
        async def put_sys(payload, token):
            self.assertEqual(payload.data, {"other": 1, "avahi_hostname": "local", "feature": True})
        async def put_app(app_id, payload, token):
            self.assertEqual((app_id, payload.version, payload.data), ("demo", 3, {"port": 42}))
        events = []
        with patch.object(import_service, "get_versioning_service", return_value=versioning), \
                patch.object(import_service, "get_config_service", return_value=config), \
                patch.object(import_service, "get_installer_service", return_value=installer), \
                patch.object(import_service, "get_runtime_service") as runtime, \
                patch.object(import_service, "get_magnet_service"), \
                patch.object(import_service, "_store_get", side_effect=[json.dumps(info).encode(), package]), \
                patch.object(import_service, "put_config", side_effect=put_sys), \
                patch.object(import_service, "put_app_config", side_effect=put_app):
            payload = import_service.validate_import(self.document, self.store)
            result = import_service.apply_import(payload, self.store, "token", lambda *args: events.append(args))
            self.assertEqual(result["installed"], ["demo"])
            self.assertEqual(result["configured"], ["demo"])
            self.assertEqual(runtime.return_value.set_autostart.call_args.args, ("demo", True))
            runtime.return_value.start.assert_not_called()
            runtime.return_value.stop.assert_not_called()
            installer.install_from_upload.assert_called_once_with(package, "demo-1.0.0.zip", overwrite=False)
            self.assertEqual([item[0] for item in events], ["download", "install", "system", "configure", "autostart"])

    def test_existing_version_does_not_download_or_rewrite_unchanged_config(self):
        versioning = Mock()
        versioning.list_versions.return_value = ["1.0.0"]
        versioning.active_version.return_value = "1.0.0"
        config = Mock()
        config.get_sys_config.return_value = SimpleNamespace(data={"feature": True}, version=2)
        config.get_app_config.return_value = SimpleNamespace(data={"port": 42}, version=2)
        config.get_app_default_config.return_value = {"port": 1}
        with patch.object(import_service, "get_versioning_service", return_value=versioning), \
                patch.object(import_service, "get_config_service", return_value=config), \
                patch.object(import_service, "get_runtime_service"), \
                patch.object(import_service, "get_magnet_service"), \
                patch.object(import_service, "get_installer_service") as installer, \
                patch.object(import_service, "_store_get") as download, \
                patch.object(import_service, "put_config") as put_sys, \
                patch.object(import_service, "put_app_config") as put_app:
            result = import_service.apply_import(self.document["payload"], self.store, "token", lambda *args: None)
            self.assertEqual(result["installed"], [])
            download.assert_not_called()
            installer.assert_not_called()
            put_sys.assert_not_called()
            put_app.assert_not_called()

    def test_bad_download_checksum_never_installs(self):
        versioning = Mock()
        versioning.list_versions.return_value = []
        info = {"url": "/aivuda_app_store/files/apps/demo/1.0.0/package.zip",
                "size": 3, "sha256": "0" * 64, "filename": "demo.zip"}
        with patch.object(import_service, "get_versioning_service", return_value=versioning), \
                patch.object(import_service, "get_config_service"), \
                patch.object(import_service, "get_installer_service") as installer, \
                patch.object(import_service, "_store_get", side_effect=[json.dumps(info).encode(), b"abc"]):
            with self.assertRaisesRegex(ValueError, "checksum"):
                import_service.apply_import(self.document["payload"], self.store, "token", lambda *args: None)
            installer.assert_not_called()

    def test_http_auth_validation_and_queued_result(self):
        from aivudaos.gateway.routes import config as config_route
        from aivudaos.gateway import deps
        manager = deps.get_app_operation_manager()
        async def call_api():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://test") as client:
                path = "/aivuda_os/api/config/import?token=secret"
                with patch.object(config_route, "get_auth_service") as auth:
                    auth.return_value.validate_token.side_effect = AuthenticationError("invalid")
                    self.assertEqual((await client.post(path, json={"document": self.document, "app_store_base_url": self.store})).status_code, 401)
                    auth.return_value.validate_token.side_effect = None
                    auth.return_value.validate_token.return_value = SimpleNamespace(username="admin")
                    bad = await client.post(path, json={"document": self.document, "app_store_base_url": "http://external.invalid/"})
                    self.assertEqual(bad.status_code, 400)
                    with patch.object(import_service, "apply_import", return_value={"configured": ["demo"]}):
                        response = await client.post(path, json={"document": self.document, "app_store_base_url": self.store})
                        for _ in range(100):
                            record = manager.get_operation(response.json()["operation_id"])
                            if record["done"]:
                                break
                            await asyncio.sleep(0.01)
                    self.assertEqual(response.status_code, 202)
                    self.assertEqual(record["status"], "completed")
                    self.assertEqual(record["result"]["configured"], ["demo"])
        asyncio.run(call_api())
