#!/usr/bin/env python
import subprocess
import shlex
import time
import os
import logging
import signal
import argparse
try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO


def run_command(command):
    try:
        output = subprocess.check_output(shlex.split(command))
        return list([line.strip() for line in StringIO(output).readlines()])
    except subprocess.CalledProcessError as e:
        logging.error(e.message)
        return None


def memory_usage():
    """memory usage in Megabytes
       Retrun total, used
    """
    lines = run_command("free -m")
    memory = filter(bool, lines[1].split(" "))
    return int(memory[1]), int(memory[2])


def process_snapshot():
    return run_command(
        "ps -e -o pid,uid,user,%cpu,%mem,rss,etime,start,args --sort -%mem")


def user_home(user):
    lines = run_command("getent passwd {}".format(user))
    if lines:
        entries = lines[0].split(":")
        if len(entries) >= 6:
            return entries[5]
    return "/root"


def kill_process_with_highest_memory():
    processusage = process_snapshot()
    if not processusage:
        return
    statsline = processusage[1]
    stats = filter(bool, statsline.split(" "))
    pid = int(stats[0])
    os.kill(pid, signal.SIGKILL)
    logging.warn("killed process {} with highest memory:".format(pid))
    logging.warn(processusage[0])
    logging.warn(processusage[1])
    user = stats[2]
    logfile = "{}/KILL-PROCESS-WITH-HIGHEST-MEMORY-{}.log".format(
        user_home(user), time.strftime("%Y%m%d%H%M%S"))
    with open(logfile, "wt") as file:
        file.writelines("{}\n{}".format(processusage[0], processusage[1]))


def watch(memory_ratio):
    memory_ratio = float(memory_ratio)
    memoryusage = memory_usage()
    if not memoryusage:
        return
    total = memoryusage[0]
    used = memoryusage[1]
    logging.info("memory usage, total/used: {}/{} MB".format(total, used))
    if used > total * memory_ratio:
        kill_process_with_highest_memory()


def main(interval=3, memory_ratio=0.95):
    logging.getLogger().setLevel(logging.INFO)
    logging.basicConfig(format="[%(asctime)s]:%(levelname)s:%(message)s")
    while True:
        watch(memory_ratio)
        time.sleep(int(interval))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Watch the memory used not exceeding the limit")
    parser.add_argument("--ratio", default=0.95)
    parser.add_argument("--interval", default=3)
    args = parser.parse_args()
    main(args.interval, args.ratio)
