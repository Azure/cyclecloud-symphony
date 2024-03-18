#!/bin/bash -e

cp $2 /tmp/getReturnReq.input.json

scriptDir=$(dirname $0)
# BRW: 2/13/20
# $scriptDir/./invoke_provider.sh terminate_status $@
$scriptDir/./invoke_provider.sh get_return_requests $@
exit $?
