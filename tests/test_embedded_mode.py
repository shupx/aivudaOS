import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from aivudaos.core import paths
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
                    avahi.assert_not_called()
                    caddy.assert_not_called()
                finally:
                    for item in reversed(patches):
                        item.stop()

    def test_hostname_update_skips_side_effects_only_in_embedded_mode(self):
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
                with patch.dict(os.environ, {"AIVUDAOS_EMBEDDED_MODE": "0"}):
                    config_module.ConfigService(avahi, caddy).update_os_config({"avahi_hostname": "robot-next"}, 2, "admin")
                    avahi.write_and_restart.assert_called_once_with("robot-next")
                    caddy.sync_https_hostname.assert_called_once_with("robot-next")


if __name__ == "__main__":
    unittest.main()
