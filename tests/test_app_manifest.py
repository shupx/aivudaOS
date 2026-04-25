import unittest

from aivudaos.core.apps.models import AppManifest, UI_MOUNT_TYPE_QIANKUN


class AppManifestTestCase(unittest.TestCase):
    def test_accepts_supported_ui_mount_type(self) -> None:
        manifest = AppManifest.from_dict(
            "panel-app",
            {
                "app_id": "panel-app",
                "name": "Panel App",
                "version": "1.0.0",
                "run": {"entrypoint": "./start.sh", "args": []},
                "ui_index_path": "ui/index.html",
                "ui_mount_type": UI_MOUNT_TYPE_QIANKUN,
            },
        )

        self.assertEqual(manifest.ui_mount_type, UI_MOUNT_TYPE_QIANKUN)
        self.assertTrue(manifest.is_panelhub_mountable(True))
        self.assertFalse(manifest.is_panelhub_mountable(False))
        self.assertEqual(manifest.to_dict()["ui_mount_type"], UI_MOUNT_TYPE_QIANKUN)

    def test_builtin_ui_without_mount_type_is_not_panelhub_mountable(self) -> None:
        manifest = AppManifest.from_dict(
            "plain-ui-app",
            {
                "app_id": "plain-ui-app",
                "name": "Plain UI App",
                "version": "1.0.0",
                "run": {"entrypoint": "./start.sh", "args": []},
                "ui_index_path": "ui/index.html",
            },
        )

        self.assertFalse(manifest.is_panelhub_mountable(True))

    def test_invalid_ui_mount_type_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "manifest.ui_mount_type"):
            AppManifest.from_dict(
                "bad-app",
                {
                    "app_id": "bad-app",
                    "name": "Bad App",
                    "version": "1.0.0",
                    "run": {"entrypoint": "./start.sh", "args": []},
                    "ui_mount_type": "iframe",
                },
            )


if __name__ == "__main__":
    unittest.main()
