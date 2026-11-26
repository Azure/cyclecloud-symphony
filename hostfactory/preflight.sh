#!/bin/bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

function HostFactory-Error
{
    printf 'HostFactory setup failed: %s\n' "$1" >&2
    return 1
}

function HostFactory-Warning
{
    printf 'HostFactory setup warning: %s\n' "$1" >&2
}

function Validate-HostFactory-Prerequisites
{
    executable=$(command -v python3)
    if [ -z "$executable" ] || [ ! -x "$executable" ]; then
        HostFactory-Error "python3 must be executable on PATH. Install Python 3.9 or later."
        return 1
    fi

    # The provider's pinned dependencies (requests, urllib3) require Python 3.9+.
    if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
        HostFactory-Error "Python 3.9 or later is required; found $(python3 --version 2>&1). Use an image with a newer Python (for example Ubuntu 22.04)."
        return 1
    fi

    if ! python3 -m virtualenv --version >/dev/null 2>&1; then
        if ! python3 -m pip --version >/dev/null 2>&1; then
            HostFactory-Error "Python 3 needs virtualenv or pip to bootstrap it. On Debian/Ubuntu, install python3-pip and python3-virtualenv before rerunning."
            return 1
        fi
        # PEP 668: pip refuses system-wide installs, so the pip fallback cannot install virtualenv.
        if python3 -c 'import os, sys, sysconfig; sys.exit(not os.path.exists(os.path.join(sysconfig.get_path("stdlib"), "EXTERNALLY-MANAGED")))' >/dev/null 2>&1; then
            HostFactory-Error "virtualenv is not installed and this Python is externally managed (PEP 668), so pip cannot install it. Install python3-virtualenv with your OS package manager before rerunning."
            return 1
        fi
    fi

    if [ "$1" = generate_config ]; then
        executable=$(command -v jq)
        if [ -z "$executable" ] || [ ! -x "$executable" ]; then
            HostFactory-Error "generate_config requires jq. Install jq with your OS package manager before rerunning."
            return 1
        fi
    fi

    # Jetpack only supplies the package file name used to clean up after installation.
    PKG_NAME=""
    if command -v jetpack >/dev/null 2>&1; then
        if ! PKG_NAME=$(jetpack config symphony.pkg_plugin 2>/dev/null); then
            PKG_NAME=""
            HostFactory-Warning "Cannot read Jetpack setting symphony.pkg_plugin; skipping package-file lookup."
        fi
    else
        HostFactory-Warning "jetpack is not on PATH; skipping package-file lookup."
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
