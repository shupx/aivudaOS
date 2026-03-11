from __future__ import annotations

import errno
import os
import pty
import select
import signal
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
                env=self._build_process_env(interactive=False),
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                output_lines.append(line)
                log_file.write(line.encode("utf-8", errors="replace"))
                log_file.flush()
                if on_output:
                    on_output(line)
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

    def run_interactive(
        self,
        *,
        app_id: str,
        hook_name: str,
        script_path: str,
        root_dir: Path,
        on_output: Callable[[str], None] | None = None,
        read_input: Callable[[float], str | None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> ScriptHookRunResult:
        script = self._resolve_script(script_path, root_dir)
        self._ensure_executable(script)

        OS_LOG_DIR.mkdir(parents=True, exist_ok=True)
        started_at = int(time.time())
        output_parts: list[str] = []

        master_fd, slave_fd = pty.openpty()
        proc: subprocess.Popen[str] | None = None

        with self._log_path.open("ab") as log_file:
            header = (
                f"\n[{started_at}] [{app_id}] [{hook_name}] start: {script} (interactive)\n"
            )
            log_file.write(header.encode("utf-8", errors="replace"))
            log_file.flush()

            try:
                proc = subprocess.Popen(
                    [str(script)],
                    cwd=str(root_dir),
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    env=self._build_process_env(interactive=True),
                    close_fds=True,
                    start_new_session=True,
                )
            finally:
                os.close(slave_fd)

            try:
                canceled = False
                while True:
                    if cancel_requested and cancel_requested():
                        canceled = True
                        if proc.poll() is None:
                            self._terminate_process_tree(proc)

                    try:
                        ready, _, _ = select.select([master_fd], [], [], 0.2)
                    except OSError:
                        ready = []

                    if ready:
                        try:
                            chunk = os.read(master_fd, 4096)
                        except OSError as exc:
                            if exc.errno == errno.EIO:
                                chunk = b""
                            else:
                                raise

                        if chunk:
                            text = chunk.decode("utf-8", errors="replace")
                            output_parts.append(text)
                            log_file.write(chunk)
                            log_file.flush()
                            if on_output:
                                on_output(text)

                    if read_input:
                        incoming = read_input(0.01)
                        if incoming:
                            os.write(master_fd, incoming.encode("utf-8", errors="replace"))

                    if proc.poll() is not None:
                        break

                code = int(proc.wait())
            finally:
                os.close(master_fd)

            output = "".join(output_parts)
            ended_at = int(time.time())
            footer = (
                f"[{ended_at}] [{app_id}] [{hook_name}] exit_code={code}\n"
            )
            log_file.write(footer.encode("utf-8", errors="replace"))
            log_file.flush()

        if canceled:
            raise ScriptHookError(
                f"脚本执行已取消: hook={hook_name}, script={script_path}",
                output=output,
            )

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
    def _terminate_process_tree(proc: subprocess.Popen[str], grace_seconds: float = 2.0) -> None:
        if proc.poll() is not None:
            return

        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            try:
                proc.terminate()
            except OSError:
                return

        deadline = time.time() + max(0.0, grace_seconds)
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.05)

        if proc.poll() is not None:
            return

        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            try:
                proc.kill()
            except OSError:
                pass

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

    @staticmethod
    def _build_process_env(*, interactive: bool) -> dict[str, str]:
        env = os.environ.copy()

        # Prevent inheriting VS Code askpass bridge; otherwise git credential
        # prompts may jump back to the VS Code terminal instead of hook I/O.
        blocked_keys = {
            "GIT_ASKPASS",
            "SSH_ASKPASS",
            "VSCODE_GIT_ASKPASS_NODE",
            "VSCODE_GIT_ASKPASS_EXTRA_ARGS",
            "VSCODE_GIT_ASKPASS_MAIN",
            "VSCODE_GIT_IPC_HANDLE",
            "ELECTRON_RUN_AS_NODE",
        }
        for key in blocked_keys:
            env.pop(key, None)

        env["GIT_TERMINAL_PROMPT"] = "1" if interactive else "0"
        if interactive:
            env.setdefault("TERM", "xterm-256color")

        return env
