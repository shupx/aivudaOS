from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from aivudaos.core.paths import CADDY_BIN_PATH, CADDYFILE_PATH, CADDYFILE_TEMPLATE_PATH


class CaddyRuntimeService:
    '''
    For modifying https domain in Caddyfile according to the avahi hostname (mDNS)
    '''
    _https_site_re = re.compile(
        r"(?m)^(?P<indent>\s*)https://(?:\{\$AVAHI_HOSTNAME\}|__AVAHI_HOSTNAME__|[a-z0-9][a-z0-9-]{0,62})\.local(?P<port>:\d+)?\s*\{"
    )

    # Match the original standalone gateway layout. Keep app imports, backend
    # settings and other sites verbatim when upgrading a persisted Caddyfile.
    _legacy_app_fallback = (
        "    # END AIVUDA APP IMPORTS\n\n"
        "    handle {\n      encode zstd gzip\n      root * ./ui/dist\n"
        "      try_files {path} /index.html\n      file_server\n    }\n  }\n}"
    )

    def _upgrade_app_cache_policy(self, text: str) -> str:
        start = "(aivudaos_common_route) {\n"
        prefix, marker, rest = text.partition(start)
        common, end, sites = rest.partition("\n}")
        if not marker or not end or "@appEndpoint" in common or self._legacy_app_fallback not in common + end:
            return text
        # Preserve the existing proxy, imports and sites. Replace only the
        # recognized stock fallback with its counterpart in the shipped template.
        template = self._caddy_template_path.read_text(encoding="utf-8")
        stock_common = template.partition(start)[2].partition("\n}")[0]
        policy, _, _ = stock_common.partition("  @api path ")
        imports_end = "    # END AIVUDA APP IMPORTS\n"
        _, _, fallback = stock_common.partition(imports_end)
        if "@appEndpoint" not in policy or not fallback:
            return text
        updated = (common + end).replace(self._legacy_app_fallback, imports_end + fallback + "\n}", 1)
        return prefix + marker + policy + updated + sites

    def __init__(
        self,
        *,
        caddyfile_path: Path = CADDYFILE_PATH,
        caddy_template_path: Path = CADDYFILE_TEMPLATE_PATH,
        caddy_bin_path: Path = CADDY_BIN_PATH,
    ) -> None:
        self._caddyfile_path = caddyfile_path
        self._caddy_template_path = caddy_template_path
        self._caddy_bin_path = caddy_bin_path

    def sync_https_hostname(self, hostname: str) -> bool:
        normalized = str(hostname or "").strip().lower()
        if not normalized:
            return False

        self._ensure_caddyfile_exists()

        text = self._caddyfile_path.read_text(encoding="utf-8")
        # Migrate the shipped API-only matcher without replacing custom sites,
        # application imports, backend ports or TLS configuration.
        routed = re.sub(
            r"(?m)^(\s*@api\s+path\s+/aivuda_os/api\*)[ \t]*$",
            r"\1 /aivuda_os/mcp", text,
        )
        routed = self._upgrade_app_cache_policy(routed)
        
        def _replace(match: re.Match[str]) -> str:
            indent = match.group("indent") or ""
            port = match.group("port") or ""
            return f"{indent}https://{normalized}.local{port} {{"

        updated, count = self._https_site_re.subn(_replace, routed, count=1)

        if count == 0:
            if not updated.endswith("\n"):
                updated += "\n"
            updated += (
                f"\nhttps://{normalized}.local {{\n"
                "  tls internal\n"
                "  import aivudaos_common_route\n"
                "}\n"
            )

        if updated == text:
            return False

        self._caddyfile_path.write_text(updated, encoding="utf-8")
        return True

    def reload_if_running(self) -> None:
        if not self._is_caddy_running_for_current_config():
            return
        if not self._caddy_bin_path.exists() or not self._caddy_bin_path.is_file():
            raise RuntimeError(f"Caddy binary not found: {self._caddy_bin_path}")
        if not self._caddy_bin_path.stat().st_mode & 0o111:
            raise RuntimeError(f"Caddy binary is not executable: {self._caddy_bin_path}")

        proc = subprocess.run(
            [str(self._caddy_bin_path), "reload", "--config", str(self._caddyfile_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            details = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(details or "Failed to reload Caddy")

    def _ensure_caddyfile_exists(self) -> None:
        if self._caddyfile_path.exists():
            return
        self._caddyfile_path.parent.mkdir(parents=True, exist_ok=True)
        if self._caddy_template_path.exists():
            shutil.copy2(self._caddy_template_path, self._caddyfile_path)
            return
        raise RuntimeError(f"Caddyfile not found: {self._caddyfile_path}")

    def _is_caddy_running_for_current_config(self) -> bool:
        try:
            proc = subprocess.run(
                ["pgrep", "-af", f"{self._caddy_bin_path} run --config {self._caddyfile_path}"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return False
        return proc.returncode == 0
