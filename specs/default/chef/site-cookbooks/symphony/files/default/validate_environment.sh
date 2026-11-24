#!/bin/bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

fail() {
    printf 'Symphony environment validation failed: %s\n' "$1" >&2
    printf 'Kernel: %s. Verify the Symphony executable/library paths and select an IBM-supported Symphony fix level and OS/kernel combination.\n' "$(/bin/uname -sr)" >&2
    exit 1
}

profile=${1:-/etc/profile.d/symphony.sh}
if [ ! -r "$profile" ]; then
    fail "Cannot read Symphony profile: $profile"
fi

if ! . "$profile"; then
    fail "Could not load Symphony profile: $profile"
fi

for command_name in egosh symping; do
    executable=$(command -v "$command_name")
    if [ -z "$executable" ] || [ ! -x "$executable" ]; then
        fail "$command_name is not an executable on PATH after loading $profile"
    fi
    if ! "$executable" -V >/dev/null; then
        fail "$command_name -V failed; the command or its shared libraries could not be loaded"
    fi
done

printf 'EGO and SOAM environment validated.\n'
