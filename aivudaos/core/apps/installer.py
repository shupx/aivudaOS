from __future__ import annotations

import json
import logging
import shutil
import tempfile
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, Iterator, Optional

import yaml

from aivudaos.core.apps import versioning as version_storage
from aivudaos.core.apps.caddy_config import CaddyConfigService
from aivudaos.core.apps.config_validation import validate_config_data
from aivudaos.core.apps.magnet import MagnetService
from aivudaos.core.apps.models import AppManifest
from aivudaos.core.apps.script_hooks import ScriptHookError, ScriptHookRunner
from aivudaos.core.apps.versioning import VersioningService
from aivudaos.core.config import service as config_storage
from aivudaos.core.config.filelock import rollback_config_writes_on_error
from aivudaos.core.config.service import ConfigService
from aivudaos.core.db.connection import db_conn
from aivudaos.core.errors import (
    InvalidConfigError,
    OperationCanceledError,
    PackageFormatError,
)
from aivudaos.core.paths import UPLOAD_TEMP_DIR


_install_lock = Lock()  # Magnet and Caddy publication are shared across apps.
_log = logging.getLogger(__name__)


def _require_component(value: Any, field: str) -> None:
    if (not isinstance(value, str) or not value.strip() or value in (".", "..")
            or "/" in value or "\\" in value or any(ord(c) < 32 for c in value)):
        raise PackageFormatError(f"Invalid {field}: expected a single path component")


def _require_managed_path(path: Path, root: Path) -> None:
    # Allow the configured root itself to be mounted/linked somewhere else,
    # but never replace another app's state via a symlink below that root.
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise PackageFormatError(f"Install path is outside its storage root: {path}") from exc
    current = root
    for part in relative.parts:
        current = current / part
        if part == ".." or current.is_symlink():
            raise PackageFormatError(f"Unsafe install path: {current}")


@contextmanager
def _replaceable_path(path: Path) -> Iterator[None]:
    """Move the old tree aside on its own filesystem until publication succeeds."""
    backup = None
    if path.is_symlink() or path.exists():
        backup = Path(tempfile.mkdtemp(prefix=".install-backup-", dir=str(path.parent))) / "old"
        try:
            path.rename(backup)
        except BaseException:
            backup.parent.rmdir()
            raise
    try:
        yield
    except BaseException:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.exists():
            shutil.rmtree(path)
        if backup is not None:
            backup.rename(path)
            backup.parent.rmdir()
        raise
    else:
        if backup is not None:
            try:
                shutil.rmtree(backup.parent)
            except OSError:
                # Publication succeeded. Keeping a backup is safer than falsely
                # reporting a failed installation after other backups are gone.
                _log.warning("Could not discard install backup %s", backup.parent, exc_info=True)


class InstallerService:
    """Manages app installation from local uploads."""

    def __init__(
        self,
        versioning: VersioningService,
        config_service: ConfigService,
        magnet_service: MagnetService,
    ) -> None:
        self._versioning = versioning
        self._config = config_service
        self._magnet = magnet_service
        self._script_hooks = ScriptHookRunner()
        self._caddy = CaddyConfigService(versioning=versioning)

    # ------------------------------------------------------------------ #
    #  Local upload install (primary flow)
    # ------------------------------------------------------------------ #

    def install_from_upload(
        self,
        file_data: bytes,
        filename: str,
        overwrite: bool = False,
        event_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        interactive: bool = False,
        read_input: Optional[Callable[[float], Optional[str]]] = None,
        cancel_requested: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
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
                        default_config_path: ./config/default_config.yaml
                        config_schema_path: ./config/config_schema.yaml
        """

        def emit(event_type: str, **payload: Any) -> None:
            if event_cb:
                event_cb(event_type, payload)

        def ensure_not_canceled() -> None:
            if cancel_requested and cancel_requested():
                raise OperationCanceledError("Installation canceled by user")

        _require_component(filename, "upload filename")
        UPLOAD_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        emit("status", phase="prepare", status="running", message="准备安装")

        with tempfile.TemporaryDirectory(dir=str(UPLOAD_TEMP_DIR)) as tmpdir_str:
            ensure_not_canceled()
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
            ensure_not_canceled()

            # Locate manifest.yaml
            manifest_path = self._find_manifest(extract_dir)
            if manifest_path is None:
                raise PackageFormatError("安装包缺少 manifest.yaml")

            manifest_raw = yaml.safe_load(manifest_path.read_text("utf-8"))
            if not isinstance(manifest_raw, dict):
                raise PackageFormatError("manifest.yaml 格式错误")

            app_id = manifest_raw.get("app_id")
            _require_component(app_id, "manifest.app_id")
            _require_component(manifest_raw.get("version"), "manifest.version")

            try:
                manifest = AppManifest.from_dict(app_id, manifest_raw)
            except ValueError as exc:
                raise PackageFormatError(str(exc)) from exc
            version = manifest.version

            content_root = manifest_path.parent
            self._load_and_validate_manifest_config(content_root, manifest)
            install_path = self._versioning.version_dir(app_id, version)

            runtime_path = self._versioning.version_runtime_data_dir(app_id, version)
            with _install_lock, self._caddy_publication() as publish_caddy, ExitStack() as changes:
                ensure_not_canceled()
                _require_managed_path(install_path, version_storage.APPS_DIR)
                _require_managed_path(runtime_path, version_storage.APP_RUNTIME_DATA_DIR)
                self._validate_config_paths(app_id, version)
                changes.enter_context(rollback_config_writes_on_error())
                existing_versions = self._versioning.list_versions(app_id)
                if (version in existing_versions) and (not overwrite):
                    raise PackageFormatError(
                        f"App version already installed: {app_id}@{version}"
                    )
                # Capture before overwrite hooks or activation change the source.
                source_version = version if version in existing_versions else self._versioning.active_version(app_id)
                source_data = {}
                if source_version:
                    if source_version != version:
                        _require_component(source_version, "active version")
                        self._validate_config_paths(app_id, source_version)
                    source_config = self._config.get_app_config(app_id, source_version)
                    source_data = source_config.data if source_config.version > 0 else self._config.get_app_default_config(app_id, source_version)
                emit(
                    "status",
                    phase="manifest",
                    status="running",
                    message="读取 manifest",
                    app_id=app_id,
                    version=version,
                )

                emit("status", phase="install", status="running", message="写入版本目录", app_id=app_id)
                changes.enter_context(_replaceable_path(install_path))
                changes.enter_context(_replaceable_path(runtime_path))
                self._versioning.prepare_version_dir(app_id, version)
                ensure_not_canceled()
                # Copy all files from package content root to final install path
                for item in content_root.iterdir():
                    ensure_not_canceled()
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
                                cancel_requested=cancel_requested,
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
                        if "已取消" in str(exc):
                            raise OperationCanceledError("Installation canceled by user") from exc
                        raise PackageFormatError(f"pre_install 执行失败: {exc}") from exc

                    self._load_and_validate_manifest_config(install_path, manifest)

                self._ensure_entrypoint_ready(install_path, manifest)
                try:
                    self._caddy.validate_candidate(app_id, manifest, install_path)
                except InvalidConfigError as exc:
                    raise PackageFormatError(str(exc)) from exc
                ensure_not_canceled()

                # Record in database
                changes.enter_context(self._record_installation(app_id, version, install_path, manifest))
                emit("status", phase="db", status="running", message="写入数据库", app_id=app_id)

                migration = self._config.migrate_app_config(
                    app_id, version, source_data, manifest.default_config,
                    manifest.config_schema, overwrite_default=True,
                )
                for warning in migration["config_migration_warnings"]:
                    emit("status", phase="config_migration", status="warning",
                         message="%s: %s (%s)" % (warning["path"], warning["reason"], warning["action"]),
                         app_id=app_id, warning=warning)
                ensure_not_canceled()

                # Activate this version
                changes.enter_context(self._versioning.activate_candidate(app_id, version))
                if migration["config_valid"]:
                    self._magnet.recompute(updated_by="system")
                try:
                    publish_caddy()
                except InvalidConfigError as exc:
                    raise PackageFormatError(str(exc)) from exc
                emit("status", phase="activate", status="running", message="激活版本", app_id=app_id)
                ensure_not_canceled()
                emit("status", phase="completed", status="completed", message="安装完成", app_id=app_id)

        return {
            "ok": True,
            "app_id": app_id,
            "name": manifest.name,
            "version": version,
            "install_path": str(install_path),
            **migration,
        }

    # ------------------------------------------------------------------ #
    #  Shared helpers
    # ------------------------------------------------------------------ #

    def _validate_config_paths(self, app_id: str, version: str) -> None:
        for path in (self._config.app_config_path(app_id, version),
                     self._config.app_default_config_path(app_id, version),
                     self._config.app_legacy_config_path(app_id, version)):
            _require_managed_path(path, config_storage.APP_CONFIG_DIR)

    @contextmanager
    def _caddy_publication(self) -> Iterator[Callable[[], None]]:
        attempted = False

        def publish() -> None:
            nonlocal attempted
            attempted = True
            self._caddy.sync_and_reload()

        try:
            yield publish
        except BaseException:
            # sync_and_reload can fail after replacing imports. Regenerate from
            # restored files, manifests and active links, not a stale global copy.
            if attempted:
                try:
                    self._caddy.sync_and_reload()
                except Exception:
                    _log.exception("Failed to reload restored Caddy configuration")
            raise

    @contextmanager
    def _record_installation(
        self,
        app_id: str,
        version: str,
        install_path: Path,
        manifest: AppManifest,
    ) -> Iterator[None]:
        """Publish the candidate manifest; undo just this row/placeholder on error."""
        now = int(time.time())
        manifest_json = json.dumps(manifest.to_dict(), ensure_ascii=False)
        with db_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            previous = conn.execute(
                "SELECT install_path, status, installed_at, manifest FROM app_installation "
                "WHERE app_id=? AND version=?", (app_id, version),
            ).fetchone()
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
            placeholder = conn.execute(
                "INSERT INTO app_runtime (app_id, running, autostart) "
                "VALUES (?, 0, 0) ON CONFLICT(app_id) DO NOTHING",
                (app_id,),
            )
            conn.commit()
        try:
            yield
        except BaseException:
            with db_conn() as conn:
                candidate = (app_id, version, str(install_path), now, manifest_json)
                where = "WHERE app_id=? AND version=? AND install_path=? AND installed_at=? AND manifest=? AND status='installed'"
                if previous is None:
                    conn.execute("DELETE FROM app_installation " + where, candidate)
                else:
                    conn.execute(
                        "UPDATE app_installation SET install_path=?, status=?, installed_at=?, manifest=? " + where,
                        tuple(previous) + candidate,
                    )
                if placeholder.rowcount:
                    conn.execute(
                        "DELETE FROM app_runtime WHERE app_id=? AND running=0 AND autostart=0 "
                        "AND pid IS NULL AND last_started_at IS NULL AND last_stopped_at IS NULL "
                        "AND NOT EXISTS (SELECT 1 FROM app_installation WHERE app_id=?)",
                        (app_id, app_id),
                    )
            raise

    @staticmethod
    def _find_manifest(extract_dir: Path) -> Optional[Path]:
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

    @staticmethod
    def _load_manifest_yaml_mapping(
        content_root: Path,
        relative_path: str,
        *,
        field_name: str,
    ) -> Dict[str, Any]:
        raw = str(relative_path or "").strip()
        if not raw:
            raise PackageFormatError(f"manifest 缺少 {field_name}")

        rel = Path(raw)
        if rel.is_absolute():
            raise PackageFormatError(f"{field_name} 必须是包内相对路径")

        resolved_root = content_root.resolve()
        resolved = (resolved_root / rel).resolve()
        if resolved_root != resolved and resolved_root not in resolved.parents:
            raise PackageFormatError(f"{field_name} 指向了安装包外部路径")
        if not resolved.exists() or not resolved.is_file():
            raise PackageFormatError(f"{field_name} 文件不存在: {raw}")

        try:
            parsed = yaml.safe_load(resolved.read_text("utf-8"))
        except Exception as exc:
            raise PackageFormatError(f"读取 {field_name} 失败: {exc}") from exc

        if parsed is None:
            return {}
        if not isinstance(parsed, dict):
            raise PackageFormatError(f"{field_name} 必须解析为 YAML object")
        return parsed

    def _load_and_validate_manifest_config(
        self,
        content_root: Path,
        manifest: AppManifest,
    ) -> None:
        manifest.config_schema = self._load_manifest_yaml_mapping(
            content_root,
            manifest.config_schema_path,
            field_name="config_schema_path",
        )
        manifest.default_config = self._load_manifest_yaml_mapping(
            content_root,
            manifest.default_config_path,
            field_name="default_config_path",
        )
        try:
            validate_config_data(
                manifest.default_config,
                manifest.config_schema,
                context=(
                    f"manifest {manifest.app_id}@{manifest.version} default_config"
                ),
            )
        except InvalidConfigError as exc:
            raise PackageFormatError(str(exc)) from exc
