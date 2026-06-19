#!/usr/bin/env python3

import argparse
import platform
import subprocess
import sys


def run_cmd(cmd):
    """
    Run a command and return stdout as stripped string.

    Args:
        cmd: list of command arguments, for example ["ip", "route"].
    """
    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
    except FileNotFoundError:
        raise RuntimeError("command not found: {}".format(cmd[0]))
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "command failed: {}\n"
            "stderr: {}".format(" ".join(cmd), exc.stderr.strip())
        )

    return result.stdout.strip()


def get_macos_default_interface():
    """
    macOS command:

        route get default
    """
    output = run_cmd(["route", "get", "default"])

    for line in output.splitlines():
        line = line.strip()
        if line.startswith("interface:"):
            return line.split(":", 1)[1].strip()

    raise RuntimeError("failed to find default interface from `route get default`")


def get_macos_interface_ip(interface):
    """
    macOS command:

        ipconfig getifaddr en0
    """
    ip = run_cmd(["ipconfig", "getifaddr", interface])

    if not ip:
        raise RuntimeError(
            "failed to get IP address for interface: {}".format(interface)
        )

    return ip


def get_macos_outbound_ip(interface=None):
    """
    If interface is given:

        ipconfig getifaddr "$interface"

    Otherwise:

        IFACE=$(route get default | awk '/interface:/{print $2}')
        ipconfig getifaddr "$IFACE"
    """
    if interface is None:
        interface = get_macos_default_interface()

    return get_macos_interface_ip(interface)


def get_linux_default_route_to_target(target="1.1.1.1"):
    """
    Linux command:

        ip -o route get 1.1.1.1
    """
    return run_cmd(["ip", "-o", "route", "get", target])


def parse_linux_src_ip(route_output):
    """
    Parse `src x.x.x.x` from:

        ip -o route get 1.1.1.1
    """
    parts = route_output.split()

    for index, item in enumerate(parts):
        if item == "src" and index + 1 < len(parts):
            return parts[index + 1]

    raise RuntimeError(
        "failed to parse src IP from route output: {}".format(route_output)
    )


def get_linux_interface_ip(interface):
    """
    Linux command:

        ip -o -4 addr show dev eth0 scope global

    Example output:

        2: eth0    inet 192.168.1.23/24 brd 192.168.1.255 scope global eth0
    """
    output = run_cmd(
        [
            "ip",
            "-o",
            "-4",
            "addr",
            "show",
            "dev",
            interface,
            "scope",
            "global",
        ]
    )

    for line in output.splitlines():
        parts = line.split()
        for index, item in enumerate(parts):
            if item == "inet" and index + 1 < len(parts):
                return parts[index + 1].split("/", 1)[0]

    raise RuntimeError("failed to get IPv4 address for interface: {}".format(interface))


def get_linux_outbound_ip(interface=None, target="1.1.1.1"):
    """
    If interface is given:

        ip -o -4 addr show dev "$interface" scope global

    Otherwise:

        ip -o route get 1.1.1.1
    """
    if interface is not None:
        return get_linux_interface_ip(interface)

    route_output = get_linux_default_route_to_target(target)
    return parse_linux_src_ip(route_output)


def get_outbound_ip(interface=None):
    system = platform.system()

    if system == "Darwin":
        return get_macos_outbound_ip(interface=interface)

    if system == "Linux":
        return get_linux_outbound_ip(interface=interface)

    raise RuntimeError("unsupported OS: {}".format(system))


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Get local outbound IPv4 address on macOS or Linux."
    )

    parser.add_argument(
        "-i",
        "--interface",
        default=None,
        help="network interface name, for example en0, eth0, wlan0",
    )

    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    try:
        ip = get_outbound_ip(interface=args.interface)
    except RuntimeError as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 1

    print(ip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
