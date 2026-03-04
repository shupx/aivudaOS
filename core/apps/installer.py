from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import yaml

from core.apps.models import AppManifest
from core.apps.script_hooks import ScriptHookError, ScriptHookRunner
from core.apps.versioning import VersioningService
from core.config.service import ConfigService
from core.db.connection import db_conn
from core.errors import (
    PackageFormatError,
)
from core.paths import UPLOAD_TEMP_DIR


class InstallerService:
    """Manages app installation from local uploads."""

    def __init__(
        self,
        versioning: VersioningService,
        config_service: ConfigService,
    ) -> None:
        self._versioning = versioning
        self._config = config_service
        self._script_hooks = ScriptHookRunner()

    # ------------------------------------------------------------------ #
    #  Local upload install (primary flow)
    # ------------------------------------------------------------------ #

    def install_from_upload(
        self,
        file_data: bytes,
        filename: str,
        overwrite: bool = False,
        event_cb: Callable[[str, dict[str, Any]], None] | None = None,
        interactive: bool = False,
        read_input: Callable[[float], str | None] | None = None,
    ) -> dict[str, Any]:
        """Install an app from an uploaded package file (.tar.gz / .zip).

        Package structure:
            manifest.yaml   — required, describes the app
            <other files>   — application files copied to version dir

        manifest.yaml format:
            app_id: my-app
            name: My App
            version: 1.0.0
            description: ...
            run:
              entrypoint: ./start.sh
              args: []
            default_config: {}
            config_schema: null
        """

        def emit(event_type: str, **payload: Any) -> None:
            if event_cb:
                event_cb(event_type, payload)

        UPLOAD_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        emit("status", phase="prepare", status="running", message="准备安装")

        with tempfile.TemporaryDirectory(dir=str(UPLOAD_TEMP_DIR)) as tmpdir_str:
            tmpdir = Path(tmpdir_str)
            pkg_file = tmpdir / filename
            pkg_file.write_bytes(file_data)

            # Extract archive
            extract_dir = tmpdir / "extracted"
            extract_dir.mkdir()
            emit("status", phase="extract", status="running", message="解压安装包")
            try:
                shutil.unpack_archive(str(pkg_file), str(extract_dir))
            except (shutil.ReadError, ValueError) as exc:
                raise PackageFormatError(
                    f"无法解压安装包 ({filename}): {exc}"
                ) from exc

            # Locate manifest.yaml
            manifest_path = self._find_manifest(extract_dir)
            if manifest_path is None:
                raise PackageFormatError("安装包缺少 manifest.yaml")

            manifest_raw = yaml.safe_load(manifest_path.read_text("utf-8"))
            if not isinstance(manifest_raw, dict):
                raise PackageFormatError("manifest.yaml 格式错误")

            app_id = manifest_raw.get("app_id")
            if not app_id:
                raise PackageFormatError("manifest.yaml 缺少 app_id")

            manifest = AppManifest.from_dict(app_id, manifest_raw)
            version = manifest.version

            existing_versions = self._versioning.list_versions(app_id)
            if (version in existing_versions) and (not overwrite):
                raise PackageFormatError(
                    f"App version already installed: {app_id}@{version}"
                )
            emit(
                "status",
                phase="manifest",
                status="running",
                message="读取 manifest",
                app_id=app_id,
                version=version,
            )

            content_root = manifest_path.parent

            # Prepare version directory first; this also handles overwrite case
            emit("status", phase="install", status="running", message="写入版本目录", app_id=app_id)
            install_path = self._versioning.prepare_version_dir(app_id, version)

            try:
                # Copy all files from package content root to final install path
                for item in content_root.iterdir():
                    dest = install_path / item.name
                    if item.is_dir():
                        shutil.copytree(str(item), str(dest))
                    else:
                        shutil.copy2(str(item), str(dest))

                # Run pre_install in final install directory so generated artifacts
                # (e.g. catkin devel/setup.bash) bind to stable absolute paths.
                if manifest.pre_install:
                    emit(
                        "status",
                        phase="pre_install",
                        status="running",
                        message="执行 pre_install",
                        app_id=app_id,
                    )
                    try:
                        if interactive:
                            self._script_hooks.run_interactive(
                                app_id=app_id,
                                hook_name="pre_install",
                                script_path=manifest.pre_install,
                                root_dir=install_path,
                                on_output=lambda chunk: emit(
                                    "log",
                                    phase="pre_install",
                                    hook="pre_install",
                                    chunk=chunk,
                                    app_id=app_id,
                                ),
                                read_input=read_input,
                            )
                        else:
                            self._script_hooks.run(
                                app_id=app_id,
                                hook_name="pre_install",
                                script_path=manifest.pre_install,
                                root_dir=install_path,
                                on_output=lambda line: emit(
                                    "log",
                                    phase="pre_install",
                                    hook="pre_install",
                                    line=line,
                                    app_id=app_id,
                                ),
                            )
                    except ScriptHookError as exc:
                        raise PackageFormatError(f"pre_install 执行失败: {exc}") from exc

                self._ensure_entrypoint_ready(install_path, manifest)

                # Record in database
                self._record_installation(app_id, version, install_path, manifest)
                emit("status", phase="db", status="running", message="写入数据库", app_id=app_id)

                # Initialize per-app config
                self._config.init_app_config(app_id, manifest.default_config)

                # Activate this version
                self._versioning.activate_version(app_id, version)
                emit("status", phase="activate", status="running", message="激活版本", app_id=app_id)
            except Exception:
                shutil.rmtree(install_path, ignore_errors=True)
                raise

        emit("status", phase="completed", status="completed", message="安装完成", app_id=app_id)

        return {
            "ok": True,
            "app_id": app_id,
            "name": manifest.name,
            "version": version,
            "install_path": str(install_path),
        }

    # ------------------------------------------------------------------ #
    #  Shared helpers
    # ------------------------------------------------------------------ #

    def _record_installation(
        self,
        app_id: str,
        version: str,
        install_path: Path,
        manifest: AppManifest,
    ) -> None:
        """Write installation record and runtime placeholder to DB."""
        now = int(time.time())
        manifest_json = json.dumps(manifest.to_dict(), ensure_ascii=False)
        with db_conn() as conn:
            conn.execute(
                "INSERT INTO app_installation "
                "(app_id, version, install_path, status, installed_at, manifest) "
                "VALUES (?, ?, ?, 'installed', ?, ?) "
                "ON CONFLICT(app_id, version) DO UPDATE SET "
                "install_path=excluded.install_path, "
                "status=excluded.status, installed_at=excluded.installed_at, "
                "manifest=excluded.manifest",
                (app_id, version, str(install_path), now, manifest_json),
            )
            conn.execute(
                "INSERT INTO app_runtime (app_id, running, autostart) "
                "VALUES (?, 0, 0) ON CONFLICT(app_id) DO NOTHING",
                (app_id,),
            )
            conn.commit()

    @staticmethod
    def _find_manifest(extract_dir: Path) -> Path | None:
        """Find manifest.yaml in extracted directory (root or one level deep)."""
        for name in ("manifest.yaml", "manifest.yml"):
            p = extract_dir / name
            if p.exists():
                return p
        # Check one subdirectory level (archives often wrap in a root folder)
        for subdir in extract_dir.iterdir():
            if subdir.is_dir():
                for name in ("manifest.yaml", "manifest.yml"):
                    p = subdir / name
                    if p.exists():
                        return p
        return None

    @staticmethod
    def _ensure_entrypoint_ready(install_path: Path, manifest: AppManifest) -> None:
        entrypoint = manifest.run.get("entrypoint")
        if not entrypoint:
            raise PackageFormatError("manifest.run.entrypoint 缺失")

        entry = Path(str(entrypoint))
        resolved = (
            (install_path / entry).resolve() if not entry.is_absolute() else entry
        )

        if not resolved.exists() or not resolved.is_file():
            raise PackageFormatError(
                f"entrypoint 不存在或不是文件: {entrypoint}"
            )

        try:
            mode = resolved.stat().st_mode
            resolved.chmod(mode | 0o111)
        except OSError as exc:
            raise PackageFormatError(
                f"设置 entrypoint 可执行权限失败: {exc}"
            ) from exc


