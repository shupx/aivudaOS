"""Python 3.8 compatible stateless Streamable HTTP and OpenAPI tool adapter.

Bundled with each independently distributed package to avoid cross-service
dependencies. All operations go through the authenticated backend API.
"""
from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import secrets
import socket
import time
import threading
import uuid
from email.message import Message
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from fastapi import FastAPI, Request as HTTPRequest
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from fastapi.openapi.utils import get_openapi
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.routing import WebSocketRoute


VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
FILE_SCHEMA = {
    "type": "object", "properties": {
        "filename": {"type": "string"}, "content_base64": {"type": "string"},
        "content_type": {"type": "string", "default": "application/octet-stream"},
    }, "required": ["filename", "content_base64"], "additionalProperties": False,
    "description": "File bytes encoded as base64; server-local paths are not accepted.",
}


def expand_schema(value, document, seen=()):
    if isinstance(value, list):
        return [expand_schema(item, document, seen) for item in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        ref = value["$ref"]
        if ref in seen:
            raise ValueError("Recursive API schema: " + ref)
        target = document
        for key in ref.lstrip("#/").split("/"):
            target = target[key.replace("~1", "/").replace("~0", "~")]
        merged = dict(target, **{key: item for key, item in value.items() if key != "$ref"})
        return expand_schema(merged, document, seen + (ref,))
    if value.get("format") == "binary":
        return copy.deepcopy(FILE_SCHEMA)
    return {key: expand_schema(item, document, seen) for key, item in value.items()}


def form_value(value):
    if isinstance(value, (dict, list, bool)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def multipart(payload):
    boundary = "mcp-" + uuid.uuid4().hex
    chunks = []
    for name, value in payload.items():
        if value is None:
            continue
        if any(char in name for char in '\r\n"'):
            raise ValueError("Invalid multipart field name")
        disposition = 'Content-Disposition: form-data; name="' + name + '"'
        if isinstance(value, dict) and "content_base64" in value:
            filename = value["filename"]
            content_type = value.get("content_type", "application/octet-stream")
            if any(char in filename for char in '\r\n"\\') or any(char in content_type for char in "\r\n"):
                raise ValueError("Invalid file metadata")
            disposition += '; filename="' + filename + '"\r\nContent-Type: ' + content_type
            data = base64.b64decode(value["content_base64"], validate=True)
        else:
            data = form_value(value).encode("utf-8")
        chunks.append(("--" + boundary + "\r\n" + disposition + "\r\n\r\n").encode("utf-8") + data + b"\r\n")
    chunks.append(("--" + boundary + "--\r\n").encode("ascii"))
    return b"".join(chunks), "multipart/form-data; boundary=" + boundary


class APIHTTPError(ValueError):
    def __init__(self, status, detail):
        self.status = status
        super().__init__("API HTTP {0}: {1}".format(status, detail))


class APIClient:
    def __init__(self, prefix, default_url, auth_mode, base_url=None, token=None, opener=None):
        self.base_url = (base_url or os.environ.get(prefix + "_MCP_BASE_URL", default_url)).rstrip("/")
        self.token = token if token is not None else os.environ.get(prefix + "_MCP_TOKEN", "")
        self.auth_mode = auth_mode
        self._managed_token = False
        self._login_lock = threading.Lock()
        self.username = os.environ.get(prefix + "_MCP_USERNAME", "admin")
        self.password = os.environ.get(prefix + "_MCP_PASSWORD", "admin123")
        self.opener = opener or urlopen
        self.max_bytes = int(os.environ.get(prefix + "_MCP_MAX_BYTES", str(64 * 1024 * 1024)))

    def url(self, path, query=None):
        return self.base_url + path + (("?" + urlencode(query, doseq=True)) if query else "")

    def ensure_token(self, expired_token=None):
        with self._login_lock:
            if self.token and (expired_token is None or self.token != expired_token):
                return self.token
            path = "/api/auth/login" if self.auth_mode == "query" else "/dev/auth/login"
            content_type = "application/json" if self.auth_mode == "query" else "application/x-www-form-urlencoded"
            try:
                result = self._request(path, "POST", {"username": self.username, "password": self.password},
                                       content_type=content_type)
            except APIHTTPError as exc:
                if exc.status == 401:
                    raise ValueError("Backend login failed with the configured/default account. Ask the user for the current username and password, then use the login tool and pass its token to subsequent calls.") from None
                raise
            token = result.get("access_token")
            if not isinstance(token, str) or not token:
                raise ValueError("Backend login did not return an access token")
            self.token = token
            self._managed_token = True
            return token

    def request(self, path, method="GET", payload=None, query=None, headers=None, content_type="application/json", stream=None):
        query, headers = dict(query or {}), {key.lower(): value for key, value in (headers or {}).items()}
        login_route = path in ("/api/auth/login", "/dev/auth/login", "/dev/auth/register")
        protected = not login_route and (path.startswith("/api/") if self.auth_mode == "query" else path.startswith("/dev/"))
        explicit = "token" in query if self.auth_mode == "query" else "authorization" in headers
        token = self.token
        if protected and not explicit:
            token = self.ensure_token()
        if token and not explicit and not login_route:
            if self.auth_mode == "query":
                query["token"] = token
            else:
                headers["authorization"] = "Bearer " + token
        try:
            return self._request(path, method, payload, query, headers, content_type, stream)
        except APIHTTPError as exc:
            if exc.status != 401 or not protected or explicit or not self._managed_token:
                raise
            token = self.ensure_token(expired_token=token)
            if self.auth_mode == "query":
                query["token"] = token
            else:
                headers["authorization"] = "Bearer " + token
            return self._request(path, method, payload, query, headers, content_type, stream)

    def _request(self, path, method="GET", payload=None, query=None, headers=None, content_type="application/json", stream=None):
        query, headers = dict(query or {}), dict(headers or {})
        headers["Accept"] = "application/json, text/event-stream, */*"
        body = None
        if payload is not None:
            if content_type == "multipart/form-data":
                body, content_type = multipart(payload)
            elif content_type == "application/x-www-form-urlencoded":
                body = urlencode({key: form_value(value) for key, value in payload.items() if value is not None}).encode("utf-8")
            else:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = content_type
            if len(body) > self.max_bytes:
                raise ValueError("API upload exceeds MCP_MAX_BYTES")
        req = Request(self.url(path, query), data=body, method=method, headers=headers)
        try:
            with self.opener(req, timeout=stream["timeout_seconds"] if stream else 30) as response:
                if stream:
                    return self.read_events(response, stream)
                raw = response.read(self.max_bytes + 1)
                if len(raw) > self.max_bytes:
                    raise ValueError("API response exceeds MCP_MAX_BYTES")
                media_type = response.headers.get("Content-Type", "").split(";")[0]
                if method == "HEAD":
                    return {"status": response.status, "headers": dict(response.headers)}
                if not raw:
                    return {}
                if media_type == "application/json" or media_type.endswith("+json"):
                    return json.loads(raw.decode("utf-8"))
                metadata = Message()
                metadata["Content-Disposition"] = response.headers.get("Content-Disposition", "")
                return {"content_type": media_type or "application/octet-stream", "filename": metadata.get_filename(),
                        "content_disposition": response.headers.get("Content-Disposition", ""),
                        "content_base64": base64.b64encode(raw).decode("ascii"), "size": len(raw)}
        except HTTPError as exc:
            detail = exc.read(8192).decode("utf-8", errors="replace")
            raise APIHTTPError(exc.code, detail) from None

    def read_events(self, response, options):
        events, lines = [], []
        deadline = time.monotonic() + options["timeout_seconds"]
        size, timed_out = 0, False
        try:
            while len(events) < options["max_events"] and time.monotonic() < deadline:
                line = response.readline(self.max_bytes + 1)
                if not line:
                    break
                size += len(line)
                if size > self.max_bytes:
                    raise ValueError("Event stream exceeds MCP_MAX_BYTES")
                text = line.decode("utf-8").rstrip("\r\n")
                if text:
                    lines.append(text)
                elif lines:
                    event, data = "message", []
                    for item in lines:
                        if item.startswith("event:"):
                            event = item[6:].lstrip()
                        elif item.startswith("data:"):
                            data.append(item[5:].lstrip())
                    if data:
                        value = "\n".join(data)
                        try:
                            value = json.loads(value)
                        except ValueError:
                            pass
                        events.append({"event": event, "data": value})
                    lines = []
            timed_out = time.monotonic() >= deadline
        except (socket.timeout, TimeoutError):
            timed_out = True
        return {"events": events, "timed_out": timed_out}


class OpenAPIServer:
    def __init__(self, name, client, api, aliases):
        self.name, self.client = name, client
        self.tools, self.operations = [], {}
        schema_routes = []
        for route in api.routes:
            if isinstance(route, APIRoute):
                for method in sorted(route.methods):
                    single = copy.copy(route)
                    single.methods = {method}
                    single.operation_id = route.name + "_" + method.lower()
                    schema_routes.append(single)
        document = get_openapi(title=name, version="2.0", routes=schema_routes)
        routes = {(method.lower(), route.path): route for route in api.routes if isinstance(route, APIRoute) for method in route.methods}
        for path, methods in document["paths"].items():
            for method, operation in methods.items():
                if (method, path) not in routes:
                    continue
                route = routes[(method, path)]
                tool_name = aliases.get((method.upper(), path), route.name + ("_head" if method == "head" else ""))
                schema = {"type": "object", "properties": {}, "additionalProperties": False}
                required = []
                parameters = operation.get("parameters", [])
                for param in parameters:
                    key = param["name"]
                    schema["properties"][key] = expand_schema(param["schema"], document)
                    default_auth = (key == "token" and client.auth_mode == "query") or (key == "authorization" and client.auth_mode == "bearer")
                    if param.get("required") and not default_auth:
                        required.append(key)
                body = operation.get("requestBody")
                content_type = None
                if body:
                    content_type = next(iter(body["content"]))
                    body_schema = expand_schema(body["content"][content_type]["schema"], document)
                    if content_type == "application/json":
                        schema["properties"]["body"] = body_schema
                        if body.get("required"):
                            required.append("body")
                    else:
                        schema["properties"].update(body_schema.get("properties", {}))
                        required.extend(body_schema.get("required", []))
                stream = path.endswith("/events")
                if stream:
                    schema["properties"].update({
                        "max_events": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
                        "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 60, "default": 20},
                    })
                if required:
                    schema["required"] = required
                self.operations[tool_name] = (path, method.upper(), parameters, content_type, stream)
                self.add_tool(tool_name, "{0} {1}. {2}".format(method.upper(), path, operation.get("description") or operation.get("summary", route.name)), schema)
        for route in api.routes:
            if isinstance(route, WebSocketRoute):
                self.operations[route.name] = (route.path, "WEBSOCKET", [], None, False)
                self.add_tool(route.name, "Send interactive input and read acknowledgement over " + route.path, {
                    "type": "object", "properties": {
                        "operation_id": {"type": "string"}, "token": {"type": "string"},
                        "data": {"type": "string"},
                    }, "required": ["operation_id", "data"], "additionalProperties": False,
                })

    def add_tool(self, name, description, schema):
        if any(tool["name"] == name for tool in self.tools):
            raise ValueError("Duplicate MCP tool: " + name)
        Draft202012Validator.check_schema(schema)
        self.tools.append({"name": name, "description": description, "inputSchema": schema})

    def call_tool(self, name, arguments):
        if name not in self.operations:
            raise ValueError("Unknown tool: " + name)
        arguments = dict(arguments)
        # Preserve the original config-import convenience arguments.
        if name == "queue_config_import" and "document" in arguments:
            arguments["body"] = {key: arguments.pop(key) for key in ("document", "app_store_base_url")}
        tool = next(tool for tool in self.tools if tool["name"] == name)
        try:
            Draft202012Validator(tool["inputSchema"]).validate(arguments)
        except ValidationError as exc:
            path_text = ".".join(str(item) for item in exc.absolute_path) or "arguments"
            raise ValueError("Invalid tool arguments at {0} ({1})".format(path_text, exc.validator)) from None
        path, method, parameters, content_type, stream = self.operations[name]
        if method == "WEBSOCKET":
            return self.websocket_input(path, arguments)
        query, headers = {}, {}
        fields = dict(arguments)
        for param in parameters:
            key = param["name"]
            if key not in arguments:
                continue
            value = fields.pop(key)
            if param["in"] == "path":
                path = path.replace("{" + key + "}", quote(str(value), safe=""))
            elif param["in"] == "query":
                query[key] = str(value).lower() if isinstance(value, bool) else value
            elif param["in"] == "header":
                headers[key.lower()] = str(value)
        options = None
        if stream:
            options = {"max_events": fields.pop("max_events", 100), "timeout_seconds": fields.pop("timeout_seconds", 20)}
        payload = fields.get("body") if content_type == "application/json" else fields if content_type else None
        return self.client.request(path, method, payload=payload, query=query, headers=headers,
                                   content_type=content_type or "application/json", stream=options)

    def websocket_input(self, path, arguments):
        if hasattr(self.client, "websocket_input"):
            return self.client.websocket_input(path, arguments)
        from websocket import create_connection, WebSocketBadStatusException

        token = arguments["token"] if "token" in arguments else self.client.ensure_token()
        if not token:
            raise ValueError("An API token is required")
        path = path.replace("{operation_id}", quote(arguments["operation_id"], safe=""))
        parts = urlsplit(self.client.url(path, {"token": token}))
        url = urlunsplit(("wss" if parts.scheme == "https" else "ws", parts.netloc, parts.path, parts.query, ""))
        try:
            connection = create_connection(url, timeout=30)
        except WebSocketBadStatusException as exc:
            if exc.status_code != 401 or "token" in arguments or not self.client._managed_token:
                raise
            token = self.client.ensure_token(expired_token=token)
            parts = urlsplit(self.client.url(path, {"token": token}))
            url = urlunsplit(("wss" if parts.scheme == "https" else "ws", parts.netloc, parts.path, parts.query, ""))
            connection = create_connection(url, timeout=30)
        try:
            ready = json.loads(connection.recv())
            connection.send(json.dumps({"data": arguments["data"]}))
            return {"ready": ready, "reply": json.loads(connection.recv())}
        finally:
            connection.close()

    def handle(self, message):
        request_id = message.get("id") if isinstance(message, dict) else None
        error = lambda code, text: {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": text}}
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return error(-32600, "Invalid Request")
        method = message["method"]
        if "id" not in message:
            return None
        if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
            request_id = None
            return error(-32600, "Invalid request id")
        params = message.get("params", {})
        if not isinstance(params, dict):
            return error(-32602, "Invalid params")
        if method == "initialize":
            version = params.get("protocolVersion")
            result = {"protocolVersion": version if version in VERSIONS else VERSIONS[0],
                      "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": self.name, "version": "2.0"}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": self.tools}
        elif method == "tools/call":
            if not isinstance(params.get("name"), str) or not isinstance(params.get("arguments", {}), dict):
                return error(-32602, "Invalid tool params")
            try:
                value = self.call_tool(params["name"], params.get("arguments", {}))
                result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}
            except Exception as exc:
                result = {"isError": True, "content": [{"type": "text", "text": str(exc)}]}
        else:
            return error(-32601, "Method not found")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


def create_http_app(server, access_token="", allowed_hosts=("127.0.0.1", "localhost", "::1"), allowed_origins=(),
                    server_factory=None, include_health=True):
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)

    async def health():
        return {"status": "ok", "transport": "streamable-http", "server": server.name}

    if include_health:
        app.add_api_route("/health", health, methods=["GET"])

    @app.api_route("/mcp", methods=["POST", "GET", "DELETE"], include_in_schema=False)
    async def mcp(request: HTTPRequest):
        try:
            hostname = urlsplit("//" + request.headers.get("host", "")).hostname
        except ValueError:
            return Response(status_code=403)
        if not hostname or (allowed_hosts is not None and hostname not in allowed_hosts):
            return Response(status_code=403)
        origin = request.headers.get("origin")
        if origin and origin not in allowed_origins and origin != "{0}://{1}".format(request.url.scheme, request.url.netloc):
            return Response(status_code=403)
        if access_token and not secrets.compare_digest(request.headers.get("authorization", "").encode("utf-8"), ("Bearer " + access_token).encode("utf-8")):
            return Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})
        try:
            request_server = server_factory(request) if server_factory else server
        except ValueError:
            return Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})
        if request.headers.get("mcp-session-id"):
            return Response(status_code=404)
        if request.method != "POST":
            return Response(status_code=405, headers={"Allow": "POST"})
        version = request.headers.get("mcp-protocol-version", "2025-03-26")
        if version not in VERSIONS:
            return Response(status_code=400)
        accept = request.headers.get("accept", "")
        if "application/json" not in accept or "text/event-stream" not in accept:
            return Response(status_code=406)
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            return Response(status_code=415)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > request_server.client.max_bytes:
                return Response(status_code=413)
        try:
            message = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, status_code=400)
        if isinstance(message, list) and message and version != "2025-06-18":
            def handle_batch():
                responses = [request_server.handle(item) for item in message]
                return [item for item in responses if item is not None]

            responses = await run_in_threadpool(handle_batch)
            return JSONResponse(responses) if responses else Response(status_code=202)
        if not isinstance(message, dict):
            return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}, status_code=400)
        response = await run_in_threadpool(request_server.handle, message)
        if response is None:
            return Response(status_code=202)
        return JSONResponse(response)

    return app


def serve(server, prefix, default_port):
    import uvicorn

    parser = argparse.ArgumentParser(description=server.name + " Streamable HTTP server")
    parser.add_argument("--host", default=os.environ.get(prefix + "_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get(prefix + "_MCP_PORT", str(default_port))))
    args = parser.parse_args()
    access_token = os.environ.get(prefix + "_MCP_ACCESS_TOKEN", "")
    if args.host not in ("127.0.0.1", "localhost", "::1") and not access_token:
        parser.error(prefix + "_MCP_ACCESS_TOKEN is required when binding outside loopback")
    hosts = tuple(os.environ.get(prefix + "_MCP_ALLOWED_HOSTS", "127.0.0.1,localhost,::1," + args.host).split(","))
    origins = tuple(filter(None, os.environ.get(prefix + "_MCP_ALLOWED_ORIGINS", "").split(",")))
    uvicorn.run(create_http_app(server, access_token, hosts, origins), host=args.host, port=args.port)
