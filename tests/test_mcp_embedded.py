import asyncio
import base64
import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from fastapi.responses import StreamingResponse

from aivudaos.core.errors import AuthenticationError, AppNotInstalledError
from aivudaos.gateway.main import create_app
from aivudaos.gateway.routes import apps, auth, config
from aivudaos.core.config.caddy_runtime import CaddyRuntimeService


class Auth:
    default_enabled = True

    def login(self, username, password):
        if username == "admin" and password == "admin123" and self.default_enabled:
            return self.validate_token("admin-token")
        if username not in ("alice", "bob") or password != "secret":
            raise AuthenticationError("Invalid credentials")
        return self.validate_token(username + "-token")

    def validate_token(self, token):
        if token not in ("alice-token", "bob-token", "admin-token"):
            raise AuthenticationError("Invalid token")
        return SimpleNamespace(token=token, username=token.split("-")[0], role="admin")


class EmbeddedMCPTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.auth = Auth()
        self.runtime = Mock()
        self.runtime.get_installed_list.return_value = [{"app_id": "example"}]
        self.operations = Mock()
        self.operations.get_operation.return_value = {
            "operation_id": "job", "done": True, "interactive_enabled": True, "interactive_open": True,
        }
        self.operations.wait_events.return_value = ([{"seq": 1, "type": "status", "status": "completed"}], True)
        for module in (auth, apps, config):
            self.stack.enter_context(patch.object(module, "get_auth_service", return_value=self.auth))
        self.stack.enter_context(patch.object(apps, "get_runtime_service", return_value=self.runtime))
        self.stack.enter_context(patch.object(apps, "get_app_operation_manager", return_value=self.operations))
        # Embedded MCP must never reach a network socket or implicitly log in.
        self.stack.enter_context(patch("aivudaos.mcp_runtime.urlopen", side_effect=AssertionError("Network HTTP used")))
        self.stack.enter_context(patch("websocket.create_connection", side_effect=AssertionError("Network WebSocket used")))
        self.app = create_app()
        self.app.router.on_startup.clear()
        self.app.router.on_shutdown.clear()
        self.paths = []

        @self.app.middleware("http")
        async def observe(request, call_next):
            self.paths.append(request.url.path)
            return await call_next(request)

        self.http = self.stack.enter_context(TestClient(self.app, base_url="https://robot-a.local"))

    def rpc(self, method, params=None, headers=None, http=None):
        return (http or self.http).post("/aivuda_os/mcp", headers={
            "Accept": "application/json, text/event-stream", **(headers or {}),
        }, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})

    def call(self, name, arguments=None, headers=None):
        response = self.rpc("tools/call", {"name": name, "arguments": arguments or {}}, headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["result"]

    def value(self, name, arguments=None, headers=None):
        result = self.call(name, arguments, headers)
        self.assertFalse(result.get("isError"), result)
        return json.loads(result["content"][0]["text"])

    def test_builtin_route_and_tools_exclude_mcp_and_ui(self):
        for base in ("http://127.0.0.1:28790", "https://robot-a.local"):
            with TestClient(self.app, base_url=base) as http:
                response = self.rpc("initialize", {"protocolVersion": "2025-06-18"}, http=http)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("mcp-session-id", response.headers)
                tools = self.rpc("tools/list", http=http).json()["result"]["tools"]
                self.assertEqual(len(tools), 47)
                self.assertNotIn("mcp", [tool["name"] for tool in tools])
        self.assertNotIn("/aivuda_os/mcp", self.app.openapi()["paths"])
        self.assertEqual(self.http.get("/aivuda_os/mcp").status_code, 405)
        self.assertEqual(self.http.delete("/aivuda_os/mcp").status_code, 405)

    def test_login_explicit_token_and_header_token_reach_api_middleware(self):
        token = self.value("login", {"body": {"username": "alice", "password": "secret"}})["access_token"]
        self.assertEqual(self.value("me", {"token": token})["username"], "alice")
        self.assertEqual(self.value("me", headers={"Authorization": "Bearer bob-token"})["username"], "bob")
        self.assertEqual(self.value("list_installed_apps", {"token": token})["items"], [{"app_id": "example"}])
        self.assertIn("/aivuda_os/api/auth/login", self.paths)
        self.assertIn("/aivuda_os/api/auth/me", self.paths)
        self.assertIn("/aivuda_os/api/apps/installed", self.paths)

    def test_automatic_login_does_not_inherit_explicit_identity(self):
        self.value("login", {"body": {"username": "alice", "password": "secret"}})
        self.value("me", headers={"Authorization": "Bearer bob-token"})
        self.assertEqual(self.value("me")["username"], "admin")
        self.assertTrue(self.call("me", {"token": "expired"})["isError"])
        self.assertTrue(self.call("me", headers={"Authorization": "Bearer expired"})["isError"])
        self.assertEqual(self.paths.count("/aivuda_os/api/auth/login"), 2)

    def test_default_account_rejected_prompts_for_current_credentials(self):
        self.auth.default_enabled = False
        result = self.call("me")
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("current username and password", text)
        self.assertNotIn("admin123", text)
        token = self.value("login", {"body": {"username": "alice", "password": "secret"}})["access_token"]
        self.assertEqual(self.value("me", {"token": token})["username"], "alice")

    def test_parallel_automatic_calls_share_one_login(self):
        with ThreadPoolExecutor(max_workers=4) as executor:
            values = list(executor.map(lambda _: self.value("me")["username"], range(8)))
        self.assertEqual(values, ["admin"] * 8)
        self.assertEqual(self.paths.count("/aivuda_os/api/auth/login"), 1)

    def test_expired_managed_token_refreshes_once(self):
        self.assertEqual(self.value("me")["username"], "admin")
        original = self.auth.validate_token
        rejected = [False]

        def validate(token):
            if token == "admin-token" and not rejected[0]:
                rejected[0] = True
                raise AuthenticationError("Expired")
            return original(token)

        with patch.object(self.auth, "validate_token", side_effect=validate):
            self.assertEqual(self.value("me")["username"], "admin")
        self.assertEqual(self.paths.count("/aivuda_os/api/auth/login"), 2)

    def test_network_failure_does_not_prompt_for_credentials(self):
        with patch.object(self.auth, "login", side_effect=RuntimeError("Backend unavailable")):
            result = self.call("me")
        self.assertTrue(result["isError"])
        self.assertNotIn("current username and password", result["content"][0]["text"])

    def test_automatic_websocket_refresh_and_explicit_token_priority(self):
        self.value("me")
        original = self.auth.validate_token
        rejected = [False]

        def validate(token):
            if token == "admin-token" and not rejected[0]:
                rejected[0] = True
                raise AuthenticationError("Expired")
            return original(token)

        with patch.object(self.auth, "validate_token", side_effect=validate):
            self.value("operation_interactive_ws", {"operation_id": "job", "data": "yes"})
        self.assertEqual(self.paths.count("/aivuda_os/api/auth/login"), 2)
        self.assertEqual(self.value("me", {"token": "alice-token"},
                                    {"Authorization": "Bearer bob-token"})["username"], "alice")

    def test_parallel_clients_keep_identity(self):
        def identity(user):
            return self.value("me", headers={"Authorization": "Bearer " + user + "-token"})["username"]
        users = ["alice", "bob"] * 8
        with ThreadPoolExecutor(max_workers=4) as executor:
            self.assertEqual(list(executor.map(identity, users)), users)

    def test_origin_checks_allow_each_gateway_origin(self):
        self.assertEqual(self.rpc("ping", headers={"Origin": "https://robot-a.local"}).status_code, 200)
        for origin in ("https://evil.local", "http://robot-a.local", "null"):
            self.assertEqual(self.rpc("ping", headers={"Origin": origin}).status_code, 403)
        self.assertEqual(self.rpc("ping", headers={"Authorization": "Basic invalid"}).status_code, 401)

    def test_api_errors_and_validation_are_preserved(self):
        self.runtime.get_detail.side_effect = AppNotInstalledError("Missing app")
        result = self.call("get_app_status", {"app_id": "missing", "token": "alice-token"})
        self.assertTrue(result["isError"])
        self.assertIn("API HTTP 404", result["content"][0]["text"])
        self.assertTrue(self.call("get_app_status", {"token": "alice-token"})["isError"])
        self.assertTrue(self.call("login", {"body": {"username": "alice", "password": "wrong"}})["isError"])

    def test_multipart_upload_uses_real_route_and_operation_queue(self):
        self.operations.start_operation.return_value = SimpleNamespace(operation_id="upload-job")
        with patch.object(apps, "_spawn_operation") as spawn, patch.object(apps, "get_installer_service") as installer:
            result = self.value("upload_app", {"token": "alice-token", "file": {
                "filename": "fixture.zip", "content_base64": base64.b64encode(b"package bytes").decode(),
            }})
            self.assertEqual(result["operation_id"], "upload-job")
            self.assertEqual(result["operator"], "alice")
            spawn.call_args[0][1]()
            self.assertEqual(installer.return_value.install_from_upload.call_args[0], (b"package bytes", "fixture.zip"))

    def test_binary_download_and_head_use_api_response(self):
        with tempfile.TemporaryDirectory() as root:
            certificate = Path(root) / "root.crt"
            certificate.write_bytes(b"certificate bytes")
            with patch.object(config, "_CADDY_LOCAL_CA_ROOT_PATH", certificate), patch.object(config, "_build_caddy_local_ca_filename", return_value="root.crt"):
                value = self.value("download_caddy_local_ca_root", {"token": "alice-token"})
                self.assertEqual(base64.b64decode(value["content_base64"]), b"certificate bytes")
                self.assertEqual(value["filename"], "root.crt")
                self.assertEqual(self.value("download_caddy_local_ca_root_head", {"token": "alice-token"})["status"], 200)

    def test_sse_operation_events_and_bounded_read(self):
        result = self.value("stream_operation_events", {"operation_id": "job", "token": "alice-token", "max_events": 1})
        self.assertEqual(result["events"][0]["data"]["status"], "completed")
        self.assertFalse(result["timed_out"])

    def test_sse_deadline_cancels_internal_request(self):
        closed = []

        async def delayed():
            try:
                await asyncio.sleep(10)
                yield b"data: {}\n\n"
            finally:
                closed.append(True)

        # Preserve the registered path/schema while replacing its ASGI handler.
        from starlette.routing import request_response
        route = next(route for route in self.app.routes if getattr(route, "name", "") == "stream_operation_events")

        async def endpoint(request):
            return StreamingResponse(delayed(), media_type="text/event-stream")

        route.app = request_response(endpoint)
        started = time.monotonic()
        value = self.value("stream_operation_events", {"operation_id": "job", "token": "alice-token", "timeout_seconds": 1})
        self.assertTrue(value["timed_out"])
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(closed, [True])

    def test_websocket_interactive_input_and_rejection(self):
        result = self.value("operation_interactive_ws", {"operation_id": "job", "data": "yes\n", "token": "alice-token"})
        self.assertEqual(result["ready"]["type"], "interactive_ready")
        self.assertEqual(result["reply"]["type"], "interactive_input_accepted")
        self.operations.submit_interactive_input.assert_called_once_with("job", "yes\n")
        self.assertTrue(self.call("operation_interactive_ws", {"operation_id": "job", "data": "yes", "token": "invalid"})["isError"])
        self.operations.get_operation.return_value = {"interactive_enabled": False}
        self.assertTrue(self.call("operation_interactive_ws", {"operation_id": "job", "data": "yes", "token": "alice-token"})["isError"])


class CaddyMigrationTests(unittest.TestCase):
    def test_old_matcher_migrates_without_losing_custom_settings(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "Caddyfile"
            original = "(aivudaos_common_route) {\n  @api path /aivuda_os/api*\n  reverse_proxy 127.0.0.1:8123\n  import custom.caddy\n}\nhttps://robot-a.local:8443 {\n  tls internal\n  import aivudaos_common_route\n}\n"
            path.write_text(original)
            service = CaddyRuntimeService(caddyfile_path=path)
            self.assertTrue(service.sync_https_hostname("robot-a"))
            self.assertEqual(path.read_text(), original.replace("/aivuda_os/api*", "/aivuda_os/api* /aivuda_os/mcp"))
            self.assertFalse(service.sync_https_hostname("robot-a"))


if __name__ == "__main__":
    unittest.main()
