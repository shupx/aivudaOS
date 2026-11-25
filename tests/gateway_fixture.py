"""Local-only prerequisites for real gateway/Caddy integration tests."""
import os
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CADDY = Path(os.environ.get('AIVUDAOS_TEST_CADDY') or ROOT.parent / 'resources/app-gateway/caddy').resolve()


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]
