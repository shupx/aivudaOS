import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import yaml

from aivudaos.core import paths
from aivudaos.core.apps import caddy_config as app_caddy_module
from aivudaos.core.config import service as config_module


class EmbeddedModeTests(unittest.TestCase):
    def test_environment_parsing(self):
        for value in ("1", "true", "YES", "on"):
            with patch.dict(os.environ, {"AIVUDAOS_EMBEDDED_MODE": value}):
                self.assertTrue(paths.embedded_mode())
        for value in ("", "0", "false", "off"):
            with patch.dict(os.environ, {"AIVUDAOS_EMBEDDED_MODE": value}):
                self.assertFalse(paths.embedded_mode())

    def test_embedded_bootstrap_does_not_touch_avahi_or_https_caddy(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / "config"
            config.mkdir()
            caddyfile = config / "Caddyfile"
            caddyfile.write_text("https://manager.local {\n}\n")
            patches = [
                patch.object(paths, "OS_CONFIG_PATH", config / "os.yaml"),
                patch.object(paths, "SYS_CONFIG_PATH", config / "sys.yaml"),
                patch.object(paths, "USERS_CONFIG_PATH", config / "users.yaml"),
                patch.object(paths, "MAGNET_CONFIG_PATH", config / "magnets.yaml"),
                patch.object(paths, "CADDYFILE_PATH", config / "Caddyfile"),
            ]
            with patch.dict(os.environ, {"AIVUDAOS_EMBEDDED_MODE": "1"}), patch.object(paths, "AvahiService") as avahi, patch("aivudaos.core.config.caddy_runtime.CaddyRuntimeService") as caddy:
                for item in patches:
                    item.start()
                try:
                    paths._ensure_default_runtime_files()
                    self.assertEqual(yaml.safe_load((config / "os.yaml").read_text())["avahi_hostname"], "aceswarm")
                    self.assertEqual(caddyfile.read_text(), "https://manager.local {\n}\n")
                    avahi.assert_not_called()
                    caddy.assert_not_called()
                finally:
                    for item in reversed(patches):
                        item.stop()

    def test_standalone_bootstrap_keeps_avahi_and_https_caddy_behavior(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / "config"
            config.mkdir()
            patches = [
                patch.object(paths, "OS_CONFIG_PATH", config / "os.yaml"),
                patch.object(paths, "SYS_CONFIG_PATH", config / "sys.yaml"),
                patch.object(paths, "USERS_CONFIG_PATH", config / "users.yaml"),
                patch.object(paths, "MAGNET_CONFIG_PATH", config / "magnets.yaml"),
                patch.object(paths, "CADDYFILE_PATH", config / "Caddyfile"),
            ]
            with patch.dict(os.environ, {"AIVUDAOS_EMBEDDED_MODE": "0"}), patch.object(paths, "AvahiService") as avahi, patch("aivudaos.core.config.caddy_runtime.CaddyRuntimeService") as caddy:
                avahi.return_value.generate_hostname.return_value = "robot-abc"
                caddy.return_value.sync_https_hostname.return_value = True
                for item in patches:
                    item.start()
                try:
                    paths._ensure_default_runtime_files()
                    avahi.assert_called_once_with()
                    avahi.return_value.write_and_restart.assert_called_once_with("robot-abc")
                    caddy.assert_called_once_with()
                    caddy.return_value.sync_https_hostname.assert_called_once_with("robot-abc")
                    caddy.return_value.reload_if_running.assert_called_once_with()
                finally:
                    for item in reversed(patches):
                        item.stop()

    def test_embedded_hostname_update_skips_avahi_and_https_caddy_side_effects(self):
        with tempfile.TemporaryDirectory() as root:
            os_config = Path(root) / "os.yaml"
            os_config.write_text(yaml.safe_dump({"_version": 1, "avahi_hostname": "robot-old"}))
            avahi = Mock()
            avahi.normalize_hostname.side_effect = lambda value: value.strip().lower()
            caddy = Mock()
            with patch.object(config_module, "OS_CONFIG_PATH", os_config):
                with patch.dict(os.environ, {"AIVUDAOS_EMBEDDED_MODE": "1"}):
                    config_module.ConfigService(avahi, caddy).update_os_config({"avahi_hostname": "robot-new"}, 1, "admin")
                    avahi.write_and_restart.assert_not_called()
                    caddy.sync_https_hostname.assert_not_called()
                    caddy.reload_if_running.assert_not_called()

    def test_standalone_hostname_update_keeps_avahi_and_https_caddy_side_effects(self):
        with tempfile.TemporaryDirectory() as root:
            os_config = Path(root) / "os.yaml"
            os_config.write_text(yaml.safe_dump({"_version": 1, "avahi_hostname": "robot-old"}))
            avahi = Mock()
            avahi.normalize_hostname.side_effect = lambda value: value.strip().lower()
            caddy = Mock()
            caddy.sync_https_hostname.return_value = True
            with patch.object(config_module, "OS_CONFIG_PATH", os_config):
                with patch.dict(os.environ, {"AIVUDAOS_EMBEDDED_MODE": "0"}):
                    config_module.ConfigService(avahi, caddy).update_os_config({"avahi_hostname": "robot-next"}, 1, "admin")
                    avahi.write_and_restart.assert_called_once_with("robot-next")
                    caddy.sync_https_hostname.assert_called_once_with("robot-next")
                    caddy.reload_if_running.assert_called_once_with()

    def test_embedded_app_routes_still_generate_and_reload(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root)
            caddyfile = workspace / "Caddyfile"
            caddyfile.write_text("# BEGIN AIVUDA APP IMPORTS\n# END AIVUDA APP IMPORTS\n")
            caddy_bin = workspace / "caddy"
            caddy_bin.write_text("")
            caddy_bin.chmod(0o755)
            install_path = workspace / "app"
            ui_root = install_path / "dist"
            ui_root.mkdir(parents=True)
            (ui_root / "index.html").write_text("<html></html>")
            custom_route = install_path / "custom.caddy"
            custom_route.write_text("handle /custom/* {\n}\n")
            manifest = SimpleNamespace(ui_index_path="dist/index.html")
            service = app_caddy_module.CaddyConfigService(versioning=Mock())
            active_config = app_caddy_module._ActiveCaddyConfig(
                app_id="example", config_path=custom_route, routes={"/custom/*"}
            )
            with patch.dict(os.environ, {"AIVUDAOS_EMBEDDED_MODE": "1"}), \
                    patch.object(app_caddy_module, "CADDYFILE_PATH", caddyfile), \
                    patch.object(app_caddy_module, "CADDY_BIN_PATH", caddy_bin), \
                    patch.object(app_caddy_module, "APP_CADDY_GEN_DIR", workspace / "generated"), \
                    patch.object(service, "_collect_active_configs", return_value=[active_config]), \
                    patch.object(service, "_iter_active_manifests", return_value=[("example", manifest, install_path)]), \
                    patch.object(app_caddy_module.subprocess, "run") as reload_caddy:
                reload_caddy.return_value.returncode = 0
                service.sync_and_reload()

            ui_caddy = workspace / "generated" / "example.ui.caddy"
            self.assertIn("/example/ui", ui_caddy.read_text())
            self.assertIn(str(custom_route), caddyfile.read_text())
            self.assertIn(str(ui_caddy), caddyfile.read_text())
            reload_caddy.assert_called_once_with(
                [str(caddy_bin), "reload", "--config", str(caddyfile)],
                capture_output=True, text=True, check=False,
            )


if __name__ == "__main__":
    unittest.main()
