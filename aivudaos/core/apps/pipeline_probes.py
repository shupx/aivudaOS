"""Cancellable readiness checks for startup-pipeline members (Linux)."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextlib import contextmanager
import shutil
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

_TICK = 0.05
_MISSING = object()


def _network_attempt(kind, args):
    if kind == "tcp":
        import socket
        host, port = args
        # Never resolve a configurable name for this local-only probe.
        for address in (["127.0.0.1", "::1"] if host.lower() == "localhost" else [host]):
            try:
                with socket.create_connection((address, int(port)), timeout=2):
                    return True
            except OSError:
                continue
        return False

    import http.client
    url = urlsplit(args[0])
    cls = http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
    conn = cls(url.hostname, port=url.port, timeout=5)
    try:
        conn.request("GET", (url.path or "/") + ("?" + url.query if url.query else ""))
        with conn.getresponse() as response:
            return 200 <= response.status < 300
    finally:
        conn.close()


def _helper_children():
    parent = os.getpid()
    try:
        return [int(pid) for pid in Path("/proc/self/task/{}/children".format(parent)).read_text().split()]
    except FileNotFoundError:
        # Tegra kernels can omit CONFIG_PROC_CHILDREN. Only scan when waitpid
        # confirms live children remain during helper teardown.
        children = []
        for path in Path("/proc").glob("[0-9]*/stat"):
            try:
                fields = path.read_bytes().rsplit(b")", 1)[1].split()
                if int(fields[1]) == parent:
                    children.append(int(path.parent.name))
            except (OSError, ValueError, IndexError):
                continue
        return children


def _supervise(argv):
    """Own even double-forked/setsid probe children, without adopting any app PID."""
    import ctypes
    import select

    # Linux PR_SET_CHILD_SUBREAPER. This helper has exactly one job and never
    # shares descendants with the gateway or another concurrent probe.
    if ctypes.CDLL(None).prctl(36, 1, 0, 0, 0) != 0:
        raise RuntimeError("Cannot supervise readiness command")
    child = subprocess.Popen(argv, stdin=subprocess.DEVNULL)
    try:
        while child.poll() is None:
            # EOF means cancellation (also works if the gateway itself exits).
            if select.select([sys.stdin], [], [], _TICK)[0]:
                return 1
        return child.returncode
    finally:
        while True:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if pid:
                continue
            # Killing a direct child reparents its surviving children here.
            # Unreaped child PIDs cannot have been recycled by another process.
            for pid in _helper_children():
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            time.sleep(0.01)


if __name__ == "__main__":
    # Invoked via python -I and an absolute path. No project imports, shell
    # startup files or app-local Python modules are needed by the helper.
    try:
        if sys.argv[1] == "exec":
            sys.exit(0 if _supervise(sys.argv[2:]) == 0 else 1)
        sys.exit(0 if _network_attempt(sys.argv[1], sys.argv[2:]) else 1)
    except (OSError, ValueError):
        sys.exit(1)


from aivudaos.core.apps.pipeline_ros import RosProbeSession
from aivudaos.core.apps.pipeline_config import normalize_readiness
from aivudaos.core.config.ros_domain import is_ros_domain_field
from aivudaos.core.errors import AppRuntimeError, OperationCanceledError


def _domain_values(data, default, schema, path, inherited):
    schema = schema if isinstance(schema, dict) else {}
    value = data if data is not _MISSING else default
    if value is _MISSING:
        value = schema.get("default", _MISSING)
    if isinstance(value, dict) or (value is _MISSING and "properties" in schema):
        saved = data if isinstance(data, dict) else {}
        defaults = default if isinstance(default, dict) else schema.get("default", {})
        defaults = defaults if isinstance(defaults, dict) else {}
        props = schema.get("properties", {})
        for key in sorted(set(saved) | set(defaults) | set(props)):
            label = key
            if key == "value":
                label = saved.get("name") or saved.get("key") or defaults.get("name") or defaults.get("key") or key
            yield from _domain_values(saved.get(key, _MISSING), defaults.get(key, _MISSING), props.get(key),
                                      path + [str(label)], inherited)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            fallback = default[i] if isinstance(default, list) and i < len(default) else _MISSING
            yield from _domain_values(item, fallback, schema.get("items"), path + [str(i)], inherited)
    elif path and is_ros_domain_field(".".join(path), schema, value):
        if value is _MISSING or value is None or value in (-1, "-1"):
            yield inherited
        elif (isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 232
              and int(value) == value) or (isinstance(value, str) and re.fullmatch(r"[0-9]{1,3}", value)
                                           and int(value) <= 232):
            yield str(int(value))
        else:
            raise AppRuntimeError("Invalid ROS domain at {}".format(".".join(path)))


def _environment(context):
    env, data, defaults, schema = context
    env = env.copy()
    domains = set(_domain_values(data, defaults, schema, [], env.get("ROS_DOMAIN_ID", "0")))
    if len(domains) > 1:
        raise AppRuntimeError("App configuration specifies conflicting ROS domains")
    if domains:
        env["ROS_DOMAIN_ID"] = domains.pop()
    return env


# A wedged systemctl or DB read must not create an unbounded queue of threads.
_READ_POOL = ThreadPoolExecutor(max_workers=16, thread_name_prefix="pipeline-read")
_RUNTIME_READS = threading.BoundedSemaphore(16)


class _Wait:
    def __init__(self, runtime, app_id, kind, cancel, timeout):
        self.runtime = runtime
        self.app_id = app_id
        self.kind = kind
        self.cancel = cancel
        self.deadline = time.monotonic() + timeout
        self.next_live = 0.0
        self.read_state = None

    def clock(self):
        if self.cancel.is_set():
            raise OperationCanceledError("Readiness check canceled for {}".format(self.app_id))
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise AppRuntimeError("{} readiness timed out for {}".format(self.kind, self.app_id))
        return left

    def runtime_read(self, method):
        # RuntimeService can wait on e.g. systemctl or a database lock. Do not
        # hold a probe child or cancellation hostage to a stalled read.
        while not _RUNTIME_READS.acquire(timeout=min(_TICK, self.clock())):
            pass
        try:
            result = _READ_POOL.submit(method, self.app_id)
        except RuntimeError:
            _RUNTIME_READS.release()
            raise
        result.add_done_callback(lambda _: _RUNTIME_READS.release())
        while not result.done():
            remaining = self.clock()
            try:
                result.result(timeout=min(remaining, _TICK))
            except FutureTimeout:
                continue
        return result.result()

    def check(self, force=False):
        self.clock()
        if self.kind != "exited_zero" and (force or time.monotonic() >= self.next_live):
            if self.read_state is None:
                factory = getattr(self.runtime, "readiness_state_reader", None)
                self.read_state = self.runtime_read(factory) if factory else self.runtime.get_runtime_state
            if not self.runtime_read(self.read_state).running:
                raise AppRuntimeError("App {} exited before readiness".format(self.app_id))
            self.next_live = time.monotonic() + 0.75
        return self.clock()

    def sleep(self, seconds):
        until = time.monotonic() + seconds
        while True:
            left = min(self.check(), until - time.monotonic())
            if left <= 0:
                return
            self.cancel.wait(min(left, _TICK))

    def run(self, mode, args, env=None, capture=False):
        self.check()
        proc = subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), mode] + args,
                                env=env, cwd=(env or {}).get("AIVUDA_APP_INSTALL_PATH"),
                                stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                                start_new_session=True)
        output = bytearray()
        try:
            if capture:
                os.set_blocking(proc.stdout.fileno(), False)
            while True:
                left = self.check()
                done = proc.poll() is not None
                if capture:
                    chunk = proc.stdout.read(65536)
                    if chunk:
                        output.extend(chunk)
                        if len(output) > 1024 * 1024:
                            raise AppRuntimeError("ROS readiness output exceeded 1 MiB")
                        continue
                if done:
                    return proc.returncode == 0, output.decode("utf-8", errors="replace")
                self.cancel.wait(min(left, _TICK))
        finally:
            proc.stdin.close()
            if proc.stdout:
                proc.stdout.close()
            if mode != "exec" and proc.poll() is None:
                proc.kill()  # Blocking DNS, TLS and slow HTTP headers are cancellable.
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=1)
                raise AppRuntimeError("Readiness helper did not stop cleanly")


def _attempt(wait, spec, env):
    kind = wait.kind
    if kind == "tcp":
        return wait.run("tcp", [spec["host"], str(spec["port"])])[0]
    if kind == "http":
        return wait.run("http", [spec["url"]])[0]
    if kind == "command":
        return wait.run("exec", ["/bin/bash", "-c", spec["command"]], env)[0]

    # Only `command` is shell code. ROS arguments are always separate argv
    # entries; expected names and states are compared as data in Python.
    def ros(*args):
        ok, output = wait.run("exec", ["ros2"] + list(args), env, capture=True)
        return output.strip() if ok else ""

    name = "/" + spec["topic" if kind == "ros2_topic" else "node_name"].lstrip("/")
    if kind == "ros2_lifecycle":
        # ROS CLI format: active [3]. Do not match 'inactive' or diagnostic text.
        match = re.fullmatch(r"([^\s]+)(?:\s+\[[0-9]+\])?", ros("lifecycle", "get", name, "--no-daemon"))
        return bool(match and match.group(1) == spec.get("lifecycle_state", "active"))
    entity = "topic" if kind == "ros2_topic" else "node"
    # Discover directly in this app's environment. A freshly spawned ROS CLI
    # daemon would be reaped with the probe before it could warm its graph.
    if kind == "ros2_topic" and spec.get("require_message"):
        return wait.run("exec", ["ros2", "topic", "echo", name, "--once",
                                 "--qos-reliability", "best_effort"], env)[0]
    if kind == "ros2_topic" and spec.get("require_publisher"):
        return bool(re.search(r"(?im)^Publisher count:[ \t]*0*[1-9][0-9]*[ \t]*$",
                              ros("topic", "info", name, "--no-daemon")))
    return name in ros(entity, "list", "--no-daemon").splitlines()


def _wait_log(wait, spec, path):
    # Both runtime backends truncate current.log at launch. Starting at zero
    # includes output emitted before start() returned, even for an already-live app.
    pattern = spec["pattern"]
    expression = None
    bounded_search = False
    if wait.kind == "log_regex":
        try:
            import regex
        except ImportError:
            expression = re.compile(pattern)
        else:
            expression = regex.compile(pattern)
            bounded_search = True
    literal = pattern.encode()
    offset, identity, tail = 0, None, b""
    while True:
        wait.check()
        chunk = b""
        try:
            with path.open("rb") as stream:
                stat = os.fstat(stream.fileno())
                if identity != (stat.st_dev, stat.st_ino) or stat.st_size < offset:
                    offset, tail = 0, b""
                identity = (stat.st_dev, stat.st_ino)
                stream.seek(offset)
                chunk = stream.read(65536)
                offset += len(chunk)
        except FileNotFoundError:
            pass
        if chunk:
            data = tail + chunk
            if expression:
                try:
                    options = {"timeout": min(.1, wait.clock())} if bounded_search else {}
                    matched = expression.search(data.decode("utf-8", errors="replace"), **options)
                except TimeoutError as exc:
                    raise AppRuntimeError("Log regular expression exceeded its match budget") from exc
            else:
                matched = literal in data
            if matched:
                return
            tail = data[-4096:]
            continue
        wait.sleep(spec["interval_sec"])


class ReadinessProber:
    def __init__(self, runtime):
        self.runtime = runtime
        self.ros = None

    @contextmanager
    def session(self):
        self.ros = RosProbeSession()
        try:
            yield
        finally:
            self.ros.close()
            self.ros = None

    def wait(self, app_id: str, readiness_dict: dict, cancel: threading.Event) -> None:
        """Return once ready and still running, or raise on exit, timeout or cancel."""
        spec = normalize_readiness(readiness_dict, "readiness")
        kind = spec["type"]
        wait = _Wait(self.runtime, app_id, kind, cancel, spec["timeout_sec"])
        wait.check()
        if kind == "exited_zero":
            while True:
                result = self.runtime.exit_result(app_id)
                if result == 0:
                    return
                if result is not None:
                    raise AppRuntimeError("App {} exited unsuccessfully: {}".format(app_id, result))
                wait.sleep(spec["interval_sec"])
        if kind == "started":
            return
        if kind in ("log_contains", "log_regex"):
            _wait_log(wait, spec, self.runtime._app_log_path(app_id))
        elif kind == "delay":
            wait.sleep(spec["delay_sec"])
        else:
            env = None
            if kind.startswith("ros2_") or kind == "command":
                env = _environment(wait.runtime_read(self.runtime.readiness_context))
            if kind.startswith("ros2_"):
                if self.ros is not None:
                    self.ros.wait(wait, spec, env)
                    wait.check(force=True)
                    return
                if not shutil.which("ros2", path=env.get("PATH", "")):
                    raise AppRuntimeError("ros2 was not found on the app PATH. Load the ROS environment.")
            while not _attempt(wait, spec, env):
                wait.sleep(spec["interval_sec"])
        wait.check(force=True)
