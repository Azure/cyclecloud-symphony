#!/bin/bash -e

cp $2 /tmp/getReturnReq.input.json

scriptDir=$(dirname $0)
$scriptDir/./invoke_provider.sh terminate_status $@
exit $?
