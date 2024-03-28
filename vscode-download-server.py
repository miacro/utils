#!/usr/bin/env python3
import os
import argparse
import subprocess
import shutil
import json
import logging


def get_latest_release(platform, arch):
    url = "https://update.code.visualstudio.com/api/commits/stable/{}-{}".format(
        platform, arch
    )
    curl_bin = shutil.which("curl")
    assert curl_bin, "curl not found"
    command = "curl -fsSL {}".format(url)
    res = subprocess.check_output(command, shell=True, text=True, env=os.environ)
    try:
        commits = json.loads(res)
        return commits[0]
    except Exception as e:
        raise e


def download_release_file(commit, prefix, arch, archive_file):
    if not os.path.exists(os.path.dirname(archive_file)):
        os.makedirs(os.path.dirname(archive_file))
    assert shutil.which("curl")
    url = "https://update.code.visualstudio.com/commit:{}/{}-{}/stable".format(
        commit, prefix, arch
    )
    command = "curl -fSL -C - {} -o {}".format(url, archive_file)
    subprocess.check_call(command, shell=True, text=True, env=os.environ)
    return


def prepare_release_dir(commit, archive_file, output_dir):
    bin_dir = os.path.join(output_dir, "bin")
    commit_dir = os.path.join(bin_dir, commit)
    if os.path.exists(commit_dir):
        shutil.rmtree(commit_dir)
    if not os.path.exists(commit_dir):
        os.makedirs(commit_dir)
    assert shutil.which("tar")
    tar_args = "--no-same-owner -xvz --strip-components=1 "
    command = "tar {} -C {} -f {}".format(tar_args, commit_dir, archive_file)
    subprocess.check_call(command, shell=True, text=True, env=os.environ)
    default_key = "default_version"
    default_dir = os.path.join(bin_dir, default_key)
    if not os.path.exists(default_dir):
        command = "cd {} && ln -s {} {}".format(bin_dir, commit, default_key)
        subprocess.check_call(command, text=True, shell=True)


def main():
    logging.getLogger().setLevel(logging.INFO)
    logging.basicConfig(format="[%(asctime)s]:%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="download the vscode-server",
    )
    valid_platform = ["win32", "linux", "darwin", "alpine"]
    valid_arch = ["x64", "arm64", "armhf"]
    parser.add_argument("-p", "--platform", default=None, choices=valid_platform)
    parser.add_argument("-a", "--arch", default=None, choices=valid_arch)
    parser.add_argument("-c", "--commit", default=None, help="the commit id")
    parser.add_argument("-o", "--output-dir", default="./", help="the output directory")
    args = parser.parse_args()
    arch = args.arch
    platform = args.platform
    if arch is None or platform is None:
        uname = os.uname()
        if platform is None:
            platform = uname.sysname.lower()
        if arch is None:
            arch_map = {"aarch64": "arm64", "x86_64": "x64", "armv7l": "armhf"}
            for k in valid_arch:
                arch_map[k] = k
            arch = arch_map.get(uname.machine, None)
        if arch is None:
            assert 0, f"unknown arch"
    commit = args.commit
    if commit is None:
        commit = get_latest_release(platform=platform, arch=arch)

    prefix = "server-{}".format(platform)
    if platform == "alpine":
        prefix = "cli-{}".format(platform)
    archive_name = "vscode-{}-{}.tar.gz".format(prefix, arch)
    archive_file = os.path.join(args.output_dir, archive_name)
    download_release_file(
        commit=commit, prefix=prefix, arch=arch, archive_file=archive_file
    )
    prepare_release_dir(
        commit=commit,
        archive_file=archive_file,
        output_dir=os.path.join(args.output_dir, "vscode-server"),
    )
    return


if __name__ == "__main__":
    main()
