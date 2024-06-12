#!/usr/bin/env python3
import requests
import json
import os
import sys
import argparse
import logging
import subprocess
import shutil
import gzip


class ExtensionDownloader:
    HEADERS = {
        "Content-Type": "application/json",
        "Accept": "application/json;api-version=3.0-preview.1",
        "User-Agent": "Offline VSIX/1.0",
    }
    QUERY_URL = (
        "https://marketplace.visualstudio.com/_apis/public/gallery/extensionQuery"
    )

    # {publisher} {publisher} {package} {version}
    # DOWNLOAD_URL = "https://{}.gallery.vsassets.io/_apis/public/gallery/publisher/{}/extension/{}/{}/assetbyname/Microsoft.VisualStudio.Services.VSIXPackage"
    # {publisher} {package} {version} {platform}
    DOWNLOAD_URL = "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/{}/vsextensions/{}/{}/vspackage"
    PLATFORMS = {
        "win32-x64": "Windows x64",
        "win32-ia32": "Windows ia32",
        "win32-arm64": "Windows ARM",
        "linux-x64": "Linux x64",
        "linux-arm64": "Linux ARM64",
        "linux-armhf": "Linux ARM32",
        "darwin-x64": "macOS Intel",
        "darwin-arm64": "macOS Apple Silicon",
        "alpine-x64": "Alpine Linux 64 bit",
        "web": "Web",
        "alpine-arm64": "Alpine Linux ARM64",
    }

    def __init__(
        self,
        publisher,
        package,
        platform,
        output_dir,
        version=None,
        cached=True,
    ):
        self.publisher = publisher
        self.package = package
        self.output_dir = output_dir
        self.version = None
        if platform is not None:
            assert platform in self.PLATFORMS, (platform, self.PLATFORMS)
        self.platform = platform
        if isinstance(version, str) and version:
            self.version = version
        self.cached = cached

    def download(self):
        publisher = self.publisher
        package = self.package
        version = self.version
        platform = self.platform
        if version is None:
            version, platform = self.extension_select_version(
                self.publisher, self.package, self.platform, version=version
            )
        if version is None:
            return False
        extension = self.get_extension(publisher, package, version, platform)
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        output_file = os.path.join(self.output_dir, "{}.vsix".format(extension))
        if self.cached:
            if os.path.exists(output_file):
                logging.info("{} already exists, skip download".format(output_file))
                return True
        return self.extension_download(
            self.publisher, self.package, version, platform, output_file, self.cached
        )

    @classmethod
    def get_extension(cls, publisher, package, version=None, platform=None):
        extension = "{}.{}".format(publisher, package)
        if version:
            extension = "{}@{}".format(extension, version)
        if platform:
            extension = "{}={}".format(extension, platform)
        return extension

    @classmethod
    def extension_select_version(cls, publisher, package, platform, version=None):
        extension = cls.get_extension(publisher, package)
        try:
            query_data = cls.extension_query(publisher=publisher, package=package)
        except Exception as e:
            logging.error("Query extension {} failed: {}".format(extension, e))
            return None, None
        try:
            query_versions = query_data["versions"]
            assert isinstance(query_versions, list)
            for query_version in query_versions:
                cur_version = query_version.get("version", None)
                if version is not None and version != cur_version:
                    continue
                cur_platform = query_version.get("targetPlatform", None)
                if cur_platform is not None and platform != cur_platform:
                    continue
                return cur_version, cur_platform
        except (KeyError, IndexError, AssertionError) as e:
            message = "Query extension {} failed: {}".format(extension, query_data)
            logging.error(message)
            return None, None
        message = "Query extension {} failed: on {} for version".format(
            extension, platform
        )
        if version is not None:
            message = "{} {}".format(message, version)
        logging.error(message)
        return None, None

    @classmethod
    def extension_query(cls, publisher, package, flags=None):
        extension = cls.get_extension(publisher, package)
        if flags is None:
            # query for versions
            flags = 0x55
        payload = {"flags": flags}
        payload["filters"] = [
            {
                "criteria": [{"filterType": 7, "value": extension}],
                "pageNumber": 1,
                "pageSize": 10,
            }
        ]
        payload = json.dumps(payload)
        logging.info("Querying extension {}".format(extension))
        response = requests.post(cls.QUERY_URL, headers=cls.HEADERS, data=payload)
        if response.status_code != 200:
            logging.error("Query extension {} failed".format(extension))
            return
        query_data = response.json()
        try:
            result = query_data["results"][0]["extensions"][0]
        except (KeyError, IndexError):
            message = "Query extension {} failed: {}".format(extension, query_data)
            logging.error(message)
            return
        return result

    @classmethod
    def extension_download(
        cls, publisher, package, version, platform, output_file, cached=True
    ):
        if not (publisher and package and version):
            assert 0, (publisher, package, version)
        extension = cls.get_extension(publisher, package, version, platform)
        download_url = cls.DOWNLOAD_URL.format(publisher, package, version)
        if platform is not None:
            download_url = "{}?targetPlatform={}".format(download_url, platform)
        logging.info("Downloading {}:\nURL: {}".format(extension, download_url))
        # use curl to show the progress bar
        curl_path = shutil.which("curl")
        if curl_path is None:
            assert 0, "command curl not found"
        head_file = "{}.header".format(output_file)
        body_file = "{}.downloading".format(output_file)
        curl_args = "-fSL"
        if cached:
            curl_args = "{} -C -".format(curl_args)
        download_command = "{} {} {} -o {} -D {}".format(
            curl_path, curl_args, download_url, body_file, head_file
        )
        logging.debug("Exec command: {}".format(download_command))
        res = subprocess.run(
            download_command,
            shell=True,
            start_new_session=False,
            capture_output=False,
            text=True,
            env=os.environ,
        )
        success = res.returncode == 0
        if not success:
            logging.error("Download {} failed".format(extension))

        try:
            compressed = None
            with open(head_file, "rt") as file:
                for line in file.readlines():
                    line = line.strip().lower()
                    if line.startswith("content-encoding"):
                        compressed = line.split(":")[-1].strip()
                        break
            with open(body_file, "rb") as file:
                data = file.read()
                if compressed is not None and "gzip" in compressed:
                    data = gzip.decompress(data)
            with open(output_file, "wb") as file:
                file.write(data)
            os.remove(head_file)
            os.remove(body_file)
        except Exception as e:
            logging.error("Download extension {} failed: {}".format(extension, e))
            return False
        return success


def list_full_extensions(extensions):
    def strip_suffix(line, mark):
        loc = line.rfind(mark)
        if loc < 0:
            return line, None
        return line[:loc], line[loc + len(mark) :]

    def parse_ext_line(ext_line):
        if not isinstance(ext_line, str):
            assert 0, "Invalid extension: {}".format(ext_line)
        ext_prefix, platform = strip_suffix(ext_line, "=")
        ext_prefix, version = strip_suffix(ext_prefix, "@")
        publisher, package = strip_suffix(ext_prefix, ".")
        if package is None:
            assert 0, "Invalid extension: {}".format(ext_line)
        return publisher, package, version, platform

    def parse_ext_dict(ext_data):
        if isinstance(ext_data, str):
            return parse_ext_line(ext_data)
        if not isinstance(ext_data, dict):
            assert 0, "Invalid extension: {}".format(ext_data)
        ext_id = ext_data.get("identifier", None)
        ext_name = None
        if isinstance(ext_id, dict):
            ext_name = ext_id.get("id", None)
        version = ext_data.get("version", None)
        if not version:
            version = None
        platform = ext_data.get("metadata", {}).get("targetPlatform", None)
        if platform is not None:
            platform = platform.lower()
            if platform in ("undefined", "none"):
                platform = None
        if not ext_name:
            assert 0, "Invalid extension: {}".format(ext_data)
        publisher, package, _, _ = parse_ext_line(ext_name)
        return publisher, package, version, platform

    result = []
    for ext in extensions:
        if not os.path.isfile(ext):
            result.append(parse_ext_line(ext))
            continue
        with open(ext, "rt") as file:
            content = file.read().strip()
        if content.startswith(("[", "{")):
            data = json.loads(content)
            if isinstance(data, dict):
                result.append(parse_ext_dict(data))
            elif isinstance(data, list):
                for item in data:
                    result.append(parse_ext_dict(item))
            else:
                assert 0, "Invalid extension in {}: {}".format(ext, data)
        else:
            for line in content.split("\n"):
                line = line.strip()
                result.append(parse_ext_line(line))
    result = sorted(set(result))
    return result


def str2bool(value):
    return value.lower() in (
        "true",
        "1",
        "t",
        "y",
        "yes",
        "yeah",
        "yup",
        "certainly",
    )


def get_current_platform():
    uname = os.uname()
    sys_name = uname.sysname.lower()
    arch = uname.machine.lower()
    arch_map = {
        "aarch64": "arm64",
        "x86": "ia32",
        "x86_64": "x64",
        "armv7l": "armhf",
        "arm32": "armhf",
    }
    arch = arch_map.get(arch, arch)
    platform = "{}-{}".format(sys_name, arch)
    if platform not in ExtensionDownloader.PLATFORMS:
        return
    return platform


def main():
    logging.getLogger().setLevel(logging.INFO)
    logging.basicConfig(format="[%(asctime)s]:%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description="""Download the vscode vsix extensions""",
        epilog="""
Example:
1. To download all extensions for a specific version of vscode(e.g., in ./vscode_vxx), run:
    code --list-extensions | xargs -I FN ./vscode_vxx/bin/code --extensions-dir ./extensions --install-extension FN

    {} --extensions ./extensions/extensions.json
""".format(
            sys.argv[0]
        ),
    )
    parser.add_argument(
        "--extensions",
        nargs="+",
        required=True,
        help="""list of extensions to be downloaded, each is one of the following:
    1. in the format: '<publisher>.<package>[@version][=platform]';
    2. the vscode extensions.json;
    3. the output of `code --list-extensions --show-versions`""",
    )
    parser.add_argument(
        "--download-dir",
        default="./vscode-vsix",
        help="the download dir, default: ./vscode-vsix",
    )
    parser.add_argument(
        "--cached",
        default=True,
        type=str2bool,
        help="use file cache or not, default: True",
    )
    parser.add_argument(
        "--verbose", default=False, action="store_true", help="show more debug messages"
    )
    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    extensions = list_full_extensions(args.extensions)
    failed = []
    for publisher, package, version, platform in extensions:
        downloader = ExtensionDownloader(
            publisher=publisher,
            package=package,
            version=version,
            platform=platform,
            output_dir=args.download_dir,
            cached=args.cached,
        )
        success = downloader.download()
        if not success:
            ext_name = downloader.get_extension(publisher, package, version, platform)
            failed.append(ext_name)
        logging.info("=" * 50)
    if failed:
        logging.error("Download some failed:\n{}".format(" ".join(failed)))
    else:
        logging.info("Download all succeeded")
    return


if __name__ == "__main__":
    main()
