from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import yaml

from core.apps.models import AppManifest
from core.apps.versioning import VersioningService
from core.config.service import ConfigService
from core.db.connection import db_conn
from core.errors import (
    ArtifactVerificationError,
    InstallTaskConflictError,
    NotFoundError,
    PackageFormatError,
)
from core.paths import ARTIFACT_CACHE_DIR, UPLOAD_TEMP_DIR


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _download_to_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as resp, dest.open("wb") as out:
        shutil.copyfileobj(resp, out)


def _run_cmd(
    args: list[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


class InstallerService:
    """Manages app installation from local uploads and remote catalog."""

    def __init__(
        self,
        versioning: VersioningService,
        config_service: ConfigService,
        catalog: Any | None = None,
    ) -> None:
        self._versioning = versioning
        self._config = config_service
        self._catalog = catalog  # Optional: only needed for remote installs

    # ------------------------------------------------------------------ #
    #  Local upload install (primary flow)
    # ------------------------------------------------------------------ #

    def install_from_upload(self, file_data: bytes, filename: str) -> dict[str, Any]:
        """Install an app from an uploaded package file (.tar.gz / .zip).

        Package structure:
            manifest.yaml   — required, describes the app
            <other files>   — application files copied to version dir

        manifest.yaml format:
            app_id: my-app
            name: My App
            version: 1.0.0
            description: ...
            runtime: host          # host | docker | podman
            run:
              entrypoint: ./start.sh
              args: []
            install: {}
            default_config: {}
            config_schema: null
        """
        UPLOAD_TEMP_DIR.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=str(UPLOAD_TEMP_DIR)) as tmpdir_str:
            tmpdir = Path(tmpdir_str)
            pkg_file = tmpdir / filename
            pkg_file.write_bytes(file_data)

            # Extract archive
            extract_dir = tmpdir / "extracted"
            extract_dir.mkdir()
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
            runtime = manifest.runtime

            # Conflict check
            with db_conn() as conn:
                running = conn.execute(
                    "SELECT task_id FROM app_task WHERE app_id = ? "
                    "AND task_type = 'install' AND status = 'running'",
                    (app_id,),
                ).fetchone()
                if running:
                    raise InstallTaskConflictError(
                        f"App {app_id} 正在安装中"
                    )

            # Prepare version directory
            install_path = self._versioning.prepare_version_dir(app_id, version)

            # Copy all files from content root to install path
            content_root = manifest_path.parent
            for item in content_root.iterdir():
                dest = install_path / item.name
                if item.is_dir():
                    shutil.copytree(str(item), str(dest))
                else:
                    shutil.copy2(str(item), str(dest))

            # For container runtime, pull image if specified
            if runtime in {"docker", "podman"}:
                image = manifest.install.get("image")
                if image:
                    rt_path = shutil.which(runtime)
                    if rt_path:
                        _run_cmd([rt_path, "pull", image])

            # Record in database
            self._record_installation(app_id, version, runtime, install_path, manifest)

            # Initialize per-app config
            self._config.init_app_config(app_id, manifest.default_config)

            # Activate this version
            self._versioning.activate_version(app_id, version)

        return {
            "ok": True,
            "app_id": app_id,
            "name": manifest.name,
            "version": version,
            "runtime": runtime,
            "install_path": str(install_path),
        }

    # ------------------------------------------------------------------ #
    #  Remote catalog install (secondary flow, requires catalog)
    # ------------------------------------------------------------------ #

    def create_install_task(
        self, app_id: str, install_runtime: bool = False
    ) -> dict[str, Any]:
        """Create a task record and launch the async install from catalog."""
        if self._catalog is None:
            raise RuntimeError("远端仓库未配置，请使用本地上传安装")

        manifest = self._catalog.get_manifest(app_id)

        with db_conn() as conn:
            running = conn.execute(
                "SELECT task_id FROM app_task WHERE app_id = ? "
                "AND task_type = 'install' AND status = 'running'",
                (app_id,),
            ).fetchone()
            if running:
                raise InstallTaskConflictError(
                    f"Install task already running for {app_id}"
                )

            task_id = str(uuid.uuid4())
            now = int(time.time())
            conn.execute(
                "INSERT INTO app_task "
                "(task_id, app_id, task_type, status, progress, message, error, created_at, updated_at) "
                "VALUES (?, ?, 'install', 'pending', 0, '等待执行', NULL, ?, ?)",
                (task_id, app_id, now, now),
            )
            conn.commit()

        asyncio.create_task(
            self._run_install(task_id, app_id, manifest, install_runtime)
        )
        return {"task_id": task_id}

    def get_task(self, task_id: str) -> dict[str, Any]:
        with db_conn() as conn:
            row = conn.execute(
                "SELECT * FROM app_task WHERE task_id = ?", (task_id,)
            ).fetchone()
        if not row:
            raise NotFoundError(f"Task {task_id} not found")
        return dict(row)

    def list_tasks(self, app_id: str | None = None) -> list[dict[str, Any]]:
        """List install tasks, optionally filtered by app_id."""
        with db_conn() as conn:
            if app_id:
                rows = conn.execute(
                    "SELECT * FROM app_task WHERE app_id = ? ORDER BY created_at DESC",
                    (app_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM app_task ORDER BY created_at DESC"
                ).fetchall()
        return [dict(r) for r in rows]

    async def _run_install(
        self,
        task_id: str,
        app_id: str,
        manifest: AppManifest,
        install_runtime: bool,
    ) -> None:
        try:
            version = manifest.version
            runtime = manifest.runtime

            self._set_task(task_id, "running", 10, "准备安装目录")
            install_path = self._versioning.prepare_version_dir(app_id, version)
            await asyncio.sleep(0.2)

            self._set_task(task_id, "running", 30, "下载资源包")
            await asyncio.sleep(0.2)

            if runtime in {"docker", "podman"}:
                self._install_container(
                    task_id, manifest, install_runtime, runtime
                )
            else:
                self._set_task(task_id, "running", 75, "下载并解压应用包")
                self._prepare_host_artifact(manifest, install_path)

            self._set_task(task_id, "running", 85, "写入应用配置与运行参数")

            # Record in database (with manifest)
            self._record_installation(app_id, version, runtime, install_path, manifest)

            # Initialize per-app config file
            self._config.init_app_config(app_id, manifest.default_config)

            # Activate this version
            self._versioning.activate_version(app_id, version)

            self._set_task(task_id, "succeeded", 100, "安装完成")

        except Exception as exc:
            self._set_task(task_id, "failed", 100, "安装失败", error=str(exc))

    # ------------------------------------------------------------------ #
    #  Shared helpers
    # ------------------------------------------------------------------ #

    def _record_installation(
        self,
        app_id: str,
        version: str,
        runtime: str,
        install_path: Path,
        manifest: AppManifest,
    ) -> None:
        """Write installation record and runtime placeholder to DB."""
        now = int(time.time())
        manifest_json = json.dumps(manifest.to_dict(), ensure_ascii=False)
        with db_conn() as conn:
            conn.execute(
                "INSERT INTO app_installation "
                "(app_id, version, runtime, install_path, status, installed_at, manifest) "
                "VALUES (?, ?, ?, ?, 'installed', ?, ?) "
                "ON CONFLICT(app_id, version) DO UPDATE SET "
                "runtime=excluded.runtime, install_path=excluded.install_path, "
                "status=excluded.status, installed_at=excluded.installed_at, "
                "manifest=excluded.manifest",
                (app_id, version, runtime, str(install_path), now, manifest_json),
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

    def _install_container(
        self,
        task_id: str,
        manifest: AppManifest,
        install_runtime: bool,
        runtime: str,
    ) -> None:
        if install_runtime:
            self._set_task(task_id, "running", 65, f"检查 {runtime} 运行环境")
        runtime_path = shutil.which(runtime)
        if not runtime_path:
            raise RuntimeError(f"未检测到 {runtime}，请先安装运行环境")
        image = manifest.install.get("image")
        if image:
            self._set_task(task_id, "running", 75, f"拉取镜像 {image}")
            pull = _run_cmd([runtime_path, "pull", image])
            if pull.returncode != 0:
                raise RuntimeError(
                    (pull.stderr or pull.stdout or "镜像拉取失败").strip()
                )

    def _prepare_host_artifact(
        self, manifest: AppManifest, install_path: Path
    ) -> None:
        artifact_url = manifest.install.get("url", "")
        if not artifact_url:
            raise RuntimeError("host 应用缺少 install.url")
        parsed = urllib.parse.urlparse(artifact_url)
        artifact_name = Path(parsed.path).name or "artifact.bin"
        cache_dir = ARTIFACT_CACHE_DIR / manifest.app_id / manifest.version
        cache_file = cache_dir / artifact_name

        _download_to_file(artifact_url, cache_file)

        expect_sha = (manifest.install.get("sha256") or "").strip()
        if expect_sha:
            actual = _sha256_file(cache_file)
            if actual.lower() != expect_sha.lower():
                raise ArtifactVerificationError(
                    f"artifact 校验失败: expect={expect_sha}, actual={actual}"
                )

        lower = artifact_name.lower()
        if lower.endswith((".tar.gz", ".tgz", ".tar", ".zip")):
            shutil.unpack_archive(str(cache_file), str(install_path))
        else:
            target = install_path / artifact_name
            shutil.copy2(cache_file, target)
            target.chmod(0o755)

    def _set_task(
        self,
        task_id: str,
        status: str,
        progress: int,
        message: str,
        error: str | None = None,
    ) -> None:
        now = int(time.time())
        with db_conn() as conn:
            conn.execute(
                "UPDATE app_task SET status=?, progress=?, message=?, error=?, updated_at=? "
                "WHERE task_id=?",
                (status, progress, message, error, now, task_id),
            )
            conn.commit()
