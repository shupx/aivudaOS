from __future__ import annotations

import asyncio
import copy
import hashlib
import ipaddress
import json
import re
from typing import Any, Dict
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from aivudaos.gateway.deps import (
    get_config_service, get_installer_service, get_magnet_service,
    get_runtime_service, get_versioning_service,
)
from aivudaos.gateway.routes.apps import put_app_config
from aivudaos.gateway.routes.config import put_config
from aivudaos.gateway.schemas import AppConfigUpdateRequest, ConfigUpdateRequest

APP_ID = re.compile(r"^[a-zA-Z0-9_.-]+$")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][a-zA-Z0-9_.-]+)?$")
MAX_PACKAGE_BYTES = 512 * 1024 * 1024


def validate_import(document: Any, store_url: str) -> Dict[str, Any]:
    if not isinstance(document, dict) or type(document.get("format_version")) is not int or document["format_version"] != 1:
        raise ValueError("Expected AivudaOS config export format_version=1")
    payload = document.get("payload")
    if not isinstance(payload, dict) or not isinstance(payload.get("apps"), list):
        raise ValueError("payload.apps must be an array")
    system = payload.get("system_parameters")
    if system is not None and not isinstance(system, dict):
        raise ValueError("payload.system_parameters must be an object or null")
    seen = set()
    for app in payload["apps"]:
        if not isinstance(app, dict) or not isinstance(app.get("app_id"), str) or not APP_ID.fullmatch(app["app_id"]) or app["app_id"] in (".", ".."):
            raise ValueError("Invalid app_id in config export")
        if not isinstance(app.get("version"), str) or not VERSION.fullmatch(app["version"]):
            raise ValueError("Invalid app version in config export")
        if app["app_id"] in seen:
            raise ValueError("Duplicate app_id in config export")
        seen.add(app["app_id"])
        if not isinstance(app.get("parameters"), dict):
            raise ValueError("App parameters must be an object")
        if "autostart" in app and not isinstance(app["autostart"], bool):
            raise ValueError("App autostart must be a boolean")
    parts = urlsplit(store_url)
    if parts.scheme != "http" or not parts.hostname or parts.username or parts.password or parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ValueError("AppStore URL must be a local HTTP base URL")
    try:
        if parts.hostname != "localhost" and not ipaddress.ip_address(parts.hostname).is_loopback:
            raise ValueError("AppStore URL must be loopback")
        _ = parts.port
    except (ValueError, TypeError) as exc:
        raise ValueError("AppStore URL must be loopback with a valid port") from exc
    return copy.deepcopy(payload)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def _store_get(base_url: str, path: str, limit: int) -> bytes:
    if not path.startswith("/") and not path.startswith("aivuda_app_store/"):
        raise ValueError("Invalid AppStore path")
    if any(part in (".", "..") or "/" in part or "\\" in part for part in (unquote(part) for part in path.split("/"))):
        raise ValueError("Invalid AppStore path")
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    if urlsplit(url).netloc != urlsplit(base_url).netloc:
        raise ValueError("AppStore download URL must remain on the local store")
    try:
        with build_opener(_NoRedirect()).open(Request(url), timeout=30) as response:
            data = response.read(limit + 1)
    except HTTPError as exc:
        raise ValueError("AppStore HTTP {}: {}".format(exc.code, path)) from exc
    if len(data) > limit:
        raise ValueError("AppStore response exceeds size limit")
    return data


def _leaves(data: Dict[str, Any], prefix: str = ""):
    for key, value in data.items():
        if not prefix and (key.startswith("_") or key == "avahi_hostname"):
            continue
        path = "{}.{}".format(prefix, key) if prefix else key
        if isinstance(value, dict) and value:
            yield from _leaves(value, path)
        else:
            yield path, value


def _merge(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(existing)
    for path, value in _leaves(incoming):
        cursor = merged
        parts = path.split(".")
        for key in parts[:-1]:
            if not isinstance(cursor.get(key), dict):
                cursor[key] = {}
            cursor = cursor[key]
        cursor[parts[-1]] = copy.deepcopy(value)
    return merged


def apply_import(payload: Dict[str, Any], store_url: str, token: str, progress) -> Dict[str, Any]:
    versioning = get_versioning_service()
    config = get_config_service()
    result = {"installed": [], "configured": [], "autostart": []}
    for app in payload["apps"]:
        app_id, version = app["app_id"], app["version"]
        if version not in versioning.list_versions(app_id):
            progress("download", app_id)
            path = "aivuda_app_store/store/apps/{}/versions/{}/download-url".format(quote(app_id, safe=""), quote(version, safe=""))
            info = json.loads(_store_get(store_url, path, 65536))
            download_url = info.get("url")
            if not isinstance(download_url, str) or not download_url.startswith("/aivuda_app_store/files/"):
                raise ValueError("Invalid AppStore download URL")
            size = info.get("size")
            if type(size) is not int or size < 0 or size > MAX_PACKAGE_BYTES:
                raise ValueError("Invalid AppStore package size")
            package = _store_get(store_url, download_url, MAX_PACKAGE_BYTES)
            if len(package) != size or hashlib.sha256(package).hexdigest() != info.get("sha256"):
                raise ValueError("AppStore package checksum/size mismatch: {}".format(app_id))
            filename = info.get("filename")
            if not isinstance(filename, str) or filename != filename.split("/")[-1] or not filename.endswith((".zip", ".tar.gz")):
                raise ValueError("Invalid AppStore package filename")
            progress("install", app_id)
            installed = get_installer_service().install_from_upload(package, filename, overwrite=False)
            if installed.get("app_id") != app_id or installed.get("version") != version:
                raise ValueError("Installed package identity mismatch: {}".format(app_id))
            result["installed"].append(app_id)
        elif versioning.active_version(app_id) != version:
            progress("activate", app_id)
            get_runtime_service().switch_version(app_id, version, restart=False)
    if payload["system_parameters"] is not None:
        progress("system", None)
        current = config.get_sys_config()
        data = _merge(current.data, payload["system_parameters"])
        if data != current.data:
            asyncio.run(put_config(ConfigUpdateRequest(version=current.version, data=data), token))
        result["system_configured"] = True

    for app in payload["apps"]:
        app_id, version = app["app_id"], app["version"]
        progress("configure", app_id)
        current = config.get_app_config(app_id, version)
        default = config.get_app_default_config(app_id, version)
        data = _merge(current.data if current.version else default, app["parameters"])
        if data != (current.data if current.version else default):
            asyncio.run(put_app_config(app_id, AppConfigUpdateRequest(version=current.version, data=data, app_version=version), token))
        result["configured"].append(app_id)

    for app in payload["apps"]:
        if isinstance(app.get("autostart"), bool):
            progress("autostart", app["app_id"])
            get_runtime_service().set_autostart(app["app_id"], app["autostart"])
            result["autostart"].append(app["app_id"])
    get_magnet_service().recompute(updated_by="config-import")
    return result
