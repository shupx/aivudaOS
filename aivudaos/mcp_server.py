"""Built-in Streamable HTTP MCP facade over AivudaOS API routes."""
from __future__ import annotations

import asyncio
import copy
import threading
from urllib.parse import quote

from aivudaos.mcp_runtime import APIClient as BaseAPIClient, APIHTTPError, OpenAPIServer, create_http_app
from aivudaos.mcp_asgi import ASGITransport


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


class EmbeddedAPIClient(APIClient):
    def __init__(self, transport=None, token=None, automatic_state=None):
        super().__init__(base_url="http://aivudaos.internal/aivuda_os", token=token, opener=transport)
        self.transport = transport
        self._automatic = not self.token
        self._automatic_state = automatic_state if automatic_state is not None else {
            "token": "", "managed": False, "lock": threading.Lock(),
        }

    def ensure_token(self, expired_token=None):
        if not self._automatic:
            return self.token
        state = self._automatic_state
        # Share only the configured/default account's managed token. Each
        # request retains its own ASGI transport and explicit user credentials.
        with state["lock"]:
            self.token, self._managed_token = state["token"], state["managed"]
            token = super().ensure_token(expired_token)
            state["token"], state["managed"] = self.token, self._managed_token
            return token

    def websocket_input(self, path, arguments):
        token = arguments["token"] if "token" in arguments else self.ensure_token()
        path = path.replace("{operation_id}", quote(arguments["operation_id"], safe=""))
        try:
            return self.transport.websocket_input(self.url(path, {"token": token}), arguments["data"])
        except APIHTTPError as exc:
            if exc.status != 401 or "token" in arguments or not self._managed_token:
                raise
            token = self.ensure_token(expired_token=token)
            return self.transport.websocket_input(self.url(path, {"token": token}), arguments["data"])


def install_mcp(app):
    """Register before the UI catch-all; tools derive only from business routes."""
    template = MCPServer(EmbeddedAPIClient())

    def for_request(request):
        authorization = request.headers.get("authorization", "")
        token = None
        if authorization:
            scheme, separator, token = authorization.partition(" ")
            if scheme.lower() != "bearer" or not separator or not token.strip():
                raise ValueError("Invalid Authorization header")
            token = token.strip()
        server = copy.copy(template)
        server.client = EmbeddedAPIClient(ASGITransport(app, asyncio.get_running_loop()), token,
                                          template.client._automatic_state)
        return server

    http = create_http_app(template, allowed_hosts=None, server_factory=for_request, include_health=False)
    app.include_router(http.router, prefix="/aivuda_os")
