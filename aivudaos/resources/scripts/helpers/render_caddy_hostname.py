#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


def _render_caddy(text: str, hostname: str) -> str:
    pattern = re.compile(
        r"(?m)^(?P<indent>\s*)https://(?:\{\$AVAHI_HOSTNAME\}|__AVAHI_HOSTNAME__|[a-z0-9][a-z0-9-]{0,62})\.local(?P<port>:\d+)?\s*\{"
    )

    def _replace(match: re.Match[str]) -> str:
        indent = match.group("indent") or ""
        port = match.group("port") or ""
        return f"{indent}https://{hostname}.local{port} {{"

    new_text, count = pattern.subn(_replace, text, count=1)
    if count == 0:
        if not new_text.endswith("\n"):
            new_text += "\n"
        new_text += f"\nhttps://{hostname}.local {{\n  tls internal\n  import aivudaos_common_route\n}}\n"
    return new_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Render runtime Caddyfile with concrete Avahi hostname")
    parser.add_argument("--config", required=True)
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    config_path = Path(args.config)
    hostname = args.hostname.strip().lower()
    output_path = Path(args.output)

    text = config_path.read_text(encoding="utf-8")
    output_path.write_text(_render_caddy(text, hostname), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
