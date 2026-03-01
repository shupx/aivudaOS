from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from core.paths import OS_LOG_DIR


class ScriptHookError(Exception):
    """Raised when a lifecycle script hook fails."""


class ScriptHookRunner:
    """Execute optional app lifecycle script hooks."""

    def __init__(self) -> None:
        self._log_path = OS_LOG_DIR / "install.log"

    def run(
        self,
        *,
        app_id: str,
        hook_name: str,
        script_path: str,
        root_dir: Path,
    ) -> None:
        script = self._resolve_script(script_path, root_dir)
        self._ensure_executable(script)

        OS_LOG_DIR.mkdir(parents=True, exist_ok=True)
        started_at = int(time.time())

        with self._log_path.open("ab") as log_file:
            header = (
                f"\n[{started_at}] [{app_id}] [{hook_name}] start: {script}\n"
            )
            log_file.write(header.encode("utf-8", errors="replace"))
            log_file.flush()

            proc = subprocess.Popen(
                [str(script)],
                cwd=str(root_dir),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
            )
            code = proc.wait()

            ended_at = int(time.time())
            footer = (
                f"[{ended_at}] [{app_id}] [{hook_name}] exit_code={code}\n"
            )
            log_file.write(footer.encode("utf-8", errors="replace"))

        if code != 0:
            raise ScriptHookError(
                f"脚本执行失败: hook={hook_name}, script={script_path}, exit_code={code}"
            )

    @staticmethod
    def _resolve_script(script_path: str, root_dir: Path) -> Path:
        raw = (script_path or "").strip()
        if not raw:
            raise ScriptHookError("脚本路径为空")

        candidate = Path(raw)
        if candidate.is_absolute():
            raise ScriptHookError("脚本路径必须是安装包内相对路径")

        resolved_root = root_dir.resolve()
        resolved = (resolved_root / candidate).resolve()
        if not resolved.exists() or not resolved.is_file():
            raise ScriptHookError(f"脚本不存在或不是文件: {script_path}")

        if resolved_root != resolved and resolved_root not in resolved.parents:
            raise ScriptHookError("脚本路径越界")

        return resolved

    @staticmethod
    def _ensure_executable(script: Path) -> None:
        try:
            mode = script.stat().st_mode
            script.chmod(mode | 0o111)
        except OSError as exc:
            raise ScriptHookError(f"设置脚本可执行权限失败: {exc}") from exc
