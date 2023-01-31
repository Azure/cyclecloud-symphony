import argparse
import configparser
import glob
import os
import shutil
import sys
import tarfile
import tempfile
import zipfile
from argparse import Namespace
from subprocess import check_call
from typing import Dict, List, Optional

SCALELIB_VERSION = "0.2.14"
CYCLECLOUD_API_VERSION = "8.1.0"


def get_cycle_libs(args: Namespace) -> List[str]:
    ret = []

    scalelib_file = "cyclecloud-scalelib-{}.tar.gz".format(SCALELIB_VERSION)
    cyclecloud_api_file = "cyclecloud_api-{}-py2.py3-none-any.whl".format(
        CYCLECLOUD_API_VERSION
    )

    scalelib_url = "https://github.com/Azure/cyclecloud-scalelib/archive/{}.tar.gz".format(
        SCALELIB_VERSION
    )
    # TODO RDH!!!
    cyclecloud_api_url = "https://github.com/Azure/cyclecloud-gridengine/releases/download/2.0.0/cyclecloud_api-8.0.1-py2.py3-none-any.whl"
    to_download = {
        scalelib_file: (args.scalelib, scalelib_url),
        cyclecloud_api_file: (args.cyclecloud_api, cyclecloud_api_url),
    }

    for lib_file in to_download:
        arg_override, url = to_download[lib_file]
        if arg_override:
            if not os.path.exists(arg_override):
                print(arg_override, "does not exist", file=sys.stderr)
                sys.exit(1)
            fname = os.path.basename(arg_override)
            orig = os.path.abspath(arg_override)
            dest = os.path.abspath(os.path.join("libs", fname))
            if orig != dest:
                shutil.copyfile(orig, dest)
            ret.append(fname)
        else:
            dest = os.path.join("libs", lib_file)
            check_call(["curl", "-L", "-k", "-s", "-f", "-o", dest, url])
            ret.append(lib_file)
            print("Downloaded", lib_file, "to")

    return ret


def execute() -> None:
    expected_cwd = os.path.abspath(os.path.dirname(__file__))
    os.chdir(expected_cwd)

    if not os.path.exists("libs"):
        os.makedirs("libs")

    argument_parser = argparse.ArgumentParser(
        "Builds the IBM Spectrum Symphony HostFactory provider plugin for Azure CycleCloud with all dependencies.\n"
        + "If you don't specify local copies of scalelib or cyclecloud-api they will be downloaded from github."
    )
    argument_parser.add_argument("--scalelib", default=None)
    argument_parser.add_argument("--cyclecloud-api", default=None)
    args = argument_parser.parse_args()

    cycle_libs = get_cycle_libs(args)

    parser = configparser.ConfigParser()
    ini_path = os.path.abspath("project.ini")

    with open(ini_path) as fr:
        parser.read_file(fr)

    version = parser.get("project", "version")
    if not version:
        raise RuntimeError("Missing [project] -> version in {}".format(ini_path))

    if not os.path.exists("dist"):
        os.makedirs("dist")

    zf = zipfile.ZipFile("dist/cyclecloud-symphony-pkg-{}.zip".format(version), "w", zipfile.ZIP_DEFLATED)


    build_dir = tempfile.mkdtemp("cyclecloud-symphony")

    def _unix2dos(base_path: str, patterns: Optional[str] = ['**/*.ps1', '**/*.bat']) -> None:
        import glob
        print("Converting unix2dos: ")
        for pattern in patterns:
            for name in glob.glob(os.path.join(base_path, pattern), recursive=True):
                check_call(["unix2dos", name])

    def _add(name: str, path: Optional[str] = None, mode: Optional[int] = None) -> None:
        path = path or name
        print(f"Adding : {name} from {path}")
        zf.write(path, name)




    def _add_directory(name: str, path: Optional[str] = None) -> None:
       with zf as zip_ref:
          for folder_name, subfolders, filenames in os.walk(name):
              for filename in filenames:
                 file_path = os.path.join(folder_name, filename)
                 zip_ref.write(file_path)


    packages = []
    for dep in cycle_libs:
        dep_path = os.path.abspath(os.path.join("libs", dep))
        packages.append(dep_path)

    check_call(["pip", "download"] + packages, cwd=build_dir)

    print("Using build dir", build_dir)
    by_package: Dict[str, List[str]] = {}
    for fil in os.listdir(build_dir):
        toks = fil.split("-", 1)
        package = toks[0]
        if package == "cyclecloud":
            package = "{}-{}".format(toks[0], toks[1])
        if package not in by_package:
            by_package[package] = []
        by_package[package].append(fil)

    for package, fils in by_package.items():
        
        if len(fils) > 1:
            print("WARNING: Ignoring duplicate package found:", package, fils)
            assert False

    for fil in os.listdir(build_dir):
        if fil.startswith("certifi-20"):
            print("WARNING: Ignoring duplicate certifi {}".format(fil))
            continue
        path = os.path.join(build_dir, fil)
        _add("packages/" + fil, path)

    _unix2dos("hostfactory", patterns=['**/*.ps1', '**/*.bat'])
    _add("hostfactory/install.ps1", mode=os.stat("hostfactory/install.ps1")[0])
    _add_directory("hostfactory/1.1")


    print("Created package: ", zf.filename)
    print("\n".join(f for f in zf.namelist()))

if __name__ == "__main__":
    execute()
