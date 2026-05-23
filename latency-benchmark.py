#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import socket
import argparse
import re
from concurrent.futures import ThreadPoolExecutor

# Default high-availability public IP targets for geographical profiling
DEFAULT_REGIONS = {
    "San Francisco (US-West)": "8.8.8.8",
    "New York (US-East)": "4.2.2.1",
    "Singapore (Asia)": "1.1.1.1",
    "London (UK)": "212.58.244.70",
    "Frankfurt (Germany)": "194.25.0.60",
    "Amsterdam (Amsterdam)": "193.0.14.129",
    "Sydney (Australia)": "139.130.4.5",
}


def load_regions_from_file(file_path):
    """
    Parses the target list from a user-specified file.
    Supported formats per line: Name Domain/IP
    """
    if not os.path.exists(file_path):
        print("Error: The specified target file does not exist: {}".format(file_path))
        sys.exit(1)

    custom_regions = {}
    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = re.split(r"[\s,=\t]+", line, maxsplit=1)
            if len(parts) == 2:
                name, domain = parts[0].strip(), parts[1].strip()
                domain = re.sub(r"^https?://", "", domain).split("/")[0]
                custom_regions[name] = domain
            else:
                print(
                    "Warning: Could not parse line {} -> '{}'. Skipped.".format(
                        line_num, line
                    )
                )

    if not custom_regions:
        print("Error: No valid test nodes could be parsed from the file.")
        sys.exit(1)

    return custom_regions


def test_tcp_latency(region_name, domain, count, timeout, port):
    """
    Measures network connection latency via TCP handshake timers to a specified port.
    """
    latencies = []

    try:
        ip_address = socket.gethostbyname(domain)
    except socket.gaierror:
        return {
            "region": region_name,
            "url": domain,
            "avg": float("inf"),
            "status": "DNS Failed",
        }

    for _ in range(count):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        start_time = time.time()
        try:
            s.connect((ip_address, port))
            latency = (time.time() - start_time) * 1000
            latencies.append(latency)
        except socket.timeout:
            # Strictly hit the timeout ceiling
            pass
        except socket.error:
            # Connection Refused means host is alive but port is closed.
            # We treat this round-trip time as a valid network response.
            latency = (time.time() - start_time) * 1000
            latencies.append(latency)
        finally:
            s.close()

        time.sleep(0.05)

    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        return {
            "region": region_name,
            "url": domain,
            "avg": avg_latency,
            "status": "Success",
        }
    else:
        return {
            "region": region_name,
            "url": domain,
            "avg": float("inf"),
            "status": "Timeout",
        }


def main():
    parser = argparse.ArgumentParser(
        description="Multi-threaded TCP Latency Benchmarking Tool"
    )
    parser.add_argument(
        "-c",
        "--count",
        type=int,
        default=3,
        help="Number of test connections per node (default: 3)",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=2.5,
        help="Timeout in seconds for each network probe (default: 2.5)",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=80,
        help="Target TCP port to probe (default: 80)",
    )
    parser.add_argument(
        "-f",
        "--file",
        type=str,
        default=None,
        help="Path to a file containing custom test nodes (omitting this uses built-in list)",
    )
    args = parser.parse_args()

    # Parameter boundaries validation
    if args.count < 1:
        print("Error: Test count --count must be 1 or greater.")
        sys.exit(1)

    if args.timeout <= 0:
        print("Error: Timeout value must be greater than 0.")
        sys.exit(1)

    if args.port < 1 or args.port > 65535:
        print("Error: Port range must be between 1 and 65535.")
        sys.exit(1)

    if args.file:
        print("Loading targets from file: {} ...".format(args.file))
        regions_to_test = load_regions_from_file(args.file)
    else:
        regions_to_test = DEFAULT_REGIONS

    print(
        "Benchmarking network path latency ({} probes, port {}, {}s timeout)... \n".format(
            args.count, args.port, args.timeout
        )
    )

    results = []
    max_workers = min(len(regions_to_test), 32)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                test_tcp_latency, name, domain, args.count, args.timeout, args.port
            )
            for name, domain in regions_to_test.items()
        ]
        for future in futures:
            results.append(future.result())

    results.sort(key=lambda x: x["avg"])

    print("=" * 105)
    print(
        "{:<22} | {:<42} | {:<18} | {:<10}".format(
            "Target / Region", "Target URL / IP", "Avg Latency (ms)", "Status"
        )
    )
    print("-" * 105)

    for res in results:
        if res["avg"] == float("inf"):
            latency_str = "Timeout"
        else:
            latency_str = "{:.2f} ms".format(res["avg"])

        print(
            "{:<22} | {:<42} | {:<18} | {:<10}".format(
                res["region"], res["url"], latency_str, res["status"]
            )
        )

    print("=" * 105)


if __name__ == "__main__":
    main()
