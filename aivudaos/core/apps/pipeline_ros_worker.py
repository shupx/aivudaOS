"""Short-lived ROS participant. Run with the ROS installation's Python interpreter."""
import json
import os
import queue
import sys
import threading


def serve(lines, response):
    import rclpy
    from rclpy.task import Future

    requests = queue.Queue()
    incoming = Future()

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
            from lifecycle_msgs.srv import GetState

            if token not in clients:
                clients[token] = node.create_client(GetState, name + "/get_state")
            client = clients[token]
            future = futures.get(token)
            if future is None and client.service_is_ready():
                future = futures[token] = client.call_async(GetState.Request())
                rclpy.spin_until_future_complete(node, future, timeout_sec=0.1)
            if future is not None and future.done():
                del futures[token]
                return future.result().current_state.label == spec["lifecycle_state"]
            return False
        if spec.get("require_message"):
            if token in received:
                return True
            from rclpy.exceptions import NoTypeSupportImportedException
            from rclpy.qos import (DurabilityPolicy, HistoryPolicy, QoSProfile,
                                   ReliabilityPolicy, qos_profile_sensor_data)
            from rosidl_runtime_py.utilities import get_message

            publishers = node.get_publishers_info_by_topic(name)
            if not publishers:
                return False
            types = {publisher.topic_type for publisher in publishers}
            if len(types) != 1:
                raise ValueError("Multiple message types on {}: {}".format(name, ", ".join(sorted(types))))
            message_type = types.pop()
            latched = any(p.qos_profile.durability == DurabilityPolicy.TRANSIENT_LOCAL and
                          p.qos_profile.reliability == ReliabilityPolicy.RELIABLE for p in publishers)
            signature = (message_type, latched)
            previous = subscriptions.get(token)
            if previous is None or signature != previous[0]:
                qos = qos_profile_sensor_data
                if latched:
                    qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1, reliability=ReliabilityPolicy.RELIABLE,
                                     durability=DurabilityPolicy.TRANSIENT_LOCAL)
                try:
                    message = get_message(message_type)
                    subscription = node.create_subscription(message, name, lambda msg: received.add(token), qos, raw=True)
                except (ModuleNotFoundError, ImportError, LookupError, NoTypeSupportImportedException) as exc:
                    raise ValueError("Missing ROS message Python typesupport for {} on {}. "
                                     "Install the message package or use log_contains or require_publisher."
                                     .format(message_type, name)) from exc
                if previous is not None:
                    node.destroy_subscription(previous[1])
                subscriptions[token] = (signature, subscription)
            return False
        if spec.get("require_publisher"):
            return node.count_publishers(name) > 0
        return name in dict(node.get_topic_names_and_types())

    def handle_requests():
        # Guard triggers can coalesce. Drain every queued request in wire order.
        while not requests.empty():
            req = requests.get_nowait()
            if req is None:
                return False
            token = req["token"]
            if "spec" not in req:
                if token in subscriptions:
                    node.destroy_subscription(subscriptions.pop(token)[1])
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

        return True

    def signal_input():
        if not incoming.done():
            incoming.set_result(None)

    wake = node.create_guard_condition(signal_input)

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
        # Dispatch outside the guard callback so lifecycle clients can spin for their reply.
        while rclpy.ok():
            rclpy.spin_until_future_complete(node, incoming)
            incoming = Future()
            if not handle_requests():
                break
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
