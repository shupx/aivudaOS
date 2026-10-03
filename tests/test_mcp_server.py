import json
import unittest

from aivudaos.mcp_server import MCPServer


class FakeClient:
    token = "test-token"

    def __init__(self):
        self.calls = []

    def request(self, path, method="GET", payload=None):
        self.calls.append((path, method, payload))
        return {"ok": True, "path": path}


class MCPServerTests(unittest.TestCase):
    def test_tools_list_is_protocol_response(self):
        response = MCPServer().handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(response["jsonrpc"], "2.0")
        names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertEqual(names, ["aivudaos_status", "list_installed_apps", "get_app_status", "get_config", "queue_config_import"])

    def test_tool_calls_public_api(self):
        client = FakeClient()
        result = MCPServer(client).handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_installed_apps", "arguments": {}}})
        self.assertFalse(result["result"].get("isError", False))
        self.assertEqual(client.calls, [("/api/apps/installed", "GET", None)])
        self.assertTrue(json.loads(result["result"]["content"][0]["text"])["ok"])

    def test_config_import_is_queued_via_public_api(self):
        client = FakeClient()
        MCPServer(client).call_tool("queue_config_import", {"document": {"apps": []}, "app_store_base_url": "http://store"})
        self.assertEqual(client.calls[0], ("/api/config/import", "POST", {"document": {"apps": []}, "app_store_base_url": "http://store"}))


if __name__ == "__main__":
    unittest.main()
