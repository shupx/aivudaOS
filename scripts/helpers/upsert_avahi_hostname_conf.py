#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


def _upsert_server_hostname(config_text: str, hostname: str) -> str:
    text = config_text or ""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    section_re = re.compile(r"^\s*\[([^\]]+)\]\s*(?:[;#].*)?$")
    host_re = re.compile(r"^(\s*)host-name\s*[=:].*$", re.IGNORECASE)

    if not lines:
        return f"[server]{newline}host-name={hostname}{newline}"

    server_start = -1
    server_end = len(lines)

    for idx, line in enumerate(lines):
        match = section_re.match(line.strip("\r\n"))
        if not match:
            continue
        section_name = match.group(1).strip().lower()
        if section_name == "server":
            server_start = idx
            for next_idx in range(idx + 1, len(lines)):
                if section_re.match(lines[next_idx].strip("\r\n")):
                    server_end = next_idx
                    break
            break

    if server_start >= 0:
        for idx in range(server_start + 1, server_end):
            match = host_re.match(lines[idx].strip("\r\n"))
            if match:
                indent = match.group(1)
                line_newline = ""
                if lines[idx].endswith("\r\n"):
                    line_newline = "\r\n"
                elif lines[idx].endswith("\n"):
                    line_newline = "\n"
                lines[idx] = f"{indent}host-name={hostname}{line_newline}"
                return "".join(lines)

        insert_newline = ""
        if lines[server_start].endswith("\r\n"):
            insert_newline = "\r\n"
        elif lines[server_start].endswith("\n"):
            insert_newline = "\n"
        else:
            insert_newline = newline
            lines[server_start] = f"{lines[server_start]}{insert_newline}"
        lines.insert(server_start + 1, f"host-name={hostname}{insert_newline}")
        return "".join(lines)

    if lines and not (lines[-1].endswith("\n") or lines[-1].endswith("\r\n")):
        lines[-1] = f"{lines[-1]}{newline}"
    lines.append(f"[server]{newline}")
    lines.append(f"host-name={hostname}{newline}")
    return "".join(lines)


def _read_avahi_config() -> str:
    try:
        proc = subprocess.run(
            ["sudo", "cat", "/etc/avahi/avahi-daemon.conf"],
            check=True,
            text=True,
            capture_output=True,
        )
        return proc.stdout
    except subprocess.CalledProcessError:
        return "[server]\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate avahi-daemon.conf with updated [server] host-name")
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    hostname = args.hostname.strip().lower()
    output_path = Path(args.output)

    updated_text = _upsert_server_hostname(_read_avahi_config(), hostname)
    output_path.write_text(updated_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
