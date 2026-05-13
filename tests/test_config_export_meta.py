import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from aivudaos.core.auth.models import SessionInfo
from aivudaos.core.config.models import VersionedConfig
from aivudaos.gateway.routes import config as config_routes


class _Auth:
    def validate_token(self, token):
        if token != "ok-token":
            raise config_routes.AuthenticationError("Invalid token")
        return SessionInfo(token=token, username="admin", role="admin", created_at=1)


class _Config:
    def get_os_config(self):
        return VersionedConfig(
            data={
                "avahi_hostname": "robot-abc",
                "runtime_process_manager": "auto",
            },
            version=1,
            updated_at=1,
            updated_by="system",
        )


class ConfigExportMetaTestCase(unittest.TestCase):
    def test_export_meta_requires_valid_token(self) -> None:
        with patch.object(config_routes, "get_auth_service", return_value=_Auth()):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(config_routes.get_config_export_meta(token="bad-token"))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_export_meta_returns_version_hostname_and_os_summary(self) -> None:
        with patch.object(config_routes, "get_auth_service", return_value=_Auth()), patch.object(
            config_routes,
            "get_config_service",
            return_value=_Config(),
        ):
            payload = asyncio.run(config_routes.get_config_export_meta(token="ok-token"))

        self.assertIn("aivudaos_version", payload)
        self.assertEqual(payload["avahi_hostname"], "robot-abc")
        self.assertIsInstance(payload["exported_at"], int)
        self.assertEqual(payload["os_parameters"]["count"], 2)
        self.assertEqual(
            payload["os_parameters"]["keys"],
            ["avahi_hostname", "runtime_process_manager"],
        )


if __name__ == "__main__":
    unittest.main()
