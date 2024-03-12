#!/usr/bin/env python3
import requests
import json
import os
import sys
import argparse
import logging
import subprocess
import shutil


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
    DOWNLOAD_URL = "https://{}.gallery.vsassets.io/_apis/public/gallery/publisher/{}/extension/{}/{}/assetbyname/Microsoft.VisualStudio.Services.VSIXPackage"

    def __init__(
        self,
        publisher,
        package,
        output_dir,
        version=None,
        cached=True,
    ):
        self.publisher = publisher
        self.package = package
        self.output_dir = output_dir
        self.version = None
        if isinstance(version, str) and version:
            self.version = version
        self.cached = cached

    def download(self):
        publisher = self.publisher
        package = self.package
        version = self.version
        if not version:
            query_info = self.extension_query(self.publisher, self.package)
            if query_info is None:
                return False
            version = query_info["versions"][0]["version"]

        extension = self.get_extension(publisher, package, version)
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        output_file = os.path.join(self.output_dir, "{}.vsix".format(extension))
        return self.extension_download(
            self.publisher, self.package, version, output_file, self.cached
        )

    @classmethod
    def get_extension(cls, publisher, package, version=None):
        if not version:
            return "{}.{}".format(publisher, package)
        return "{}.{}@{}".format(publisher, package, version)

    @classmethod
    def extension_query(cls, publisher, package):
        extension = cls.get_extension(publisher, package)
        payload = {"flags": 914}
        payload["filters"] = [{"criteria": [{"filterType": 7, "value": extension}]}]
        payload = json.dumps(payload)
        session = requests.Session()
        logging.info("Querying extension {}".format(extension))
        response = session.post(cls.QUERY_URL, headers=cls.HEADERS, data=payload)
        if response.status_code != 200:
            logging.error("Query extension {} failed".format(extension))
            return
        query_data = response.json()
        try:
            result = query_data["results"][0]["extensions"][0]
            version = result["versions"][0]["version"]
        except (KeyError, IndexError):
            message = "Query extension {} failed: {}".format(extension, query_data)
            logging.error(message)
            return
        return result

    @classmethod
    def extension_download(cls, publisher, package, version, output_file, cached=True):
        if not (publisher and package and version):
            assert 0, (publisher, package, version)
        extension = cls.get_extension(publisher, package, version)
        download_url = cls.DOWNLOAD_URL.format(publisher, publisher, package, version)
        logging.info("Downloading {}:\nURL: {}".format(extension, download_url))
        # use curl to show the progress bar
        curl_path = shutil.which("curl")
        if curl_path is None:
            assert 0, "command curl not found"
        curl_args = "-fSL"
        if cached:
            curl_args = "{} -C -".format(curl_args)
        download_command = "{} {} {} -o {}".format(
            curl_path, curl_args, download_url, output_file
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
        return success


def list_full_extensions(extensions):
    def parse_ext_line(ext_line):
        if not isinstance(ext_line, str):
            assert 0, "Invalid extension: {}".format(ext_line)
        v_loc = ext_line.rfind("@")
        version = None
        if v_loc >= 0:
            version = ext_line[v_loc + 1 :]
        else:
            v_loc = len(ext_line)
        p_loc = ext_line[:v_loc].rfind(".")
        if p_loc < 0:
            assert 0, "Invalid extension: {}".format(ext_line)
        publisher = ext_line[:p_loc]
        package = ext_line[p_loc + 1 : v_loc]
        if not version:
            version = None
        return publisher, package, version

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
        if not ext_name:
            assert 0, "Invalid extension: {}".format(ext_data)
        publisher, package, _ = parse_ext_line(ext_name)
        return publisher, package, version

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
    1. in the format: '<publisher>.<package>[@version]';
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
    args = parser.parse_args()
    extensions = list_full_extensions(args.extensions)
    failed = []
    for publisher, package, version in extensions:
        downloader = ExtensionDownloader(
            publisher=publisher,
            package=package,
            version=version,
            output_dir=args.download_dir,
            cached=args.cached,
        )
        success = downloader.download()
        if not success:
            failed.append(downloader.get_extension(publisher, package, version))
        logging.info("=" * 50)
    if failed:
        logging.error("Download some failed:\n{}".format(" ".join(failed)))
    else:
        logging.info("Download all succeeded")
    return


if __name__ == "__main__":
    main()
