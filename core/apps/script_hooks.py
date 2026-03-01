from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.paths import OS_LOG_DIR


class ScriptHookError(Exception):
    """Raised when a lifecycle script hook fails."""

    def __init__(self, message: str, output: str = "") -> None:
        super().__init__(message)
        self.output = output


@dataclass
class ScriptHookRunResult:
    hook_name: str
    script_path: str
    exit_code: int
    output: str


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
        on_output: Callable[[str], None] | None = None,
    ) -> ScriptHookRunResult:
        script = self._resolve_script(script_path, root_dir)
        self._ensure_executable(script)

        OS_LOG_DIR.mkdir(parents=True, exist_ok=True)
        started_at = int(time.time())

        output_lines: list[str] = []

        with self._log_path.open("ab") as log_file:
            header = (
                f"\n[{started_at}] [{app_id}] [{hook_name}] start: {script}\n"
            )
            log_file.write(header.encode("utf-8", errors="replace"))
            log_file.flush()

            proc = subprocess.Popen(
                [str(script)],
                cwd=str(root_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                output_lines.append(line)
                log_file.write(line.encode("utf-8", errors="replace"))
                log_file.flush()
                if on_output:
                    on_output(line.rstrip("\n"))
            code = proc.wait()
            output = "".join(output_lines)

            ended_at = int(time.time())
            footer = (
                f"[{ended_at}] [{app_id}] [{hook_name}] exit_code={code}\n"
            )
            log_file.write(footer.encode("utf-8", errors="replace"))
            log_file.flush()

        if code != 0:
            raise ScriptHookError(
                f"脚本执行失败: hook={hook_name}, script={script_path}, exit_code={code}",
                output=output,
            )

        return ScriptHookRunResult(
            hook_name=hook_name,
            script_path=script_path,
            exit_code=code,
            output=output,
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
