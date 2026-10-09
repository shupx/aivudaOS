"""In-process HTTP/WebSocket transport for the embedded MCP adapter.

Synchronous MCP dispatch runs in a worker thread. API requests run on the main
ASGI event loop, preserving routing, middleware, validation and authorization.
No listener, DNS lookup, TLS connection or proxy round trip is involved.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import socket
import time
from email.message import Message
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit


def scope_for(url, kind, headers=()):
    parts = urlsplit(url)
    return {
        "type": kind, "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "scheme": "http" if kind == "http" else "ws",
        "method": "GET", "path": unquote(parts.path), "raw_path": parts.path.encode("ascii"),
        "root_path": "", "query_string": parts.query.encode("ascii"),
        "headers": list(headers), "server": ("aivudaos.internal", 80),
        "client": ("127.0.0.1", 0),
    }


class ASGIResponse:
    def __init__(self, loop, timeout):
        self.loop, self.timeout = loop, timeout
        self.deadline = time.monotonic() + timeout
        self.buffer = bytearray()
        self.eof = False

    async def start(self, app, request):
        self.queue = asyncio.Queue(maxsize=1)
        started = asyncio.get_running_loop().create_future()
        body_sent = False
        disconnected = asyncio.Event()
        scope = scope_for(request.full_url, "http", [
            (key.lower().encode("latin-1"), value.encode("latin-1"))
            for key, value in request.header_items()
        ])
        scope["method"] = request.get_method()

        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": request.data or b"", "more_body": False}
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.start":
                self.status = message["status"]
                self.headers = Message()
                for key, value in message.get("headers", []):
                    self.headers[key.decode("latin-1")] = value.decode("latin-1")
                started.set_result(None)
            elif message["type"] == "http.response.body":
                if message.get("body"):
                    await self.queue.put(message["body"])
                if not message.get("more_body", False):
                    await self.queue.put(None)

        async def run():
            try:
                await app(scope, receive, send)
                if not started.done():
                    started.set_exception(RuntimeError("API did not start a response"))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not started.done():
                    started.set_exception(exc)
                else:
                    await self.queue.put(exc)

        self.task = asyncio.create_task(run())
        try:
            await asyncio.wait_for(started, self.timeout)
        except BaseException:
            await self.aclose()
            raise

    def _next(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise socket.timeout("API response timed out")
        future = asyncio.run_coroutine_threadsafe(self.queue.get(), self.loop)
        try:
            chunk = future.result(timeout=remaining)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise socket.timeout("API response timed out") from None
        if isinstance(chunk, Exception):
            raise chunk
        if chunk is None:
            self.eof = True
        else:
            self.buffer.extend(chunk)

    def read(self, size=-1):
        while not self.eof and (size < 0 or len(self.buffer) < size):
            self._next()
        count = len(self.buffer) if size < 0 else min(size, len(self.buffer))
        value = bytes(self.buffer[:count])
        del self.buffer[:count]
        return value

    def readline(self, size=-1):
        while True:
            end = self.buffer.find(b"\n")
            if end >= 0 or self.eof or (size >= 0 and len(self.buffer) >= size):
                count = end + 1 if end >= 0 else len(self.buffer)
                if size >= 0:
                    count = min(count, size)
                value = bytes(self.buffer[:count])
                del self.buffer[:count]
                return value
            self._next()

    async def aclose(self):
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass

    def close(self):
        future = asyncio.run_coroutine_threadsafe(self.aclose(), self.loop)
        try:
            future.result(timeout=5)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise socket.timeout("API response cleanup timed out") from None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ASGITransport:
    def __init__(self, app, loop):
        self.app, self.loop = app, loop

    def __call__(self, request, timeout=30):
        response = ASGIResponse(self.loop, timeout)
        future = asyncio.run_coroutine_threadsafe(response.start(self.app, request), self.loop)
        try:
            future.result(timeout=timeout + 1)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise socket.timeout("API response timed out") from None
        if response.status >= 400:
            # Materialize bounded error details before releasing the ASGI task.
            import io
            try:
                detail = response.read(8192)
            finally:
                response.close()
            raise HTTPError(request.full_url, response.status, "API error", response.headers, io.BytesIO(detail))
        return response

    async def websocket(self, url, data):
        incoming, outgoing = asyncio.Queue(), asyncio.Queue(maxsize=1)
        await incoming.put({"type": "websocket.connect"})

        async def run():
            try:
                await self.app(scope_for(url, "websocket"), incoming.get, outgoing.put)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await outgoing.put(exc)
            await outgoing.put({"type": "websocket.close", "code": 1000})

        task = asyncio.create_task(run())

        async def receive(expected):
            message = await asyncio.wait_for(outgoing.get(), 30)
            if isinstance(message, Exception):
                raise message
            if message["type"] != expected:
                if message.get("code") == 1008 and message.get("reason") in ("Invalid token", "Missing token"):
                    from aivudaos.mcp_runtime import APIHTTPError
                    raise APIHTTPError(401, "Invalid token")
                raise ValueError("API WebSocket closed or rejected the request (code {0})".format(message.get("code", "unknown")))
            return message

        try:
            await receive("websocket.accept")
            ready = await receive("websocket.send")
            await incoming.put({"type": "websocket.receive", "text": json.dumps({"data": data})})
            reply = await receive("websocket.send")
            return {"ready": json.loads(ready.get("text") or ready["bytes"]),
                    "reply": json.loads(reply.get("text") or reply["bytes"])}
        finally:
            # Give the route its normal disconnect before cancelling leftovers.
            await incoming.put({"type": "websocket.disconnect", "code": 1000})
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def websocket_input(self, url, data):
        future = asyncio.run_coroutine_threadsafe(self.websocket(url, data), self.loop)
        try:
            return future.result(timeout=65)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise socket.timeout("API WebSocket timed out") from None
