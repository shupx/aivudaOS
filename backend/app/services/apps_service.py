from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shlex
import shutil
import signal
import subprocess
import textwrap
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.app.core.settings import APP_REPO_URL, APPS_ROOT, ARTIFACT_CACHE_ROOT
from backend.app.services.db import db_conn


def app_install_dir(app_id: str) -> Path:
    return APPS_ROOT / app_id


def run_cmd(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def runtime_bin(runtime: str) -> str:
    bin_path = shutil.which(runtime)
    if not bin_path:
        raise RuntimeError(f"未检测到 {runtime}，请先安装运行环境")
    return bin_path


def host_exec_command(manifest: dict[str, Any], install_path: Path) -> list[str]:
    run = manifest.get("run", {})
    entrypoint = run.get("entrypoint")
    if not entrypoint:
        raise RuntimeError("app run.entrypoint 未配置")
    entry = Path(entrypoint)
    resolved = (install_path / entry).resolve() if not entry.is_absolute() else entry
    args = run.get("args", [])
    return [str(resolved), *[str(x) for x in args]]


def current_app_config(app_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
    with db_conn() as conn:
        row = conn.execute("SELECT data FROM app_config WHERE app_id = ?", (app_id,)).fetchone()
    if row:
        return json.loads(row["data"])
    return dict(manifest.get("default_config", {}))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def fetch_repo_index() -> dict[str, Any]:
    url = f"{APP_REPO_URL}/index"
    with urllib.request.urlopen(url, timeout=20) as resp:  # noqa: S310
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict) or "items" not in data:
        raise RuntimeError("远端仓库 index 格式错误")
    return data


def sync_catalog_from_repo() -> dict[str, Any]:
    repo_data = fetch_repo_index()
    items = repo_data.get("items", [])
    now = int(time.time())
    repo_origin = urllib.parse.urlsplit(APP_REPO_URL)
    host_base = f"{repo_origin.scheme}://{repo_origin.netloc}"
    with db_conn() as conn:
        conn.execute("DELETE FROM app_catalog")
        for item in items:
            app_id = item.get("app_id")
            manifest = item.get("manifest")
            if not app_id or not isinstance(manifest, dict):
                continue
            install_obj = manifest.get("install", {})
            if isinstance(install_obj, dict) and install_obj.get("url", "").startswith("/"):
                install_obj["url"] = urllib.parse.urljoin(host_base, install_obj["url"])
            conn.execute(
                "INSERT INTO app_catalog (app_id, manifest, updated_at) VALUES (?, ?, ?)",
                (app_id, json.dumps(manifest), now),
            )
        conn.commit()
    return {"ok": True, "source": APP_REPO_URL, "count": len(items), "updated_at": now}


def app_manifest(app_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        row = conn.execute("SELECT manifest FROM app_catalog WHERE app_id = ?", (app_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="App not found")
    return json.loads(row["manifest"])


def app_task_detail(task_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM app_task WHERE task_id = ?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return dict(row)


def set_task_state(
    task_id: str,
    *,
    status: str,
    progress: int,
    message: str,
    error: str | None = None,
) -> None:
    now = int(time.time())
    with db_conn() as conn:
        conn.execute(
            """
            UPDATE app_task
            SET status = ?, progress = ?, message = ?, error = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (status, progress, message, error, now, task_id),
        )
        conn.commit()


def download_to_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as resp, dest.open("wb") as out:  # noqa: S310
        shutil.copyfileobj(resp, out)


def prepare_host_artifact(manifest: dict[str, Any], install_path: Path) -> None:
    install_cfg = manifest.get("install", {})
    artifact_url = install_cfg.get("url", "")
    if not artifact_url:
        raise RuntimeError("host 应用缺少 install.url")

    parsed = urllib.parse.urlparse(artifact_url)
    artifact_name = Path(parsed.path).name or "artifact.bin"
    cache_dir = ARTIFACT_CACHE_ROOT / manifest.get("app_id", "unknown") / manifest.get("version", "0")
    cache_file = cache_dir / artifact_name
    download_to_file(artifact_url, cache_file)

    expect_sha = (install_cfg.get("sha256") or "").strip()
    if expect_sha:
        actual_sha = sha256_file(cache_file)
        if actual_sha.lower() != expect_sha.lower():
            raise RuntimeError(f"artifact 校验失败: expect={expect_sha}, actual={actual_sha}")

    if install_path.exists():
        shutil.rmtree(install_path)
    install_path.mkdir(parents=True, exist_ok=True)

    lower = artifact_name.lower()
    if lower.endswith((".tar.gz", ".tgz", ".tar", ".zip")):
        shutil.unpack_archive(str(cache_file), str(install_path))
    else:
        target = install_path / artifact_name
        shutil.copy2(cache_file, target)
        target.chmod(0o755)


def unit_name(app_id: str) -> str:
    return f"aivuda-app-{app_id}.service"


def systemd_user_dir() -> Path:
    p = Path.home() / ".config" / "systemd" / "user"
    p.mkdir(parents=True, exist_ok=True)
    return p


def systemd_user_call(*args: str) -> None:
    result = run_cmd(["systemctl", "--user", *args])
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "systemctl 执行失败").strip()
        raise RuntimeError(err)


def ensure_systemd_unit(app_id: str) -> Path:
    manifest = app_manifest(app_id)
    with db_conn() as conn:
        install_row = conn.execute("SELECT install_path, runtime FROM app_installation WHERE app_id = ?", (app_id,)).fetchone()
    if not install_row:
        raise RuntimeError("应用未安装")

    install_path = Path(install_row["install_path"])
    runtime = install_row["runtime"]
    unit_path = systemd_user_dir() / unit_name(app_id)

    if runtime == "host":
        cmd = host_exec_command(manifest, install_path)
        cmd_line = shlex.join(cmd)
        exec_start = f"/bin/bash -lc {shlex.quote(f'cd {shlex.quote(str(install_path))} && {cmd_line}') }"
        exec_stop = ""
    else:
        runtime_path = runtime_bin(runtime)
        container_name = manifest.get("run", {}).get("container_name", f"aivuda-{app_id}")
        exec_start = f"{runtime_path} start -a {container_name}"
        exec_stop = f"{runtime_path} stop {container_name}"

    content = textwrap.dedent(
        f"""
        [Unit]
        Description=AivudaOS App {app_id}
        After=network.target

        [Service]
        Type=simple
        WorkingDirectory={install_path}
        ExecStart={exec_start}
        Restart=on-failure
        RestartSec=3
        {f'ExecStop={exec_stop}' if exec_stop else ''}

        [Install]
        WantedBy=default.target
        """
    ).strip() + "\n"

    unit_path.write_text(content, encoding="utf-8")
    return unit_path


def remove_systemd_unit(app_id: str) -> None:
    service = unit_name(app_id)
    try:
        systemd_user_call("disable", service)
    except Exception:
        pass
    try:
        systemd_user_call("stop", service)
    except Exception:
        pass
    unit_path = systemd_user_dir() / service
    if unit_path.exists():
        unit_path.unlink()
    try:
        systemd_user_call("daemon-reload")
    except Exception:
        pass


def runtime_row_or_default(conn, app_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT running, autostart, pid, container_id, last_started_at, last_stopped_at FROM app_runtime WHERE app_id = ?",
        (app_id,),
    ).fetchone()
    if not row:
        return {
            "running": 0,
            "autostart": 0,
            "pid": None,
            "container_id": None,
            "last_started_at": None,
            "last_stopped_at": None,
        }
    return dict(row)


async def run_install_task(task_id: str, app_id: str, install_runtime: bool) -> None:
    try:
        manifest = app_manifest(app_id)
        runtime = manifest.get("runtime", "host")
        install_path = app_install_dir(app_id)

        set_task_state(task_id, status="running", progress=10, message="准备安装目录")
        install_path.mkdir(parents=True, exist_ok=True)
        await asyncio.sleep(0.2)

        set_task_state(task_id, status="running", progress=30, message="下载资源包")
        await asyncio.sleep(0.2)

        set_task_state(task_id, status="running", progress=50, message="校验资源完整性")
        await asyncio.sleep(0.2)

        if runtime in {"docker", "podman"}:
            if install_runtime:
                set_task_state(task_id, status="running", progress=65, message=f"检查 {runtime} 运行环境")
            runtime_path = runtime_bin(runtime)
            image = manifest.get("install", {}).get("image")
            if image:
                set_task_state(task_id, status="running", progress=75, message=f"拉取镜像 {image}")
                pull = run_cmd([runtime_path, "pull", image])
                if pull.returncode != 0:
                    raise RuntimeError((pull.stderr or pull.stdout or "镜像拉取失败").strip())
        else:
            set_task_state(task_id, status="running", progress=75, message="下载并解压应用包")
            prepare_host_artifact(manifest, install_path)

        set_task_state(task_id, status="running", progress=85, message="写入应用配置与运行参数")
        now = int(time.time())
        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO app_installation (app_id, version, runtime, install_path, status, installed_at)
                VALUES (?, ?, ?, ?, 'installed', ?)
                ON CONFLICT(app_id) DO UPDATE SET
                    version = excluded.version,
                    runtime = excluded.runtime,
                    install_path = excluded.install_path,
                    status = excluded.status,
                    installed_at = excluded.installed_at
                """,
                (app_id, manifest.get("version", "0.0.0"), runtime, str(install_path), now),
            )
            conn.execute(
                """
                INSERT INTO app_config (app_id, data, version, updated_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(app_id) DO NOTHING
                """,
                (app_id, json.dumps(manifest.get("default_config", {})), now),
            )
            conn.execute(
                """
                INSERT INTO app_runtime (app_id, running, autostart, pid, container_id, last_started_at, last_stopped_at)
                VALUES (?, 0, 0, NULL, NULL, NULL, NULL)
                ON CONFLICT(app_id) DO NOTHING
                """,
                (app_id,),
            )
            conn.commit()

        set_task_state(task_id, status="succeeded", progress=100, message="安装完成")
    except Exception as exc:
        set_task_state(
            task_id,
            status="failed",
            progress=100,
            message="安装失败",
            error=str(exc),
        )


def get_catalog() -> dict[str, Any]:
    with db_conn() as conn:
        rows = conn.execute("SELECT app_id, manifest, updated_at FROM app_catalog ORDER BY app_id").fetchall()
    return {
        "items": [
            {
                "app_id": row["app_id"],
                "manifest": json.loads(row["manifest"]),
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
    }


def get_installed() -> dict[str, Any]:
    with db_conn() as conn:
        rows = conn.execute(
            """
            SELECT i.app_id, i.version, i.runtime, i.install_path, i.status, i.installed_at,
                   r.running, r.autostart, r.pid, r.container_id, r.last_started_at, r.last_stopped_at
            FROM app_installation i
            LEFT JOIN app_runtime r ON r.app_id = i.app_id
            ORDER BY i.installed_at DESC
            """
        ).fetchall()
    return {
        "items": [
            {
                "app_id": row["app_id"],
                "version": row["version"],
                "runtime": row["runtime"],
                "install_path": row["install_path"],
                "status": row["status"],
                "installed_at": row["installed_at"],
                "running": bool(row["running"] or 0),
                "autostart": bool(row["autostart"] or 0),
                "pid": row["pid"],
                "container_id": row["container_id"],
                "last_started_at": row["last_started_at"],
                "last_stopped_at": row["last_stopped_at"],
            }
            for row in rows
        ]
    }


def create_install_task(app_id: str, install_runtime: bool) -> dict[str, Any]:
    _ = app_manifest(app_id)

    with db_conn() as conn:
        running_task = conn.execute(
            "SELECT task_id FROM app_task WHERE app_id = ? AND task_type = 'install' AND status = 'running'",
            (app_id,),
        ).fetchone()
        if running_task:
            raise HTTPException(status_code=409, detail="Install task is running")

        task_id = str(uuid.uuid4())
        now = int(time.time())
        conn.execute(
            """
            INSERT INTO app_task (task_id, app_id, task_type, status, progress, message, error, created_at, updated_at)
            VALUES (?, ?, 'install', 'pending', 0, '等待执行', NULL, ?, ?)
            """,
            (task_id, app_id, now, now),
        )
        conn.commit()

    asyncio.create_task(run_install_task(task_id, app_id, install_runtime))
    return {"task_id": task_id}


def app_runtime_detail(app_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        install_row = conn.execute("SELECT * FROM app_installation WHERE app_id = ?", (app_id,)).fetchone()
        runtime_row = conn.execute("SELECT * FROM app_runtime WHERE app_id = ?", (app_id,)).fetchone()
        config_row = conn.execute("SELECT version, updated_at FROM app_config WHERE app_id = ?", (app_id,)).fetchone()

    if not install_row:
        raise HTTPException(status_code=404, detail="App is not installed")

    return {
        "app_id": app_id,
        "installed": True,
        "install": dict(install_row),
        "runtime": dict(runtime_row) if runtime_row else None,
        "config": dict(config_row) if config_row else None,
    }


def start_app_runtime(app_id: str) -> dict[str, Any]:
    manifest = app_manifest(app_id)
    now = int(time.time())

    with db_conn() as conn:
        install_row = conn.execute(
            "SELECT app_id, runtime, install_path FROM app_installation WHERE app_id = ?",
            (app_id,),
        ).fetchone()
        if not install_row:
            raise HTTPException(status_code=404, detail="App is not installed")
        runtime_row = runtime_row_or_default(conn, app_id)

    runtime = install_row["runtime"]
    install_path = Path(install_row["install_path"])
    pid: int | None = None
    container_id: str | None = None

    if runtime == "host":
        command = host_exec_command(manifest, install_path)
        proc = subprocess.Popen(  # noqa: S603
            command,
            cwd=str(install_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        pid = proc.pid
    elif runtime in {"docker", "podman"}:
        runtime_path = runtime_bin(runtime)
        run_cfg = manifest.get("run", {})
        install_cfg = manifest.get("install", {})
        image = install_cfg.get("image")
        container_name = run_cfg.get("container_name", f"aivuda-{app_id}")

        exists_check = run_cmd([runtime_path, "ps", "-a", "--filter", f"name=^{container_name}$", "--format", "{{.ID}}"])
        if exists_check.returncode != 0:
            raise HTTPException(status_code=500, detail=(exists_check.stderr or exists_check.stdout).strip())

        existing_id = (exists_check.stdout or "").strip()
        if existing_id:
            start_result = run_cmd([runtime_path, "start", container_name])
            if start_result.returncode != 0:
                raise HTTPException(status_code=500, detail=(start_result.stderr or start_result.stdout).strip())
        else:
            if not image:
                raise HTTPException(status_code=400, detail="容器应用未配置镜像")
            cmd = [runtime_path, "run", "-d", "--name", container_name]
            for port in run_cfg.get("ports", []):
                cmd.extend(["-p", str(port)])
            cfg = current_app_config(app_id, manifest)
            merged_env = dict(run_cfg.get("env", {}))
            merged_env.update({k.upper(): str(v) for k, v in cfg.items()})
            for key, value in merged_env.items():
                cmd.extend(["-e", f"{key}={value}"])
            cmd.append(image)
            run_result = run_cmd(cmd)
            if run_result.returncode != 0:
                raise HTTPException(status_code=500, detail=(run_result.stderr or run_result.stdout).strip())
            existing_id = (run_result.stdout or "").strip()

        id_check = run_cmd([runtime_path, "ps", "--filter", f"name=^{container_name}$", "--format", "{{.ID}}"])
        if id_check.returncode == 0 and id_check.stdout.strip():
            container_id = id_check.stdout.strip()
        else:
            container_id = existing_id[:12] if existing_id else None
    else:
        raise HTTPException(status_code=400, detail=f"不支持的 runtime: {runtime}")

    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO app_runtime (app_id, running, autostart, pid, container_id, last_started_at, last_stopped_at)
            VALUES (?, 1, ?, ?, ?, ?, NULL)
            ON CONFLICT(app_id) DO UPDATE SET
                running = 1,
                autostart = excluded.autostart,
                pid = excluded.pid,
                container_id = excluded.container_id,
                last_started_at = excluded.last_started_at
            """,
            (app_id, runtime_row.get("autostart", 0), pid, container_id, now),
        )
        conn.commit()

    return {"ok": True, "app_id": app_id, "running": True, "runtime": runtime}


def stop_app_runtime(app_id: str) -> dict[str, Any]:
    now = int(time.time())

    with db_conn() as conn:
        install_row = conn.execute(
            "SELECT app_id, runtime FROM app_installation WHERE app_id = ?",
            (app_id,),
        ).fetchone()
        if not install_row:
            raise HTTPException(status_code=404, detail="App is not installed")
        runtime_row = runtime_row_or_default(conn, app_id)

    runtime = install_row["runtime"]
    if runtime == "host":
        pid = runtime_row.get("pid")
        if pid:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
    elif runtime in {"docker", "podman"}:
        manifest = app_manifest(app_id)
        runtime_path = runtime_bin(runtime)
        container_name = manifest.get("run", {}).get("container_name", f"aivuda-{app_id}")
        stop_result = run_cmd([runtime_path, "stop", container_name])
        if stop_result.returncode != 0 and "No such container" not in (stop_result.stderr or ""):
            raise HTTPException(status_code=500, detail=(stop_result.stderr or stop_result.stdout).strip())

    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO app_runtime (app_id, running, autostart, pid, container_id, last_started_at, last_stopped_at)
            VALUES (?, 0, ?, NULL, NULL, NULL, ?)
            ON CONFLICT(app_id) DO UPDATE SET
                running = 0,
                autostart = excluded.autostart,
                pid = NULL,
                container_id = NULL,
                last_stopped_at = excluded.last_stopped_at
            """,
            (app_id, runtime_row.get("autostart", 0), now),
        )
        conn.commit()

    return {"ok": True, "app_id": app_id, "running": False}


def set_autostart(app_id: str, enabled: bool) -> dict[str, Any]:
    with db_conn() as conn:
        install_row = conn.execute(
            "SELECT app_id FROM app_installation WHERE app_id = ?",
            (app_id,),
        ).fetchone()
        if not install_row:
            raise HTTPException(status_code=404, detail="App is not installed")
        runtime_row = runtime_row_or_default(conn, app_id)

    try:
        _ = ensure_systemd_unit(app_id)
        systemd_user_call("daemon-reload")
        if enabled:
            systemd_user_call("enable", unit_name(app_id))
        else:
            systemd_user_call("disable", unit_name(app_id))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"systemd 自启动设置失败: {exc}") from exc

    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO app_runtime (app_id, running, autostart, pid, container_id, last_started_at, last_stopped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(app_id) DO UPDATE SET
                autostart = excluded.autostart
            """,
            (
                app_id,
                int(runtime_row.get("running", 0)),
                1 if enabled else 0,
                runtime_row.get("pid"),
                runtime_row.get("container_id"),
                runtime_row.get("last_started_at"),
                runtime_row.get("last_stopped_at"),
            ),
        )
        conn.commit()

    return {"ok": True, "app_id": app_id, "autostart": enabled}


def uninstall_app(app_id: str, purge: bool) -> dict[str, Any]:
    with db_conn() as conn:
        install_row = conn.execute(
            "SELECT runtime, install_path FROM app_installation WHERE app_id = ?",
            (app_id,),
        ).fetchone()
        runtime_row = conn.execute("SELECT pid FROM app_runtime WHERE app_id = ?", (app_id,)).fetchone()
    if not install_row:
        raise HTTPException(status_code=404, detail="App is not installed")

    runtime = install_row["runtime"]
    install_path = Path(install_row["install_path"])

    if runtime == "host":
        pid = runtime_row["pid"] if runtime_row else None
        if pid:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
    elif runtime in {"docker", "podman"}:
        manifest = app_manifest(app_id)
        runtime_path = runtime_bin(runtime)
        container_name = manifest.get("run", {}).get("container_name", f"aivuda-{app_id}")
        _ = run_cmd([runtime_path, "stop", container_name])
        _ = run_cmd([runtime_path, "rm", container_name])

    remove_systemd_unit(app_id)

    if install_path.exists():
        shutil.rmtree(install_path, ignore_errors=True)

    with db_conn() as conn:
        conn.execute("DELETE FROM app_installation WHERE app_id = ?", (app_id,))
        conn.execute("DELETE FROM app_runtime WHERE app_id = ?", (app_id,))
        if purge:
            conn.execute("DELETE FROM app_config WHERE app_id = ?", (app_id,))
        conn.commit()

    return {"ok": True, "app_id": app_id, "purge": purge}


def get_app_config(app_id: str) -> dict[str, Any]:
    _ = app_manifest(app_id)
    with db_conn() as conn:
        row = conn.execute(
            "SELECT data, version, updated_at FROM app_config WHERE app_id = ?",
            (app_id,),
        ).fetchone()

    if row:
        return {
            "app_id": app_id,
            "data": json.loads(row["data"]),
            "version": row["version"],
            "updated_at": row["updated_at"],
        }

    manifest = app_manifest(app_id)
    return {
        "app_id": app_id,
        "data": manifest.get("default_config", {}),
        "version": 0,
        "updated_at": None,
    }


def put_app_config(app_id: str, version: int, data: dict[str, Any]) -> dict[str, Any]:
    _ = app_manifest(app_id)
    now = int(time.time())

    with db_conn() as conn:
        existing = conn.execute(
            "SELECT version FROM app_config WHERE app_id = ?",
            (app_id,),
        ).fetchone()

        if existing is None:
            if version != 0:
                raise HTTPException(status_code=409, detail="App config version conflict")
            new_version = 1
            conn.execute(
                "INSERT INTO app_config (app_id, data, version, updated_at) VALUES (?, ?, ?, ?)",
                (app_id, json.dumps(data), new_version, now),
            )
        else:
            if version != existing["version"]:
                raise HTTPException(status_code=409, detail="App config version conflict")
            new_version = existing["version"] + 1
            conn.execute(
                "UPDATE app_config SET data = ?, version = ?, updated_at = ? WHERE app_id = ?",
                (json.dumps(data), new_version, now, app_id),
            )
        conn.commit()

    return {"ok": True, "version": new_version}
