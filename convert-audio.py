#!/usr/bin/env python3

import os
import argparse
import glob
import subprocess
import shlex

CODEC_MAP = {"flac": "flac", "m4a": "alac", "mp3": "libmp3lame"}


def convert(input_file: str, output_file: str):
    input_type = os.path.splitext(input_file)[1][1:]
    input_codec = CODEC_MAP[input_type]
    output_type = os.path.splitext(output_file)[1][1:]
    output_codec = CODEC_MAP[output_type]
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    input_file = os.path.abspath(input_file)
    output_file = os.path.abspath(output_file)
    input_file = shlex.quote(input_file)
    output_file = shlex.quote(output_file)
    command = f"ffmpeg -i {input_file} -y -c:v copy -c:a {output_codec} {output_file}"
    subprocess.run(command, shell=True, check=True)
    return


def find_files(file_type: str, base_dir: str) -> dict:
    base_dir = os.path.expanduser(os.path.expandvars(base_dir))
    base_dir = os.path.abspath(base_dir)
    files = glob.glob(os.path.join(base_dir, "**", f"*.{file_type}"), recursive=True)
    result = {}
    for file in files:
        name = file[len(base_dir) :]
        name = name.lstrip(os.path.sep)
        name = os.path.splitext(name)[0]
        result[name] = file
    return result


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output-type", required=True, choices=list(CODEC_MAP.keys()))
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--input-type", required=True, choices=list(CODEC_MAP.keys()))
    args = parser.parse_args()
    audio_files = find_files(file_type=args.input_type, base_dir=args.input_dir)
    for name, input_file in audio_files.items():
        output_file = os.path.join(args.output_dir, f"{name}.{args.output_type}")
        convert(input_file, output_file)


if __name__ == "__main__":
    main()
