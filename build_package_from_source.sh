#!/bin/bash
# Download and build the source code of the project and its dependencies.
set -e
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

cyclecloud_api_package=${1}

cd "${SCRIPT_DIR}"
echo "Clearing build_deps and dist directories"
rm -rf ./build_deps ./dist
mkdir -p ./build_deps ./dist
pushd ./build_deps

    echo "Fetching cyclecloud-api package"
    if [ -z "${cyclecloud_api_package}" ]; then
        echo "WARNING: cyclecloud-api package not provided. Downloading from GitHub."
        echo "         (This package may be found in the /opt/cycle_server/tools directory.)"
        CYCLECLOUD_API_VERSION="8.6.0"
        cyclecloud_api_package="cyclecloud_api-${CYCLECLOUD_API_VERSION}-py2.py3-none-any.whl"
        cyclecloud_api_url="https://github.com/Azure/cyclecloud-symphony/releases/download/2024-03-01-bins/${cyclecloud_api_package}"

        curl -L -k -s -o "../dist/${cyclecloud_api_package}" "${cyclecloud_api_url}"
    else
        echo "Using provided cyclecloud-api package: ${cyclecloud_api_package}"
        short_name=$(basename "${cyclecloud_api_package}")
        cp "${cyclecloud_api_package}" "../dist/${short_name}"
        cyclecloud_api_package="${short_name}"
    fi

    echo "Building cyclecloud-scalelib package"
    git clone 'https://github.com/Azure/cyclecloud-scalelib.git'
    pushd cyclecloud-scalelib
        # TODO: Remove once branch is merged
        git checkout ryhamel/last-capacity-failure
        python3 setup.py sdist
        cyclecloud_scalelib_package=$(basename $(ls dist/cyclecloud-scalelib-*.tar.gz))
        cp "./dist/${cyclecloud_scalelib_package}" "../../dist/${cyclecloud_scalelib_package}"
    popd

    echo "Building concurrent-log-handler package"l
    git clone 'https://github.com/Preston-Landers/concurrent-log-handler.git'
    pushd concurrent-log-handler
        python3 -m venv ./hatch
        . ./hatch/bin/activate
        pip install -U pip hatchling
        hatchling build
        deactivate
        concurrent_log_handler_package=$(basename $(ls dist/concurrent_log_handler-*.whl))
        cp "dist/${concurrent_log_handler_package}" "../../dist/${concurrent_log_handler_package}"
    popd

popd


echo "Building final cyclecloud-symphony package"
python3 ./package.py --cyclecloud-api "./dist/${cyclecloud_api_package}" --scalelib "./dist/${cyclecloud_scalelib_package}" --concurrent-log-handler "./dist/${concurrent_log_handler_package}"
 
