"""Real backend + shipped Caddy template, HTTP and verified HTTPS integration."""
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CADDY = ROOT.parent / "resources/app-gateway/caddy"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@unittest.skipUnless(CADDY.is_file(), "ACEswarm development Caddy binary is required")
class MCPGatewayTests(unittest.TestCase):
    def test_same_backend_over_http_and_verified_https(self):
        with tempfile.TemporaryDirectory(prefix="aivudaos-mcp-gateway-") as directory:
            temp = Path(directory)
            backend_port, http_port, https_port = free_port(), free_port(), free_port()
            environment = dict(os.environ, AIVUDAOS_EMBEDDED_MODE="1",
                               AIVUDAOS_WS_ROOT=str(temp / "workspace"), PYTHONPATH=str(ROOT),
                               XDG_DATA_HOME=str(temp / "caddy-data"), XDG_CONFIG_HOME=str(temp / "caddy-config"))
            template = (ROOT / "aivudaos/resources/caddy/Caddyfile_template").read_text()
            template = template.replace("127.0.0.1:8000", "127.0.0.1:" + str(backend_port))
            template = template.replace(":80 {", "http://127.0.0.1:" + str(http_port) + " {")
            template = template.replace("https://avahihostname-placeholder.local:443", "https://localhost:" + str(https_port))
            config = temp / "Caddyfile"
            config.write_text("{\n admin off\n skip_install_trust\n auto_https disable_redirects\n}\n" + template)
            processes = []
            with (temp / "services.log").open("w+") as log:
                try:
                    processes.append(subprocess.Popen([
                        sys.executable, "-m", "uvicorn", "aivudaos.gateway.main:app", "--host", "127.0.0.1",
                        "--port", str(backend_port),
                    ], cwd=str(ROOT), env=environment, stdout=log, stderr=log))
                    subprocess.run([str(CADDY), "validate", "--config", str(config), "--adapter", "caddyfile"],
                                   cwd=str(ROOT / "aivudaos/resources"), env=environment, stdout=log, stderr=log, check=True)
                    processes.append(subprocess.Popen([str(CADDY), "run", "--config", str(config)],
                                     cwd=str(ROOT / "aivudaos/resources"), env=environment, stdout=log, stderr=log))

                    ca = temp / "caddy-data/caddy/pki/authorities/local/root.crt"
                    deadline = time.monotonic() + 20
                    while not ca.exists() and time.monotonic() < deadline:
                        self.assertTrue(all(proc.poll() is None for proc in processes), (temp / "services.log").read_text())
                        time.sleep(0.05)
                    self.assertTrue(ca.exists(), (temp / "services.log").read_text())
                    tls = ssl.create_default_context(cafile=str(ca))

                    for origin in ("http://127.0.0.1:" + str(http_port), "https://localhost:" + str(https_port)):
                        def rpc(method, params=None, token=None, request_origin=None):
                            headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
                                       "Origin": request_origin or origin}
                            if token:
                                headers["Authorization"] = "Bearer " + token
                            request = Request(origin + "/aivuda_os/mcp", method="POST", headers=headers,
                                              data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                                                               "params": params or {}}).encode())
                            with urlopen(request, context=tls, timeout=5) as response:
                                self.assertEqual(response.status, 200)
                                self.assertNotIn("mcp-session-id", response.headers)
                                return json.load(response)["result"]

                        while True:
                            try:
                                self.assertEqual(rpc("ping"), {})
                                break
                            except (URLError, HTTPError):
                                if time.monotonic() >= deadline:
                                    self.fail((temp / "services.log").read_text())
                                time.sleep(0.1)
                        self.assertEqual(len(rpc("tools/list")["tools"]), 47)
                        login = rpc("tools/call", {"name": "login", "arguments": {"body": {
                            "username": "admin", "password": "admin123",
                        }}})
                        self.assertFalse(login.get("isError"), login)
                        token = json.loads(login["content"][0]["text"])["access_token"]
                        me = rpc("tools/call", {"name": "me"}, token=token)
                        self.assertFalse(me.get("isError"), me)
                        self.assertEqual(json.loads(me["content"][0]["text"])["username"], "admin")
                        automatic = rpc("tools/call", {"name": "me"})
                        self.assertFalse(automatic.get("isError"), automatic)
                        self.assertEqual(json.loads(automatic["content"][0]["text"])["username"], "admin")
                        with self.assertRaises(HTTPError) as caught:
                            rpc("ping", request_origin="https://evil.local")
                        self.assertEqual(caught.exception.code, 403)
                finally:
                    for proc in reversed(processes):
                        proc.terminate()
                    for proc in reversed(processes):
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=5)
            for port in (backend_port, http_port, https_port):
                with socket.socket() as sock:
                    self.assertNotEqual(sock.connect_ex(("127.0.0.1", port)), 0)


if __name__ == "__main__":
    unittest.main()
