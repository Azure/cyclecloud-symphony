#!/bin/bash -e

cp $2 /tmp/getReqStatus.input.json

scriptDir=$(dirname $0)
$scriptDir/./invoke_provider.sh create_status $@
exit $?
