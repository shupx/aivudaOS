"""Share discovery within one operation, keeping distinct middleware environments isolated."""
import json
import queue
import shlex
import shutil
import subprocess
import threading
import uuid
from pathlib import Path

from aivudaos.core.errors import AppRuntimeError


def ros_installation(env):
    executable = shutil.which("ros2", path=env.get("PATH", ""))
    if executable:
        return executable, None
    installs = sorted(Path("/opt/ros").glob("*/bin/ros2"))
    distro = env.get("ROS_DISTRO")
    if distro:
        installs = [p for p in installs if p.parents[1].name == distro]
    if len(installs) == 1:
        setup = installs[0].parents[1] / "setup.bash"
        if setup.is_file():
            return str(installs[0]), str(setup)
    raise AppRuntimeError("ros2 was not found on the app PATH. Load the intended ROS environment.")


class _Participant:
    def __init__(self, ros, setup, env):
        with open(ros, "rb") as entry:
            shebang = entry.readline(512).decode().strip()
        interpreter = shlex.split(shebang[2:]) if shebang.startswith("#!") else []
        if not interpreter or not any("python" in Path(part).name for part in interpreter):
            raise AppRuntimeError("Cannot identify ROS Python interpreter from " + ros)
        worker = str(Path(__file__).with_name("pipeline_ros_worker.py"))
        command = interpreter + [worker]
        if setup:
            command = ["/bin/bash", "--noprofile", "--norc", "-c",
                       'source "$1" >&2 && shift && exec "$@"', "ros-probe", setup] + command
        self.proc = subprocess.Popen(command, env=env, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, text=True, bufsize=1)
        self.lock = threading.Lock()
        self.requests = {}
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.proc.stdout:
                reply = json.loads(line)
                with self.lock:
                    dest = self.requests.get(reply["token"])
                    if dest is not None:
                        dest.put(reply)
        finally:
            with self.lock:
                for dest in self.requests.values():
                    dest.put({"error": "ROS participant exited. Check the ROS Python and middleware environment."})

    def _send(self, message):
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def wait(self, wait, spec):
        token = uuid.uuid4().hex
        result = queue.Queue()
        try:
            with self.lock:
                self.requests[token] = result
            while True:
                with self.lock:
                    self._send({"token": token, "spec": spec})
                while True:
                    try:
                        reply = result.get(timeout=min(.05, wait.check()))
                        break
                    except queue.Empty:
                        continue
                if reply.get("error"):
                    raise AppRuntimeError(reply["error"])
                if reply["ready"]:
                    return
                wait.sleep(spec["interval_sec"])
        except BrokenPipeError as exc:
            raise AppRuntimeError("ROS participant could not run. Check the ROS Python environment.") from exc
        finally:
            with self.lock:
                self.requests.pop(token, None)
                try:
                    self._send({"token": token})
                except BrokenPipeError:
                    pass

    def close(self):
        try:
            self.proc.stdin.close()
        except BrokenPipeError:
            pass
        try:
            self.proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.reader.join()
        self.proc.stdout.close()


class RosProbeSession:
    def __init__(self):
        self.lock = threading.Lock()
        self.workers = {}

    def wait(self, wait, spec, env):
        ros, setup = ros_installation(env)
        # Include overlay paths and DDS vendor/security settings in addition to the domain.
        prefixes = ("ROS_", "RMW_", "CYCLONE", "FAST", "RTI_", "NDDS_", "ZENOH_", "AMENT_", "COLCON_")
        paths = {"PATH", "PYTHONPATH", "LD_LIBRARY_PATH"}
        key = (ros, setup, tuple(sorted((k, v) for k, v in env.items() if k in paths or k.startswith(prefixes))))
        with self.lock:
            if key not in self.workers:
                self.workers[key] = _Participant(ros, setup, env)
            worker = self.workers[key]
        worker.wait(wait, spec)

    def close(self):
        for worker in self.workers.values():
            worker.close()
        self.workers.clear()
