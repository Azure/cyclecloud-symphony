#!/bin/bash -e

cp $2 /tmp/reqMach.input.json

scriptDir=$(dirname $0)
$scriptDir/./invoke_provider.sh create_machines $@
exit $?
