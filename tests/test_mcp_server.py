from aivudaos.mcp_server import APIClient, MCPServer, api_schema
from aivudaos.mcp_runtime import create_http_app

AUTH_MODE = "query"
LEGACY_NAMES = ["aivudaos_status","list_installed_apps","get_app_status","get_config","queue_config_import"]

import base64
import io
import json
import unittest
from email.parser import BytesParser
from email.policy import default
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import WebSocketRoute


class FakeClient:
    token = "test-token"
    max_bytes = 64 * 1024 * 1024

    def __init__(self):
        self.auth_mode = AUTH_MODE
        self.calls = []

    def request(self, path, method="GET", **kwargs):
        self.calls.append((path, method, kwargs))
        return {"ok": True, "path": path}


def sample(schema):
    if "default" in schema and schema["default"] is not None:
        return schema["default"]
    if "enum" in schema:
        return schema["enum"][0]
    if "anyOf" in schema:
        return sample(next(item for item in schema["anyOf"] if item.get("type") != "null"))
    if schema.get("type") == "object":
        return {key: sample(schema["properties"][key]) for key in schema.get("required", [])}
    if schema.get("type") == "array":
        return [sample(schema["items"]) for _ in range(schema.get("minItems", 0))]
    if schema.get("type") in ("integer", "number"):
        return schema.get("minimum", 1)
    if schema.get("type") == "boolean":
        return True
    return "example"


class MCPServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = FakeClient()
        cls.server = MCPServer(cls.client)

    def test_every_backend_route_has_tool(self):
        expected = set()
        for route in api_schema().routes:
            if isinstance(route, APIRoute):
                expected.update((route.path, method) for method in route.methods)
            elif isinstance(route, WebSocketRoute):
                expected.add((route.path, "WEBSOCKET"))
        actual = {(operation[0], operation[1]) for operation in self.server.operations.values()}
        self.assertEqual(actual, expected)
        self.assertEqual(len(self.server.tools), len(expected))

    def test_every_http_tool_dispatches_with_valid_arguments(self):
        for tool in self.server.tools:
            path, method, params, content_type, stream = self.server.operations[tool["name"]]
            if method == "WEBSOCKET":
                continue
            with self.subTest(tool=tool["name"]):
                arguments = sample(tool["inputSchema"])
                self.server.call_tool(tool["name"], arguments)
                actual_path, actual_method, kwargs = self.client.calls[-1]
                self.assertEqual(actual_method, method)
                self.assertNotIn("{", actual_path)
                for param in params:
                    if param["name"] not in arguments:
                        continue
                    value = arguments[param["name"]]
                    if param["in"] == "query":
                        self.assertEqual(kwargs["query"][param["name"]], value)
                    if param["in"] == "header":
                        self.assertEqual(kwargs["headers"][param["name"]], str(value))
                if content_type == "application/json":
                    self.assertEqual(kwargs["payload"], arguments["body"])

    def test_legacy_tool_names_preserved(self):
        self.assertTrue(set(LEGACY_NAMES).issubset({tool["name"] for tool in self.server.tools}))

    def test_invalid_arguments_do_not_call_backend_or_echo_secrets(self):
        message = {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                   "params": {"name": LEGACY_NAMES[0], "arguments": {"password": "private-secret"}}}
        count = len(self.client.calls)
        response = self.server.handle(message)
        self.assertTrue(response["result"]["isError"])
        self.assertNotIn("private-secret", json.dumps(response))
        self.assertEqual(count, len(self.client.calls))

    def test_config_import_legacy_arguments(self):
        self.server.call_tool("queue_config_import", {"document": {"apps": []}, "app_store_base_url": "http://store"})
        self.assertEqual(self.client.calls[-1][2]["payload"], {"document": {"apps": []}, "app_store_base_url": "http://store"})

    def test_websocket_input_and_cleanup(self):
        client = APIClient(base_url="http://127.0.0.1:8000/aivuda_os", token="configured")
        server = MCPServer(client)
        with patch("websocket.create_connection") as connect:
            connection = connect.return_value
            connection.recv.side_effect = ['{"type":"interactive_ready"}', '{"type":"interactive_input_accepted"}']
            result = server.call_tool("operation_interactive_ws", {"operation_id": "id with spaces", "token": "override", "data": "yes\n"})
            self.assertEqual(connect.call_args[0][0], "ws://127.0.0.1:8000/aivuda_os/api/apps/operations/id%20with%20spaces/interactive/ws?token=override")
            self.assertEqual(json.loads(connection.send.call_args[0][0]), {"data": "yes\n"})
            self.assertEqual(result["reply"]["type"], "interactive_input_accepted")
            connection.close.assert_called_once()

    def test_websocket_failure_closes_connection(self):
        server = MCPServer(APIClient(token="configured"))
        with patch("websocket.create_connection") as connect:
            connect.return_value.recv.side_effect = RuntimeError("Disconnected")
            with self.assertRaises(RuntimeError):
                server.call_tool("operation_interactive_ws", {"operation_id": "test", "data": "yes"})
            connect.return_value.close.assert_called_once()

    def test_unknown_tool_and_method(self):
        with self.assertRaises(ValueError):
            self.server.call_tool("unknown", {})
        self.assertEqual(self.server.handle({"jsonrpc": "2.0", "id": 1, "method": "unknown"})["error"]["code"], -32601)

    def test_http_handshake_and_notifications(self):
        with TestClient(create_http_app(self.server), base_url="http://127.0.0.1") as http:
            headers = {"Accept": "application/json, text/event-stream"}
            response = http.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["result"]["protocolVersion"], "2025-03-26")
            self.assertNotIn("mcp-session-id", response.headers)
            self.assertEqual(http.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "method": "notifications/initialized"}).status_code, 202)
            self.assertEqual(len(http.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "id": 2, "method": "tools/list"}).json()["result"]["tools"]), len(self.server.tools))
            self.assertEqual(http.get("/mcp").status_code, 405)
            self.assertEqual(http.delete("/mcp").status_code, 405)
            self.assertEqual(http.get("/health").status_code, 200)

    def test_http_validation_and_security(self):
        with TestClient(create_http_app(self.server, access_token="mcp-secret"), base_url="http://127.0.0.1") as http:
            headers = {"Accept": "application/json, text/event-stream", "Authorization": "Bearer mcp-secret"}
            message = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
            self.assertEqual(http.post("/mcp", json=message).status_code, 401)
            self.assertEqual(http.post("/mcp", json=message, headers=dict(headers, Origin="https://evil.example")).status_code, 403)
            self.assertEqual(http.post("/mcp", json=message, headers=dict(headers, Host="evil.example")).status_code, 403)
            self.assertEqual(http.post("/mcp", json=message, headers=dict(headers, Accept="application/json")).status_code, 406)
            self.assertEqual(http.post("/mcp", json=message, headers=dict(headers, **{"MCP-Protocol-Version": "invalid"})).status_code, 400)
            self.assertEqual(http.post("/mcp", json=message, headers=dict(headers, **{"Mcp-Session-Id": "unknown"})).status_code, 404)
            malformed = http.post("/mcp", content="{", headers=dict(headers, **{"Content-Type": "application/json"}))
            self.assertEqual(malformed.json()["error"]["code"], -32700)
            self.assertEqual(http.post("/mcp", json=[], headers=headers).status_code, 400)
            self.assertEqual(http.post("/mcp", json=message, headers=headers).json()["result"], {})

    def test_http_request_limit(self):
        client = FakeClient()
        client.max_bytes = 8
        with TestClient(create_http_app(MCPServer(client)), base_url="http://127.0.0.1") as http:
            response = http.post("/mcp", json={"jsonrpc": "2.0"}, headers={"Accept": "application/json, text/event-stream"})
            self.assertEqual(response.status_code, 413)

    def test_batches_only_for_older_protocols(self):
        with TestClient(create_http_app(self.server), base_url="http://127.0.0.1") as http:
            headers = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-03-26"}
            batch = [{"jsonrpc": "2.0", "id": 1, "method": "ping"},
                     {"jsonrpc": "2.0", "method": "notifications/initialized"}]
            response = http.post("/mcp", json=batch, headers=headers)
            self.assertEqual(response.json(), [{"jsonrpc": "2.0", "id": 1, "result": {}}])
            self.assertEqual(http.post("/mcp", json=batch[1:], headers=headers).status_code, 202)
            headers["MCP-Protocol-Version"] = "2025-06-18"
            self.assertEqual(http.post("/mcp", json=batch, headers=headers).status_code, 400)


class APIClientTests(unittest.TestCase):
    def open_response(self, request, timeout):
        self.request = request
        response = io.BytesIO(self.response)
        response.headers = self.headers
        response.status = 200
        return response

    def setUp(self):
        self.response = b'{"ok":true}'
        self.headers = {"Content-Type": "application/json"}
        self.client = APIClient(base_url="http://127.0.0.1:8000/prefix", token="configured-token", opener=self.open_response)

    def test_json_query_encoding_and_auth_override(self):
        kwargs = {"query": {"count": 2}}
        if AUTH_MODE == "query":
            kwargs["query"]["token"] = "per-call-token"
        else:
            kwargs["headers"] = {"authorization": "Bearer per-call-token"}
        self.client.request("/example", "PUT", {"enabled": True}, **kwargs)
        self.assertEqual(json.loads(self.request.data), {"enabled": True})
        self.assertEqual(parse_qs(urlsplit(self.request.full_url).query)["count"], ["2"])
        if AUTH_MODE == "query":
            self.assertEqual(parse_qs(urlsplit(self.request.full_url).query)["token"], ["per-call-token"])
        else:
            self.assertEqual(self.request.get_header("Authorization"), "Bearer per-call-token")

    def test_configured_auth(self):
        self.client.request("/example")
        if AUTH_MODE == "query":
            self.assertEqual(parse_qs(urlsplit(self.request.full_url).query)["token"], ["configured-token"])
        else:
            self.assertEqual(self.request.get_header("Authorization"), "Bearer configured-token")

    def test_urlencoded_form(self):
        self.client.request("/login", "POST", {"username": "a+b", "password": "x&y"}, content_type="application/x-www-form-urlencoded")
        self.assertEqual(parse_qs(self.request.data.decode()), {"username": ["a+b"], "password": ["x&y"]})

    def test_multipart_file_and_form(self):
        self.client.request("/upload", "POST", {"name": "example", "package_zip": {
            "filename": "test.zip", "content_base64": base64.b64encode(b"binary\x00data").decode()}}, content_type="multipart/form-data")
        content_type = self.request.get_header("Content-type")
        parsed = BytesParser(policy=default).parsebytes(("Content-Type: " + content_type + "\r\nMIME-Version: 1.0\r\n\r\n").encode() + self.request.data)
        parts = list(parsed.iter_parts())
        self.assertEqual(parts[0].get_payload(decode=True), b"example")
        self.assertEqual(parts[1].get_filename(), "test.zip")
        self.assertEqual(parts[1].get_payload(decode=True), b"binary\x00data")

    def test_binary_download_and_head(self):
        self.response = b"binary\x00data"
        self.headers = {"Content-Type": "application/zip", "Content-Disposition": 'attachment; filename="test.zip"'}
        result = self.client.request("/download")
        self.assertEqual(base64.b64decode(result["content_base64"]), self.response)
        self.assertEqual(result["size"], len(self.response))
        self.assertEqual(result["filename"], "test.zip")
        self.assertEqual(self.client.request("/download", "HEAD")["status"], 200)

    def test_response_size_limit(self):
        self.client.max_bytes = 2
        with self.assertRaises(ValueError):
            self.client.request("/download")

    def test_sse_events(self):
        self.response = b'event: status\ndata: {"seq":1}\n\nevent: done\ndata: {"seq":2}\n\n'
        result = self.client.request("/events", stream={"max_events": 1, "timeout_seconds": 1})
        self.assertEqual(result["events"], [{"event": "status", "data": {"seq": 1}}])


if __name__ == "__main__":
    unittest.main()
