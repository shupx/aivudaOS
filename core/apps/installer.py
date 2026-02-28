from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from core.apps.catalog import CatalogService
from core.apps.models import AppManifest
from core.apps.versioning import VersioningService
from core.config.service import ConfigService
from core.db.connection import db_conn
from core.errors import (
    ArtifactVerificationError,
    InstallTaskConflictError,
    NotFoundError,
)
from core.paths import ARTIFACT_CACHE_DIR


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
    def __init__(
        self,
        catalog: CatalogService,
        versioning: VersioningService,
        config_service: ConfigService,
    ) -> None:
        self._catalog = catalog
        self._versioning = versioning
        self._config = config_service

    def create_install_task(
        self, app_id: str, install_runtime: bool = False
    ) -> dict[str, Any]:
        """Create a task record and launch the async install."""
        manifest = self._catalog.get_manifest(app_id)

        with db_conn() as conn:
            running = conn.execute(
                "SELECT task_id FROM app_task WHERE app_id = ? AND task_type = 'install' AND status = 'running'",
                (app_id,),
            ).fetchone()
            if running:
                raise InstallTaskConflictError(
                    f"Install task already running for {app_id}"
                )

            task_id = str(uuid.uuid4())
            now = int(time.time())
            conn.execute(
                "INSERT INTO app_task (task_id, app_id, task_type, status, progress, message, error, created_at, updated_at) "
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
            now = int(time.time())
            with db_conn() as conn:
                conn.execute(
                    "INSERT INTO app_installation (app_id, version, runtime, install_path, status, installed_at) "
                    "VALUES (?, ?, ?, ?, 'installed', ?) "
                    "ON CONFLICT(app_id, version) DO UPDATE SET "
                    "runtime=excluded.runtime, install_path=excluded.install_path, "
                    "status=excluded.status, installed_at=excluded.installed_at",
                    (app_id, version, runtime, str(install_path), now),
                )
                conn.execute(
                    "INSERT INTO app_runtime (app_id, running, autostart) VALUES (?, 0, 0) "
                    "ON CONFLICT(app_id) DO NOTHING",
                    (app_id,),
                )
                conn.commit()

            # Initialize per-app config file (only if not yet present)
            self._config.init_app_config(app_id, manifest.default_config)

            # Activate this version (set symlink)
            self._versioning.activate_version(app_id, version)

            self._set_task(task_id, "succeeded", 100, "安装完成")

        except Exception as exc:
            self._set_task(task_id, "failed", 100, "安装失败", error=str(exc))

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
                "UPDATE app_task SET status=?, progress=?, message=?, error=?, updated_at=? WHERE task_id=?",
                (status, progress, message, error, now, task_id),
            )
            conn.commit()
