from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from aivudaos import __version__


@dataclass(frozen=True)
class CommandSpec:
    name: str
    script_relpath: str
    summary: str
    usage: str


COMMANDS: dict[str, CommandSpec] = {
    "install": CommandSpec(
        name="install",
        script_relpath="scripts/install_aivudaos.sh",
        summary="Install or update the AivudaOS user service.",
        usage="aivudaos install",
    ),
    "uninstall": CommandSpec(
        name="uninstall",
        script_relpath="scripts/uninstall_aivudaos.sh",
        summary="Uninstall the AivudaOS user service.",
        usage="aivudaos uninstall",
    ),
    "start": CommandSpec(
        name="start",
        script_relpath="scripts/_start_aivudaos_service.sh",
        summary="Start the AivudaOS systemd user service.",
        usage="aivudaos start",
    ),
    "stop": CommandSpec(
        name="stop",
        script_relpath="scripts/_stop_aivudaos_service.sh",
        summary="Stop the AivudaOS systemd user service.",
        usage="aivudaos stop",
    ),
    "restart": CommandSpec(
        name="restart",
        script_relpath="scripts/_restart_aivudaos_service.sh",
        summary="Restart the AivudaOS systemd user service.",
        usage="aivudaos restart",
    ),
    "enable-autostart": CommandSpec(
        name="enable-autostart",
        script_relpath="scripts/_enable_autostart_aivudaos_service.sh",
        summary="Enable service autostart in user systemd.",
        usage="aivudaos enable-autostart",
    ),
    "disable-autostart": CommandSpec(
        name="disable-autostart",
        script_relpath="scripts/_disable_autostart_aivudaos_service.sh",
        summary="Disable service autostart in user systemd.",
        usage="aivudaos disable-autostart",
    ),
    "run-stack": CommandSpec(
        name="run-stack",
        script_relpath="scripts/_run_aivudaos_stack.sh",
        summary="Run the backend and Caddy stack in the foreground.",
        usage="aivudaos run-stack [--dev]",
    ),
    "get-avahi-hostname": CommandSpec(
        name="get-avahi-hostname",
        script_relpath="scripts/_get_avahi_hostname.sh",
        summary="Print the resolved Avahi hostname.",
        usage="aivudaos get-avahi-hostname [--debug]",
    ),
    "download-caddy": CommandSpec(
        name="download-caddy",
        script_relpath="scripts/_download_caddy.sh",
        summary="Download or install the Caddy binary into the runtime tools directory.",
        usage="aivudaos download-caddy [--source PATH_OR_URL] [--output PATH]",
    ),
}


def _resource_root() -> str:
    return str((Path(__file__).resolve().parent / "resources").resolve())


def _script_path(command: CommandSpec) -> str:
    return os.path.join(_resource_root(), command.script_relpath)


def _print_main_help() -> int:
    print("Usage: aivudaos [--help] [--version] <command> [args...]")
    print("")
    print("Commands:")
    for command in COMMANDS.values():
        print(f"  {command.name:<18} {command.summary}")
    print("  version            Print the installed AivudaOS package version.")
    print("")
    print("Run 'aivudaos <command> --help' for command-specific usage.")
    return 0


def _print_command_help(command: CommandSpec) -> int:
    print(f"Usage: {command.usage}")
    print("")
    print(command.summary)
    print("")
    print("This command delegates to:")
    print(f"  {command.script_relpath}")
    return 0


def _run_shell_script(command: CommandSpec, forwarded_args: list[str]) -> int:
    script_path = _script_path(command)
    if not os.path.exists(script_path):
        print(f"Packaged script not found: {script_path}", file=sys.stderr)
        return 1

    env = os.environ.copy()
    env["AIVUDAOS_VERSION"] = __version__
    env["AIVUDAOS_PACKAGE_ROOT"] = _resource_root()
    env["AIVUDAOS_CLI_COMMAND"] = command.name

    completed = subprocess.run(["bash", script_path, *forwarded_args], env=env, check=False)
    return completed.returncode


def main(argv: Optional[list[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        return _print_main_help()

    head = args[0]
    if head in {"-h", "--help", "help"}:
        if len(args) == 1:
            return _print_main_help()
        command = COMMANDS.get(args[1])
        if command is None:
            print(f"Unknown command: {args[1]}", file=sys.stderr)
            return 2
        return _print_command_help(command)

    if head in {"-V", "--version", "version"}:
        print(__version__)
        return 0

    command = COMMANDS.get(head)
    if command is None:
        print(f"Unknown command: {head}", file=sys.stderr)
        print("")
        return _print_main_help()

    forwarded_args = args[1:]
    if any(arg in {"-h", "--help"} for arg in forwarded_args):
        return _print_command_help(command)
    if any(arg in {"-V", "--version"} for arg in forwarded_args):
        print(__version__)
        return 0

    return _run_shell_script(command, forwarded_args)


if __name__ == "__main__":
    raise SystemExit(main())
