"""Import TestReadinessProbes into test_startup_pipeline for suite discovery."""
import builtins
import io
import json
import os
import shlex
import signal
import socket
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import Future
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aivudaos.core.apps.pipeline_probes import ReadinessProber
from aivudaos.core.apps.process_cleanup import process_stat
from aivudaos.core.apps.runtime import RuntimeService
from aivudaos.core.errors import AppRuntimeError, OperationCanceledError


class TestReadinessProbes(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.cancel = threading.Event()
        self.alive = True
        config = self.config = Mock()
        config.get_os_config.return_value.data = {"runtime_environment": {
            "PATH": str(self.root) + os.pathsep + os.environ.get("PATH", ""),
            "ROS_DOMAIN_ID": "3", "EXTRA_SETTING": "two words",
        }}
        config.get_sys_config.return_value.data = {"sys": {"ros2_default_domain_id": 9}}
        config.get_app_config.return_value.data = {"camera": {"ros_domain_id": 42}}
        version = Mock()
        version.active_version.return_value = "1.0"
        self.runtime = RuntimeService(version, config, Mock())
        self.runtime.get_runtime_state = Mock(side_effect=lambda app: SimpleNamespace(running=self.alive))
        self.runtime.readiness_state_reader = lambda app: self.runtime.get_runtime_state
        self.manifest = SimpleNamespace(config_schema={}, default_config={})
        self.runtime._get_manifest = Mock(return_value=self.manifest)
        self.runtime._build_config_env = Mock(return_value={"AIVUDA_APP_INSTALL_PATH": str(self.root)})
        self.prober = ReadinessProber(self.runtime)

    def wait(self, kind, **fields):
        return self.prober.wait("camera", dict({"type": kind, "timeout_sec": 3, "interval_sec": .05}, **fields),
                                self.cancel)

    def later(self, seconds, action):
        timer = threading.Timer(seconds, action)
        timer.start()
        self.addCleanup(timer.cancel)

    def test_started_requires_live_app_and_default_is_immediate(self):
        self.assertIsNone(self.prober.wait("camera", {}, self.cancel))
        self.alive = False
        with self.assertRaisesRegex(AppRuntimeError, "exited before readiness"):
            self.wait("started")
        self.cancel.set()
        with self.assertRaisesRegex(OperationCanceledError, "canceled"):
            self.wait("started")
        self.runtime._get_manifest.assert_not_called()

    def test_delay_checks_liveness_and_uses_deadline(self):
        start = time.monotonic()
        self.wait("delay", delay_sec=.06)
        self.assertGreaterEqual(time.monotonic() - start, .06)
        with self.assertRaisesRegex(AppRuntimeError, "timed out"):
            self.wait("delay", delay_sec=5, timeout_sec=.12)
        self.later(.05, lambda: setattr(self, "alive", False))
        with self.assertRaisesRegex(AppRuntimeError, "exited before readiness"):
            self.wait("delay", delay_sec=20, interval_sec=20)

    def test_blocked_runtime_query_does_not_block_cancellation(self):
        release = threading.Event()
        self.runtime.get_runtime_state.side_effect = lambda app: release.wait(5)
        self.later(.08, self.cancel.set)
        try:
            started = time.monotonic()
            with self.assertRaisesRegex(OperationCanceledError, "canceled"):
                self.wait("started")
            self.assertLess(time.monotonic() - started, 1)
        finally:
            release.set()

    def test_tcp_retries_until_listening_and_rejects_remote_hosts(self):
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            port = server.getsockname()[1]
            self.later(.15, server.listen)
            self.wait("tcp", host="LOCALHOST", port=port)
            self.wait("tcp", port=port)
        with self.assertRaisesRegex(ValueError, "loopback"):
            self.wait("tcp", host="192.0.2.1", port=port)
        with self.assertRaisesRegex(AppRuntimeError, "timed out"):
            self.wait("tcp", port=port, timeout_sec=.2, interval_sec=20)

    def http_server(self, action):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                action(self)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        t = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
        t.start()
        self.addCleanup(server.server_close)
        self.addCleanup(t.join, 2)
        self.addCleanup(server.shutdown)
        return "http://127.0.0.1:{}/ready?check=1".format(server.server_port)

    def test_http_requires_2xx_retries_and_does_not_follow_redirects(self):
        seen = []
        statuses = [302, 503, 204]

        def serve(request):
            seen.append(request.path)
            request.send_response(statuses[len(seen) - 1])
            request.send_header("Location", "/different")
            request.end_headers()

        self.wait("http", url=self.http_server(serve))
        self.assertEqual(seen, ["/ready?check=1"] * 3)

    def test_http_stalled_response_is_cancellable(self):
        release = threading.Event()

        def serve(_request):
            self.cancel.set()
            release.wait(5)

        url = self.http_server(serve)
        try:
            started = time.monotonic()
            with self.assertRaisesRegex(OperationCanceledError, "canceled"):
                self.wait("http", url=url, interval_sec=60)
            self.assertLess(time.monotonic() - started, 1.5)
        finally:
            release.set()

    def fake_ros(self):
        exe = self.root / "ros2"
        exe.write_text("#!" + sys.executable + "\n" + '''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with Path("calls").open("a") as log:
    print(json.dumps([args, os.environ["ROS_DOMAIN_ID"], os.environ["EXTRA_SETTING"]]), file=log)
if args == ["node", "list", "--no-daemon"]:
    print("/robot/driver_backup\\n/robot/driver")
elif args == ["topic", "list", "--no-daemon"]:
    print("/pose")
elif args == ["topic", "info", "/pose", "--no-daemon"]:
    # First try has subscribers but no publisher.
    count = sum('"info"' in line for line in Path("calls").read_text().splitlines())
    print("Type: geometry_msgs/msg/Pose\\nPublisher count:", int(count > 1))
    print("Subscription count: 4")
elif args == ["lifecycle", "get", "/driver", "--no-daemon"]:
    print("inactive [2]" if Path("inactive").exists() else "active [3]")
else:
    sys.exit(2)
''')
        exe.chmod(0o755)

    def test_ros_node_topic_and_lifecycle_match_exact_output_and_share_app_env(self):
        self.fake_ros()
        self.wait("ros2_node", node_name="robot/driver")
        self.wait("ros2_topic", topic="/pose", require_publisher=True)
        self.wait("ros2_lifecycle", node_name="driver")
        calls = [json.loads(line) for line in (self.root / "calls").read_text().splitlines()]
        self.assertEqual([c[0] for c in calls], [["node", "list", "--no-daemon"],
                         ["topic", "info", "/pose", "--no-daemon"], ["topic", "info", "/pose", "--no-daemon"],
                         ["lifecycle", "get", "/driver", "--no-daemon"]])
        self.assertTrue(all(c[1:] == ["42", "two words"] for c in calls))
        with self.assertRaisesRegex(AppRuntimeError, "timed out"):
            self.wait("ros2_node", node_name="/robot", timeout_sec=.3)
        (self.root / "inactive").touch()
        with self.assertRaisesRegex(AppRuntimeError, "timed out"):
            self.wait("ros2_lifecycle", node_name="driver", timeout_sec=.3)
        self.wait("ros2_lifecycle", node_name="driver", lifecycle_state="inactive")

    def test_ros_worker_wakes_for_batched_requests_and_idle_eof(self):
        from aivudaos.core.apps.pipeline_ros_worker import serve

        triggered = threading.Event()
        batch_queued = threading.Event()
        close_input = threading.Event()
        response = io.StringIO()
        node = Mock()
        node.create_guard_condition.return_value.trigger.side_effect = triggered.set
        node.get_node_names_and_namespaces.return_value = [("driver", "/")]

        def lines():
            for name in ("driver", "missing"):
                yield json.dumps({"token": name, "spec": {"type": "ros2_node", "node_name": name}})
            batch_queued.set()
            close_input.wait(5)

        def spin_for_input(registered_node, incoming):
            self.assertIs(registered_node, node)
            if response.tell():
                self.assertEqual([json.loads(line) for line in response.getvalue().splitlines()], [
                    {"token": "driver", "ready": True}, {"token": "missing", "ready": False}])
                close_input.set()
            else:
                self.assertTrue(batch_queued.wait(2))  # Two triggers coalesced into one wake.
            self.assertTrue(triggered.wait(2))
            triggered.clear()
            node.create_guard_condition.call_args[0][0]()
            self.assertTrue(incoming.done())

        ros = Mock()
        ros.create_node.return_value = node
        ros.spin_until_future_complete.side_effect = spin_for_input
        modules = {"rclpy": ros, "rclpy.task": SimpleNamespace(Future=Future), "lifecycle_msgs.srv": None}
        try:
            with patch.dict(sys.modules, modules):
                serve(lines(), response)
        finally:
            close_input.set()
        self.assertEqual(ros.spin_until_future_complete.call_count, 2)
        node.destroy_node.assert_called_once()
        ros.shutdown.assert_called_once()

    def test_message_overlays_load_in_order_and_metadata_probes_share_a_worker(self):
        from aivudaos.core.apps.pipeline_ros import RosProbeSession

        app = self.root / "app $(unused)"
        scripts = ["install/local_setup.bash", "install/setup.bash", "nested/install/local_setup.bash"]
        system = self.root / "system.bash"
        system.write_text("export LOADED=system\n")
        for i, name in enumerate(scripts):
            script = app / name
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text('export LOADED="${LOADED},%d"\necho "overlay diagnostic"\n' % i)
        # This executable stands in for the ROS Python interpreter, after Bash setup.
        interpreter = self.root / "fixture-python"
        interpreter.write_text("#!" + sys.executable + "\n" + """
import json, os, sys
for line in sys.stdin:
    req = json.loads(line)
    if "spec" in req:
        print("native diagnostic", flush=True)
        print("[]", flush=True)
        ok = os.environ["LOADED"] == req["spec"]["expected"]
        print(json.dumps({"token": req["token"], "ready": ok, "error": None if ok else os.environ["LOADED"]}), flush=True)
""")
        interpreter.chmod(0o755)
        ros = self.root / "ros2"
        ros.write_text("#!" + str(interpreter) + "\n")
        session = RosProbeSession()
        self.addCleanup(session.close)
        env = dict(os.environ, AIVUDA_APP_INSTALL_PATH=str(app))
        wait = Mock()
        wait.check.return_value = 1
        with patch("aivudaos.core.apps.pipeline_ros.ros_installation", return_value=(str(ros), str(system))):
            for path, message, expected in [(app, True, "system,0,1,2"), (app, False, "system"),
                                            (self.root / "empty", False, "system"), (app, True, "system,0,1,2")]:
                session.wait(wait, {"require_message": message, "expected": expected}, dict(env, AIVUDA_APP_INSTALL_PATH=str(path)))
        self.assertEqual(len(session.workers), 2)

    def test_ros_worker_uses_publisher_qos_and_checks_fast_lifecycle_reply(self):
        from aivudaos.core.apps.pipeline_ros_worker import serve

        qos = SimpleNamespace(DurabilityPolicy=SimpleNamespace(TRANSIENT_LOCAL="latched"),
                              ReliabilityPolicy=SimpleNamespace(RELIABLE="reliable"),
                              HistoryPolicy=SimpleNamespace(KEEP_LAST="last"), QoSProfile=SimpleNamespace,
                              qos_profile_sensor_data=object())
        def publisher(durability, reliability, kind="pkg/msg/T"):
            return SimpleNamespace(topic_type=kind, qos_profile=SimpleNamespace(durability=durability, reliability=reliability))
        volatile = publisher("volatile", "reliable")
        best_effort = publisher("latched", "best_effort")
        latched = publisher("latched", "reliable")
        class NoTypeSupportImportedException(Exception):
            pass

        node, ros, utilities = Mock(), Mock(), Mock()
        node.create_subscription.side_effect = [object(), object(), NoTypeSupportImportedException()]
        ros.create_node.return_value = node
        node.get_publishers_info_by_topic.side_effect = [[], [volatile, best_effort], [volatile, latched],
                                                          [latched, publisher("latched", "reliable", "other/msg/T")], [latched], [latched]]
        utilities.get_message.side_effect = [object(), object(), ModuleNotFoundError("pkg"), object()]
        future = Future()
        node.create_client.return_value.call_async.return_value = future
        queued = threading.Event()
        def spin(registered_node, result, timeout_sec=None):
            self.assertIs(registered_node, node)
            if result is future:
                self.assertEqual(timeout_sec, .1)
                result.set_result(SimpleNamespace(current_state=SimpleNamespace(label="active")))
            else:
                self.assertTrue(queued.wait(2))
                node.create_guard_condition.call_args[0][0]()
        ros.spin_until_future_complete.side_effect = spin
        topic = {"type": "ros2_topic", "topic": "/map", "require_message": True}
        def lines():
            for token in ["waiting", "waiting", "waiting", "multiple", "missing", "no_extension"]:
                yield json.dumps({"token": token, "spec": topic})
            yield json.dumps({"token": "state", "spec": {"type": "ros2_lifecycle", "node_name": "/driver", "lifecycle_state": "active"}})
            queued.set()

        response = io.StringIO()
        modules = {"rclpy": ros, "rclpy.task": SimpleNamespace(Future=Future), "rclpy.qos": qos,
                   "rclpy.exceptions": SimpleNamespace(NoTypeSupportImportedException=NoTypeSupportImportedException),
                   "lifecycle_msgs.srv": Mock(), "rosidl_runtime_py.utilities": utilities}
        with patch.dict(sys.modules, modules):
            serve(lines(), response)
        replies = [json.loads(line) for line in response.getvalue().splitlines()]
        self.assertEqual([r["ready"] for r in replies[:3]], [False] * 3)
        self.assertIn("Multiple message types", replies[3]["error"])
        self.assertRegex(replies[4]["error"], "Python typesupport.*pkg/msg/T.*log_contains.*require_publisher")
        self.assertEqual(replies[4]["error"], replies[5]["error"])
        self.assertTrue(replies[6]["ready"])
        first, second = node.create_subscription.call_args_list[:2]
        self.assertIs(first[0][3], qos.qos_profile_sensor_data)
        self.assertEqual(vars(second[0][3]), dict(history="last", depth=1, reliability="reliable", durability="latched"))

    def test_ros_fields_are_never_shell_code(self):
        self.fake_ros()
        for kind, field in (("ros2_topic", "topic"), ("ros2_node", "node_name"), ("ros2_lifecycle", "node_name")):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.wait(kind, **{field: "/a;touch BAD"})
        with self.assertRaisesRegex(AppRuntimeError, "timed out"):
            self.wait("ros2_lifecycle", node_name="driver", lifecycle_state="$(touch BAD)", timeout_sec=.3)
        self.assertFalse((self.root / "BAD").exists())

    def test_command_retries_and_uses_active_config_defaults_or_inheritance(self):
        self.manifest.config_schema = {"properties": {"lane": {"x-ros-domain": True}}}
        self.manifest.default_config = {"lane": "11"}
        for data, domain in [({}, "11"), ({"lane": "0"}, "0"), ({"lane": None}, "9"), ({"lane": -1}, "9")]:
            with self.subTest(data=data), patch("aivudaos.core.apps.runtime.has_ros2", return_value=True):
                self.config.get_app_config.return_value.data = data
                command = 'test "$EXTRA_SETTING" = "two words" && test "$ROS_DOMAIN_ID" = {} && test -f flag'.format(domain)
                self.later(.1, (self.root / "flag").touch)
                self.wait("command", command=command)
                (self.root / "flag").unlink()
        self.config.get_app_config.return_value.data = {"lane": "10", "ros": {"domain_id": 2}}
        with self.assertRaisesRegex(AppRuntimeError, "conflicting ROS domains"):
            self.wait("command", command="touch BAD")
        self.assertFalse((self.root / "BAD").exists())

    def test_named_array_domains_agree_and_absent_fields_preserve_launch_domain(self):
        self.config.get_app_config.return_value.data = {"params": [
            {"name": "ROS_DOMAIN_ID", "value": 12}, {"key": "domain_id", "value": "12"}]}
        self.wait("command", command='test "$ROS_DOMAIN_ID" = 12')
        self.config.get_app_config.return_value.data = {}
        with patch("aivudaos.core.apps.runtime.has_ros2", return_value=False):
            self.wait("command", command='test "$ROS_DOMAIN_ID" = 9')

    def test_command_descendants_cleaned_after_success_cancel_timeout_and_app_exit(self):
        # A double-forked session escapes killpg(), even when the leader exits
        # before its first poll. Verify that this command cannot leave it behind.
        script = self.root / "spawn.py"
        script.write_text('''
import os, signal, time
from pathlib import Path
if os.fork():
    os._exit(0)
os.setsid()
if os.fork():
    os._exit(0)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
Path("child").write_text(str(os.getpid()))
time.sleep(30)
''')
        pidfile = self.root / "child"
        for mode in ("success", "cancel", "timeout", "exit"):
            with self.subTest(mode=mode):
                self.cancel.clear()
                self.alive = True
                command = '{} spawn.py; while [ ! -s child ]; do sleep .01; done; '.format(shlex.quote(sys.executable))
                command += "exit 0" if mode == "success" else "sleep 30"
                if mode in ("cancel", "exit"):
                    def interrupt(mode=mode):
                        end = time.monotonic() + 2
                        while (not pidfile.exists() or pidfile.stat().st_size == 0) and time.monotonic() < end:
                            time.sleep(.01)
                        if mode == "cancel":
                            self.cancel.set()
                        else:
                            self.alive = False
                    thread = threading.Thread(target=interrupt, daemon=True)
                    thread.start()
                try:
                    if mode == "success":
                        self.wait("command", command=command)
                    else:
                        message = {"cancel": "canceled", "exit": "exited", "timeout": "timed out"}[mode]
                        with self.assertRaisesRegex((AppRuntimeError, OperationCanceledError), message):
                            self.wait("command", command=command, timeout_sec=.6 if mode == "timeout" else 5)
                    pid = int(pidfile.read_text())
                    self.assertFalse(Path("/proc/{}/stat".format(pid)).exists(), "probe descendant was not reaped")
                finally:
                    if mode in ("cancel", "exit"):
                        thread.join(timeout=3)
                    if pidfile.exists() and pidfile.read_text():
                        pid = int(pidfile.read_text())
                        try:
                            if process_stat(Path("/proc/{}/stat".format(pid))):
                                os.kill(pid, signal.SIGKILL)
                        except (ProcessLookupError, FileNotFoundError):
                            pass
                        pidfile.unlink()

    def test_log_probes_match_split_output_and_ignore_previous_invocation(self):
        path = self.root / "current.log"
        self.runtime._app_log_path = Mock(return_value=path)
        path.write_text("old READY")
        path.write_text("new RE")
        def append():
            with path.open("a") as stream:
                stream.write("ADY")
        self.later(.1, append)
        self.wait("log_contains", pattern="READY")
        self.wait("log_regex", pattern="new R[A-Z]+")
        with self.assertRaisesRegex(AppRuntimeError, "timed out"):
            self.wait("log_contains", pattern="old", timeout_sec=.12)

    def test_log_contains_never_imports_regex_and_log_regex_falls_back_to_re(self):
        path = self.root / "current.log"
        self.runtime._app_log_path = Mock(return_value=path)
        path.write_bytes(b"x" * 65534 + b"READY")
        imports = []
        real_import = builtins.__import__
        def without_regex(name, *args, **kwargs):
            if name == "regex":
                imports.append(name)
                raise ImportError(name)
            return real_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=without_regex):
            self.wait("log_contains", pattern="READY")
            self.assertEqual(imports, [])
            self.wait("log_regex", pattern="RE[A-Z]{3}")
            self.assertEqual(imports, ["regex"])

    def test_exited_zero_requires_recorded_success_even_if_no_process_is_running(self):
        self.alive = False
        self.runtime._app_log_path = Mock(return_value=self.root / "current.log")
        with self.assertRaisesRegex(AppRuntimeError, "timed out"):
            self.wait("exited_zero", timeout_sec=.1)
        self.runtime._record_exit("camera", 3)
        with self.assertRaisesRegex(AppRuntimeError, "unsuccessfully"):
            self.wait("exited_zero")
        self.runtime._record_exit("camera", 0)
        self.wait("exited_zero")
