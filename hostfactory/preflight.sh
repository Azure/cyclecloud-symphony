#!/bin/bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

function HostFactory-Error
{
    printf 'HostFactory setup failed: %s\n' "$1" >&2
    return 1
}

function Validate-HostFactory-Prerequisites
{
    for command_name in python3 jetpack; do
        executable=$(command -v "$command_name")
        if [ -z "$executable" ] || [ ! -x "$executable" ]; then
            HostFactory-Error "$command_name must be executable on PATH. Install Python 3 and include /opt/cycle/jetpack/bin in the privileged installer shell's PATH."
            return 1
        fi
    done

    if ! python3 -m virtualenv --version >/dev/null 2>&1 &&
       ! python3 -m pip --version >/dev/null 2>&1; then
        HostFactory-Error "Python 3 needs virtualenv or pip to bootstrap it. On Debian/Ubuntu, install python3-pip and python3-virtualenv before rerunning."
        return 1
    fi

    if [ "$1" = generate_config ]; then
        executable=$(command -v jq)
        if [ -z "$executable" ] || [ ! -x "$executable" ]; then
            HostFactory-Error "generate_config requires jq. Install jq with your OS package manager before rerunning."
            return 1
        fi
    fi

    if ! PKG_NAME=$(jetpack config symphony.pkg_plugin); then
        HostFactory-Error "Cannot read Jetpack configuration. Run the installer with authorized Jetpack access."
        return 1
    fi
    if [ -z "${PKG_NAME//[[:space:]]/}" ]; then
        HostFactory-Error "Jetpack setting symphony.pkg_plugin must not be empty. Configure the provider package before rerunning."
        return 1
    fi
}

function Validate-Symphony-Environment
(
    profile="$EGO_TOP/profile.platform"
    if [ ! -r "$profile" ]; then
        HostFactory-Error "Cannot read Symphony profile: $profile. Install Symphony first or set EGO_TOP to its existing installation."
        exit 1
    fi
    if ! . "$profile"; then
        HostFactory-Error "Could not load Symphony profile: $profile"
        exit 1
    fi

    for command_name in egosh symping; do
        executable=$(command -v "$command_name")
        if [ -z "$executable" ] || [ ! -x "$executable" ]; then
            HostFactory-Error "$command_name is not executable on PATH after loading $profile. Select an IBM-supported Symphony fix level and OS/kernel combination; kernel: $(/bin/uname -sr)."
            exit 1
        fi
        if ! "$executable" -V >/dev/null; then
            HostFactory-Error "$command_name -V failed. Check the installed Symphony library paths and IBM-supported OS/kernel combination; kernel: $(/bin/uname -sr)."
            exit 1
        fi
    done

    printf 'Symphony EGO and SOAM environment validated.\n'
)
