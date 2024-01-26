#!/bin/bash -e

cp $2 /tmp/getAvail.input.json

scriptDir=$(dirname $0)
$scriptDir/./invoke_provider.sh templates $@
exit $?
