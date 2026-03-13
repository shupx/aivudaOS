from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.apps.models import AppManifest
from core.apps.versioning import VersioningService
from core.db.connection import db_conn
from core.errors import InvalidConfigError
from core.paths import CADDY_BIN_PATH, CADDYFILE_PATH


@dataclass
class _ActiveCaddyConfig:
    app_id: str
    config_path: Path
    routes: set[str]


class CaddyConfigService:
    _BEGIN_MARKER = "# BEGIN AIVUDA APP IMPORTS"
    _END_MARKER = "# END AIVUDA APP IMPORTS"

    def __init__(self, versioning: VersioningService) -> None:
        self._versioning = versioning

    def validate_candidate(
        self,
        app_id: str,
        manifest: AppManifest,
        install_path: Path,
    ) -> None:
        candidate = self._resolve_manifest_caddyfile_path(
            install_path,
            manifest,
            required=bool(manifest.caddyfile_config_path),
        )
        if candidate is None:
            return

        candidate_routes = self._extract_routes(candidate.read_text("utf-8"))
        existing_routes = self._collect_active_route_owners(exclude_app_ids={app_id})
        conflicts = sorted(route for route in candidate_routes if route in existing_routes)
        if conflicts:
            conflict_route = conflicts[0]
            owner = existing_routes[conflict_route]
            raise InvalidConfigError(
                f"Caddy route conflict: route '{conflict_route}' is already owned by app '{owner}'"
            )

    def sync_and_reload(self) -> None:
        active_configs = self._collect_active_configs()
        self._ensure_no_active_route_conflicts(active_configs)
        self._rewrite_top_level_caddyfile([entry.config_path for entry in active_configs])
        self._reload_caddy()

    def _collect_active_configs(self) -> list[_ActiveCaddyConfig]:
        with db_conn() as conn:
            rows = conn.execute("SELECT DISTINCT app_id FROM app_installation").fetchall()

        active_configs: list[_ActiveCaddyConfig] = []
        for row in rows:
            app_id = str(row["app_id"])
            active_version = self._versioning.active_version(app_id)
            if not active_version:
                continue

            with db_conn() as conn:
                manifest_row = conn.execute(
                    "SELECT manifest FROM app_installation WHERE app_id = ? AND version = ?",
                    (app_id, active_version),
                ).fetchone()
            if not manifest_row or not manifest_row["manifest"]:
                continue

            manifest = AppManifest.from_dict(app_id, json.loads(manifest_row["manifest"]))
            if not manifest.caddyfile_config_path:
                continue

            install_path = self._versioning.active_install_path(app_id)
            if install_path is None:
                continue

            config_path = self._resolve_manifest_caddyfile_path(
                install_path,
                manifest,
                required=True,
            )
            if config_path is None:
                continue
            routes = self._extract_routes(config_path.read_text("utf-8"))
            active_configs.append(
                _ActiveCaddyConfig(
                    app_id=app_id,
                    config_path=config_path,
                    routes=routes,
                )
            )

        active_configs.sort(key=lambda item: item.app_id)
        return active_configs

    def _collect_active_route_owners(
        self,
        *,
        exclude_app_ids: set[str] | None = None,
    ) -> dict[str, str]:
        route_owners: dict[str, str] = {}
        for entry in self._collect_active_configs():
            if exclude_app_ids and entry.app_id in exclude_app_ids:
                continue
            for route in entry.routes:
                route_owners[route] = entry.app_id
        return route_owners

    def _ensure_no_active_route_conflicts(self, active_configs: list[_ActiveCaddyConfig]) -> None:
        route_owners: dict[str, str] = {}
        for entry in active_configs:
            for route in entry.routes:
                owner = route_owners.get(route)
                if owner and owner != entry.app_id:
                    raise InvalidConfigError(
                        f"Caddy route conflict: route '{route}' is declared by both '{owner}' and '{entry.app_id}'"
                    )
                route_owners[route] = entry.app_id

    def _rewrite_top_level_caddyfile(self, import_paths: list[Path]) -> None:
        if not CADDYFILE_PATH.exists():
            raise InvalidConfigError(f"Caddyfile not found: {CADDYFILE_PATH}")

        content = CADDYFILE_PATH.read_text("utf-8")
        pattern = re.compile(
            rf"(?ms)^([ \t]*){re.escape(self._BEGIN_MARKER)}\n.*?^\1{re.escape(self._END_MARKER)}$"
        )

        def replace_block(match: re.Match[str]) -> str:
            indent = match.group(1)
            import_lines = "\n".join(
                f'{indent}import "{self._escape_caddy_string(str(path))}"'
                for path in import_paths
            )
            if import_lines:
                return (
                    f"{indent}{self._BEGIN_MARKER}\n"
                    f"{import_lines}\n"
                    f"{indent}{self._END_MARKER}"
                )
            return f"{indent}{self._BEGIN_MARKER}\n{indent}{self._END_MARKER}"

        updated, count = pattern.subn(replace_block, content)
        if count == 0:
            raise InvalidConfigError(
                "Top-level Caddyfile missing managed import markers; cannot update app imports"
            )

        CADDYFILE_PATH.write_text(updated, encoding="utf-8")

    def _reload_caddy(self) -> None:
        if not CADDY_BIN_PATH.exists() or not CADDY_BIN_PATH.is_file():
            raise InvalidConfigError(f"Caddy binary not found: {CADDY_BIN_PATH}")
        if not CADDY_BIN_PATH.stat().st_mode & 0o111:
            raise InvalidConfigError(f"Caddy binary is not executable: {CADDY_BIN_PATH}")

        proc = subprocess.run(
            [
                str(CADDY_BIN_PATH),
                "reload",
                "--config",
                str(CADDYFILE_PATH),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            details = (proc.stderr or proc.stdout or "").strip()
            raise InvalidConfigError(f"Failed to reload Caddy: {details}")

    @staticmethod
    def _resolve_manifest_caddyfile_path(
        install_path: Path,
        manifest: AppManifest,
        *,
        required: bool,
    ) -> Path | None:
        raw = str(manifest.caddyfile_config_path or "").strip()
        if not raw:
            if required:
                raise InvalidConfigError(
                    f"App {manifest.app_id}@{manifest.version} missing caddyfile_config_path"
                )
            return None

        relative = Path(raw)
        if relative.is_absolute():
            raise InvalidConfigError("manifest.caddyfile_config_path must be a relative path")

        root = install_path.resolve()
        resolved = (root / relative).resolve()
        if root != resolved and root not in resolved.parents:
            raise InvalidConfigError("manifest.caddyfile_config_path escapes install root")
        if not resolved.exists() or not resolved.is_file():
            raise InvalidConfigError(f"manifest.caddyfile_config_path does not exist: {raw}")
        return resolved

    @staticmethod
    def _extract_routes(caddy_text: str) -> set[str]:
        routes: set[str] = set()
        path_matchers: dict[str, set[str]] = {}

        for raw_line in caddy_text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue

            matcher = re.match(r"^@([A-Za-z0-9_-]+)\s+path\s+(.+)$", line)
            if matcher:
                name = matcher.group(1)
                tokens = matcher.group(2).split()
                parsed = {
                    normalized
                    for token in tokens
                    if (normalized := CaddyConfigService._normalize_route_token(token))
                }
                if parsed:
                    path_matchers[name] = parsed
                continue

            direct_route = re.match(r"^(?:handle|handle_path|route)\s+(/[^\s{]+)", line)
            if direct_route:
                normalized = CaddyConfigService._normalize_route_token(direct_route.group(1))
                if normalized:
                    routes.add(normalized)
                continue

            matcher_ref = re.match(r"^(?:handle|handle_path|route)\s+@([A-Za-z0-9_-]+)\b", line)
            if matcher_ref:
                name = matcher_ref.group(1)
                routes.update(path_matchers.get(name, set()))

        return routes

    @staticmethod
    def _normalize_route_token(token: str) -> str | None:
        value = token.strip().rstrip("{").strip()
        if not value or not value.startswith("/"):
            return None
        while value.endswith("*"):
            value = value[:-1]
        while value.endswith("/") and value != "/":
            value = value[:-1]
        return value or "/"

    @staticmethod
    def _escape_caddy_string(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')
