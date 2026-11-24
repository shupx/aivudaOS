"""Short-lived ROS participant. Run with the ROS installation's Python interpreter."""
import json
import os
import queue
import sys
import threading


def serve(lines, response):
    import rclpy
    from lifecycle_msgs.srv import GetState
    from rclpy.qos import qos_profile_sensor_data
    from rclpy.task import Future
    from rosidl_runtime_py.utilities import get_message

    requests = queue.Queue()
    eof = Future()

    rclpy.init(args=[])
    node = rclpy.create_node("aivuda_readiness_{}".format(os.getpid()), enable_rosout=False,
                             start_parameter_services=False)
    subscriptions, received, clients, futures = {}, set(), {}, {}

    def check(token, spec):
        kind = spec["type"]
        name = "/" + spec.get("topic", spec.get("node_name", "")).lstrip("/")
        if kind == "ros2_node":
            return any(ns.rstrip("/") + "/" + n == name for n, ns in node.get_node_names_and_namespaces())
        if kind == "ros2_lifecycle":
            if token not in clients:
                clients[token] = node.create_client(GetState, name + "/get_state")
            client = clients[token]
            future = futures.get(token)
            if future and future.done():
                del futures[token]
                return future.result().current_state.label == spec["lifecycle_state"]
            if not future and client.service_is_ready():
                futures[token] = client.call_async(GetState.Request())
            return False
        if spec.get("require_message"):
            if token in received:
                return True
            if token not in subscriptions:
                types = dict(node.get_topic_names_and_types()).get(name, [])
                if len(types) > 1:
                    raise ValueError("Multiple message types on " + name)
                if types:
                    subscriptions[token] = node.create_subscription(
                        get_message(types[0]), name, lambda msg: received.add(token),
                        qos_profile_sensor_data, raw=True)
            return False
        if spec.get("require_publisher"):
            return node.count_publishers(name) > 0
        return name in dict(node.get_topic_names_and_types())

    def handle_requests():
        # Guard triggers can coalesce. Drain every queued request in wire order.
        while not requests.empty():
            req = requests.get_nowait()
            if req is None:
                eof.set_result(None)
                return
            token = req["token"]
            if "spec" not in req:
                if token in subscriptions:
                    node.destroy_subscription(subscriptions.pop(token))
                if token in clients:
                    futures.pop(token, None)
                    node.destroy_client(clients.pop(token))
                received.discard(token)
                continue
            try:
                reply = {"ready": check(token, req["spec"])}
            except Exception as exc:
                reply = {"error": str(exc)}
            reply["token"] = token
            response.write(json.dumps(reply) + "\n")

    wake = node.create_guard_condition(handle_requests)

    def read_requests():
        try:
            for line in lines:
                requests.put(json.loads(line))
                wake.trigger()
        finally:
            requests.put(None)
            wake.trigger()

    try:
        threading.Thread(target=read_requests, daemon=True).start()
        rclpy.spin_until_future_complete(node, eof)
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main():
    # Keep middleware/extension diagnostics off the JSON response channel.
    with os.fdopen(os.dup(sys.stdout.fileno()), "w", buffering=1) as response:
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        serve(sys.stdin, response)


if __name__ == "__main__":
    main()
