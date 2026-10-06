"""Standalone Streamable HTTP MCP facade over every AivudaOS API route."""
from __future__ import annotations

from aivudaos.mcp_runtime import APIClient as BaseAPIClient, OpenAPIServer, serve


class APIClient(BaseAPIClient):
    def __init__(self, base_url=None, token=None, opener=None):
        super().__init__("AIVUDAOS", "http://127.0.0.1/aivuda_os", "query", base_url, token, opener)


def api_schema():
    from fastapi import FastAPI
    from aivudaos.gateway.routes import apps, auth, config

    app = FastAPI()
    for router in (auth.router, config.router, apps.router):
        app.include_router(router)
    return app


class MCPServer(OpenAPIServer):
    def __init__(self, client=None):
        super().__init__("aivudaos-mcp", client or APIClient(), api_schema(), {
            ("GET", "/api/config/system/aivudaos-service"): "aivudaos_status",
            ("GET", "/api/apps/installed"): "list_installed_apps",
            ("GET", "/api/apps/{app_id}/status"): "get_app_status",
            ("GET", "/api/config"): "get_config",
            ("POST", "/api/config/import"): "queue_config_import",
        })


def main():
    serve(MCPServer(), "AIVUDAOS", 28794)


if __name__ == "__main__":
    main()
