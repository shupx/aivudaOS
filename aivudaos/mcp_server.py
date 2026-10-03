"""Small stdlib MCP server for AivudaOS.

Transport: line-delimited JSON-RPC 2.0 over stdin/stdout.  The server talks
only to AivudaOS's public HTTP API; it does not open the AivudaOS database.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable, Dict, Optional
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class APIClient:
    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None,
                 opener: Optional[Callable[..., Any]] = None) -> None:
        self.base_url = (base_url or os.environ.get("AIVUDAOS_MCP_BASE_URL", "http://127.0.0.1:8000/aivuda_os")).rstrip("/")
        self.token = token if token is not None else os.environ.get("AIVUDAOS_MCP_TOKEN", "")
        self.opener = opener or urlopen

    def request(self, path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Any:
        query = {"token": self.token} if self.token else {}
        url = self.base_url + path
        if query:
            url += "?" + urlencode(query)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = Request(url, data=body, method=method, headers={"Content-Type": "application/json"})
        with self.opener(req, timeout=30) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8")) if raw else {}


TOOLS = [
    {"name": "aivudaos_status", "description": "Read AivudaOS service status.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_installed_apps", "description": "List installed AivudaOS apps.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_app_status", "description": "Read the runtime status of an installed app.", "inputSchema": {"type": "object", "properties": {"app_id": {"type": "string"}}, "required": ["app_id"]}},
    {"name": "get_config", "description": "Read the public AivudaOS system configuration.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "queue_config_import", "description": "Validate and queue a configuration import through AivudaOS.", "inputSchema": {"type": "object", "properties": {"document": {"type": "object"}, "app_store_base_url": {"type": "string"}}, "required": ["document", "app_store_base_url"]}},
]


class MCPServer:
    def __init__(self, client: Optional[APIClient] = None) -> None:
        self.client = client or APIClient()

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        if name == "aivudaos_status":
            return self.client.request("/api/config/system/aivudaos-service")
        if name == "list_installed_apps":
            return self.client.request("/api/apps/installed")
        if name == "get_app_status":
            return self.client.request("/api/apps/{0}/status".format(quote(str(arguments["app_id"]), safe="")))
        if name == "get_config":
            return self.client.request("/api/config")
        if name == "queue_config_import":
            return self.client.request("/api/config/import", "POST", {"document": arguments["document"], "app_store_base_url": arguments["app_store_base_url"]})
        raise ValueError("Unknown tool: {0}".format(name))

    def handle(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method = message.get("method")
        request_id = message.get("id")
        if method == "notifications/initialized":
            return None
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "aivudaos-mcp", "version": "1.0"}}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
        if method == "tools/call":
            params = message.get("params") or {}
            try:
                result = self.call_tool(str(params.get("name")), params.get("arguments") or {})
                return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}}
            except Exception as exc:
                return {"jsonrpc": "2.0", "id": request_id, "result": {"isError": True, "content": [{"type": "text", "text": str(exc)}]}}
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}


def main() -> None:
    server = MCPServer()
    for line in sys.stdin:
        if not line.strip():
            continue
        response = server.handle(json.loads(line))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
